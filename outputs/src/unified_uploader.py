#!/usr/bin/env python3
"""Unified POD Uploader - Simplified and Fixed."""

import os
import sys
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from pod_credentials_manager import PODCredentialsManager


@dataclass
class UploadResult:
    success: bool
    platform: str
    image_path: str = ""
    title: str = ""
    tags: List[str] = field(default_factory=list)
    url: Optional[str] = None
    error: Optional[str] = None
    upload_time: Optional[str] = None
    product_id: Optional[str] = None
    listing_id: Optional[str] = None


def _load_credentials(platform: str, profile: str = None) -> Optional[Dict]:
    """Load decrypted credentials for platform from a specific profile."""
    mgr = PODCredentialsManager()
    account = mgr.get_account(platform, profile=profile)
    if not account:
        return None
    if platform in ("printful", "printify"):
        return {"api_key": account["password"]}
    return {
        "email": account["username"],
        "username": account["username"],
        "password": account["password"]
    }


def _create_platform(platform: str):
    """Safe platform factory - returns None on any error."""
    try:
        from pod_sites import create_platform
        return create_platform(platform)
    except Exception as e:
        print("Could not load platform " + platform + ": " + str(e))
        return None


def upload_single(platform: str, image_path: str, title: str,
                  tags: List[str], description: str = "", profile: str = None, 
                  primary_tag: str = "", profile_path: str = None, headless: bool = True) -> UploadResult:
    """Upload to a single platform synchronously with profile selection."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    base = UploadResult(success=False, platform=platform, image_path=image_path,
                        title=title, tags=tags, upload_time=ts)

    creds = _load_credentials(platform, profile=profile)
    if not creds:
        base.error = "No credentials configured for " + platform
        return base

    # SPECIAL: Use the specialized bots for Redbubble and TeePublic
    if platform.lower() == "redbubble" or platform.lower() == "teepublic":
        try:
            from bot_integration import upload_redbubble, upload_teepublic
            if platform.lower() == "redbubble":
                success = upload_redbubble(image_path, title, tags, description, primary_tag, creds, profile_path=profile_path, headless=headless)
            else:
                success = upload_teepublic(image_path, title, tags, description, primary_tag, creds, headless=headless)
            
            base.success = success
            if not success:
                base.error = f"{platform} specialized bot failed"
            return base
        except Exception as e:
            base.error = f"Bot integration error: {e}"
            return base

    plat = _create_platform(platform)
    if not plat:
        base.error = "Platform " + platform + " could not be loaded"
        return base
    
    # ... rest of the original logic for other platforms (printful, printify)
    try:
        from PIL import Image
        image = Image.open(image_path)
    except Exception as e:
        base.error = "Could not open image: " + str(e)
        return base

    # Authenticate
    try:
        auth_method = plat.authenticate
        if asyncio.iscoroutinefunction(auth_method):
            ok = asyncio.run(auth_method(creds))
        else:
            ok = auth_method(creds)
        if not ok:
            base.error = "Authentication failed for " + platform
            return base
    except Exception as e:
        base.error = "Auth error: " + str(e)
        return base

    # Upload
    metadata = {"title": title, "description": description, "tags": tags, "primary_tag": primary_tag}
    try:
        upload_method = plat.upload_product
        if asyncio.iscoroutinefunction(upload_method):
            result = asyncio.run(upload_method(image=image, metadata=metadata))
        else:
            result = upload_method(image=image, metadata=metadata)
        base.success = result.success
        base.url = result.url
        base.product_id = result.product_id
        base.listing_id = getattr(result, "listing_id", None)
        base.error = result.error_message if not result.success else None
    except Exception as e:
        import traceback; traceback.print_exc()
        base.error = "Upload error: " + str(e)

    return base


def upload_to_all(image_path: str, title: str,
                  tags: List[str], description: str = "", profile: str = None,
                  platforms: List[str] = None, primary_tag: str = "", 
                  profile_path: str = None, 
                  headless_redbubble: bool = True,
                  headless_teepublic: bool = True) -> List[UploadResult]:
    """Upload an image to multiple platforms in parallel/sequential."""
    if not platforms:
        platforms = ["redbubble", "teepublic"]

    results = []
    for plat in platforms:
        headless = headless_redbubble if plat.lower() == "redbubble" else headless_teepublic
        print(f"\n🚀 Uploading to {plat} with profile '{profile or 'default'}' (Headless: {headless})...")
        r = upload_single(plat, image_path, title, tags, description, profile=profile, 
                          primary_tag=primary_tag, profile_path=profile_path, headless=headless)
        results.append(r)
        if r.success:
            print("OK " + plat + ": Bot succeeded")
        else:
            print("FAIL " + plat + ": " + str(r.error))
            
    return results


# Legacy compatibility wrappers
class UnifiedPODUploader:
    def __init__(self):
        self.credentials_manager = PODCredentialsManager()

    def is_platform_configured(self, platform: str) -> bool:
        return self.credentials_manager.get_account(platform) is not None

    def get_available_platforms(self) -> List[str]:
        return ["printful", "printify", "teepublic", "redbubble"]

    async def upload_to_all_platforms(self, image_path, title, tags, description=""):
        results = []
        for p in self.get_available_platforms():
            if self.is_platform_configured(p):
                r = upload_single(p, image_path, title, tags, description)
                results.append(r)
        return results


def upload_to_platform_sync(uploader, platform, image_path, title, tags, description="", product_type="t-shirt"):
    return upload_single(platform, image_path, title, tags, description)


def upload_to_all_platforms_sync(uploader, image_path, title, tags, description="", product_type="t-shirt"):
    return upload_to_all(image_path, title, tags, description)


if __name__ == "__main__":
    mgr = PODCredentialsManager()
    print("Configured platforms:")
    for p in ["printful", "printify", "teepublic", "redbubble"]:
        ok = mgr.get_account(p) is not None
        status = "configured" if ok else "not configured"
        print("  " + p + ": " + status)
