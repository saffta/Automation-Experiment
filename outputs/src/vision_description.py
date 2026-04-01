#!/usr/bin/env python3
"""
Vision-based Image Description Generator with Fallback
Priority: Z.AI (GLM-4.6V) → Ollama (local vision models)
Auto-detects environment: Docker (host.docker.internal) vs Windows (localhost)
"""

import os
import base64
import json
import requests
from pathlib import Path
import litellm


def _detect_environment():
    """Detect if running in Docker or on Windows."""
    # Check for Docker indicators
    docker_indicators = [
        '/.dockerenv',
        '/proc/1/cgroup',
        os.path.exists('/.dockerenv')
    ]
    
    # Try to detect Docker
    if os.path.exists('/proc/1/cgroup'):
        try:
            with open('/proc/1/cgroup', 'r') as f:
                if 'docker' in f.read():
                    return 'docker'
        except:
            pass
    
    return 'windows'


def _get_ollama_base_url():
    """Get Ollama API URL based on environment."""
    env = _detect_environment()
    if env == 'docker':
        return 'http://host.docker.internal:11434'
    else:
        return 'http://localhost:11434'

def _load_config():
    """Load configuration from config file or environment."""
    config_path = Path(__file__).parent / "vision_config.json"
    
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    
    return {
        "api_key": os.environ.get("API_KEY_ZAI_CODING", ""),
        "api_base": "https://api.z.ai/api/coding/paas/v4",
        "model": "GLM-4.6V",
        "timeout": 30,
        "max_tags": 10,
        "ollama_fallback_enabled": True,
        "ollama_vision_model": "hf.co/unsloth/GLM-4.6V-Flash-GGUF:UD-Q4_K_XL",
        "prefer_ollama": True
    }

CONFIG = _load_config()
API_KEY = CONFIG.get("api_key", "")
API_BASE = CONFIG.get("api_base", "https://api.z.ai/api/coding/paas/v4")
MODEL = CONFIG.get("model", "GLM-4.6V")
TIMEOUT = CONFIG.get("timeout", 30)
MAX_TAGS = CONFIG.get("max_tags", 10)
OLLAMA_FALLBACK = CONFIG.get("ollama_fallback_enabled", True)
OLLAMA_VISION_MODEL = CONFIG.get("ollama_vision_model", "llava")
PREFER_OLLAMA = CONFIG.get("prefer_ollama", False)

def _list_ollama_models():
    """List available Ollama models."""
    try:
        ollama_base = _get_ollama_base_url()
        response = requests.get(f"{ollama_base}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = [m['name'] for m in data.get('models', [])]
            return models
    except Exception as e:
        print(f"Could not list Ollama models: {e}")
    return []

def _encode_image_to_base64(image_path: str) -> str:
    """Encode an image file to base64 string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def _generate_with_ollama(image_path: str, max_tags: int, model_override: str = None) -> dict:
    """Generate description using local Ollama vision model."""
    try:
        ollama_base = _get_ollama_base_url()
        
        # List models to find a vision-capable one
        available_models = _list_ollama_models()
        vision_models = [
            'llava', 'bakllava', 'moondream', 'llama3.2-vision',
            'llama3-vision', 'minicpm-v', 'nanoLLaVA', 'GLM-4.6V'
        ]
        
        # Find the best available vision model
        model_to_use = model_override
        if not model_to_use:
            if OLLAMA_VISION_MODEL in available_models:
                model_to_use = OLLAMA_VISION_MODEL
            else:
                for vm in vision_models:
                    if any(vm in m for m in available_models):
                        model_to_use = vm
                        break
        
        if not model_to_use:
            return {
                "description": "",
                "tags": [],
                "error": "No Ollama vision model available. Please pull: ollama pull llava"
            }
        
        print(f"Using Ollama vision model: {model_to_use}")
        
        # Prepare payload for Ollama
        with open(image_path, 'rb') as img_file:
            image_data = base64.b64encode(img_file.read()).decode('utf-8')
        
        prompt = f"""Describe this image in 2-3 sentences suitable for e-commerce/social media. 
Also provide a 'Primary Tag' (A SINGLE word or short phrase representing the main subject ONLY, e.g., 'cat', 'mountain', 'robot') and {max_tags} relevant secondary tags (lowercase, comma-separated).

Format as:
Description: [your description]
Primary Tag: [single tag only]
Tags: tag1, tag2, tag3, ..."""
        
        payload = {
            "model": model_to_use,
            "prompt": prompt,
            "images": [image_data],
            "stream": False
        }
        
        response = requests.post(
            f"{ollama_base}/api/generate",
            json=payload,
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            result = response.json()
            text = result.get('response', '')
            
            # Parse description, primary tag, and tags from response
            description = ""
            primary_tag = ""
            tags = []
            
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if 'description:' in line.lower():
                    description = line.split(':', 1)[1].strip()
                elif 'primary tag:' in line.lower():
                    primary_tag = line.split(':', 1)[1].strip().lower()
                elif 'tags:' in line.lower():
                    tags = [t.strip().lower() for t in line.split(':', 1)[1].split(',')]
            
            # If primary tag not found but tags exist, use first tag
            if not primary_tag and tags:
                primary_tag = tags[0]
            
            # CRITICAL: Ensure only ONE tag (no commas allowed in primary subject)
            if ',' in primary_tag:
                primary_tag = primary_tag.split(',')[0].strip()

            return {
                "description": description,
                "primary_tag": primary_tag,
                "tags": tags[:max_tags],
                "provider": "ollama"
            }
        else:
            return {
                "description": "",
                "tags": [],
                "error": f"Ollama error: {response.status_code}"
            }
            
    except Exception as e:
        return {
            "description": "",
            "tags": [],
            "error": f"Ollama fallback error: {str(e)}"
        }

def generate_description_and_tags(
    image_path: str,
    max_tags: int = None,
    timeout: int = None,
    provider: str = None,
    model_override: str = None,
    api_key: str = None,
    api_base: str = None
) -> dict:
    """
    Generate a description and tags for an image.
    Priority: Z.AI (GLM-4.6V) → Ollama (local vision model)
    """
    if not Path(image_path).exists():
        return {"description": "", "tags": [], "error": "Image not found"}
    
    max_tags = max_tags or MAX_TAGS
    timeout = timeout or TIMEOUT
    
    # Explicit provider routing
    if provider == "ollama":
        return _generate_with_ollama(image_path, max_tags, model_override)
        
    # Try Ollama first if preferred and no explicit provider
    if not provider and PREFER_OLLAMA and OLLAMA_FALLBACK:
        result = _generate_with_ollama(image_path, max_tags)
        if not result.get("error"):
            return result
        print(f"Ollama failed or not available, trying cloud... Error: {result.get('error')}")

    # Try Cloud/Custom API
    current_key = api_key or API_KEY
    current_base = api_base or API_BASE
    current_model = model_override or MODEL
    
    if current_key or provider == "openai":
        try:
            if current_key:
                os.environ['OPENAI_API_KEY'] = current_key
            else:
                os.environ['OPENAI_API_KEY'] = 'dummy-key-for-local-compatible-endpoint'
                
            base64_image = _encode_image_to_base64(image_path)
            
            prompt = f"""Analyze this image and provide:
1. A concise, engaging description (2-3 sentences) suitable for e-commerce/social media
2. A 'primary_tag' which is the SINGLE most important subject matter (e.g., 'vintage car', 'fantasy landscape', 'portrait'). MUST NOT contain commas.
3. {max_tags} relevant secondary tags (comma-separated, lowercase, single words or short phrases)

Format your response as JSON:
{{
    "description": "your description here",
    "primary_tag": "main subject here (single entry)",
    "tags": ["tag1", "tag2", "tag3", ...]
}}"""
            
            
            req_model = current_model
            # Ensure proper openai prefix for litellm unless it's already a litellm standard format
            if "/" not in req_model and ":" not in req_model:
                req_model = f"openai/{current_model}"
                
            # If no base URL is defined, fallback to Z.AI backwards compatibility
            kwargs = {
                "model": req_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "timeout": timeout,
                "temperature": 0.7
            }
            
            if current_base:
                kwargs["api_base"] = current_base
                
            response = litellm.completion(**kwargs)
            
            content = response.choices[0].message.content.strip()
            
            try:
                start = content.find('{')
                end = content.rfind('}') + 1
                if start >= 0 and end > start:
                    json_str = content[start:end]
                    result = json.loads(json_str)
                    result["tags"] = result.get("tags", [])[:max_tags]
                    result["description"] = result.get("description", "")
                    # Ensure primary_tag is present, fallback to first tag if not
                    pt = result.get("primary_tag", result["tags"][0] if result.get("tags") else "")
                    
                    # CRITICAL: Ensure only ONE tag (no commas allowed in primary subject)
                    if isinstance(pt, str) and ',' in pt:
                        pt = pt.split(',')[0].strip()
                    elif isinstance(pt, list) and len(pt) > 0:
                        pt = pt[0]
                        
                    result["primary_tag"] = pt
                    result["provider"] = "zai"
                    return result
            except json.JSONDecodeError:
                pass

            
            lines = content.split('\n')
            description = ""
            tags = []
            
            for i, line in enumerate(lines):
                line = line.strip()
                if 'description' in line.lower() and ':' in line:
                    description = line.split(':', 1)[1].strip()
                elif 'tag' in line.lower():
                    if ',' in line:
                        tags = [t.strip().lower() for t in line.split(':')[1].split(',')]
                    else:
                        tags = [line.strip().lower()]
            
            return {
                "description": description,
                "tags": tags[:max_tags],
                "provider": "zai"
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            # Check for quota/rate limit errors
            quota_errors = ['insufficient', 'rate limit', 'quota', 'balance', 'no resource']
            if any(qe in error_msg for qe in quota_errors) or '429' in str(e) or '402' in str(e):
                print(f"Z.AI quota exhausted, falling back to Ollama...")
                return _generate_with_ollama(image_path, max_tags)
            else:
                print(f"Z.AI error: {e}")
                if OLLAMA_FALLBACK:
                    print(f"Falling back to Ollama...")
                    return _generate_with_ollama(image_path, max_tags)
                return {
                    "description": "",
                    "tags": [],
                    "error": str(e)
                }
    
    # No Z.AI API key - try Ollama directly
    if OLLAMA_FALLBACK:
        return _generate_with_ollama(image_path, max_tags)
    
    return {
        "description": "",
        "tags": [],
        "error": "No API key configured and Ollama fallback disabled"
    }

def generate_title_from_description(description: str) -> str:
    """Generate a short title from a description."""
    if not description:
        return ""
    words = description.split()[:6]
    title = " ".join(words).strip(".")
    return title.capitalize() if title else ""

if __name__ == "__main__":
    import sys
    
    print(f"=== Vision Module Test ===")
    print(f"Environment: {_detect_environment()}")
    print(f"Ollama URL: {_get_ollama_base_url()}")
    print(f"Z.AI API key set: {bool(API_KEY)}")
    print(f"Ollama fallback enabled: {OLLAMA_FALLBACK}")
    
    # List Ollama models
    models = _list_ollama_models()
    if models:
        print(f"Available Ollama models: {models}")
    else:
        print("No Ollama models found (Ollama not running or no models pulled)")
    
    # Test if image provided
    if len(sys.argv) > 1:
        test_image = sys.argv[1]
        print(f"\nTesting vision on: {test_image}")
        result = generate_description_and_tags(test_image)
        print(f"\nProvider: {result.get('provider', 'unknown')}")
        print(f"Description: {result.get('description', '')}")
        print(f"Tags: {result.get('tags', [])}")
        print(f"Error: {result.get('error')}")
