#!/usr/bin/env python3
import json
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, List

class SwarmUI:
    """Interface for SwarmUI API"""
    
    def __init__(self, base_url: str = "http://localhost:7801"):
        self.base_url = base_url.rstrip("/")
        self.session_id = None

    def get_session(self) -> Optional[str]:
        """Obtain a new session ID from SwarmUI"""
        try:
            url = f"{self.base_url}/API/GetNewSession"
            print(f"🔍 SwarmUI: Attempting to connect to {url}...")
            req = urllib.request.Request(url, data=json.dumps({}).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                self.session_id = data.get("session_id")
                if self.session_id:
                    print(f"✅ SwarmUI: Session established: {self.session_id[:8]}...")
                return self.session_id
        except Exception as e:
            print(f"❌ SwarmUI Session Error (Is SwarmUI running at {self.base_url}?): {e}")
            return None

    def list_models(self) -> List[Dict[str, Any]]:
        """List available models from SwarmUI"""
        if not self.session_id:
            if not self.get_session():
                return []
        try:
            url = f"{self.base_url}/API/ListModels"
            payload = {
                "session_id": self.session_id,
                "path": "",
                "depth": 10
            }
            print(f"🔍 SwarmUI: Fetching models from {url}...")
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode()
                data = json.loads(body)
                
                if "error" in data:
                    print(f"❌ SwarmUI API Error: {data['error']}")
                    return []

                # SwarmUI might return 'files', 'folders', or 'models' depending on version/folder
                files = data.get("files", [])
                folders = data.get("folders", [])
                all_models = files + folders
                
                if not all_models and "models" in data:
                    all_models = data["models"]
                
                print(f"✅ SwarmUI: Found {len(all_models)} potential model entries.")
                return all_models
        except Exception as e:
            print(f"❌ SwarmUI List Models Error: {e}")
            return []

    def generate_image(self, config: Dict[str, Any]) -> bool:
        """
        Generate an image using SwarmUI T2I API.
        Expected config keys: prompt, negative_prompt, model, width, height, seed, cfg_scale, output_path
        """
        if not self.session_id:
            if not self.get_session():
                return False

        try:
            # Prepare SwarmUI T2I parameters
            swarm_params = {
                "session_id": self.session_id,
                "images": 1,
                "prompt": config.get("prompt", ""),
                "negativeprompt": config.get("negative_prompt", ""),
                "model": config.get("model", ""),
                "width": config.get("width", 1024),
                "height": config.get("height", 1024),
                "seed": config.get("seed", -1),
                "cfgscale": config.get("cfg_scale", 7),
            }

            url = f"{self.base_url}/API/GenerateText2Image"
            req = urllib.request.Request(url, data=json.dumps(swarm_params).encode(), headers={"Content-Type": "application/json"}, method="POST")
            
            print(f"🎨 SwarmUI generating: {config.get('prompt')[:50]}...")
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode())
                
                if "images" in result and result["images"]:
                    # SwarmUI returns image as base64 or URL. Usually base64 in default API.
                    img_data_raw = result["images"][0]
                    
                    # Debug logging to see what we actually got
                    print(f"   [DEBUG] SwarmUI returned type: {type(img_data_raw)}")
                    if isinstance(img_data_raw, str):
                        print(f"   [DEBUG] SwarmUI returned string (len {len(img_data_raw)}): {img_data_raw[:200]}")
                        
                        # Check if it's a URL path instead of base64
                        if img_data_raw.startswith("Output/") or img_data_raw.startswith("/Output/") or img_data_raw.startswith("View/") or img_data_raw.startswith("/View/") or "://" in img_data_raw:
                            print("   ⚠️ SwarmUI returned a file path/URL instead of base64. Downloading...")
                            # It's a URL. We need to construct the full URL and download it.
                            file_url = img_data_raw if "://" in img_data_raw else f"{self.base_url}/{img_data_raw.lstrip('/')}"
                            # Encode the URL to handle spaces and special characters in the filename
                            # Parse the URL into components
                            parsed_url = urllib.parse.urlsplit(file_url)
                            # Re-encode the path part specifically
                            encoded_path = urllib.parse.quote(parsed_url.path)
                            # Reconstruct the URL
                            file_url = urllib.parse.urlunsplit((parsed_url.scheme, parsed_url.netloc, encoded_path, parsed_url.query, parsed_url.fragment))
                            
                            req_dl = urllib.request.Request(file_url)
                            with urllib.request.urlopen(req_dl, timeout=30) as resp_dl:
                                img_bytes = resp_dl.read()
                        else:
                            # It's base64
                            if img_data_raw.startswith("data:image/"):
                                img_data_raw = img_data_raw.split(",")[1]
                            
                            # Fix padding if necessary
                            missing_padding = len(img_data_raw) % 4
                            if missing_padding:
                                img_data_raw += '=' * (4 - missing_padding)
                            
                            import base64
                            try:
                                img_bytes = base64.b64decode(img_data_raw)
                            except Exception as e:
                                # Try urlsafe_b64decode if standard fails
                                print(f"⚠️ Standard base64 decode failed, trying urlsafe: {e}")
                                img_bytes = base64.urlsafe_b64decode(img_data_raw)
                    else:
                        print(f"❌ Unexpected image data format from SwarmUI: {img_data_raw}")
                        return False
                    
                    output_path = Path(config["output_path"])
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(img_bytes)
                    
                    print(f"✅ SwarmUI Image saved: {output_path}")
                    return True
                else:
                    print(f"❌ SwarmUI Error: {result.get('error', 'Unknown error')}")
                    return False

        except Exception as e:
            print(f"❌ SwarmUI Generation Error: {e}")
            return False

if __name__ == "__main__":
    # Quick test
    swarm = SwarmUI()
    test_config = {
        "prompt": "a beautiful forest",
        "model": "OfficialStableDiffusion/sd_xl_base_1.0.safetensors",
        "output_path": "swarm_test.png"
    }
    swarm.generate_image(test_config)
