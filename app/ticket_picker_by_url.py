import asyncio
from app.config import Config
from loguru import logger


async def fetch_trains(
    page,
    from_city: str,
    to_city: str,
    date_of_journey: str,
    ticket_class: str,
    seat_count: int = 4,
    preferred_train: str = None,
):
    ticket_url = (
        f"{Config.TICKET_URL}"
        f"?fromcity={from_city}"
        f"&tocity={to_city}"
        f"&doj={date_of_journey}"
        f"&class={ticket_class}"
    )

    logger.info(f"Navigating to: {ticket_url}")
    await page.goto(ticket_url, timeout=60_000)

    # Wait for train rows to render
    await page.locator("app-single-trip").first.wait_for(
        state="visible", timeout=20_000
    )
    await asyncio.sleep(1)  # Let Angular finish re-rendering all rows

    await click_book_now(page, ticket_class, seat_count, preferred_train)
    await asyncio.sleep(3)
    await select_seats(page)
    await asyncio.sleep(20)
    # await continue_purchase(page)


async def click_book_now(
    page, ticket_class: str, seat_count: int = 4, preferred_train: str = None
):
    await page.locator("app-single-trip").first.wait_for(
        state="visible", timeout=20_000
    )
    await asyncio.sleep(1)

    all_rows = page.locator("app-single-trip")
    row_count = await all_rows.count()

    if row_count == 0:
        raise Exception("No train rows found on page.")

    logger.info(f"Scanning {row_count} train rows for class: {ticket_class}")

    candidates = []  # list of (available_seats, row_index, train_name)

    for i in range(row_count):
        row = all_rows.nth(i)
        train_name = (await row.locator("h2").inner_text()).strip()

        # If preferred train specified, skip non-matching rows
        if preferred_train and preferred_train.upper() not in train_name.upper():
            continue

        class_card = row.locator(
            f".single-seat-class.seat-available-wrap"
            f":has(.seat-class-name:text-is('{ticket_class}'))"
        )

        if await class_card.count() == 0:
            continue

        seat_count_text = await class_card.locator(".all-seats").inner_text()
        try:
            available = int(seat_count_text.strip())
        except ValueError:
            available = 0

        logger.info(f"  {train_name} — {ticket_class}: {available} seats")

        if available > 0:
            candidates.append((available, i, train_name))

    if not candidates:
        raise Exception(
            f"No trains found with available {ticket_class} seats"
            + (f" for train: {preferred_train}" if preferred_train else "")
        )

    # Pick the one with most available seats
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_available, best_index, best_train = candidates[0]

    logger.info(f"Selected: {best_train} — {ticket_class} ({best_available} seats)")

    target_row = all_rows.nth(best_index)

    # Expand if collapsed
    collapsible = target_row.locator(".trip-collapsible")
    is_collapsed = await collapsible.evaluate(
        "el => el.classList.contains('trip-collapsed')"
    )
    if is_collapsed:
        logger.info("Row collapsed — expanding...")
        await target_row.locator("button.trip-collapse-btn").click()
        # Wait for expansion animation to fully complete
        await page.wait_for_function(
            """
            (index) => {
                const rows = document.querySelectorAll('app-single-trip');
                const row = rows[index];
                if (!row) return false;
                const collapsible = row.querySelector('.trip-collapsible');
                return collapsible && !collapsible.classList.contains('trip-collapsed');
            }
            """,
            arg=best_index,
            timeout=10_000,
        )
        await asyncio.sleep(0.5)

    # Locate the exact seat class card
    seat_class_card = target_row.locator(
        f".single-seat-class.seat-available-wrap"
        f":has(.seat-class-name:text-is('{ticket_class}'))"
    )
    await seat_class_card.wait_for(state="visible", timeout=10_000)

    book_btn = seat_class_card.locator("button.book-now-btn")
    await book_btn.wait_for(state="visible", timeout=10_000)
    await book_btn.scroll_into_view_if_needed()
    await asyncio.sleep(0.5)

    # dispatch_event bypasses pointer interception from overlapping divs
    await book_btn.dispatch_event("click")

    logger.info(f"Clicked BOOK NOW — {best_train} / {ticket_class}")


async def select_best_coach(page) -> int:
    coach_select = page.locator("#select-bogie")
    await coach_select.wait_for(state="visible", timeout=15_000)

    options = await coach_select.locator("option").all()

    best_value = None
    best_seats = 0
    best_label = None

    for option in options:
        text = (await option.inner_text()).strip()
        value = await option.get_attribute("value")

        try:
            seat_count = int(text.split("-")[1].strip().split(" ")[0])
        except (IndexError, ValueError):
            continue

        logger.info(f"  Coach: {text}")

        if seat_count > best_seats:
            best_seats = seat_count
            best_value = value
            best_label = text

    if best_value is None or best_seats == 0:
        raise Exception("No coaches with available seats found.")

    logger.info(f"Selecting coach: {best_label} (value={best_value})")

    # Bootstrap Select + Angular — must set value via native setter
    # and fire both 'change' and 'input' events to trigger Angular's change detection
    await page.evaluate(
        """
        (value) => {
            const select = document.querySelector('#select-bogie');
            if (!select) throw new Error('Coach select not found');

            // Use native setter to bypass Angular's value tracking
            const nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLSelectElement.prototype, 'value'
            ).set;
            nativeSetter.call(select, value);

            // Fire events Angular listens to
            select.dispatchEvent(new Event('change', { bubbles: true }));
            select.dispatchEvent(new Event('input', { bubbles: true }));
        }
        """,
        best_value,
    )

    # Wait for Angular to re-render the seat map
    await page.wait_for_load_state(timeout=15_000)
    await asyncio.sleep(1)

    # Verify the selection actually changed by re-reading the select value
    current_value = await page.evaluate(
        "() => document.querySelector('#select-bogie').value"
    )
    if current_value != best_value:
        logger.warning(
            f"Coach selection may not have registered. "
            f"Expected {best_value}, got {current_value}"
        )

    return best_seats


async def select_seats(page, count: int = 4):
    logger.info("Waiting for seat map to load...")

    # Handle coach selection first
    coach_selector = page.locator("#select-bogie")
    if await coach_selector.count() > 0:
        available_in_coach = await select_best_coach(page)
        logger.info(f"Coach selected — {available_in_coach} seats available")

    available_seat = page.locator(
        "button.seat-available, button.btn-seat.seat-available"
    )
    await available_seat.first.wait_for(state="visible", timeout=30_000)

    total_available = await available_seat.count()
    logger.info(f"Found {total_available} selectable seats in coach.")

    if total_available == 0:
        raise Exception("No available seats found in selected coach.")

    to_select = min(count, total_available)

    if to_select < count:
        logger.warning(
            f"Requested {count} seats but only {total_available} available. "
            f"Proceeding with {to_select}."
        )

    selected = []
    seats = await available_seat.all()
    for seat in seats[:to_select]:
        seat_title = await seat.get_attribute("title")
        await seat.click()
        selected.append(seat_title)
        logger.info(f"Selected seat: {seat_title}")
        await asyncio.sleep(0.4)

    logger.success(f"Selected {len(selected)} seats: {', '.join(selected)}")
    return selected


async def continue_purchase(page):
    continue_btn = page.locator("button.continue-btn")
    await continue_btn.wait_for(state="visible", timeout=10_000)
    await continue_btn.wait_for(state="visible", timeout=10_000)
    await continue_btn.click()
    logger.info("Clicked CONTINUE PURCHASE")
