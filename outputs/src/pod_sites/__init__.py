#!/usr/bin/env python3
"""
POD Sites Package
"""

import importlib
from typing import Optional
from .base import PODPlatform, UploadResult


def create_platform(platform_name: str) -> Optional[PODPlatform]:
    """
    Factory: returns platform instance or None on any error.
    Note: 'teepublic' and 'redbubble' are primarily automated via specialized external bots.
    """
    platform_map = {
        "printful":           ("printful_full",            "PrintfulFullPlatform"),
        "printify":           ("printify_full",            "PrintifyFullPlatform"),
    }

    entry = platform_map.get(platform_name.lower())
    if not entry:
        print(f"Unknown platform: {platform_name}")
        return None

    module_name, class_name = entry
    try:
        module = importlib.import_module(f".{module_name}", package="pod_sites")
        cls = getattr(module, class_name, None)
        if cls:
            return cls()
        print(f"Class {class_name} not found in {module_name}")
        return None
    except Exception as e:
        print(f"Error loading {platform_name}: {e}")
        return None


__all__ = ["PODPlatform", "UploadResult", "create_platform"]
