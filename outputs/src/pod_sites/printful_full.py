#!/usr/bin/env python3
"""Printful Full Product Creation - Complete Product Listing Automation


This module creates complete Printful products:
1. Upload image to file library
2. Create product with blueprint
3. Set variants (sizes, colors)
4. Add title, description
"""

import base64
import requests
from typing import Dict, List, Optional, Any
from PIL import Image
from io import BytesIO


from .base import PODPlatform, UploadResult


class PrintfulFullPlatform(PODPlatform):
    """Printful API v2 integration with full product creation"""

    BASE_URL = "https://api.printful.com"

    # Blueprint IDs for common products
    BLUEPRINTS = {
        "t-shirt": 35,
        "poster": 40,
        "mug": 7,
        "sticker": 81,
        "tote-bag": 23,
        "hoodie": 37
    }

    def __init__(self):
        super().__init__()
        self.api_key = None
        self.store_id = None
        self.session = requests.Session()


    def authenticate(self, credentials: Dict[str, str]) -> bool:
        self.api_key = credentials.get("api_key") or credentials.get("password")
        if not self.api_key:
            print("❌ Printful: API key required")
            return False

        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

        try:
            r = self.session.get(f"{self.BASE_URL}/v2/stores", timeout=10)
            if r.status_code == 200:
                stores = r.json().get("data", [])
                if stores:
                    self.store_id = stores[0]["id"]
                    print(f"✅ Printful authenticated. Store: {stores[0].get('name')} (id={self.store_id})")
                self.enabled = True
                return True
            print(f"❌ Printful auth failed: {r.status_code} {r.text[:200]}")
            return False
        except Exception as e:
            print(f"❌ Printful auth error: {e}")
            return False

    def upload_product(
        self,
        image: Image.Image,
        metadata: Dict[str, Any],
        product_type: str = "t-shirt",
        **kwargs
    ) -> UploadResult:
        """Create complete Printful product with variants and details."""
        if not self.store_id:
            return UploadResult(success=False,
                error_message="Printful store not configured. Please create a store at app.printful.com")

        try:
            buf = BytesIO()
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            image.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()

            title = metadata.get("title", "AI Art Design")
            description = metadata.get("description", "")
            tags = metadata.get("tags", [])
            blueprint_id = self.BLUEPRINTS.get(product_type.lower(), self.BLUEPRINTS["t-shirt"])

            print(f"Creating Printful product: {title[:40]}")

            # Step 1: Upload image to file library
            file_payload = {
                "type": "default",
                "url": f"data:image/png;base64,{img_b64}",
                "filename": f"{title[:40].replace(' ', '_')}.png"
            }
            print("Uploading image to file library...")
            r = self.session.post(
                f"{self.BASE_URL}/files?store_id={self.store_id}",
                json=file_payload,
                timeout=120
            )
            if r.status_code not in (200, 201):
                return UploadResult(success=False, error_message=f"File upload failed: {r.status_code}")
            file_data = r.json().get("result", r.json())
            file_id = file_data.get("id")
            print(f"File uploaded: {file_id}")

            # Step 2: Create product with blueprint and variants
            product_payload = {
                "sync_product": {
                    "name": title[:60],
                    "description": description[:500],
                    "variants": [
                        {
                            "id": str(blueprint_id),
                            "files": [{"id": file_id}],
                            "is_enabled": True,
                            "options": [
                                {"id": "size", "value": "M"},
                                {"id": "color", "value": "Black"}
                            ]
                        },
                        {
                            "id": str(blueprint_id),
                            "files": [{"id": file_id}],
                            "is_enabled": True,
                            "options": [
                                {"id": "size", "value": "L"},
                                {"id": "color", "value": "White"}
                            ]
                        }
                    ],
                    "tags": tags[:10]  # Max 10 tags
                }
            }
            print("Creating product with variants...")
            r = self.session.post(
                f"{self.BASE_URL}/products?store_id={self.store_id}",
                json=product_payload,
                timeout=120
            )
            if r.status_code in (200, 201):
                product = r.json().get("result", {})
                product_id = product.get("sync_product_id", product.get("id"))
                print(f"✅ Printful product created! ID: {product_id}")
                return UploadResult(
                    success=True,
                    product_id=str(product_id),
                    url=f"https://app.printful.com/store/{self.store_id}/products/{product_id}"
                )
            else:
                return UploadResult(success=False,
                    error_message=f"Product creation failed: {r.status_code} {r.text[:300]}")

        except Exception as e:
            return UploadResult(success=False, error_message=f"Printful error: {e}")

    def get_product_types(self) -> List[str]:
        return ["t-shirt", "poster", "mug", "sticker", "tote-bag", "hoodie"]

    def get_listing_url(self, listing_id: str) -> str:
        return f"https://app.printful.com/products/{listing_id}"

    def get_platform_name(self) -> str:
        return "Printful"
