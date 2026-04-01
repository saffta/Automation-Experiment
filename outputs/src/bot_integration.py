#!/usr/bin/env python3
import sys
import os
from pathlib import Path
from typing import List, Dict, Any

# Add the bot directories to path
PROJECT_ROOT = Path(__file__).parent.parent
RB_DIR = PROJECT_ROOT.parent / "Redbubble-Bot"
TP_DIR = PROJECT_ROOT.parent / "Teepublic-Bot"

def upload_redbubble(image_path: str, title: str, tags: List[str], description: str, primary_tag: str, credentials: Dict[str, str], profile_path: str = None, headless: bool = True):
    """Call the specialized Redbubble bot."""
    try:
        # Target the unified main folder
        target_dir = str(RB_DIR)
        
        # Ensure the directory is in sys.path
        if target_dir not in sys.path:
            sys.path.insert(0, target_dir)
            
        # Set the HEADLESS env var for the bot's @browser decorator
        os.environ['HEADLESS'] = 'true' if headless else 'false'
        
        # Clear previous import if it exists to avoid caching issues
        if 'redbubble_bot' in sys.modules:
            del sys.modules['redbubble_bot']
            
        from redbubble_bot import login_and_upload
        
        # Prepare work data
        work_data = {
            'email': credentials.get('username'),
            'password': credentials.get('password'),
            'image_path': image_path,
            'title': title,
            'primary_tag': primary_tag,
            'tags': tags,
            'description': description,
            'profile_path': profile_path,
            'headless': headless
        }
        
        result = login_and_upload(work_data)
        return result
    except Exception as e:
        print(f"❌ Redbubble bot integration error: {e}")
        return False

def upload_teepublic(image_path: str, title: str, tags: List[str], description: str, primary_tag: str, credentials: Dict[str, str], headless: bool = True):
    """Call the specialized TeePublic bot."""
    try:
        if str(TP_DIR) not in sys.path:
            sys.path.insert(0, str(TP_DIR))
            
        # Set environment variable so the @browser decorator picks it up
        os.environ['HEADLESS'] = 'true' if headless else 'false'
        
        # Clear previous import if it exists to avoid caching issues
        if 'TE_BOTASAURUS_ULTIMATE' in sys.modules:
            del sys.modules['TE_BOTASAURUS_ULTIMATE']
            
        from TE_BOTASAURUS_ULTIMATE import main_task
        
        # Prepare data for main_task
        work_data = {
            'images': [image_path],
            'metadata': {
                os.path.basename(image_path): {
                    'title': title,
                    'description': description,
                    'primary_tag': primary_tag,
                    'tags': tags
                }
            },
            'credentials': {
                'email': credentials.get('username'),
                'password': credentials.get('password')
            },
            'headless': headless
        }
        
        # Trigger the bot
        result = main_task(work_data)
        return result
    except Exception as e:
        print(f"❌ TeePublic bot integration error: {e}")
        return False
