import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from app.config import Config
from loguru import logger

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
                # wait_until="networkidle",
                timeout=60_000,
            )

            # Already logged in?
            if "dashboard" in page.url:
                logger.success("Already logged in via session!")
                return

            logger.info("Filling credentials...")

            phone_input = page.locator("#mobile_number")
            password_input = page.locator("#password")

            await phone_input.wait_for(state="visible", timeout=15_000)

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
            await submit_btn.wait_for(state="enabled", timeout=10_000)
            await submit_btn.click()

            # Confirm login
            try:
                await page.wait_for_url("**/dashboard**", timeout=15_000)
                logger.success("Login successful!")
            except PlaywrightTimeoutError:
                error = page.locator(".error, .alert-danger, [class*='error']")
                if await error.count() > 0:
                    msg = await error.first.inner_text()
                    raise Exception(f"Login rejected by server: {msg}")
                logger.warning("No dashboard redirect — inspect manually.")

            await asyncio.sleep(15)

        except Exception as e:
            logger.error(f"Login failed: {e}")
            await page.screenshot(path="login_error.png")

        finally:
            # IMPORTANT: Don't close the browser — you don't own this process
            # Just disconnect. Chrome keeps running.
            await browser.close()  # This disconnects CDP, doesn't kill Chrome


if __name__ == "__main__":
    asyncio.run(login_to_railway())