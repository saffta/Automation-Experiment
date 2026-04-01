from botasaurus.browser import browser, Wait
from botasaurus_driver import Driver
from botasaurus_driver import cdp
import time
import os
import json
import glob
import random
from dotenv import load_dotenv

# Load environment variables from the root .env file
# To allow running from anywhere, we can locate the root directory heuristically
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(root_dir, '.env')
load_dotenv(dotenv_path=env_path)

# Credentials
EMAIL = os.getenv("REDBUBBLE_EMAIL")
PASSWORD = os.getenv("REDBUBBLE_PASSWORD")

# Cookie file path
COOKIE_FILE = 'redbubble_cookies.json'

# Upload folder — place your .png/.jpg files here
UPLOAD_FOLDER = 'uploads'

def load_and_inject_cookies(driver):
    """Load cookies from JSON file and inject them via CDP Network.setCookie
    
    This uses Chrome DevTools Protocol directly, which is the ONLY way to set
    httpOnly cookies (document.cookie cannot touch those).
    """
    if not os.path.exists(COOKIE_FILE):
        print(f"No cookie file found at {COOKIE_FILE}")
        return False

    print(f"Loading cookies from {COOKIE_FILE}...")
    try:
        with open(COOKIE_FILE, 'r') as f:
            cookies = json.load(f)

        # First navigate to the domain so cookies can be set
        driver.get("https://www.redbubble.com/robots.txt")
        time.sleep(2)

        injected = 0
        for cookie in cookies:
            try:
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                domain = cookie.get('domain', '.redbubble.com')
                path = cookie.get('path', '/')
                secure = cookie.get('secure', True)
                http_only = cookie.get('httpOnly', False)

                # Handle expiry
                expires = None
                if 'expirationDate' in cookie and cookie['expirationDate'] not in (-1, None, 0):
                    expires = cookie['expirationDate']
                elif 'expires' in cookie and cookie['expires'] not in (-1, None, 0):
                    expires = cookie['expires']

                # Handle sameSite — CDP expects exact casing
                ss_raw = cookie.get('sameSite', 'Lax')
                if ss_raw in ('None', 'no_restriction'):
                    same_site = 'None'
                elif ss_raw == 'Strict':
                    same_site = 'Strict'
                elif ss_raw == 'unspecified':
                    same_site = 'Lax'  # Default fallback
                else:
                    same_site = 'Lax'

                # Build the CDP command URL (required for cross-domain cookies)
                url = f"https://{domain.lstrip('.')}{path}"

                # Use CDP Network.setCookie — this handles httpOnly cookies!
                cdp_cmd = cdp.network.set_cookie(
                    name=name,
                    value=value,
                    domain=domain,
                    path=path,
                    secure=secure,
                    http_only=http_only,
                    same_site=same_site,
                    url=url,
                )
                # If we have an expiry, set it
                if expires:
                    cdp_cmd = cdp.network.set_cookie(
                        name=name,
                        value=value,
                        domain=domain,
                        path=path,
                        secure=secure,
                        http_only=http_only,
                        same_site=same_site,
                        url=url,
                        expires=expires,
                    )

                try:
                    driver.run_cdp_command(cdp_cmd)
                    injected += 1
                except Exception as cdp_err:
                    # Fallback: try document.cookie for non-httpOnly
                    if not http_only:
                        cookie_str = f"{name}={value}; path={path}; domain={domain}"
                        if secure:
                            cookie_str += "; Secure"
                        cookie_str += f"; SameSite={same_site}"
                        driver.run_js(f"document.cookie = `{cookie_str}`;")
                        injected += 1
                    else:
                        print(f"  Warning: CDP setCookie failed for '{name}': {cdp_err}")

            except Exception as e:
                print(f"  Warning: Could not process cookie '{cookie.get('name', '?')}': {e}")

        print(f"Injected {injected}/{len(cookies)} cookies via CDP")
        return injected > 0

    except Exception as e:
        print(f"Failed to load cookies: {e}")
        return False


def is_on_upload_page(driver):
    """Quick non-blocking check if we're on the upload page with the form loaded"""
    try:
        current_url = driver.current_url
        if "portfolio/images/new" not in current_url:
            return False
        # Use instant JS check instead of blocking check_element
        has_form = driver.run_js("""
            return (document.querySelector('#select-image-single') !== null ||
                    document.querySelector('input[type="file"]') !== null ||
                    document.querySelector('#work_title_en') !== null);
        """)
        return bool(has_form)
    except:
        return False


def is_on_login_page(driver):
    """Quick non-blocking check if we're on login/signup page"""
    try:
        current_url = driver.current_url
        if any(kw in current_url for kw in ['login', 'auth', 'signup', 'sign_up']):
            return True
        has_login_form = driver.run_js("""
            return document.querySelector('input[name="usernameOrEmail"]') !== null;
        """)
        return bool(has_login_form)
    except:
        return False


def upload_single_image(driver, image_path, title, tags, description, primary_tag=None):
    """Upload a single image, fill form, and publish. Assumes we're on the upload page."""

    print(f"\n{'='*50}")
    print(f"Uploading: {os.path.basename(image_path)}")
    print(f"Title: {title}")
    print(f"{'='*50}")

    abs_path = os.path.abspath(image_path)
    if not os.path.exists(abs_path):
        print(f"ERROR: File not found: {abs_path}")
        return False

    # Step A: Upload image via CDP
    print("\n=== Uploading Image ===")
    try:
        # Standard Botasaurus method for file input injection
        print(f"=== Uploading Image: {os.path.basename(abs_path)} ===")
        driver.upload_file('#select-image-single', abs_path)
        print("  Image uploaded successfully!")
    except Exception as e:
        print(f"  Upload attempt failed: {e}")
        # Secondary fallback just in case the ID changed
        try:
            driver.upload_file('input[type="file"]', abs_path)
            print("  Image uploaded via fallback input[type='file']")
        except Exception as e2:
            print(f"  Fallback upload also failed: {e2}")
            return False

    # Wait for upload to process
    print("Waiting for image to process...")
    time.sleep(15)

    # Step B: Fill form fields
    print("\n=== Filling Form Fields ===")

    # Title
    try:
        title_field = driver.select('#work_title_en', wait=Wait.SHORT)
        if title_field:
            title_field.clear()
            driver.type('#work_title_en', title)
            print(f"  Title: {title}")
    except Exception as e:
        print(f"  Could not set title: {e}")

    # Main tag
    try:
        main_tag = primary_tag or (tags[0] if tags else '')
        driver.type('#main-tag-en', main_tag)
        print(f"  Main tag: {main_tag}")
    except Exception as e:
        print(f"  Could not set main tag: {e}")

    # Supporting tags
    try:
        supporting = ', '.join(tags[1:15]) if len(tags) > 1 else ''
        driver.type('#supporting-tags-en', supporting)
        print(f"  Supporting tags: {supporting}")
    except Exception as e:
        print(f"  Could not set supporting tags: {e}")

    # Description
    try:
        driver.type('#work_description_en', description)
        print("  Description set")
    except Exception as e:
        print(f"  Could not set description: {e}")

    # Step C: Set media type (digital)
    print("\n=== Setting Media Type ===")
    try:
        driver.click('#media_digital')
        print("  Digital media selected")
    except Exception as e:
        print(f"  Could not set media type: {e}")

    # Step D: Set default product
    print("\n=== Setting Default Product ===")
    try:
        driver.run_js("""
            let sel = document.querySelector('#work_default_product_type_code');
            if (sel) {
                sel.value = 't-shirt';
                sel.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)
        print("  Default product: t-shirt")
    except Exception as e:
        print(f"  Could not set default product: {e}")

    # Step E: Set Mature Content filter to "No" (Safe for Work)
    print("\n=== Setting Mature Content ===")
    try:
        # Use JS to ensure the radio button is checked AND its change events fire
        # Many sites hide real radios with div/labels that standard .click() might miss
        driver.run_js("""
            const noEl = document.querySelector('#work_safe_for_work_true');
            if (noEl) {
                noEl.checked = true;
                noEl.dispatchEvent(new Event('change', { bubbles: true }));
                noEl.dispatchEvent(new Event('click', { bubbles: true }));
            }
        """)
        print("  Mature content: No (Safe for Work)")
    except Exception as e:
        print(f"  Could not set mature content filter: {e}")

    # Step F: Accept rights declaration
    print("\n=== Accepting Rights Declaration ===")
    try:
        # Forced JS check for the rights checkbox
        driver.run_js("""
            const rightsEl = document.querySelector('#rightsDeclaration');
            if (rightsEl) {
                rightsEl.checked = true;
                rightsEl.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)
        print("  Rights declaration accepted")
    except Exception as e:
        print(f"  Could not accept rights declaration: {e}")

    # Step G: Publish
    print("\n=== Publishing ===")
    try:
        # Use robust JS click to ensure we hit the actual submit button and not a file input or overlay
        clicked = driver.run_js("""
            const buttons = Array.from(document.querySelectorAll('button, input[type="submit"]'));
            const submitBtn = buttons.find(btn => 
                (btn.id === 'submit-work') || 
                (btn.innerText && (btn.innerText.includes('Upload') || btn.innerText.includes('Publish')))
            );
            if (submitBtn) {
                submitBtn.scrollIntoView();
                submitBtn.click();
                return true;
            }
            return false;
        """)
        
        if clicked:
            print("  Submit button clicked via JS!")
        else:
            # Fallback to standard selector if JS fails to find it
            submit = driver.select('#submit-work', wait=Wait.SHORT)
            if submit:
                submit.scroll_into_view()
                time.sleep(1)
                driver.click('#submit-work')
                print("  Submit button clicked via fallback!")
            else:
                print("  ERROR: Submit button not found")
                return False

        time.sleep(10)

        final_url = driver.current_url
        print(f"  Final URL: {final_url}")

        if "promote" in final_url or "manage" in final_url:
            print(f"  SUCCESS: '{title}' published!")
            return True
        else:
            print("  Checking for error messages on page...")
            try:
                # Target Redbubble's specific error containers
                error_info = driver.run_js("""
                    const err = document.querySelector('#error-explanation, .error-messages, .errors');
                    if (err) return err.innerText.trim();
                    
                    // Fallback: check for generic error alerts
                    const alerts = Array.from(document.querySelectorAll('.alert--error, .message-box--error'));
                    if (alerts.length > 0) return alerts[0].innerText.trim();
                    
                    return null;
                """)
                if error_info:
                    print(f"    ❌ Site Error Detected: {error_info}")
                else:
                    # Capture a broad look if no specific container matches
                    page_text = driver.run_js("return document.body.innerText;")
                    if "error" in page_text.lower():
                        print("    ❌ Potential validation error detected in page text.")
            except:
                pass
            return False

    except Exception as e:
        print(f"  Error in publish step: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_upload_files():
    """Get list of image files to upload from the uploads folder"""
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        print(f"Created '{UPLOAD_FOLDER}/' folder. Place your .png/.jpg files there.")
        return []

    patterns = ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp', '*.webp']
    files = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(UPLOAD_FOLDER, pattern)))

    files.sort()
    return files


@browser(
    headless=os.environ.get('HEADLESS', 'false').lower() == 'true',
    close_on_crash=False,
    profile="redbubble_profile",
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    add_arguments=[
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        "--disable-software-rasterizer",
        "--disable-blink-features=AutomationControlled",
    ],
)
def login_and_upload(driver: Driver, data):
    """Complete workflow: login -> upload -> fill -> publish"""
    try:
        driver.enable_human_mode()
        print("Starting Redbubble automation...")
        print(f"Headless mode: {os.environ.get('HEADLESS', 'false')}")

        # ===== STEP 1: Inject cookies and navigate =====
        print("\n" + "="*50)
        print("STEP 1: Cookie Injection & Navigation")
        print("="*50)

        cookies_loaded = load_and_inject_cookies(driver)

        # Navigate to upload page using google_get for Cloudflare bypass
        print("\nNavigating to upload page...")
        try:
            driver.google_get("https://www.redbubble.com/portfolio/images/new", bypass_cloudflare=True)
        except Exception as e:
            print(f"google_get failed ({e}), falling back to direct get...")
            driver.get("https://www.redbubble.com/portfolio/images/new")

        # ===== STEP 2: Wait for page and check auth =====
        print("\n" + "="*50)
        print("STEP 2: Authentication Check")
        print("="*50)

        time.sleep(5)  # Give the page a moment to settle

        max_wait = 60
        elapsed = 0

        while elapsed < max_wait:
            # Check if we landed on the upload page
            if is_on_upload_page(driver):
                print(f"Upload page loaded successfully! (took {elapsed}s)")
                break

            # Check if we need to login
            if is_on_login_page(driver):
                print("Login/Signup page detected.")
                break

            # Check for Cloudflare "Just a moment"
            try:
                title = driver.run_js("return document.title;") or ""
                if "just a moment" in title.lower():
                    if elapsed % 15 == 0:
                        print(f"  Cloudflare challenge in progress... ({elapsed}s)")
            except:
                pass

            time.sleep(3)
            elapsed += 3

            if elapsed % 15 == 0:
                current_url = driver.current_url or "unknown"
                print(f"  Waiting... ({elapsed}s/{max_wait}s) URL: {current_url}")

        # ===== STEP 3: Login if needed =====
        if is_on_login_page(driver):
            print("\n" + "="*50)
            print("STEP 3: Human-Mode Auto Login")
            print("  NOTE: Redbubble uses invisible reCAPTCHA v2 + Redux-Form")
            print("="*50)

            # Generate some mouse movement on the page first to build reCAPTCHA score
            print("  Warming up reCAPTCHA with mouse movements...")
            driver.enable_human_mode()
            try:
                # Move mouse around the page to build a natural interaction history
                # reCAPTCHA scores based on mouse movement patterns before form submission
                page_body = driver.select('body', wait=Wait.SHORT)
                if page_body:
                    page_body.click()  # Click somewhere on the body
                time.sleep(random.uniform(0.5, 1.0))
            except:
                pass

            time.sleep(random.uniform(1.5, 3.0))

            # --- Fill Email using React's NATIVE value setter ---
            # React overrides HTMLInputElement.prototype.value with a custom getter/setter.
            # When you do el.value = 'x', React's setter intercepts it and updates React state.
            # BUT only if you call the NATIVE setter first, then dispatch 'input'.
            # This is the well-known "React controlled input" workaround.
            print("  Entering email via React native setter...")
            email_input = driver.select('input[name="usernameOrEmail"]', wait=Wait.SHORT)
            if email_input:
                email_input.click()  # Focus
                time.sleep(random.uniform(0.3, 0.7))

            driver.run_js("""
                const el = document.querySelector('input[name="usernameOrEmail"]');
                if (el) {
                    const nativeSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    nativeSetter.call(el, args.val);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            """, {"val": data['email']})
            print(f"  Email set: {data['email']}")
            time.sleep(random.uniform(0.8, 1.5))

            # --- Fill Password using React's NATIVE value setter ---
            print("  Entering password via React native setter...")
            pass_input = driver.select('input[name="password"]', wait=Wait.SHORT)
            if pass_input:
                pass_input.click()  # Focus
                time.sleep(random.uniform(0.3, 0.7))

            driver.run_js("""
                const el = document.querySelector('input[name="password"]');
                if (el) {
                    const nativeSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    nativeSetter.call(el, args.val);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            """, {"val": data['password']})
            print("  Password set")
            time.sleep(random.uniform(0.5, 1.0))

            # Try remember me
            try:
                remember = driver.select('input[name="rememberMe"]', wait=Wait.SHORT)
                if remember:
                    remember.click()
                    print("  Remember me checked")
            except:
                pass

            time.sleep(random.uniform(1.0, 2.0))

            # --- Click Login with human-mode mouse movement ---
            # The invisible reCAPTCHA monitors the click event for human-like mouse trajectory.
            print("  Clicking 'Log In' button...")
            try:
                # Target the button directly using its unique text or unique primary button class
                # We'll use JS to find and click it to ensure we're not hitting the search bar's button
                driver.run_js("""
                    const buttons = Array.from(document.querySelectorAll('button[type="submit"]'));
                    const loginBtn = buttons.find(btn => btn.innerText.includes('Log In'));
                    if (loginBtn) {
                        loginBtn.click();
                        return true;
                    }
                    return false;
                """)
                print("  Login button clicked!")
            except Exception as e:
                print(f"  Login click error: {e}")

            driver.disable_human_mode()

            # Wait for login to complete
            print("\n  Waiting for login to complete...")
            login_wait = 300
            login_elapsed = 0
            while login_elapsed < login_wait:
                if is_on_upload_page(driver):
                    print(f"\n  Login successful! Upload page loaded after {login_elapsed}s.")
                    break

                current_url = driver.current_url or ""
                # If we're on Redbubble but NOT on upload or login, try to re-navigate
                if login_elapsed > 0 and login_elapsed % 20 == 0:
                    if "redbubble.com" in current_url and not is_on_login_page(driver):
                        if "portfolio/images/new" not in current_url:
                            print("  Authenticated but on wrong page. Re-navigating to upload...")
                            driver.get("https://www.redbubble.com/portfolio/images/new")

                time.sleep(5)
                login_elapsed += 5

                if login_elapsed % 30 == 0:
                    print(f"  Still waiting for login... ({login_elapsed}s/{login_wait}s)")

            if not is_on_upload_page(driver):
                print(f"\nFAILED: Could not reach upload page after {login_wait}s.")
                print(f"Current URL: {driver.current_url}")
                return False

        elif not is_on_upload_page(driver):
            # Neither on login nor upload page — something went wrong
            print(f"\nERROR: Unexpected page state.")
            print(f"Current URL: {driver.current_url}")
            print("The page might be stuck on Cloudflare or an error page.")
            return False

        else:
            print("\nAlready authenticated — proceeding to upload!")

        # ===== STEP 4: Upload images =====
        print("\n" + "="*50)
        print("STEP 4: Upload & Publish")
        print("="*50)

        # Determine what to upload
        files_to_upload = []

        if 'image_path' in data and data['image_path']:
            # Single file mode
            files_to_upload.append({
                'path': data['image_path'],
                'title': data.get('title', 'Untitled'),
                'tags': data.get('tags', []),
                'description': data.get('description', ''),
                'primary_tag': data.get('primary_tag', ''),
            })

        if 'upload_folder' in data and data['upload_folder']:
            # Batch folder mode
            folder = data['upload_folder']
            if os.path.isdir(folder):
                patterns = ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp', '*.webp']
                for pattern in patterns:
                    for f in sorted(glob.glob(os.path.join(folder, pattern))):
                        name = os.path.splitext(os.path.basename(f))[0]
                        files_to_upload.append({
                            'path': f,
                            'title': name.replace('_', ' ').replace('-', ' ').title(),
                            'tags': data.get('tags', []),
                            'description': data.get('description', ''),
                        })

        if not files_to_upload:
            print("ERROR: No files to upload!")
            print(f"  - Set 'image_path' for single file, or")
            print(f"  - Set 'upload_folder' for batch upload")
            return False

        print(f"\nFiles to upload: {len(files_to_upload)}")
        for i, f in enumerate(files_to_upload):
            print(f"  {i+1}. {os.path.basename(f['path'])} -> \"{f['title']}\"")

        # Process each file
        successes = 0
        failures = 0

        for i, file_data in enumerate(files_to_upload):
            print(f"\n{'#'*50}")
            print(f"# Processing {i+1}/{len(files_to_upload)}")
            print(f"{'#'*50}")

            # Make sure we're on the upload page
            if i > 0:
                print("Navigating to upload page for next image...")
                driver.get("https://www.redbubble.com/portfolio/images/new")
                time.sleep(5)

                # Wait for upload page to load
                wait_count = 0
                while not is_on_upload_page(driver) and wait_count < 30:
                    time.sleep(2)
                    wait_count += 2

                if not is_on_upload_page(driver):
                    print(f"ERROR: Could not reload upload page for image {i+1}")
                    failures += 1
                    continue

            result = upload_single_image(
                driver,
                file_data['path'],
                file_data['title'],
                file_data['tags'],
                file_data['description'],
                primary_tag=file_data.get('primary_tag')
            )

            if result:
                successes += 1
            else:
                failures += 1

        # Summary
        print(f"\n{'='*50}")
        print(f"UPLOAD COMPLETE")
        print(f"  Successes: {successes}")
        print(f"  Failures:  {failures}")
        print(f"  Total:     {len(files_to_upload)}")
        print(f"{'='*50}")

        return failures == 0

    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # === CONFIGURATION ===
    work_data = {
        'email': EMAIL,
        'password': PASSWORD,

        # Option 1: Single file upload
        'image_path': 'test_design.png',
        'title': 'Test Design Agent Zero',
        'tags': ['test', 'design', 'automation'],
        'description': 'A test design uploaded by Agent Zero automation bot for Redbubble',

        # Option 2: Batch folder upload (uncomment to use)
        # 'upload_folder': 'uploads',
    }

    print("="*50)
    print("Redbubble Upload Bot v2.0")
    print("  - CDP Cookie Injection")
    print("  - Cloudflare Bypass")
    print("  - Batch Folder Upload")
    print("="*50)

    result = login_and_upload(work_data)

    print("\n" + "="*50)
    if result:
        print("ALL UPLOADS COMPLETED SUCCESSFULLY!")
    else:
        print("SOME UPLOADS FAILED — Check logs above")
    print("="*50)
