import asyncio
from app.config import Config
from loguru import logger


MAX_SEATS = 4  # Hard limit per account


async def fetch_trains(
    page,
    from_city: str,
    to_city: str,
    date_of_journey: str,
    ticket_class: str,
    seat_count: int = 4,
    preferred_train: str = None,
):
    # Clamp to the hard max of 4
    seat_count = min(seat_count, MAX_SEATS)

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

    # await click_book_now(page, ticket_class, seat_count, preferred_train)
    return

    # selected_count = await select_seats_with_coach_fallback(page, seat_count)

    # if selected_count > 0:
    #     logger.success(f"Total seats locked: {selected_count}")
    #     # await continue_purchase(page)
    # else:
    #     logger.error("Failed to select any seats.")


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


async def get_ranked_coaches(page) -> list[tuple[int, str, str]]:
    """Return coaches sorted by available seats descending: [(seats, value, label)]."""
    coach_select = page.locator("#select-bogie")
    await coach_select.wait_for(state="visible", timeout=15_000)

    options = await coach_select.locator("option").all()
    coaches = []

    for option in options:
        text = (await option.inner_text()).strip()
        value = await option.get_attribute("value")

        try:
            seat_count = int(text.split("-")[1].strip().split(" ")[0])
        except (IndexError, ValueError):
            continue

        logger.info(f"  Coach: {text}")

        if seat_count > 0:
            coaches.append((seat_count, value, text))

    coaches.sort(key=lambda x: x[0], reverse=True)
    return coaches


async def apply_coach_selection(page, coach_value: str, coach_label: str) -> bool:
    """Select a specific coach and wait for the seat map to re-render."""
    # Skip if already selected
    current_value = await page.evaluate(
        "() => document.querySelector('#select-bogie')?.value"
    )
    if current_value == coach_value:
        logger.info(f"Coach {coach_label} already selected, skipping switch.")
        return True

    logger.info(f"Switching to coach: {coach_label} (value={coach_value})")

    # Bootstrap Select + Angular — must set value via native setter
    # and fire both 'change' and 'input' events to trigger Angular's change detection
    await page.evaluate(
        """
        (value) => {
            const select = document.querySelector('#select-bogie');
            if (!select) throw new Error('Coach select not found');

            const nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLSelectElement.prototype, 'value'
            ).set;
            nativeSetter.call(select, value);

            select.dispatchEvent(new Event('change', { bubbles: true }));
            select.dispatchEvent(new Event('input', { bubbles: true }));
        }
        """,
        coach_value,
    )

    # Wait for Angular to re-render the seat map
    await asyncio.sleep(1.5)

    # Verify the selection actually changed
    new_value = await page.evaluate(
        "() => document.querySelector('#select-bogie')?.value"
    )
    if new_value != coach_value:
        logger.warning(
            f"Coach selection failed. Expected {coach_value}, got {new_value}"
        )
        return False

    return True


SEAT_AVAILABLE = "button.btn-seat.seat-available"
SEAT_SELECTED = "button.btn-seat.seat-selected"


async def dismiss_swal2(page):
    """Dismiss any SweetAlert2 modal that may be blocking clicks."""
    swal = page.locator(".swal2-container")
    if await swal.count() > 0:
        logger.info("SweetAlert2 modal detected — dismissing...")
        # Try confirm button first, then cancel, then click backdrop
        for selector in [
            ".swal2-confirm",
            ".swal2-cancel",
            ".swal2-close",
            ".swal2-container",
        ]:
            btn = page.locator(selector)
            if await btn.count() > 0:
                try:
                    await btn.first.click(timeout=2_000)
                    await asyncio.sleep(0.5)
                    if await swal.count() == 0:
                        logger.info("SweetAlert2 dismissed.")
                        return
                except Exception:
                    continue
        # Last resort: remove it via JS
        await page.evaluate(
            "document.querySelector('.swal2-container')?.remove()"
        )
        logger.info("SweetAlert2 removed via JS.")
        await asyncio.sleep(0.3)


async def get_total_selected(page) -> int:
    """Count all currently selected seats across all coaches (DOM truth)."""
    return await page.locator(SEAT_SELECTED).count()


async def select_seats_in_current_coach(
    page, need: int, already_selected: int
) -> int:
    """
    Select up to `need` MORE seats in the currently-displayed coach.
    Returns how many NEW seats were successfully selected.

    - Checks the DOM for `seat-available` buttons and clicks them one by one.
    - After each click, verifies the total selected count went up.
    - If a click triggers a swal2 error (seat snatched), dismisses it and moves on.
    - Never deselects an already-selected seat.
    """
    await dismiss_swal2(page)

    logger.info(f"Need {need} more seat(s). Already selected: {already_selected}")

    new_selections = 0
    consecutive_failures = 0
    max_consecutive_failures = 8  # give up on this coach after too many fails

    while new_selections < need and consecutive_failures < max_consecutive_failures:
        # Dismiss modals if they reappear mid-selection
        swal = page.locator(".swal2-container")
        if await swal.count() > 0:
            await dismiss_swal2(page)
            await asyncio.sleep(0.3)

        # Fresh DOM query each iteration
        available = page.locator(SEAT_AVAILABLE)
        available_count = await available.count()

        if available_count == 0:
            logger.warning("No more available seats in this coach.")
            break

        # Snapshot selected count BEFORE clicking
        selected_before = await get_total_selected(page)

        target = available.first
        seat_title = await target.get_attribute("title") or "unknown"

        # Click the seat
        try:
            await target.dispatch_event("click")
        except Exception as e:
            logger.warning(f"Click failed on {seat_title}: {e}")
            consecutive_failures += 1
            await asyncio.sleep(0.3)
            continue

        # Brief pause for Angular to update DOM
        await asyncio.sleep(0.4)

        # Dismiss any error modal that may have appeared (seat snatched by someone)
        swal = page.locator(".swal2-container")
        if await swal.count() > 0:
            logger.warning(f"Seat {seat_title} might be snatched — swal appeared.")
            await dismiss_swal2(page)
            consecutive_failures += 1
            await asyncio.sleep(0.3)
            continue

        # Verify: did the total selected count increase?
        selected_after = await get_total_selected(page)

        if selected_after > selected_before:
            new_selections += 1
            consecutive_failures = 0
            total = already_selected + new_selections
            logger.info(
                f"✓ Seat selected: {seat_title}  "
                f"({total}/{already_selected + need} total)"
            )
        else:
            # The seat may also change to a non-available state without becoming
            # "selected" (e.g., sold-out). Check if it's gone from available.
            still_available = await page.locator(
                f"button.btn-seat.seat-available[title='{seat_title}']"
            ).count()
            if still_available > 0:
                logger.warning(
                    f"Seat {seat_title} still available after click — "
                    f"click didn't register."
                )
            else:
                logger.warning(
                    f"Seat {seat_title} disappeared but wasn't marked selected."
                )
            consecutive_failures += 1
            await asyncio.sleep(0.3)

    if new_selections > 0:
        logger.success(
            f"Selected {new_selections} new seat(s) from this coach. "
            f"Total now: {already_selected + new_selections}"
        )
    else:
        logger.warning("No new seats selected from this coach.")

    return new_selections


# async def select_seats_with_coach_fallback(
#     page, count: int = 4
# ) -> int:
#     """
#     Orchestrator: tries coaches in order of most available seats.
#     Accumulates selections across multiple coaches.

#     Returns the total number of selected seats (1 to count).
#     Selections persist when switching coaches, so we just keep adding.
#     """
#     # Clamp count to max
#     count = min(count, MAX_SEATS)

#     logger.info("Waiting for seat map to load...")

#     coach_selector = page.locator("#select-bogie")
#     has_coaches = await coach_selector.count() > 0

#     if not has_coaches:
#         # No coach dropdown — select seats directly
#         available = page.locator(SEAT_AVAILABLE)
#         await available.first.wait_for(state="visible", timeout=30_000)
#         selected = await select_seats_in_current_coach(page, need=count, already_selected=0)
#         return selected

#     # Get all coaches ranked by availability
#     coaches = await get_ranked_coaches(page)

#     if not coaches:
#         raise Exception("No coaches with available seats found.")

#     total_selected = 0

#     for seats_avail, coach_value, coach_label in coaches:
#         if total_selected >= count:
#             break

#         need = count - total_selected

#         logger.info(
#             f"Trying coach: {coach_label} ({seats_avail} seats available, "
#             f"need {need} more)"
#         )

#         ok = await apply_coach_selection(page, coach_value, coach_label)
#         if not ok:
#             continue

#         # Wait for seats to appear
#         available = page.locator(SEAT_AVAILABLE)
#         try:
#             await available.first.wait_for(state="visible", timeout=10_000)
#         except Exception:
#             logger.warning(f"No seats rendered for {coach_label}, skipping.")
#             continue

#         # Check how many are already selected (persisted from previous coaches)
#         already = await get_total_selected(page)
#         if already > total_selected:
#             # Selections persisted from previous coach switch — update our count
#             logger.info(
#                 f"Detected {already} already-selected seats after coach switch "
#                 f"(was tracking {total_selected})"
#             )
#             total_selected = already

#         if total_selected >= count:
#             logger.info("Already have enough seats, no more needed.")
#             break

#         need = count - total_selected
#         new = await select_seats_in_current_coach(
#             page, need=need, already_selected=total_selected
#         )
#         total_selected += new

#     if total_selected > 0:
#         logger.success(f"Final seat count: {total_selected}/{count}")
#     else:
#         logger.error("Could not select any seats from any coach.")

#     return total_selected


# async def continue_purchase(page):
#     continue_btn = page.locator("button.continue-btn")
#     await continue_btn.wait_for(state="visible", timeout=10_000)
#     await continue_btn.click()
#     logger.info("Clicked CONTINUE PURCHASE")
