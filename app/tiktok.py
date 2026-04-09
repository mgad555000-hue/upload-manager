"""
TikTok Playwright — رفع نصف أوتوماتيك على تيكتوك
يفتح متصفح Chromium مرئي، يملى البيانات، الموظف يراجع ويأكد
"""
import os
import json
import asyncio
from pathlib import Path

COOKIES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tiktok_sessions")
Path(COOKIES_DIR).mkdir(parents=True, exist_ok=True)

# Active browser sessions: {key: asyncio.Task}
_active_sessions = {}


def _cookies_path(account_name: str = "default") -> str:
    return os.path.join(COOKIES_DIR, f"{account_name}.json")


def is_playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def get_active_session_key(topic_id: int, platform_id: int) -> str:
    return f"{topic_id}_{platform_id}"


def is_session_active(topic_id: int, platform_id: int) -> bool:
    key = get_active_session_key(topic_id, platform_id)
    task = _active_sessions.get(key)
    return task is not None and not task.done()


async def start_tiktok_upload(
    topic_id: int,
    platform_id: int,
    video_path: str,
    description: str,
    hashtags: str = "",
    account_name: str = "default",
) -> dict:
    """
    Launch a headed Playwright browser to upload to TikTok.
    Returns immediately — browser runs in background.
    """
    if not is_playwright_available():
        return {
            "status": "error",
            "message": "playwright \u0645\u0634 \u0645\u0646\u0635\u0651\u0628 \u2014 \u0634\u063a\u0651\u0644: pip install playwright && playwright install chromium",
        }

    key = get_active_session_key(topic_id, platform_id)
    if key in _active_sessions and not _active_sessions[key].done():
        return {
            "status": "already_running",
            "message": "\u0627\u0644\u0645\u062a\u0635\u0641\u062d \u0645\u0641\u062a\u0648\u062d \u0628\u0627\u0644\u0641\u0639\u0644 \u0644\u0644\u0645\u0648\u0636\u0648\u0639 \u062f\u0647",
        }

    task = asyncio.create_task(
        _run_upload(video_path, description, hashtags, account_name)
    )
    _active_sessions[key] = task
    task.add_done_callback(lambda t: _active_sessions.pop(key, None))

    return {
        "status": "browser_opened",
        "message": "\u0627\u0644\u0645\u062a\u0635\u0641\u062d \u0641\u062a\u062d \u2014 \u0623\u0643\u0645\u0644 \u0627\u0644\u0631\u0641\u0639 \u0645\u0646 \u0647\u0646\u0627\u0643 \u0648\u0627\u0631\u062c\u0639 \u0623\u0643\u062f",
    }


async def _run_upload(
    video_path: str,
    description: str,
    hashtags: str,
    account_name: str,
) -> dict:
    """Run the actual Playwright upload flow."""
    from playwright.async_api import async_playwright

    cookies_file = _cookies_path(account_name)
    result = {"status": "done"}

    try:
        async with async_playwright() as p:
            # Use headless in Docker (no display), headed locally
            is_docker = os.path.exists("/.dockerenv")
            browser = await p.chromium.launch(
                headless=is_docker,
                args=["--start-maximized"] if not is_docker else ["--no-sandbox", "--disable-gpu"],
            )

            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="ar",
            )

            # Load saved cookies
            if os.path.exists(cookies_file):
                try:
                    with open(cookies_file, "r", encoding="utf-8") as f:
                        cookies = json.load(f)
                    await context.add_cookies(cookies)
                except Exception:
                    pass

            page = await context.new_page()

            try:
                # Navigate to TikTok Studio upload
                await page.goto(
                    "https://www.tiktok.com/creator#/upload?scene=creator_center",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await page.wait_for_timeout(3000)

                # Check if login needed
                current_url = page.url
                if "login" in current_url.lower() or "signup" in current_url.lower():
                    print("[TikTok] Waiting for user login...")
                    try:
                        await page.wait_for_url("**/creator**", timeout=300000)
                        await page.wait_for_timeout(3000)
                    except Exception:
                        result["status"] = "login_timeout"
                        return result

                # Save cookies after login
                await _save_cookies(context, cookies_file)

                # Upload video file
                file_input = page.locator('input[type="file"]').first
                if await file_input.count() > 0:
                    await file_input.set_input_files(video_path)
                    print("[TikTok] Video file selected")
                    await page.wait_for_timeout(5000)
                else:
                    # Try clicking upload area to trigger file chooser
                    upload_area = page.locator('[class*="upload"]').first
                    if await upload_area.count() > 0:
                        async with page.expect_file_chooser(timeout=10000) as fc_info:
                            await upload_area.click()
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(video_path)
                        await page.wait_for_timeout(5000)

                # Fill caption/description
                caption_text = description
                if hashtags:
                    caption_text += "\n" + hashtags

                if caption_text.strip():
                    caption_selectors = [
                        '[data-text="true"]',
                        '[contenteditable="true"]',
                        '.DraftEditor-root',
                        '[class*="caption"] [contenteditable]',
                        '.notranslate[contenteditable]',
                    ]

                    filled = False
                    for sel in caption_selectors:
                        editor = page.locator(sel).first
                        if await editor.count() > 0:
                            await editor.click()
                            await page.keyboard.press("Control+A")
                            await page.keyboard.type(caption_text, delay=20)
                            filled = True
                            print("[TikTok] Caption filled")
                            break

                    if not filled:
                        print("[TikTok] Could not find caption editor — user will fill manually")

                # Keep browser open — wait for user to close it (up to 30 min)
                print("[TikTok] Browser ready — waiting for user to finish and close...")
                try:
                    await page.wait_for_event("close", timeout=1800000)
                except Exception:
                    pass

                # Save cookies one more time
                await _save_cookies(context, cookies_file)

            except Exception as e:
                print(f"[TikTok] Error: {e}")
                result["status"] = "error"
                # Keep browser open so user can finish manually
                try:
                    await page.wait_for_event("close", timeout=1800000)
                except Exception:
                    pass
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass

    except Exception as e:
        print(f"[TikTok] Fatal error: {e}")
        result["status"] = "error"

    return result


async def _save_cookies(context, cookies_file: str):
    """Save browser cookies to file."""
    try:
        cookies = await context.cookies()
        with open(cookies_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f)
    except Exception:
        pass
