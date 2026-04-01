#!/usr/bin/env python3
# Civitai -> Perchance-T2I -> POD Automation
import os, sys, time, json, urllib.request, urllib.parse, re, argparse, uuid
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, asdict, field
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from perchance_t2i_integration import PerchanceT2I, ImageGenerationConfig, sanitize_prompt
from image_processor import process_for_pod
from swarmui_integration import SwarmUI
from generation_profile_manager import GenerationProfileManager


@dataclass
class CivitaiImage:
    id: int
    prompt: str
    creatorName: str
    thumbnailUrl: str
    modelId: int = 0
    modelVersionId: int = 0
    baseModel: str = "Unknown"
    negativePrompt: str = ""
    seed: int = -1
    width: int = 1024
    height: int = 1024
    steps: int = 20
    sampler: str = "Euler"
    cfgScale: float = 7.0
    creatorId: int = 0
    likes: int = 0
    reactions_per_day: float = 0.0
    nsfw: bool = False
    tags: List[str] = field(default_factory=list)
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return asdict(self)


MODEL_EXCLUDE_LIST = [
    "Google", "Google DeepMind", "Gemini", "Vertex AI",
    "Nano Banana", "Midjourney", "DALL-E",
    "Playground AI", "Leonardo AI", "Bing Image Creator",
    "Kandinsky", "Stable Audio", "Suno", "Udio",
    "Runway", "Pika", "HeyGen", "Synthesia"
]

MODEL_ALLOW_LIST = [
    "Flux", "Flux.1", "Flux Pro", "Flux Dev",
    "Z-Image", "Z-Image Turbo",
    "SDXL", "Stable Diffusion XL",
    "SD 1.5", "Stable Diffusion 1.5",
    "Illustrious", "Llama", "Journey", "Ideogram"
]

QUALITY_WORDS = [
    "masterpiece", "best quality", "amazing quality", "high quality", "perfect quality",
    "ultra quality", "excellent quality", "very aesthetic",
    "high resolution", "ultra detailed", "hyper detailed", "highly detailed",
    "intricate details", "sharp focus", "perfect anatomy",
    "absurdres", "highres", "uhd", "hdr", "4k", "8k",
    "score_9", "score_8", "score_7", "score_6", "score_5",
    "source_anime", "source_illustration", "source_pony",
    "very beautiful", "very detailed", "very realistic",
    "photorealistic", "photorealism", "hyper-realism",
    "cinematic", "professional", "award-winning", "stunning", "breathtaking",
    "newest", "esthetic", "awa", "bw9t", "dreamwash", "traditional_media",
    "absolutely eye-catching", "very awa"
]

SKIP_WORDS = {
    "a", "an", "the", "with", "and", "or", "at", "in", "on", "of", "to",
    "is", "are", "was", "be", "very", "some", "no", "not", "its",
    "solo", "break", "style", "quality", "perfect", "best", "high", "ultra",
}


def predict_model_for_image(tags, base_model):
    tag_text = " ".join(tags).lower()
    if any(k in tag_text for k in ["anime", "character", "portrait", "illustration", "manga"]):
        return "zimage"
    if any(k in tag_text for k in ["photorealistic", "photo", "realistic"]):
        return "flux"
    return "zimage"


def should_include_model(base_model, model_name=""):
    model_text = (base_model + " " + model_name).lower()
    for exc in MODEL_EXCLUDE_LIST:
        if exc.lower() in model_text:
            return False
    return True


def clean_prompt(prompt):
    """Remove quality/technical words and LoRA tags from a prompt."""
    clean = re.sub(r"<[^>]+>", " ", prompt)
    for word in sorted(QUALITY_WORDS, key=len, reverse=True):
        clean = re.sub(re.escape(word), " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(score_\d+[_.]?\w*)\b", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(source_\w+)\b", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(4k|8k|hdr|uhd|nsfw|sfw)\b", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"[,;]+", ",", clean)
    clean = re.sub(r",\s*,+", ",", clean)
    clean = re.sub(r"^[,\s]+|[,\s]+$", "", clean)
    clean = re.sub(r"\s{2,}", " ", clean)
    return clean.strip()


def extract_tags_from_prompt(prompt):
    """Extract meaningful subject/style tags."""
    clean = clean_prompt(prompt)
    parts = re.split(r"[,;]|\bBREAK\b", clean, flags=re.IGNORECASE)
    tags, seen = [], set()
    for part in parts:
        part = part.strip().lower()
        if len(part) < 3 or re.match(r"^[\W_]+$", part):
            continue
        words = part.split()
        meaningful = [w for w in words if w not in SKIP_WORDS and len(w) > 2]
        if not meaningful:
            continue
        tag = " ".join(meaningful[:2]).strip(".,;- ") if len(words) > 4 else " ".join(meaningful[:3]).strip(".,;- ")
        if tag and tag not in seen and len(tag) > 2:
            tags.append(tag)
            seen.add(tag)
    return tags[:15] or ["ai-art", "digital-art", "artwork"]


def generate_metadata_from_prompt(prompt):
    """Generate title, tags, description from prompt."""
    clean = clean_prompt(prompt)
    tags = extract_tags_from_prompt(prompt)
    title_words = [w for w in clean.split()[:12] if w.lower() not in SKIP_WORDS and len(w) > 1]
    title = " ".join(title_words[:8]).title().strip(" ,.;")
    if len(title) > 60: title = title[:57] + "..."
    title = title or "AI Generated Artwork"
    desc_parts = [t for t in tags[:8] if len(t) > 3]
    description = ", ".join(desc_parts).capitalize()
    description = (description + ". AI-generated artwork.") if description else "AI-generated artwork from CivitAI."
    return {"title": title, "tags": tags, "description": description}


def fetch_model_details(model_version_id, headers):
    try:
        url = f"https://civitai.com/api/v1/model-versions/{model_version_id}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            mi = data.get("model", {})
            return {"modelId": mi.get("id", 0), "modelName": mi.get("name", "Unknown"),
                    "baseModel": data.get("baseModel", "Unknown"), "success": True}
    except Exception:
        return {"modelId": 0, "modelName": "Unknown", "baseModel": "Unknown", "success": False}


class CivitaiScraper:
    BASE_URL = "https://civitai.com/api/v1/images"

    def __init__(self, limit=20):
        self.limit = limit
        self.headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    def get_trending_images(self):
        print("📥 Fetching trending images (Most Reactions Per Day)...")
        try:
            params = {"sort": "Most Reactions", "period": "Day",
                      "limit": str(self.limit), "nsfw": "False"}
            url = self.BASE_URL + "?" + urllib.parse.urlencode(params)
            print("🔗 URL: " + url)
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not data or "items" not in data:
                print("⚠️  No items - using fallback")
                return self._fallback()
            images, excluded = [], 0
            for item in data["items"][:self.limit]:
                try:
                    meta = item.get("meta", {})
                    prompt = meta.get("prompt", "")
                    if not prompt:
                        continue
                    stats = item.get("stats", {})
                    likes = stats.get("likeCount", 0)
                    mvids = item.get("modelVersionIds", [])
                    model_id, model_version_id = 0, 0
                    base_model = item.get("baseModel", "Unknown")
                    if mvids:
                        model_version_id = mvids[0]
                        d = fetch_model_details(model_version_id, self.headers)
                        if d["success"]:
                            model_id = d["modelId"]
                            base_model = d["baseModel"]
                    if not should_include_model(base_model, item.get("model", "")):
                        print("   ✗ Excluding: " + base_model)
                        excluded += 1
                        continue
                    tags = extract_tags_from_prompt(prompt)
                    images.append(CivitaiImage(
                        id=item.get("id", 0), modelId=model_id,
                        modelVersionId=model_version_id, baseModel=base_model,
                        prompt=prompt, negativePrompt=meta.get("negativePrompt", ""),
                        seed=meta.get("seed", -1), width=meta.get("width", 512),
                        height=meta.get("height", 512),
                        sampler=meta.get("sampler", "Euler a"),
                        cfgScale=meta.get("cfgScale", 7.0),
                        creatorId=item.get("creatorId", 0),
                        creatorName=item.get("username", "Unknown"),
                        likes=likes, reactions_per_day=float(likes),
                        nsfw=item.get("nsfw", False),
                        thumbnailUrl=item.get("url", ""), tags=tags
                    ))
                except Exception as e:
                    print("   ⚠️ Parse error: " + str(e))
            print("✅ Got " + str(len(images)) + " images, excluded " + str(excluded))
            return images or self._fallback()
        except Exception as e:
            print("❌ API error: " + str(e))
            return self._fallback()

    def _fallback(self):
        print("🔄 Using fallback sample images")
        return [
            CivitaiImage(
                id=1, 
                prompt="cyberpunk city night neon rain reflections wet street", 
                creatorName="AI Artist", 
                thumbnailUrl="", 
                modelId=100, 
                modelVersionId=10001, 
                baseModel="Flux",
                tags=["cyberpunk", "city", "neon"]
            ),
            CivitaiImage(
                id=2, 
                prompt="anime girl pink hair magical cherry blossom garden", 
                creatorName="Manga Creator", 
                thumbnailUrl="", 
                modelId=101, 
                modelVersionId=10002, 
                baseModel="Z-Image",
                tags=["anime", "garden"]
            ),
            CivitaiImage(
                id=3, 
                prompt="dragon flying over mountains sunset fantasy epic landscape", 
                creatorName="Fantasy World", 
                thumbnailUrl="", 
                modelId=102, 
                modelVersionId=10003, 
                baseModel="Flux",
                tags=["fantasy", "dragon"]
            ),
        ]


class AutomationPipeline:
    def __init__(self, project_root, remove_bg=False, upscale=True):
        self.project_root = Path(project_root)
        self.remove_bg = remove_bg
        self.upscale = upscale
        self.pending_dir = self.project_root / "images" / "by_status" / "pending"
        self.approved_dir = self.project_root / "images" / "by_status" / "approved"
        self.denied_dir = self.project_root / "images" / "by_status" / "denied"
        self.favorites_dir = self.project_root / "images" / "by_status" / "favorites"
        self.metadata_dir = self.project_root / "metadata"
        for d in [self.pending_dir, self.approved_dir, self.denied_dir,
                  self.favorites_dir, self.metadata_dir]:
            d.mkdir(parents=True, exist_ok=True)
        self.t2i = PerchanceT2I()
        self.swarm = SwarmUI()
        self.profile_mgr = GenerationProfileManager()

    def _get_existing_ids(self):
        ids = set()
        for folder in [self.pending_dir, self.approved_dir,
                       self.denied_dir, self.favorites_dir]:
            for f in folder.glob("civitai_*.png"):
                m = re.match(r"civitai_(\d+)_", f.name)
                if m:
                    ids.add(int(m.group(1)))
        return ids

    def save_metadata(self, filename, civitai_img, metadata):
        meta_path = self.metadata_dir / filename.replace(".png", "_metadata.json")
        data = {
            "id": str(uuid.uuid4()),
            "civitai_image_id": civitai_img.id,
            "source": "civitai_most_reactions_per_day",
            "model": predict_model_for_image(civitai_img.tags, civitai_img.baseModel),
            "model_id": civitai_img.modelId,
            "model_version_id": civitai_img.modelVersionId,
            "base_model": civitai_img.baseModel,
            "prompt": civitai_img.prompt,
            "negative_prompt": civitai_img.negativePrompt,
            "seed": civitai_img.seed,
            "steps": civitai_img.steps,
            "sampler": civitai_img.sampler,
            "cfg_scale": civitai_img.cfgScale,
            "width": civitai_img.width,
            "height": civitai_img.height,
            "style": "No Style",
            "suggested": True,
            "title": metadata["title"],
            "tags": metadata["tags"],
            "tags_suggested": metadata["tags"],
            "description": metadata["description"],
            "creator_name": civitai_img.creatorName,
            "likes": civitai_img.likes,
            "reactions_per_day": civitai_img.reactions_per_day,
            "nsfw": civitai_img.nsfw,
            "generated_at": datetime.now().isoformat(),
            "image_path": str(self.pending_dir / filename),
        }
        with open(meta_path, "w") as mf:
            json.dump(data, mf, indent=2)
        return meta_path

    def regenerate_image(self, filename, profile_name=None, overrides=None):
        """Regenerate an existing image with new parameters"""
        cid = None
        m = re.match(r"civitai_(\d+)_", filename)
        if m:
            cid = int(m.group(1))
        
        if not cid:
            print(f"❌ Could not extract Civitai ID from {filename}")
            return False

        # Load existing metadata to get civilai info
        meta_path = self.metadata_dir / filename.replace(".png", "_metadata.json")
        if not meta_path.exists():
            print(f"❌ Metadata not found for {filename}")
            return False
            
        with open(meta_path, "r") as f:
            old_data = json.load(f)

        # Determine config
        config = {
            "prompt": old_data.get("prompt", ""),
            "negative_prompt": old_data.get("negative_prompt", ""),
            "width": old_data.get("width", 1024),
            "height": old_data.get("height", 1024),
            "seed": old_data.get("seed", -1),
            "cfg_scale": old_data.get("cfg_scale", 7),
            "model": old_data.get("model", "flux"),
            "backend": "perchance"
        }

        if profile_name:
            profile = self.profile_mgr.get_profile(profile_name)
            if profile:
                config.update(profile)
        
        if overrides:
            config.update(overrides)

        output_path = self.pending_dir / filename
        config["output_path"] = str(output_path)

        success = False
        if config["backend"] == "swarmui":
            success = self.swarm.generate_image(config)
        else:
            # Perchance T2I config
            p_config = ImageGenerationConfig(
                prompt=sanitize_prompt(config["prompt"]),
                negative_prompt=config["negative_prompt"],
                width=config["width"],
                height=config["height"],
                guidance_scale=int(config["cfg_scale"]),
                seed=config["seed"],
                model=config["model"],
                output_path=str(output_path)
            )
            success = self.t2i.generate_image(p_config)

        if success:
            # Update metadata
            old_data["generated_at"] = datetime.now().isoformat()
            old_data["model"] = config["model"]
            old_data["backend"] = config["backend"]
            old_data["width"] = config["width"]
            old_data["height"] = config["height"]
            old_data["cfg_scale"] = config["cfg_scale"]
            old_data["seed"] = config["seed"]
            
            with open(meta_path, "w") as f:
                json.dump(old_data, f, indent=2)
            
            # Post-process
            if self.remove_bg or self.upscale:
                try:
                    import shutil
                    final = process_for_pod(str(output_path), remove_bg=self.remove_bg, upscale=self.upscale)
                    if final and final != str(output_path):
                        shutil.move(final, str(output_path))
                except Exception as pe:
                    print(f"⚠️ Post-process error: {pe}")
            
            return True
        return False

    def run(self, num_images=5, style="No Style", force_model=None, profile_name=None):
        print("\n" + "="*60)
        print("🚀 Civitai -> Perchance -> POD Pipeline")
        print("="*60)
        print(f"   Generating: {num_images} images")
        
        profile = None
        if profile_name:
            profile = self.profile_mgr.get_profile(profile_name)
            if profile:
                print(f"   Using Profile: {profile_name}")
                style = profile.get("style", style)
                force_model = profile.get("model", force_model)
        
        print(f"   BG removal: {self.remove_bg} | Upscale: {self.upscale}")

        scraper = CivitaiScraper(limit=50)
        all_images = scraper.get_trending_images()
        if not all_images:
            print("❌ No images fetched.")
            return

        existing_ids = self._get_existing_ids()
        new_images = [img for img in all_images if img.id not in existing_ids]
        print("\n🔍 Existing: " + str(len(existing_ids)) + " | New: " + str(len(new_images)))
        if not new_images:
            print("⚠️  All trending images already generated. Nothing new to add.")
            return
        to_process = new_images[:num_images]

        print("\n🎨 Generating " + str(len(to_process)) + " images...")
        generated, skipped = [], 0
        for i, img in enumerate(to_process, 1):
            print(f"\n[{i}/{len(to_process)}] Civitai #{img.id} by {img.creatorName}")
            clean = sanitize_prompt(img.prompt)
            if not clean or len(clean) < 5:
                print("   ⚠️ Empty prompt, skipping")
                skipped += 1
                continue
            # Model selection logic
            model = None
            if profile and "base_model_map" in profile:
                # Check for direct matches or substrings in Civitai's baseModel (e.g., "Pony", "Flux.1")
                cv_base = (img.baseModel or "").lower()
                for key, target_model in profile["base_model_map"].items():
                    if key.lower() in cv_base:
                        model = target_model
                        print(f"   🎯 Profile Map: Matched {key} -> {model}")
                        break
            
            if not model:
                model = force_model or predict_model_for_image(img.tags, img.baseModel)
            
            backend = "perchance"
            if profile and profile.get("backend"):
                backend = profile["backend"]
            elif model == "swarmui": # fallback if manually passed
                backend = "swarmui"

            print(f"   Backend: {backend} | Model: {model} | Base: {img.baseModel}")
            filename = "civitai_" + str(img.id) + "_v1.png"
            output_path = self.pending_dir / filename
            
            success = False
            try:
                if backend == "swarmui":
                    swarm_config = {
                        "prompt": clean,
                        "negative_prompt": img.negativePrompt,
                        "width": profile.get("width", 1024) if profile else 1024,
                        "height": profile.get("height", 1024) if profile else 1024,
                        "cfg_scale": profile.get("cfg_scale", 7) if profile else 7,
                        "seed": img.seed,
                        "model": model,
                        "output_path": str(output_path)
                    }
                    success = self.swarm.generate_image(swarm_config)
                else:
                    config = ImageGenerationConfig(
                        prompt=clean,
                        negative_prompt=img.negativePrompt,
                        width=1024, height=1024,
                        guidance_scale=int(img.cfgScale or 7),
                        seed=img.seed,
                        model=model,
                        style=style,
                        output_path=str(output_path)
                    )
                    success = self.t2i.generate_image(config)

                if success and output_path.exists():
                    if self.remove_bg or self.upscale:
                        try:
                            import shutil
                            final = process_for_pod(
                                str(output_path),
                                remove_bg=self.remove_bg,
                                upscale=self.upscale
                            )
                            if final and final != str(output_path):
                                shutil.move(final, str(output_path))
                        except Exception as pe:
                            print("   ⚠️ Post-process error: " + str(pe))
                    metadata = generate_metadata_from_prompt(img.prompt)
                    self.save_metadata(filename, img, metadata)
                    generated.append(filename)
                    print("   ✅ Saved: " + filename)
                    print("   🏷️  Title: " + metadata["title"])
                    print("   🔖 Tags: " + ", ".join(metadata["tags"][:5]))
                    time.sleep(2)
                else:
                    print("   ❌ Generation failed")
                    skipped += 1
            except Exception as e:
                print("   ❌ Error: " + str(e))
                skipped += 1

        print("\n" + "="*60)
        print("✅ Done! Generated: " + str(len(generated)) + " | Skipped: " + str(skipped))
        print("="*60)
        print("📝 Next: open web interface to approve images")
        print("   Open http://localhost:5001")


def main():
    parser = argparse.ArgumentParser(description="Civitai -> Perchance -> POD automation")
    parser.add_argument("--num-images", type=int, default=5, help="Number of images to generate")
    parser.add_argument("--style", default="No Style", help="Image style")
    parser.add_argument("--model", default=None, help="Force model: flux or zimage")
    parser.add_argument("--remove-bg", action="store_true", help="Remove background from images")
    parser.add_argument("--no-upscale", action="store_true", help="Skip upscaling")
    parser.add_argument("--project-root", default=None, help="Project root directory")
    args = parser.parse_args()

    project_root = args.project_root or str(Path(__file__).parent.parent)
    pipeline = AutomationPipeline(
        project_root=project_root,
        remove_bg=args.remove_bg,
        upscale=not args.no_upscale
    )
    pipeline.run(
        num_images=args.num_images,
        style=args.style,
        force_model=args.model
    )


if __name__ == "__main__":
    main()
