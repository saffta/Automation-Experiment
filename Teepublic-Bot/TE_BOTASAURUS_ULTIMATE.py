import os
import sys
import json
import time
import random
import glob
from botasaurus.browser import browser, Wait
from botasaurus_driver import Driver
from dotenv import load_dotenv

# Load environment variables from the root .env file
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(root_dir, '.env')
load_dotenv(dotenv_path=env_path)

# CONFIGURATION
EMAIL = os.getenv("TEEPUBLIC_EMAIL")
PASSWORD = os.getenv("TEEPUBLIC_PASSWORD")
BASE_URL = "https://www.teepublic.com"
LOGIN_URL = f"{BASE_URL}/users/sign_in"
UPLOAD_URL = f"{BASE_URL}/design/quick_create"
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")

def accept_cookies(driver):
    """Accept Cookiebot banner if present"""
    try:
        # Check for Cookiebot button
        btn = driver.select('#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll, .allow-all', wait=Wait.SHORT)
        if btn:
            print("🍪 Accepting Cookiebot banner...")
            btn.click()
            time.sleep(2)
    except:
        pass

def is_on_login_page(driver):
    """Check if we are logged in by looking for Account menu vs Login link"""
    # If the page has "Account" or "Profile", we are likely logged in.
    # If it has "Log In", "Sign In", or "Create Account" prominently, we are not.
    has_account = driver.is_element_present('a[href*="/account"], .account-dropdown, #account-menu')
    is_on_signin_url = "/users/sign_in" in driver.current_url or "/login" in driver.current_url
    
    return is_on_signin_url or not has_account

def login_if_needed(driver):
    """Handle login flow"""
    print(f"🔐 Checking authentication at {LOGIN_URL}...")
    driver.get(LOGIN_URL)
    time.sleep(5)
    
    accept_cookies(driver)

    if is_on_login_page(driver):
        print("🔑 Login page detected. Starting login flow...")
        
        # Check if email field exists (sometimes it's a 'Sign In' button first)
        email_selector = 'input[name="email"], input[name="user[email]"], #user_email'
        if not driver.is_element_present(email_selector):
            print("   (Wait for login form to appear...)")
            # Try clicking a 'Sign In' tab if present
            signin_tab = driver.select('a:contains("Log In"), .login-tab', wait=Wait.SHORT)
            if signin_tab: signin_tab.click(); time.sleep(2)

        email_field = driver.select(email_selector, wait=Wait.LONG)
        if email_field:
            email_field.type(EMAIL)
            time.sleep(random.uniform(0.5, 1.0))
            
            # Fill password
            pass_field = driver.select('input[name="password"], input[name="user[password]"], #user_password', wait=Wait.SHORT)
            pass_field.type(PASSWORD)
            time.sleep(random.uniform(1.0, 2.0))
            
            # Click login
            login_btn = driver.select('button[type="submit"], input[type="submit"], .signin-button', wait=Wait.SHORT)
            login_btn.click()
            
            print("⏳ Waiting for login success...")
            time.sleep(10)
            
            if not is_on_login_page(driver):
                print(f"✅ Login successful! Landed on: {driver.current_url}")
                return True
            else:
                print("❌ Still on login page. CAPTCHA might be present.")
                driver.save_screenshot("login_failed.png")
                return False
        else:
            print("❌ Could not find login fields.")
            return False
    else:
        print("✅ Already logged in (Account menu found).")
        return True

def upload_and_publish(driver, image_path, metadata):
    """Perform the upload and publish workflow for one image"""
    print(f"\n{'='*60}")
    print(f"📤 Processing: {os.path.basename(image_path)}")
    title = metadata.get('title', 'Untitled')
    print(f"   Target Title: {title}")
    print(f"{'='*60}")

    try:
        # 0. Navigation
        print(f"🚀 Navigating to {UPLOAD_URL}...")
        
        # Ensure screenshot directory exists
        current_dir = os.path.dirname(os.path.abspath(__file__))
        screenshot_dir = os.path.join(current_dir, "output", "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        
        ts_nav = int(time.time())
        driver.save_screenshot(os.path.join(screenshot_dir, f"before_funnel_{ts_nav}.png"))
        
        driver.get(UPLOAD_URL)
        time.sleep(5)
        
        accept_cookies(driver)

        # Click "Single File Upload" if we are on the selection page
        driver.save_screenshot("before_funnel_click.png")
        
        # Check if we are on the "Select Your Upload Type" page
        is_funnel = driver.is_element_present('.m-uploader-funnel') or driver.is_element_present(':contains("Select Your Upload Type")')
        
        if is_funnel:
            print("🎯 Selection funnel detected. Looking for 'Single File Upload'...")
            time.sleep(2) # Stabilize DOM
            
            selectors = [
                '.m-uploader-funnel__option-h:contains("Single File Upload")',
                '.m-uploader-funnel__option-text:contains("Single File Upload")',
                'h3:contains("Single File Upload")',
                '.m-uploader-funnel__option'
            ]
            
            clicked = False
            for selector in selectors:
                try:
                    btn = driver.select(selector, wait=Wait.SHORT)
                    if btn:
                        print(f"   Clicking '{selector}'...")
                        driver.run_js(f"document.querySelector('{selector}')?.scrollIntoView({{block: 'center'}})")
                        time.sleep(1)
                        btn.click()
                        clicked = True
                        break
                except:
                    continue
            
            if not clicked:
                print("⚠️ Selectors failed. Forcing funnel selection via JS...")
                # TeePublic funnel options often map to a specific form or action
                driver.run_js("""
                    (function() {
                        const options = Array.from(document.querySelectorAll('.m-uploader-funnel__option, .m-uploader-funnel__option-text, h3'));
                        const singleOpt = options.find(o => o.textContent.toLowerCase().includes('single file'));
                        if (singleOpt) {
                            singleOpt.click();
                            // Fallback to internal TP event if needed
                            const parent = singleOpt.closest('.m-uploader-funnel__option');
                            if (parent) parent.click();
                        } else {
                            // Last resort: navigate directly if we can guess the URL or trigger the default action
                            const getStarted = document.querySelector('.jsBulkUploaderSubmit');
                            if (getStarted) getStarted.click();
                        }
                    })();
                """)
                time.sleep(5)
        else:
            print("ℹ️ Not on funnel page or already bypassed.")

        # 2. Upload file
        print("📁 Finding file input...")
        # Try multiple common selectors for TeePublic
        input_selectors = [
            'input[type="file"]',
            '#design_artwork',
            'input[name="design[artwork]"]',
            '.uploader-file-input'
        ]
        
        target_input = None
        for sel in input_selectors:
            if driver.is_element_present(sel):
                target_input = sel
                print(f"✅ Found file input with selector: {sel}")
                break
        
        if not target_input:
            print("❌ Could not find file input element.")
            driver.save_screenshot("upload_page_missing_input.png")
            return False

        abs_path = os.path.abspath(image_path)
        driver.upload_file(target_input, abs_path)
        
        print("⏳ File uploaded. Waiting for processing UI to populate metadata fields...")
        # TeePublic's quick_create usually starts processing and reveals metadata fields
        # once the file is selected. No 'Get Started' button is needed here.
        
        ts = int(time.time())
        driver.save_screenshot(os.path.join(screenshot_dir, f"after_upload_{ts}.png"))
        
        # --- NEW: Check for flash-notice-red errors immediately after upload (e.g., resolution error) ---
        # Only treat it as an error if it's visible AND contains actual numbers (for resolution error) or other content
        is_error_visible = driver.run_js("""
            const el = document.querySelector('#flash-notice-red');
            if (!el) return false;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
            
            const text = el.innerText.trim();
            if (text.length < 5) return false;
            
            // If it's the resolution error, check if the specific width/height numbers are populated
            if (text.includes('Your artwork is') && text.includes('not large enough')) {
                const w = document.querySelector('#jsSizeErrorWidth')?.innerText.trim();
                const h = document.querySelector('#jsSizeErrorHeight')?.innerText.trim();
                if (!w || !h) return false; // Not fully loaded or empty
            }
            
            return true;
        """)
        
        if is_error_visible:
            error_text = driver.run_js("return document.querySelector('#flash-notice-red')?.innerText || ''")
            print(f"❌ Upload Error Detected: {error_text.strip()}")
            driver.save_screenshot(os.path.join(screenshot_dir, f"error_{ts}.png"))
            return False
            
        title_selector = 'input[name="design[title]"], input[name="design[design_title]"]'
        
        # Wait up to 60s for the form to populate
        success = False
        for i in range(20):
            time.sleep(3)
            if driver.is_element_present(title_selector):
                print("✅ Processing started! Form fields are visible.")
                success = True
                break
            print(f"   Waiting... ({i*3}s)")
        
        if not success:
            print("❌ Form fields did not appear.")
            return False

        # Helper for robust typing
        def robust_type(selector, value, press_enter=False):
            el = driver.select(selector, wait=Wait.SHORT)
            if el:
                print(f"   Typing '{value}' into {selector}...")
                driver.run_js(f"document.querySelector('{selector}')?.scrollIntoView({{block: 'center'}})")
                time.sleep(0.5)
                el.type(value)
                time.sleep(0.5)
                if press_enter:
                    # Generic Enter keypress using selector in JS to avoid serialization error
                    js_enter = f"""
                        (function() {{
                            const element = document.querySelector('{selector}');
                            if (element) {{
                                ['keydown', 'keypress', 'keyup'].forEach(type => {{
                                    element.dispatchEvent(new KeyboardEvent(type, {{
                                        bubbles: true, cancelable: true, keyCode: 13, key: 'Enter', which: 13
                                    }}));
                                }});
                            }}
                        }})();
                    """
                    driver.run_js(js_enter)
                return True
            return False

        # 3. Fill Metadata
        print("📝 Filling metadata...")
        robust_type(title_selector, title)
        time.sleep(1)

        desc_selector = 'textarea[name*="description"], #design_description'
        robust_type(desc_selector, metadata.get('description', ''))
        time.sleep(1)

        # Tags - Main Tag (CRITICAL: Needs to be selected from autocomplete)
        print(f"🏷️ Entering Main Tag: {metadata.get('primary_tag', 'test')}...")
        primary_tag_selector = 'input[name$="[primary_tag]"], #design_primary_tag'
        pt_field = driver.select(primary_tag_selector, wait=Wait.SHORT)
        if pt_field:
            driver.run_js(f"document.querySelector('{primary_tag_selector}')?.scrollIntoView({{block: 'center'}})")
            pt_field.type(metadata.get('primary_tag', 'test'))
            time.sleep(4) # Wait for autocomplete results
            
            # Try to click the first autocomplete result if it appeared
            # TeePublic often uses a list for autocomplete
            dropdown_item = driver.select('.autocomplete-results li, .ui-menu-item, .tt-suggestion, .easy-autocomplete-container li', wait=Wait.SHORT)
            if dropdown_item:
                print("   Found autocomplete result, clicking...")
                dropdown_item.click()
            else:
                print("   No autocomplete dropdown found, forcing Enter and blur...")
                driver.run_js(f"""
                    const el = document.querySelector('{primary_tag_selector}');
                    if (el) {{
                        ['keydown', 'keypress', 'keyup'].forEach(t => {{
                            el.dispatchEvent(new KeyboardEvent(t, {{ bubbles: true, keyCode: 13, key: 'Enter', which: 13 }}));
                        }});
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                    }}
                """)
        
        time.sleep(5) # Wait for supporting tags to unlock
        
        # 🎨 Color Selection (Black/White based on title/design)
        print("🎨 Selecting default product colors (Targeting swatches and dropdowns)...")
        driver.run_js("""
            (function() {
                // 1. Direct Swatches
                const sections = document.querySelectorAll('.m-uploader-form-section, .js-configurator-section');
                sections.forEach(section => {
                    const swatches = Array.from(section.querySelectorAll('.m-swatch, .js-swatch, .color-swatch'));
                    if (swatches.length > 0) {
                        const black = swatches.find(s => s.title?.toLowerCase().includes('black') || s.getAttribute('data-color-name')?.toLowerCase() === 'black');
                        if (black) black.click();
                        else swatches[0].click();
                    }
                });
                
                // 2. Dropdowns (dd-selected / dd-container pattern)
                const ddContainers = document.querySelectorAll('.dd-container, .dd-selected');
                ddContainers.forEach(container => {
                    const parent = container.closest('.dd-container') || container.parentElement;
                    const options = Array.from(parent?.querySelectorAll('.dd-option') || []);
                    const blackOpt = options.find(o => o.textContent.toLowerCase().includes('black') || (o.getAttribute('data-color-name') || "").toLowerCase().includes('black'));
                    
                    if (blackOpt) {
                        blackOpt.click();
                    } else {
                        // Open first
                        const trigger = container.querySelector('.dd-selected') || container;
                        if (trigger) {
                            trigger.click();
                            setTimeout(() => {
                                const opt = Array.from(document.querySelectorAll('.dd-option'))
                                    .find(o => o.textContent.toLowerCase().includes('black'));
                                if (opt) opt.click();
                            }, 500);
                        }
                    }
                });

                // 3. Fallback for specific products
                const products = ['phone', 'mug', 'pillow', 'pin', 'sock', 'tote', 'hat', 'short', 'bag'];
                products.forEach(p => {
                    const sections = Array.from(document.querySelectorAll('.dd-container, .m-uploader-form-section'));
                    const productSection = sections.find(el => el.textContent.toLowerCase().includes(p));
                    if (productSection) {
                        const swatches = Array.from(productSection.querySelectorAll('.m-swatch, .dd-option'));
                        const black = swatches.find(s => (s.title || "").toLowerCase().includes('black') || s.textContent.toLowerCase().includes('black'));
                        if (black) black.click();
                    }
                });
            })();
        """)
        time.sleep(3)

        # Mature Content -> NO
        print("🔞 Setting Mature Content to 'No'...")
        driver.run_js("""
            (function() {
                // Try clicking the specific 'No' label or radio
                const labels = Array.from(document.querySelectorAll('label'));
                const noLabel = labels.find(l => l.textContent.trim().toLowerCase() === 'no' || (l.textContent.trim().toLowerCase() === 'no' && l.closest('.m-uploader-form-section')));
                if (noLabel) {
                    noLabel.click();
                } else {
                    const noRadio = Array.from(document.querySelectorAll('input[type="radio"]'))
                        .find(r => r.value === 'false' || r.id?.toLowerCase().includes('false'));
                    if (noRadio) noRadio.click();
                }
            })();
        """)
        time.sleep(1)

        # ⚖️ Marking policies
        print("⚖️ Marking policies...")
        driver.run_js("""
            const cbs = document.querySelectorAll('input[type="checkbox"]');
            cbs.forEach(cb => {
                if (!cb.checked) {
                    cb.click();
                    cb.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        """)
        time.sleep(1)

        # 🏷️ Supporting Tags (Moved after color/mature to prevent clearing)
        print("🏷️ Entering Supporting Tags (Confirmed Native Loop)...")
        primary_tag = metadata.get('primary_tag', 'test').lower()
        tags = metadata.get('tags', metadata.get('secondary_tags', []))
        if not tags or len(tags) < 1:
            tags = ["art", "design", "creative"] # Force at least one
            
        tags_list = tags if isinstance(tags, list) else [t.strip() for t in tags.split(',')]
        
        # Omit primary tag from secondary tags list
        tags_list = [t for t in tags_list if t.lower() != primary_tag]

        # Unlock and clear first via JS
        driver.run_js("""
            const container = document.querySelector('#secondary_tags');
            const input = container?.querySelector('.taggle_input');
            if (input) {
                input.disabled = false;
                input.readOnly = false;
                input.value = '';
                // Clear existing
                container.querySelectorAll('.taggle_tag').forEach(t => t.querySelector('.taggle_tag_close')?.click());
            }
        """)
        time.sleep(1)

        # Native typing loop with comma + space + Enter
        for tag in tags_list:
            tag_input = driver.select('#secondary_tags .taggle_input, .taggle_input', wait=Wait.SHORT)
            if tag_input:
                print(f"   Typing tag: {tag}...")
                tag_input.type(tag + ", ") # Type tag AND the comma + space
                time.sleep(0.5)
                # Press Enter as extra confirmation
                driver.run_js("""
                    const el = document.querySelector('#secondary_tags .taggle_input, .taggle_input');
                    if (el) {
                        el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, keyCode: 13, key: 'Enter', which: 13 }));
                    }
                """)
                time.sleep(0.3)
            else:
                print("   ⚠️ Taggle input lost, retrying search...")
                
        time.sleep(2)

        # 5. Publish
        print("🚀 Publishing (targeting form button)...")
        # Try finding the PUBLISH button specifically by text and color if possible
        publish_selectors = [
            'button.js-submit-design-form',
            '#publish_design',
            '.m-uploader-form button[type="submit"]',
            'button:contains("PUBLISH")',
            'input[value="PUBLISH"]',
            'button.btn--green.btn--big'
        ]
        
        published = False
        for sel in publish_selectors:
            try:
                btn = driver.select(sel, wait=Wait.SHORT)
                if btn:
                    # Final check: is it the primary green button in the main area?
                    is_in_header = driver.run_js(f"return !!document.querySelector('{sel}')?.closest('header, .header, #header')")
                    if is_in_header:
                        continue
                        
                    print(f"🖱️ Clicking Publish button: {sel}")
                    driver.run_js(f"document.querySelector('{sel}')?.scrollIntoView({{block: 'center'}})")
                    time.sleep(1)
                    btn.click()
                    published = True
                    break
            except:
                continue

        if not published:
            print("⚠️ Falling back to JS click on button containing 'PUBLISH'...")
            driver.run_js("""
                const btns = Array.from(document.querySelectorAll('button, input[type="submit"]'));
                const publishBtn = btns.find(b => {
                    const text = (b.textContent || b.value || "").toUpperCase();
                    return text.includes('PUBLISH') && !b.closest('header, .header, #header');
                });
                if (publishBtn) publishBtn.click();
                else {
                    const form = document.querySelector('form[action*="/designs"]');
                    if (form) form.submit();
                }
            """)
            published = True

        # 6. Verify
        print("⏳ Verifying...")
        time.sleep(15)
        final_url = driver.current_url
        print(f"🔗 Final URL: {final_url}")
        
        # Check for final post-publish flash errors
        # Only treat it as an error if it's visible and meaningful
        is_final_error_visible = driver.run_js("""
            const el = document.querySelector('#flash-notice-red');
            if (!el) return false;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
            
            const text = el.innerText.trim();
            if (text.length < 5) return false;
            
            // If it's the resolution error, check if the specific width/height numbers are populated
            if (text.includes('Your artwork is') && text.includes('not large enough')) {
                const w = document.querySelector('#jsSizeErrorWidth')?.innerText.trim();
                const h = document.querySelector('#jsSizeErrorHeight')?.innerText.trim();
                if (!w || !h) return false;
            }
            
            return true;
        """)
        
        if is_final_error_visible:
            error_text = driver.run_js("return document.querySelector('#flash-notice-red')?.innerText || ''")
            print(f"❌ Post-Publish Error Detected: {error_text.strip()}")
            driver.save_screenshot(os.path.join(screenshot_dir, f"publish_error_{int(time.time())}.png"))
            return False

        # Success if we are on a product page AND not on edit page
        is_edit_page = "/edit" in final_url or "/designs/" in final_url and final_url.endswith("/edit")
        success_patterns = ["/t-shirt/", "/mug/", "/sticker/", "/case/", "/pillow/", "/mask/", "/poster/", "/tote/", "/wall-art/"]
        
        if any(pattern in final_url for pattern in success_patterns) and not is_edit_page:
            print("🎉 SUCCESS! Product URL generated.")
            driver.save_screenshot(f"success_{int(time.time())}.png")
            return True
        else:
            if is_edit_page:
                print("❌ FAILED: Still on edit page after publishing. Check for form errors.")
            else:
                print("⚠️ Status unclear. Final URL does not match known product patterns.")
            driver.save_screenshot(f"check_{int(time.time())}.png")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        driver.save_screenshot("error.png")
        return False

@browser(
    headless=os.environ.get('HEADLESS', 'false').lower() == 'true',
    close_on_crash=False,
    profile="teepublic_profile",
    add_arguments=[
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        "--disable-software-rasterizer",
    ]
)
def main_task(driver: Driver, data):
    print("🚀 Starting TeePublic Ultimate Uploader...")
    driver.enable_human_mode()
    
    if login_if_needed(driver):
        image_files = data.get('images', [])
        metadata_config = data.get('metadata', {})
        
        for img_path in image_files:
            img_name = os.path.basename(img_path)
            
            # Prepare metadata for a test image
            if img_name == "test_massive.png":
                meta = {
                    "title": "Test Massive High Res",
                    "description": "A test upload with massive resolution.",
                    "primary_tag": "test",
                    "tags": ["test", "highres", "massive"]
                }
            else:
                meta = metadata_config.get(img_name, {
                    "title": img_name.split('.')[0].replace('_', ' ').title(),
                    "description": "Amazing AI Design",
                    "primary_tag": "test",
                    "tags": ["art", "digital"]
                })
            
            success = upload_and_publish(driver, img_path, meta)
            if success:
                print(f"✅ Finished: {img_name}")
                return True
            else:
                print(f"❌ Failed: {img_name}")
                return False
            
            time.sleep(random.uniform(5, 10))
    return False

if __name__ == "__main__":
    # Discover images
    images = glob.glob(os.path.join(UPLOAD_FOLDER, "*.png"))
    images += glob.glob(os.path.join(UPLOAD_FOLDER, "*.jpg"))
    if not images:
        test_images = glob.glob("test_massive.png") + glob.glob("test_basic.png") + glob.glob("test_design.png")
        images = [test_images[0]] if test_images else []

    if not images:
        print("❌ No images found.")
        sys.exit(1)

    # Metadata
    metadata = {}
    if os.path.exists("design_metadata.json"):
        with open("design_metadata.json", "r") as f:
            metadata = json.load(f)

    # Run Botasaurus
    main_task({'images': images, 'metadata': metadata})
