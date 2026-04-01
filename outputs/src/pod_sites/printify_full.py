#!/usr/bin/env python3
import base64
"""Printify Full Product Creation - Complete Product Listing Automation


This module creates complete Printify products:
1. Upload image to media library
2. Create product with blueprint (t-shirt, stickers, etc.)
3. Add title, description, tags
4. Publish product
"""

import requests
from typing import Dict, List, Optional, Any
from PIL import Image
from io import BytesIO
from datetime import datetime

from .base import PODPlatform, UploadResult

class PrintifyFullPlatform(PODPlatform):
    """Printify API v1 integration with full product creation"""

    BASE_URL = "https://api.printify.com/v1"

    # Blueprint IDs for common Printify products
    BLUEPRINTS = {
        "t-shirt": "607",
        "sticker": "585",
        "poster": "594",
        "mug": "576",
        "tote-bag": "592",
        "hoodie": "639"
    }

    def __init__(self):
        super().__init__()
        self.api_key = None
        self.shop_id = None
        self.session = requests.Session()

    def authenticate(self, credentials: Dict[str, str]) -> bool:
        self.api_key = credentials.get("api_key") or credentials.get("password")
        if not self.api_key:
            print("❌ Printify: API key required")
            return False

        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
        try:
            r = self.session.get(f"{self.BASE_URL}/shops.json", timeout=10)
            if r.status_code == 200:
                shops = r.json()
                if shops:
                    self.shop_id = shops[0]["id"]
                    print(f"✅ Printify authenticated. Shop: {shops[0].get('title')} (id={self.shop_id})")
                self.enabled = True
                return True
            print(f"❌ Printify auth failed: {r.status_code} {r.text[:200]}")
            return False
        except Exception as e:
            print(f"❌ Printify auth error: {e}")
            return False

    def upload_product(
        self,
        image: Image.Image,
        metadata: Dict[str, Any],
        product_type: str = "t-shirt",
        **kwargs
    ) -> UploadResult:
        """Create complete Printify product with variants and details."""
        try:
            buf = BytesIO()
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")
            image.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()

            title = metadata.get("title", "AI Art Design")
            description = metadata.get("description", "")
            tags = metadata.get("tags", [])
            blueprint_id = self.BLUEPRINTS.get(product_type.lower(), self.BLUEPRINTS["t-shirt"])
            print(f"Creating Printify product: {title[:40]}")
            # Step 1: Upload image to media library
            payload = {
                "file_name": f"{title[:40].replace(' ', '_')}.png",
                "url": f"data:image/png;base64,{img_b64}"
            }
            print("Uploading image to media library...")
            r = self.session.post(
                f"{self.BASE_URL}/uploads.json",
                json=payload,
                timeout=120
            )
            if r.status_code not in (200, 201):
                return UploadResult(success=False, error_message=f"Upload failed: {r.status_code}")
            upload_data = r.json()
            image_url = upload_data.get("src") or upload_data.get("url")
            print(f"Image uploaded to media library")
            # Step 2: Create product with blueprint and variants
            product_payload = {
                "title": title[:60],
                "description": description[:500],
                "tags": tags[:10],  # Max 10 tags
                "blueprint_id": blueprint_id,
                "is_visible": True,
                "print_files": [{"id": image_url}],
                "print_provider_id": 1  # Printify default
            }
            print("Creating product with blueprint...")
            r = self.session.post(
                f"{self.BASE_URL}/shops/{self.shop_id}/products.json",
                json=product_payload,
                timeout=120
            )
            if r.status_code in (200, 201):
                product = r.json()
                product_id = product.get("id")
                print(f"✅ Printify product created! ID: {product_id}")
                return UploadResult(
                    success=True,
                    product_id=str(product_id),
                    url=f"https://printify.com/shop/{self.shop_id}/products/{product_id}"
                )
            else:
                return UploadResult(success=False,
                    error_message=f"Product creation failed: {r.status_code} {r.text[:300]}")
        except Exception as e:
            return UploadResult(success=False, error_message=f"Printify error: {e}")
    def get_product_types(self) -> List[str]:
        return ["T-Shirt", "Stickers", "Posters", "Mugs", "Pins", "Tote Bags"]
    def get_listing_url(self, listing_id: str) -> str:
        return f"https://printify.com/products/{listing_id}"
    def get_platform_name(self) -> str:
        return "Printify"
