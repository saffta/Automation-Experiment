#!/usr/bin/env python3
"""
Base class for POD platform integrations
"""

import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from PIL import Image
from dataclasses import dataclass
from datetime import datetime

@dataclass
class UploadResult:
    """Result of upload attempt"""
    success: bool
    product_id: Optional[str] = None
    listing_id: Optional[str] = None
    url: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict] = None

class PODPlatform(ABC):
    """
    Abstract base class for POD platform integrations
    """
    
    def __init__(self):
        self.enabled = False
        self.api_config = {}
        self.session_id = None
        self.logger = None
    
    @abstractmethod
    def authenticate(self, credentials: Dict[str, str]) -> bool:
        """
        Authenticate with platform
        
        Args:
            credentials: Platform-specific credentials
            
        Returns:
            bool: True if authentication successful
        """
        pass
    
    @abstractmethod
    def upload_product(
        self,
        image: Image.Image,
        metadata: Dict[str, Any],
        product_type: str = "t-shirt",
        **kwargs
    ) -> UploadResult:
        """
        Upload image as product to platform
        
        Args:
            image: PIL Image object
            metadata: Listing metadata (title, description, tags)
            product_type: Type of product to upload
            **kwargs: Additional platform-specific options
            
        Returns:
            UploadResult: Result of upload attempt
        """
        pass
    
    @abstractmethod
    def get_product_types(self) -> List[str]:
        """
        Get list of available product types for platform
        
        Returns:
            List of product type names
        """
        pass
    
    @abstractmethod
    def get_listing_url(self, listing_id: str) -> str:
        """
        Get public URL for listing
        
        Args:
            listing_id: Platform-specific listing ID
            
        Returns:
            str: Public URL for listing
        """
        pass
    
    @abstractmethod
    def get_platform_name(self) -> str:
        """
        Get platform name
        
        Returns:
            str: Platform name
        """
        pass
    
    def validate_metadata(self, metadata: Dict) -> Tuple[bool, List[str]]:
        """
        Validate metadata before upload
        
        Args:
            metadata: Listing metadata
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check required fields
        if not metadata.get("title"):
            errors.append("Title is required")
        
        if not metadata.get("description"):
            errors.append("Description is required")
        
        if not metadata.get("tags") or len(metadata["tags"]) == 0:
            errors.append("At least one tag is required")
        
        # Check length limits
        title = metadata.get("title", "")
        if len(title) > 100:
            errors.append(f"Title too long: {len(title)} characters (max 100)")
        
        tags = metadata.get("tags", [])
        if len(tags) > 50:
            errors.append(f"Too many tags: {len(tags)} (max 50)")
        
        return len(errors) == 0, errors
    
    def save_upload_log(self, result: UploadResult, metadata: Dict, output_dir: str) -> str:
        """
        Save upload result to log file
        
        Args:
            result: UploadResult object
            metadata: Original metadata
            output_dir: Directory to save logs
            
        Returns:
            str: Path to log file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"upload_log_{timestamp}.json"
        filepath = os.path.join(output_dir, filename)
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "platform": self.get_platform_name(),
            "success": result.success,
            "product_id": result.product_id,
            "listing_id": result.listing_id,
            "url": result.url,
            "error_message": result.error_message,
            "metadata": metadata,
            "result_metadata": result.metadata
        }
        
        import json
        with open(filepath, "w") as f:
            json.dump(log_entry, f, indent=2)
        
        return filepath


def create_platform(platform_name: str) -> Optional[PODPlatform]:
    """
    Factory function to create platform instance
    
    Args:
        platform_name: Name of platform (printful, printify, redbubble, teepublic)
        
    Returns:
        PODPlatform instance or None
    """
    platform_map = {
        "printful": "printful",
        "printify": "printify",
        "redbubble": "redbubble",
        "teepublic": "teepublic"
    }
    
    module_name = platform_map.get(platform_name.lower())
    if not module_name:
        return None
    
    try:
        module = __import__(
            f"{platform_name}",
            fromlist=[module_name]
        )
        return getattr(module, module_name.capitalize() + "Platform")()
    except ImportError:
        return None
