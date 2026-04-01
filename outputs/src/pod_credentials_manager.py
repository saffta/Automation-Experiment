#!/usr/bin/env python3
"""
POD Credentials Manager - .env Adapter
=======================================

Securely manages multiple POD platform profiles by dynamically 
reading from and writing to the root .env file.
"""

import os
import datetime
from pathlib import Path
from typing import Dict, Optional, List
from dotenv import load_dotenv, set_key, unset_key

class PODCredentialsManager:
    """Manages POD platform credentials seamlessly within the .env file"""
    
    def __init__(self):
        """Initialize credentials manager with root .env support"""
        # Get the root directory
        self.root_dir = Path(__file__).resolve().parent.parent.parent
        self.env_file = self.root_dir / ".env"
        
        # Ensure .env exists
        if not self.env_file.exists():
            self.env_file.touch()
            self._set("ACTIVE_POD_PROFILE", "default")
            self._set("POD_PROFILES", "default")
        else:
            load_dotenv(dotenv_path=self.env_file)
            if not os.getenv("ACTIVE_POD_PROFILE"):
                self._set("ACTIVE_POD_PROFILE", "default")
            if not os.getenv("POD_PROFILES"):
                self._set("POD_PROFILES", "default")
                
    def _set(self, key: str, value: str):
        """Helper to write to .env directly"""
        set_key(str(self.env_file), key, value)
        os.environ[key] = value

    def _unset(self, key: str):
        """Helper to remove a key from .env"""
        unset_key(str(self.env_file), key)
        if key in os.environ:
            del os.environ[key]
            
    def _get(self, key: str, default: str = "") -> str:
        """Helper to load dynamically"""
        load_dotenv(dotenv_path=self.env_file, override=True)
        return os.getenv(key, default)

    def list_profiles(self) -> List[str]:
        """List all profile names securely from .env"""
        profiles_str = self._get("POD_PROFILES", "default")
        return [p.strip() for p in profiles_str.split(",") if p.strip()]

    def add_profile(self, name: str):
        """Add a new empty profile variable into .env tracking string"""
        profiles = self.list_profiles()
        if name not in profiles:
            profiles.append(name)
            self._set("POD_PROFILES", ",".join(profiles))
            print(f"✅ Created profile in .env: {name}")

    def delete_profile(self, name: str):
        """Remove a profile tracking string"""
        profiles = self.list_profiles()
        if name in profiles and name != "default":
            profiles.remove(name)
            self._set("POD_PROFILES", ",".join(profiles))
            
            # Clean up active trace
            if self.get_active_profile() == name:
                self.set_active_profile("default")
                
            # Clean up all keys associated with this profile
            # Just loop a known set of platforms for cleanup.
            platforms = ["REDBUBBLE", "TEEPUBLIC", "PRINTFUL", "PRINTIFY", "ETSY"]
            for plat in platforms:
                prefix = f"{name.upper()}_{plat}"
                self._unset(f"{prefix}_EMAIL")
                self._unset(f"{prefix}_PASSWORD")
                self._unset(f"{prefix}_LAST_USED")
                
            print(f"🗑️ Deleted profile from .env: {name}")

    def get_active_profile(self) -> str:
        """Get the globally focused active profile"""
        return self._get("ACTIVE_POD_PROFILE", "default")

    def set_active_profile(self, name: str):
        """Set active profile directly into .env"""
        if name in self.list_profiles():
            self._set("ACTIVE_POD_PROFILE", name)
            print(f"🎯 Active profile tracking set to: {name}")

    def add_account(self, platform: str, username: str, password: str, profile: str = None, extra_data: Optional[Dict] = None):
        """Securely inject credentials formatted for multiple profiles directly into .env"""
        profile = profile or self.get_active_profile()
        self.add_profile(profile)
        
        prefix = f"{profile.upper()}_{platform.upper()}"
        self._set(f"{prefix}_EMAIL", username)
        self._set(f"{prefix}_PASSWORD", password)
        self._set(f"{prefix}_LAST_USED", str(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        print(f"✅ Updated .env account '{platform}' for profile '{profile}': {username}")
    
    def get_account(self, platform: str, profile: str = None) -> Optional[Dict]:
        """Fetch credentials from .env via the adapter"""
        profile = profile or self.get_active_profile()
        
        prefix = f"{profile.upper()}_{platform.upper()}"
        email = self._get(f"{prefix}_EMAIL")
        password = self._get(f"{prefix}_PASSWORD")
        last_used = self._get(f"{prefix}_LAST_USED", "Never")
        
        # Fallback to defaults without prefix if the specific one is missing 
        # (This is great backward compatibility behavior for simple standard defaults)
        if not email and profile == "default":
            email = self._get(f"{platform.upper()}_EMAIL")
            password = self._get(f"{platform.upper()}_PASSWORD")
            last_used = "Never"
            
        # For printful/printify API keys
        if platform.lower() in ["printful", "printify"] and not password:
            api_key = self._get(f"{prefix}_API_KEY")
            if not api_key and profile == "default": 
                 api_key = self._get(f"{platform.upper()}_API_KEY")
            if api_key:
                 return {
                    "username": "api_key",
                    "password": api_key,
                    "last_used": last_used,
                    "extra_data": {}
                 }
            
        if email and password:
            return {
                "username": email,
                "password": password,
                "extra_data": {},
                "last_used": last_used
            }
        
        return None
    
    def list_accounts(self, profile: str = None) -> List[Dict]:
        """Scan known platforms to summarize registered configuration inside .env"""
        profile = profile or self.get_active_profile()
        
        platforms = ["redbubble", "teepublic", "printful", "printify", "etsy"]
        accounts = []
        
        for p in platforms:
            acc = self.get_account(p, profile)
            if acc:
                accounts.append({
                    "platform": p,
                    "username": acc.get("username", "Unknown"),
                    "last_used": acc.get("last_used", "Never"),
                    "added_at": "N/A" # .env does not cleanly track this specific stat
                })
        
        return accounts
    
    def delete_account(self, platform: str, profile: str = None) -> bool:
        """Revoke variables corresponding to an account inside .env"""
        profile = profile or self.get_active_profile()
        prefix = f"{profile.upper()}_{platform.upper()}"
        
        if self._get(f"{prefix}_EMAIL") or self._get(f"{prefix}_PASSWORD") or self._get(f"{prefix}_API_KEY"):
             self._unset(f"{prefix}_EMAIL")
             self._unset(f"{prefix}_PASSWORD")
             self._unset(f"{prefix}_API_KEY")
             self._unset(f"{prefix}_LAST_USED")
             print(f"🗑️ Deleted {platform} account keys from .env profile '{profile}'")
             return True
             
        return False
    
    def update_last_used(self, platform: str, profile: str = None):
        """Update last tracked timestamp locally within .env"""
        profile = profile or self.get_active_profile()
        prefix = f"{profile.upper()}_{platform.upper()}"
        
        if self.get_account(platform, profile):
            self._set(f"{prefix}_LAST_USED", str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


if __name__ == "__main__":
    manager = PODCredentialsManager()
    
    # Test adding accounts
    manager.add_account(
        "redbubble",
        "test_env_adapter@example.com",
        "secure_env_password_123",
        profile="mystore"
    )
    
    # List accounts
    print(f"\n📋 Stored .env Accounts mapped to '{manager.get_active_profile()}':")
    for account in manager.list_accounts():
        print(f"   • {account['platform']}: {account['username']}")
    
    # Get specific account
    print("\n🔑 Redbubble Account (mystore):")
    rb_account = manager.get_account("redbubble", profile="mystore")
    if rb_account:
        print(f"   Username: {rb_account['username']}")
        print(f"   Password: {'*' * len(rb_account['password'])}")
