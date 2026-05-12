import asyncio
from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)
from app.config import Config
from loguru import logger
from app.ticket_picker_by_url import fetch_trains

# No playwright-stealth needed — real Chrome doesn't need it


async def wait_for_turnstile(page, timeout: int = 30_000):
    logger.info("Waiting for Turnstile to resolve...")
    try:
        await page.wait_for_function(
            """
            () => {
                const el = document.querySelector('input[name="cf-turnstile-response"]');
                return el && el.value && el.value.length > 100;
            }
            """,
            timeout=timeout,
        )
        logger.success("Turnstile resolved.")
    except PlaywrightTimeoutError:
        raise Exception("Turnstile did not resolve within timeout.")


async def setup_agree_listener(page):
    """
    Watches for the AGREE button in the background and clicks it whenever it appears.
    Run this once after page load — it stays active for the entire session.
    """

    async def click_if_agree_appears():
        while True:
            try:
                agree_btn = page.locator("button.agree-btn")
                if await agree_btn.count() > 0:
                    if await agree_btn.is_visible():
                        await agree_btn.click()
                        logger.info("Clicked I AGREE")
                await asyncio.sleep(1)
            except Exception:
                # Page may be navigating — ignore and keep polling
                await asyncio.sleep(1)

    # Fire and forget — runs concurrently with main flow
    asyncio.create_task(click_if_agree_appears())


async def login_to_railway():
    async with async_playwright() as p:

        # Connect to your already-running real Chrome instance
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception:
            raise RuntimeError(
                "Could not connect to Chrome. "
                "Make sure Chrome is running with --remote-debugging-port=9222"
            )

        # CDP gives you a browser with existing contexts
        # Default context holds your persistent session
        context = browser.contexts[0]
        pages = context.pages
        page = pages[0] if pages else await context.new_page()

        try:
            logger.info(f"Navigating to: {Config.LOGIN_URL}")
            await page.goto(
                Config.LOGIN_URL,
                timeout=60_000,
            )

            # Already logged in?
            logged_in_indicator = page.locator(".user-name-text")

            if await logged_in_indicator.count() > 0:
                logger.success("Already logged in via session!")
                # Fetch trains
                return await fetch_trains(
                    page, "Dhaka", "Rajshahi", "16-May-2026", "SNIGDHA"
                )

            logger.info("Filling credentials...")

            phone_input = page.locator("#mobile_number")
            password_input = page.locator("#password")

            # Subtle mouse movement — helps Turnstile's behavioral analysis
            await page.mouse.move(200, 300)
            await asyncio.sleep(0.4)
            await page.mouse.move(250, 350)

            # Fill phone
            await phone_input.click()
            await phone_input.clear()
            await phone_input.press_sequentially(Config.PHONE, delay=120)
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.3)

            # Fill password
            await password_input.click()
            await password_input.clear()
            await password_input.press_sequentially(Config.PASSWORD, delay=120)
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.3)

            # Wait for Turnstile to auto-resolve
            await wait_for_turnstile(page, timeout=30_000)
            await asyncio.sleep(1)

            # Submit
            submit_btn = page.locator("button[type='submit']")
            await submit_btn.wait_for(state="visible", timeout=10_000)
            await submit_btn.click()

            # Confirm login
            try:
                await page.wait_for_url(Config.BASE_URL, timeout=15_000)
                logger.success("Login successful!")
                await setup_agree_listener(page)
            except PlaywrightTimeoutError:
                error = page.locator(".error, .alert-danger, [class*='error']")
                if await error.count() > 0:
                    msg = await error.first.inner_text()
                    raise Exception(f"Login rejected by server: {msg}")
                logger.warning("No home redirect — inspect manually.")

            await asyncio.sleep(3)

            # Fetch trains
            return await fetch_trains(
                page, "Dhaka", "Rajshahi", "16-May-2026", "SNIGDHA"
            )

        except Exception as e:
            logger.error(f"Login failed: {e}")
            await page.screenshot(path="login_error.png")
            # page.goto()

        finally:
            # IMPORTANT: Don't close the browser — you don't own this process
            # Just disconnect. Chrome keeps running.
            await browser.close()  # This disconnects CDP, doesn't kill Chrome


if __name__ == "__main__":
    asyncio.run(login_to_railway())
