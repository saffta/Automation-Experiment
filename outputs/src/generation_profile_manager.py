#!/usr/bin/env python3
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

class GenerationProfileManager:
    """Manages generation profiles for image backends"""
    
    def __init__(self, profiles_path: str = None):
        if profiles_path is None:
            # Default to metadata/generation_profiles.json relative to project root
            base_dir = Path(__file__).parent.parent
            self.profiles_path = base_dir / "metadata" / "generation_profiles.json"
        else:
            self.profiles_path = Path(profiles_path)
            
        self.profiles_path.parent.mkdir(parents=True, exist_ok=True)
        self.profiles = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.profiles_path.exists():
            try:
                return json.loads(self.profiles_path.read_text())
            except Exception as e:
                print(f"⚠️ Failed to load profiles: {e}")
        
        # Default profiles
        return {
            "Perchance Flux": {
                "backend": "perchance",
                "model": "flux",
                "width": 1024,
                "height": 1024,
                "guidance_scale": 7
            },
            "Perchance Z-Image": {
                "backend": "perchance",
                "model": "zimage",
                "width": 1024,
                "height": 1024,
                "guidance_scale": 7
            },
            "Local SwarmUI SDXL": {
                "backend": "swarmui",
                "model": "OfficialStableDiffusion/sd_xl_base_1.0.safetensors",
                "width": 1024,
                "height": 1024,
                "cfg_scale": 7,
                "base_model_map": {
                    "SDXL": "OfficialStableDiffusion/sd_xl_base_1.0.safetensors",
                    "Flux": "OfficialStableDiffusion/flux1-dev-fp8.safetensors",
                    "Pony": "OfficialStableDiffusion/noobaiInpainting_v10.safetensors"
                }
            }
        }

    def _save(self):
        try:
            self.profiles_path.write_text(json.dumps(self.profiles, indent=2))
        except Exception as e:
            print(f"⚠️ Failed to save profiles: {e}")

    def get_profile(self, name: str) -> Optional[Dict[str, Any]]:
        return self.profiles.get(name)

    def list_profiles(self) -> List[str]:
        return list(self.profiles.keys())

    def add_profile(self, name: str, config: Dict[str, Any]):
        self.profiles[name] = config
        self._save()

    def delete_profile(self, name: str):
        if name in self.profiles:
            del self.profiles[name]
            self._save()

if __name__ == "__main__":
    mgr = GenerationProfileManager()
    print(f"Loaded profiles: {mgr.list_profiles()}")
