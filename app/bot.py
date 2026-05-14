import asyncio
from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)
from app.config import Config
from loguru import logger


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


async def agree_listener(page, member_name: str):
    while True:
        try:
            agree_btn = page.locator("button.agree-btn")
            if await agree_btn.count() > 0 and await agree_btn.is_visible():
                await agree_btn.click()
                logger.info(f"[{member_name}] Clicked I AGREE")
            await asyncio.sleep(1)
        except Exception:
            await asyncio.sleep(1)


async def login(page, phone: str, password: str, member_name: str):
    logger.info(f"[{member_name}] Navigating to login...")
    await page.goto(Config.LOGIN_URL, timeout=60_000)

    logged_in_indicator = page.locator(".user-name-text")
    if await logged_in_indicator.count() > 0:
        logger.success(f"[{member_name}] Already logged in via session!")
        return

    logger.info(f"[{member_name}] Filling credentials...")

    phone_input = page.locator("#mobile_number")
    password_input = page.locator("#password")

    await page.mouse.move(200, 300)
    await asyncio.sleep(0.1)
    await page.mouse.move(250, 350)

    await phone_input.click()
    await phone_input.clear()
    await phone_input.press_sequentially(phone, delay=100)
    await page.keyboard.press("Tab")
    await asyncio.sleep(0.1)

    await password_input.click()
    await password_input.clear()
    await password_input.press_sequentially(password, delay=100)
    await page.keyboard.press("Tab")
    await asyncio.sleep(0.1)

    await wait_for_turnstile(page, timeout=30_000)
    await asyncio.sleep(0.5)

    submit_btn = page.locator("button[type='submit']")
    await submit_btn.wait_for(state="visible", timeout=10_000)
    await submit_btn.click()

    try:
        await page.wait_for_url(Config.BASE_URL, timeout=15_000)
        logger.success(f"[{member_name}] Login successful!")
    except PlaywrightTimeoutError:
        error = page.locator(".error, .alert-danger, [class*='error']")
        if await error.count() > 0:
            msg = await error.first.inner_text()
            raise Exception(f"[{member_name}] Login rejected: {msg}")
        logger.warning(f"[{member_name}] No home redirect — inspect manually.")


async def run_member(member: dict):
    from app.ticket_picker_by_url import fetch_trains

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(
                f"http://localhost:{member['debugging_port']}"
            )
        except Exception:
            raise RuntimeError(
                f"[{member['name']}] Chrome not running on port {member['debugging_port']}.\n"
                f"Launch with: chrome --remote-debugging-port={member['debugging_port']} "
                f"--user-data-dir={member['user_data_dir']}"
            )

        context = browser.contexts[0]
        pages = context.pages
        page = pages[0] if pages else await context.new_page()

        agree_task = asyncio.create_task(agree_listener(page, member["name"]))

        try:
            await login(page, member["phone"], member["password"], member["name"])
            await asyncio.sleep(0.1)
            await fetch_trains(
                page,
                from_city=Config.FROM_CITY,
                to_city=Config.TO_CITY,
                date_of_journey=Config.DATE_OF_JOURNEY,
                ticket_class=Config.TICKET_CLASS,
                seat_count=Config.SEATS_PER_MEMBER,
                preferred_train=Config.PREFERRED_TRAIN,
            )

        except Exception as e:
            logger.error(f"[{member['name']}] Flow failed: {e}")
            # await page.screenshot(
            #     path=f"logs/error_{member['name'].replace(' ', '_')}.png"
            # )

        finally:
            agree_task.cancel()
            try:
                await agree_task
            except asyncio.CancelledError:
                pass
            await browser.close()
