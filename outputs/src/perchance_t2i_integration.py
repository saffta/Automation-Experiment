#!/usr/bin/env python3
"""
Perchance-T2I Image Generation Integration
===========================================

This module provides a clean Python interface to the Perchance-T2I Cloudflare Workers proxy.

API URL: https://t2i.manh9011.workers.dev/
Maintainer: manh9011 (Perchance-T2I-Desktop author)

Available Models:
- flux: Flux Schnell (best quality)
- zimage: Z-Image Turbo (fast, good quality)
- turbo: SDXL Turbo (very fast, lower quality)

Available Styles: 67 total (see STYLES constant below)
"""

import urllib.request
import urllib.parse
import urllib.error
import json
import re
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path

# Available Models
MODELS = {
    "flux": "Flux Schnell",
    "zimage": "Z-Image Turbo",
    "turbo": "SDXL Turbo"
}

# Available Art Styles (67 total)
STYLES = [
    "No Style", "Painted Anime", "Casual Photo", "Cinematic", "Digital Painting",
    "Concept Art", "3D Disney Character", "2D Disney Character", "Disney Sketch",
    "Concept Sketch", "Painterly", "Oil Painting", "Oil Painting - Realism",
    "Oil Painting - Old", "Professional Photo", "Anime", "Drawn Anime", "Cute Anime",
    "Soft Anime", "Fantasy Painting", "Fantasy Landscape", "Fantasy Portrait",
    "Studio Ghibli", "50s Enamel Sign", "Vintage Comic", "Franco-Belgian Comic",
    "Tintin Comic", "Medieval", "Pixel Art", "Furry - Oil", "Furry - Cinematic",
    "Furry - Painted", "Furry - Drawn", "Cute Figurine", "3D Emoji", "Illustration",
    "Flat Illustration", "Watercolor", "1990s Photo", "1980s Photo", "1970s Photo",
    "1960s Photo", "1950s Photo", "1940s Photo", "1930s Photo", "1920s Photo",
    "Vintage Pulp Art", "50s Infomercial Anime", "3D Pokemon", "Painted Pokemon",
    "2D Pokemon", "Vintage Anime", "Neon Vintage Anime", "Manga", "Fantasy World Map",
    "Fantasy City Map", "Old World Map", "3D Isometric Icon", "Flat Style Icon",
    "Flat Style Logo", "Game Art Icon", "Digital Painting Icon", "Concept Art Icon",
    "Cute 3D Icon", "Cute 3D Icon Set", "Crayon Drawing", "Pencil", "Tattoo Design"
]

# Proxy URL
PROXY_URL = "https://t2i.manh9011.workers.dev/"


def sanitize_prompt(prompt: str) -> Optional[str]:
    """Remove AI tagging syntax that might cause API issues
    Returns None if prompt becomes empty after sanitization"""
    if not prompt:
        return None
    
    # Remove LoRA references: <lora:Name:weight>
    prompt = re.sub(r'<lora:[^>]+>', '', prompt)
    
    # Remove common AI tagging patterns that might trigger API restrictions
    patterns_to_remove = [
        r'\bscore_\d+\b',  # score_9, score_8_up, etc.
        r'\bsan\b',        # Sanitized/safety tag
        r'\b1girl\b',      # Character tags
        r'\b1boy\b',
        r'\b2girls\b',
        r'\b2boys\b',
        r'\bnsfw\b',
        r'\bexplicit\b',
        r'\bfull_body\b',
        r'\bsquare\b',
        r'\bhighly_detailed\b',
        r'\bsharp_focus\b',
        r'\bhdr\b',
        r'\b8k\b',
        r'\bmasterpiece\b',
        r'\bbest_quality\b',
        r'\bhigh_quality\b',
        r'\b4k\b',
        r'\bultra_detailed\b',
        r'\bphotorealistic\b',
    ]
    
    sanitized = prompt
    for pattern in patterns_to_remove:
        sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
    
    # Clean up extra commas and spaces
    sanitized = re.sub(r',\s*,', ',', sanitized)
    sanitized = re.sub(r',\s*$', '', sanitized)
    sanitized = sanitized.strip()
    
    # Check if prompt is empty after sanitization
    if not sanitized or len(sanitized) < 15:
        return None
    
    return sanitized


@dataclass
class ImageGenerationConfig:
    """Configuration for image generation"""
    prompt: str
    model: str = "zimage"
    negative_prompt: str = ""
    guidance_scale: int = 7
    quality: str = "high"  # low, medium, high
    width: int = 1024
    height: int = 1024
    seed: int = -1  # -1 for random seed
    output_path: str = "output.png"
    style: str = "No Style"  # Optional: apply an art style

    def __post_init__(self):
        """Validate configuration"""
        if self.model not in MODELS:
            raise ValueError(f"Invalid model. Choose from: {list(MODELS.keys())}")
        if self.quality not in ["low", "medium", "high"]:
            raise ValueError("Quality must be: low, medium, or high")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Width and height must be positive integers")
        if self.style not in STYLES:
            raise ValueError(f"Invalid style. Choose from: {STYLES}")


class PerchanceT2I:
    """Perchance-T2I Image Generation Client"""

    def __init__(self, proxy_url: str = PROXY_URL):
        """Initialize the client"""
        self.proxy_url = proxy_url.rstrip("/")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://t2i.manh9011.workers.dev/",
            "Origin": "https://t2i.manh9011.workers.dev"
        }

    def generate_image(self, config: ImageGenerationConfig, retry_models: bool = True) -> bool:
        """
        Generate an image using the Perchance-T2I proxy.

        Args:
            config: ImageGenerationConfig object
            retry_models: If True, try other models if first fails

        Returns:
            True if successful, False otherwise
        """
        # Sanitize prompts
        sanitized_prompt = sanitize_prompt(config.prompt)
        sanitized_negative = sanitize_prompt(config.negative_prompt)
        
        # Check if prompt is valid after sanitization
        if not sanitized_prompt:
            print(f"❌ Prompt is empty after sanitization: '{config.prompt}'")
            return False
        
        models_to_try = [config.model]
        if retry_models and config.model != "turbo":
            models_to_try.append("turbo")
        
        for model in models_to_try:
            try:
                # Prepare parameters
                params = {
                    "prompt": sanitized_prompt,
                    "negative_prompt": sanitized_negative or "",
                    "guidance_scale": str(config.guidance_scale),
                    "quality": config.quality,
                    "width": str(config.width),
                    "height": str(config.height),
                    "seed": str(config.seed),
                    "model": model
                }

                # Build URL
                url = f"{self.proxy_url}?{urllib.parse.urlencode(params)}"

                print(f"🔗 Request URL: {url[:100]}...")
                print(f"📝 Prompt: {sanitized_prompt[:80]}...")
                print(f"🎨 Model: {MODELS.get(model, model)}")

                # Make request
                request = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(request, timeout=120) as response:
                    image_data = response.read()

                # Save image
                output_path = Path(config.output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, "wb") as f:
                    f.write(image_data)

                print(f"✅ Image generated successfully: {output_path}")
                print(f"   Size: {len(image_data)} bytes")
                print(f"   Model: {MODELS.get(model, model)}")
                print(f"   Style: {config.style}")
                return True

            except urllib.error.HTTPError as e:
                print(f"❌ HTTP Error {e.code} with {model}: {e.reason}")
                if e.code == 403:
                    print(f"   ⚠️  Trying alternative model...")
                    continue
                elif e.code == 400:
                    print(f"   ⚠️  Bad request - skipping this prompt")
                    return False
                return False
            except urllib.error.URLError as e:
                print(f"❌ URL Error with {model}: {e.reason}")
                continue
            except Exception as e:
                print(f"❌ Unexpected error with {model}: {e}")
                continue
        
        print(f"❌ Failed to generate image with all available models")
        return False

    def _apply_style(self, prompt: str, style: str) -> str:
        """Apply art style to prompt (basic implementation)"""
        if style == "No Style" or not prompt:
            return prompt

        # Simple style prefixes (can be enhanced with full artStyles.ts logic)
        style_prompts = {
            "Anime": f"anime style, {prompt}",
            "Cinematic": f"cinematic shot, {prompt}",
            "Watercolor": f"watercolor painting, {prompt}",
            "Digital Painting": f"digital painting, {prompt}",
            "Pixel Art": f"pixel art, {prompt}",
            "3D Emoji": f"3D emoji style, {prompt}",
            "Vintage Comic": f"vintage comic style, {prompt}",
            "Studio Ghibli": f"studio ghibli style, {prompt}",
            "Professional Photo": f"professional photograph, {prompt}",
            "Pencil": f"pencil drawing, {prompt}",
        }

        return style_prompts.get(style, prompt)

    def generate_batch(self, configs: list) -> Dict[str, bool]:
        """Generate multiple images in batch"""
        results = {}
        for i, config in enumerate(configs):
            key = f"image_{i+1}"
            results[key] = self.generate_image(config)
        return results


def main():
    """Example usage"""
    client = PerchanceT2I()

    # Example 1: Simple generation
    config1 = ImageGenerationConfig(
        prompt="a beautiful sunset over mountains",
        model="flux",
        width=512,
        height=512,
        output_path="example1.png"
    )
    client.generate_image(config1)

    # Example 2: With style
    config2 = ImageGenerationConfig(
        prompt="a cute cat",
        model="zimage",
        style="Painted Anime",
        output_path="example2.png"
    )
    client.generate_image(config2)

    # Example 3: Batch generation
    batch_configs = [
        ImageGenerationConfig(prompt="sunset", model="flux", output_path="batch1.png"),
        ImageGenerationConfig(prompt="mountain", model="flux", output_path="batch2.png"),
        ImageGenerationConfig(prompt="ocean", model="flux", output_path="batch3.png"),
    ]
    results = client.generate_batch(batch_configs)
    print(f"Batch results: {results}")


if __name__ == "__main__":
    main()
