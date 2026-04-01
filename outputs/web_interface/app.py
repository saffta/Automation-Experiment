#!/usr/bin/env python3
"""
Perchance POD Automation - Web Interface
Simplified and fixed version:
 - Proper metadata save on approve
 - Fixed auto-upload using new unified_uploader.upload_to_all
 - Fixed jupytext typo in unfavorite route
"""

import os
import sys
import shutil
import json
import re
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from pathlib import Path
import signal

def _force_shutdown(signum, frame):
    print("\n⚠️ Force quitting application to free ports...")
    os._exit(0)

signal.signal(signal.SIGINT, _force_shutdown)
signal.signal(signal.SIGTERM, _force_shutdown)
if hasattr(signal, 'SIGBREAK'):
    signal.signal(signal.SIGBREAK, _force_shutdown)

app = Flask(__name__)
app.config["SECRET_KEY"] = "perchance_pod_automation_secret"

# Paths
BASE_DIR = Path(__file__).parent.parent
PENDING_DIR  = BASE_DIR / "images" / "by_status" / "pending"
APPROVED_DIR = BASE_DIR / "images" / "by_status" / "approved"
COMPLETE_DIR = BASE_DIR / "images" / "by_status" / "complete"
DENIED_DIR   = BASE_DIR / "images" / "by_status" / "denied"
FAVORITES_DIR= BASE_DIR / "images" / "by_status" / "favorites"
METADATA_DIR = BASE_DIR / "metadata"
POD_LOGS_DIR = BASE_DIR / "logs" / "pod_uploads"

for d in [PENDING_DIR, APPROVED_DIR, COMPLETE_DIR, DENIED_DIR, FAVORITES_DIR, METADATA_DIR, POD_LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BASE_DIR / "src"))
from vision_description import generate_description_and_tags, generate_title_from_description
from civitai_pod_automation import AutomationPipeline
from generation_profile_manager import GenerationProfileManager
from swarmui_integration import SwarmUI

CIVITAI_PATTERN = re.compile(r"^civitai_(\d+)_v\d+\.png$")


# ─── Metadata helpers ────────────────────────────────────────────────────────

def _civitai_id(filename: str):
    m = CIVITAI_PATTERN.match(filename)
    return m.group(1) if m else None


def _meta_path(civitai_id: str) -> Path:
    return METADATA_DIR / f"civitai_{civitai_id}_v1_metadata.json"


def load_metadata(filename: str):
    """Returns (meta_dict, civitai_data_dict_or_None)"""
    cid = _civitai_id(filename)
    if cid:
        mp = _meta_path(cid)
        if mp.exists():
            try:
                data = json.loads(mp.read_text())
                return {
                    "title":       data.get("title", ""),
                    "description": data.get("description", ""),
                    "primary_tag": data.get("primary_tag", ""),
                    "tags":        data.get("tags_suggested", data.get("tags", [])),
                    "is_favorite": data.get("is_favorite", False),
                    "created_at":  data.get("generated_at", datetime.now().isoformat()),
                    "suggested":   True,
                }, data
            except Exception as e:
                print(f"⚠️  Metadata load error {mp}: {e}")
    return {
        "title": "", "description": "", "primary_tag": "", "tags": [],
        "is_favorite": False, "created_at": datetime.now().isoformat()
    }, None


def save_metadata(filename: str, title: str, description: str, tags: list, extra: dict = None):
    """Persist metadata update for a civitai image."""
    cid = _civitai_id(filename)
    if not cid:
        return
    mp = _meta_path(cid)
    data = {}
    if mp.exists():
        try:
            data = json.loads(mp.read_text())
        except Exception:
            pass
    data["title"]          = title
    data["description"]    = description
    data["primary_tag"]    = extra.get("primary_tag", data.get("primary_tag", "")) if extra else data.get("primary_tag", "")
    data["tags_suggested"] = tags
    data["tags"]           = tags
    if extra:
        data.update(extra)
    mp.write_text(json.dumps(data, indent=2))


def get_pending_images():
    images = []
    if PENDING_DIR.exists():
        for f in sorted(PENDING_DIR.glob("*.png")):
            meta, cdata = load_metadata(f.name)
            images.append({
                "filename":    f.name,
                "url":         f"/images/pending/{f.name}",
                "metadata":    meta,
                "civitai_data": cdata,
                "timestamp":   f.stat().st_mtime,
            })
    return sorted(images, key=lambda x: x["timestamp"], reverse=True)


# ─── Upload helper ────────────────────────────────────────────────────────────

def _auto_upload_background(image_path: str, filename: str, title: str, tags: list, description: str, primary_tag: str, platforms: list, profile: str, headless_redbubble: bool, headless_teepublic: bool, profile_path: str):
    """Run upload in background thread."""
    try:
        from unified_uploader import upload_to_all
        print(f"\n🚀 Auto-uploading {filename} to {platforms or 'all'} platforms using profile '{profile or 'default'}'...")
        
        results = upload_to_all(image_path, title, tags, description, 
                                profile=profile, platforms=platforms, 
                                primary_tag=primary_tag, profile_path=profile_path, 
                                headless_redbubble=headless_redbubble, 
                                headless_teepublic=headless_teepublic)
        
        ok  = sum(1 for r in results if r.success)
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        log = POD_LOGS_DIR / f"{filename}_{ts}.json"
        log.write_text(json.dumps([
            {"platform": r.platform, "success": r.success, "url": r.url, "error": r.error}
            for r in results
        ], indent=2))
        
        print(f"✅ Upload done: {ok}/{len(results or platforms or [])} platforms succeeded")
        
        # If all succeeded, move to complete
        if ok == len(results) and ok > 0:
            dst = COMPLETE_DIR / filename
            if Path(image_path).exists():
                shutil.move(image_path, str(dst))
                print(f"📦 Moved to complete: {filename}")
                
    except Exception as e:
        import traceback
        print(f"❌ Auto-upload failed: {e}")
        traceback.print_exc()


def start_upload(image_path: str, filename: str, title: str, tags: list, description: str, primary_tag: str, platforms: list, profile: str, headless_redbubble: bool, headless_teepublic: bool, profile_path: str):
    # Convert Windows path E:\... to /mnt/e/... if in WSL
    if profile_path and ":" in profile_path and sys.platform != "win32":
        match = re.match(r'^([a-zA-Z]):\\(.*)', profile_path)
        if match:
            drive, path = match.groups()
            wsl_path = path.replace('\\', '/')
            profile_path = f"/mnt/{drive.lower()}/{wsl_path}"
            print(f"🔄 Converted Windows path to WSL: {profile_path}")

    try:
        t = threading.Thread(
            target=_auto_upload_background,
            args=(image_path, filename, title, tags, description, primary_tag, platforms, profile, headless_redbubble, headless_teepublic, profile_path),
            daemon=True
        )
        t.start()
        print(f"🧵 Background upload thread started for {filename}")
    except Exception as e:
        print(f"❌ Failed to start background thread: {e}")


# ─── Jinja filters ───────────────────────────────────────────────────────────

@app.template_filter("timestamp_to_date")
def ts_filter(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "Unknown"


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", images=get_pending_images())


@app.route("/images/pending/<filename>")
def serve_pending(filename):
    return send_from_directory(PENDING_DIR, filename)


@app.route("/images/favorites/<filename>")
def serve_favorite(filename):
    return send_from_directory(FAVORITES_DIR, filename)


@app.route("/images/approved/<filename>")
def serve_approved(filename):
    return send_from_directory(APPROVED_DIR, filename)


@app.route("/api/images")
def api_images():
    return jsonify({"images": get_pending_images()})


@app.route("/api/image/<filename>/approve", methods=["POST"])
def api_approve(filename):
    src = PENDING_DIR / filename
    if not src.exists():
        return jsonify({"error": "Image not found"}), 404

    data        = request.get_json() or {}
    title       = data.get("title", "").strip()
    description = data.get("description", "").strip()
    primary_tag = data.get("primary_tag", "").strip()
    tags        = data.get("tags", [])
    platforms    = data.get("platforms", [])
    profile      = data.get("profile", "default")
    headless_redbubble = data.get("headless_redbubble", True)
    headless_teepublic = data.get("headless_teepublic", True)
    profile_path = data.get("profile_path", "")

    # Fall back to stored metadata if not provided
    if not title or not tags:
        meta, _ = load_metadata(filename)
        title       = title or meta.get("title", Path(filename).stem)
        description = description or meta.get("description", "")
        primary_tag = primary_tag or meta.get("primary_tag", "")
        tags        = tags or meta.get("tags", [])

    # Save metadata
    save_metadata(filename, title, description, tags, {
        "status": "approved", 
        "approved_at": datetime.now().isoformat(),
        "primary_tag": primary_tag
    })

    # Move to approved
    dst = APPROVED_DIR / filename
    shutil.move(str(src), str(dst))
    print(f"✅ Approved: {filename}")

    # Start upload in background
    start_upload(str(dst), filename, title, tags, description, 
                 primary_tag=primary_tag, platforms=platforms, profile=profile, 
                 headless_redbubble=headless_redbubble, headless_teepublic=headless_teepublic, 
                 profile_path=profile_path)

    return jsonify({"success": True, "message": "Approved and uploading"})


@app.route("/api/image/<filename>/deny", methods=["POST"])
def api_deny(filename):
    src = PENDING_DIR / filename
    if not src.exists():
        return jsonify({"error": "Image not found"}), 404

    # Delete metadata
    cid = _civitai_id(filename)
    if cid:
        mp = _meta_path(cid)
        if mp.exists():
            mp.unlink()

    src.unlink()
    print(f"🗑️  Denied: {filename}")
    return jsonify({"success": True})


@app.route("/api/image/<filename>/favorite", methods=["POST"])
def api_favorite(filename):
    src = PENDING_DIR / filename
    if not src.exists():
        return jsonify({"error": "Image not found"}), 404

    meta, _ = load_metadata(filename)
    save_metadata(filename, meta["title"], meta["description"], meta["tags"], {"is_favorite": True})

    dst = FAVORITES_DIR / filename
    shutil.move(str(src), str(dst))
    print(f"⭐ Favorited: {filename}")
    return jsonify({"success": True})


@app.route("/api/image/<filename>/unfavorite", methods=["POST"])
def api_unfavorite(filename):
    src = FAVORITES_DIR / filename
    if not src.exists():
        return jsonify({"error": "Image not found"}), 404

    meta, _ = load_metadata(filename)
    save_metadata(filename, meta["title"], meta["description"], meta["tags"], {"is_favorite": False})

    dst = PENDING_DIR / filename
    shutil.move(str(src), str(dst))
    return jsonify({"success": True})


@app.route("/api/upload/logs")
def api_upload_logs():
    logs = []
    for lf in sorted(POD_LOGS_DIR.glob("*.json"), reverse=True)[:20]:
        try:
            logs.append({"file": lf.name, "data": json.loads(lf.read_text())})
        except Exception:
            pass
    return jsonify({"logs": logs})



@app.route("/api/image/<filename>/upload", methods=["POST"])
def api_manual_upload(filename):
    """Manually trigger upload for an approved image."""
    src = APPROVED_DIR / filename
    if not src.exists():
        src = PENDING_DIR / filename  # also accept from pending
    if not src.exists():
        return jsonify({"error": "Image not found in approved or pending"}), 404

    data        = request.get_json() or {}
    meta, _     = load_metadata(filename)
    title       = data.get("title") or meta.get("title", filename)
    tags        = data.get("tags")  or meta.get("tags", [])
    description = data.get("description") or meta.get("description", "")

    start_upload(str(src), filename, title, tags, description)
    return jsonify({"success": True, "message": "Upload started in background"})

def _generate_vision_metadata(filename: str, config: dict = None) -> dict:
    """Generate description and tags using vision model with optional custom config."""
    config = config or {}
    try:
        for base_dir in [PENDING_DIR, APPROVED_DIR, FAVORITES_DIR]:
            img_path = base_dir / filename
            if img_path.exists():
                result = generate_description_and_tags(
                    str(img_path),
                    provider=config.get("provider"),
                    model_override=config.get("model"),
                    api_key=config.get("api_key"),
                    api_base=config.get("api_base")
                )
                description = result.get("description", "")
                tags = result.get("tags", [])
                primary_tag = result.get("primary_tag", "")
                
                if result.get("error"):
                    return {"success": False, "error": result["error"]}
                
                title = generate_title_from_description(description) or Path(filename).stem
                
                return {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "primary_tag": primary_tag,
                    "success": True
                }
        
        return {"success": False, "error": "Image not found"}
    except Exception as e:
        print(f"Vision generation error for {filename}: {e}")
        return {"success": False, "error": str(e)}

@app.route("/api/image/<filename>/generate_description", methods=["POST"])
def api_generate_description(filename):
    """Generate AI-powered description and tags for an image."""
    data = request.get_json() or {}
    result = _generate_vision_metadata(filename, config=data)
    
    if result.get("success"):
        save_metadata(
            filename,
            result["title"],
            result["description"],
            result["tags"],
            {"primary_tag": result["primary_tag"]}
        )
        return jsonify({
            "success": True,
            "title": result["title"],
            "description": result["description"],
            "tags": result["tags"],
            "primary_tag": result["primary_tag"]
        })
    
    return jsonify({
        "success": False,
        "error": result.get("error", "Failed to generate description")
    }), 500


# ─── Profile & Credentials APIs ──────────────────────────────────────────────

@app.route("/api/profiles")
def api_profiles():
    from pod_credentials_manager import PODCredentialsManager
    mgr = PODCredentialsManager()
    return jsonify({
        "profiles": mgr.list_profiles(),
        "active": mgr.get_active_profile()
    })

@app.route("/api/profiles/add", methods=["POST"])
def api_profile_add():
    name = request.json.get("name")
    if not name: return jsonify({"error": "Name required"}), 400
    from pod_credentials_manager import PODCredentialsManager
    mgr = PODCredentialsManager()
    mgr.add_profile(name)
    return jsonify({"success": True})

@app.route("/api/accounts/update", methods=["POST"])
def api_account_update():
    data = request.json
    profile = data.get("profile")
    platform = data.get("platform")
    username = data.get("username")
    password = data.get("password")
    
    if not all([profile, platform, username, password]):
        return jsonify({"error": "Missing fields"}), 400
        
    from pod_credentials_manager import PODCredentialsManager
    mgr = PODCredentialsManager()
    mgr.add_account(platform, username, password, profile=profile)
    return jsonify({"success": True})




# ─── Regeneration APIs ───────────────────────────────────────────────────────

@app.route("/api/generation-profiles")
def api_generation_profiles():
    mgr = GenerationProfileManager()
    return jsonify({
        "profiles": mgr.profiles,
        "names": mgr.list_profiles()
    })

@app.route("/api/generation-profiles/save", methods=["POST"])
def api_generation_profile_save():
    data = request.json
    name = data.get("name")
    config = data.get("config")
    if not name or not config:
        return jsonify({"error": "Name and config required"}), 400
    
    mgr = GenerationProfileManager()
    mgr.add_profile(name, config)
    return jsonify({"success": True})

@app.route("/api/generation-profiles/delete", methods=["POST"])
def api_generation_profile_delete():
    name = request.json.get("name")
    if not name: return jsonify({"error": "Name required"}), 400
    
    mgr = GenerationProfileManager()
    mgr.delete_profile(name)
    return jsonify({"success": True})

@app.route("/api/models")
def api_models():
    """List all available models from all backends"""
    models = {
        "perchance": ["flux", "zimage", "turbo"],
        "swarmui": []
    }
    
    try:
        swarm = SwarmUI()
        swarm_files = swarm.list_models()
        # Extract friendly names/paths, handling both dictionaries and strings
        swarm_names = []
        for f in swarm_files:
            if isinstance(f, dict):
                name = f.get("name") or f.get("path") or f.get("model")
                if name: swarm_names.append(name)
            elif isinstance(f, str):
                swarm_names.append(f)
        
        if not swarm_names:
            print(f"⚠️ SwarmUI: API returned success but 0 models found. Raw count: {len(swarm_files)}")
            
        models["swarmui"] = swarm_names
    except Exception as e:
        print(f"❌ SwarmUI: Exception while fetching models: {e}")
        import traceback
        traceback.print_exc()
        
    return jsonify(models)


@app.route("/api/image/<filename>/regenerate", methods=["POST"])
def api_regenerate(filename):
    data = request.get_json() or {}
    profile_name = data.get("profile")
    overrides = data.get("overrides")
    
    pipeline = AutomationPipeline(BASE_DIR)
    success = pipeline.regenerate_image(filename, profile_name=profile_name, overrides=overrides)
    
    if success:
        return jsonify({"success": True, "message": "Image regenerated!"})
    return jsonify({"success": False, "error": "Regeneration failed"}), 500


def _run_scrape_background(profile_name, num_images):
    try:
        pipeline = AutomationPipeline(BASE_DIR)
        pipeline.run(num_images=num_images, profile_name=profile_name)
        print(f"✅ Background scraping complete for profile: {profile_name}")
    except Exception as e:
        print(f"❌ Background scraping failed: {e}")

@app.route("/api/scrape/start", methods=["POST"])
def api_scrape_start():
    data = request.get_json() or {}
    profile_name = data.get("profile")
    num_images = int(data.get("num_images", 5))
    
    if not profile_name:
        return jsonify({"success": False, "error": "Profile name required"}), 400
        
    t = threading.Thread(target=_run_scrape_background, args=(profile_name, num_images), daemon=True)
    t.start()
    
    return jsonify({"success": True, "message": "Scraping started in background"})


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("Perchance POD Automation Web Interface")
    print(f"{'='*60}")
    print(f"Project Root: {BASE_DIR.absolute()}")
    print(f"Pending: {len(get_pending_images())} images")
    print(f"Server: http://127.0.0.1:5001")
    print(f"{'='*60}\n")
    app.run(host="127.0.0.1", port=5001, debug=False)