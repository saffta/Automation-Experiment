import json
import time
import os
from botasaurus.browser import browser, Wait
from botasaurus_driver import Driver

COOKIE_FILE = 'redbubble_cookies.json'

@browser(
    headless=False,
    profile="redbubble_profile",
    add_arguments=[
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ],
)
def manual_login_and_fetch_cookies(driver: Driver, data):
    print("Opening Redbubble. Please log in manually in the opened browser window.")
    driver.get("https://www.redbubble.com/auth/login")
    
    # Wait until user navigates away from the login page, meaning successful login
    print("\n" + "="*50)
    print("⏳ Waiting for you to log in...")
    print("Once logged in, this script will automatically capture and save your cookies.")
    print("="*50 + "\n")
    
    for i in range(300): # 5 minutes max wait
        current_url = driver.current_url
        if "login" not in current_url and "auth" not in current_url:
            print("✅ Detected login success! Capturing cookies...")
            time.sleep(5)  # Let cookies settle
            break
        time.sleep(1)
        if i % 30 == 0 and i > 0:
            print(f"Still waiting... ({i}/300 seconds)")
    
    # Use CDP to fetch ALL cookies accurately across domains (including HTTP-only)
    try:
        cookies_response = driver.run_cdp_command("Network.getAllCookies", {})
        cookies = cookies_response.get("cookies", [])
    except Exception as e:
        print(f"Failed to use CDP: {e}. Falling back to standard method.")
        cookies = driver.get_cookies()
    
    if cookies:
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f, indent=4)
        print(f"🍪 Successfully saved {len(cookies)} cookies to {COOKIE_FILE}!")
        print("\nYou can now run the main redbubble_bot.py script. It will use these cookies.")
    else:
        print("❌ Failed to fetch cookies. The list is empty.")
    
    return True

if __name__ == "__main__":
    manual_login_and_fetch_cookies()
