from app.config import Config
from loguru import logger
import asyncio


async def fetch_trains(page, from_city, to_city, date_of_journey, ticket_class):
    ticket_url = f"{Config.TICKET_URL}?fromcity={from_city}&tocity={to_city}&doj={date_of_journey}&class={ticket_class}"

    await page.goto(ticket_url)

    async def book_four_tickets(page):

        book_btn = page.locator("button.book-now-btn").first
        await book_btn.wait_for(state="visible", timeout=10_000)
        await book_btn.click()
        asyncio.sleep(3)

    await book_four_tickets(page)
    await select_seats(page)
    await continue_purchase(page)


async def select_seats(page, count: int = 4):
    """
    Waits for seat map to load and selects up to `count` available seats.
    Only clicks seats with class 'seat-available' — skips booked/unavailable ones.
    """
    logger.info("Waiting for seat map to load...")

    available_seat = page.locator(
        "button.seat-available, button.btn-seat.seat-available"
    )
    await available_seat.first.wait_for(state="visible", timeout=30_000)

    total_available = await available_seat.count()
    logger.info(f"Found {total_available} available seats.")

    if total_available < count:
        raise Exception(
            f"Not enough seats available. Requested {count}, found {total_available}."
        )

    selected = []
    for i in range(count):
        seat = available_seat.nth(i)
        seat_title = await seat.get_attribute("title")
        await seat.click()
        selected.append(seat_title)
        logger.info(f"Selected seat: {seat_title}")
        await asyncio.sleep(0.3)  # Small gap between clicks

    logger.success(f"Selected {len(selected)} seats: {', '.join(selected)}")
    return selected


async def continue_purchase(page):
    continue_btn = page.locator("button.continue-btn")
    await continue_btn.wait_for(state="visible", timeout=10_000)
    await continue_btn.click()
    logger.info("Clicked CONTINUE PURCHASE")
