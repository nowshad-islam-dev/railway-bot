import asyncio
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from loguru import logger

# async def select_autocomplete(page, input_selector: str, search_text: str, label: str):
#     """
#     Handles jQuery UI autocomplete fields correctly.
#     The ul may exist in DOM but be hidden — wait for the wrapper to be visible first.
#     """
#     input_el = page.locator(input_selector)
#     await input_el.click()
#     await input_el.clear()
#     await input_el.press_sequentially(search_text, delay=100)

#     # Wait for the autocomplete LIST to become visible first
#     # jQuery UI sets display:none on the ul, not the li
#     autocomplete_list = page.locator("ul.ui-autocomplete")
#     await autocomplete_list.wait_for(state="visible", timeout=10_000)

#     # Now wait for at least one item to be visible inside it
#     first_item = autocomplete_list.locator("li.ui-menu-item").first
#     await first_item.wait_for(state="visible", timeout=5_000)
#     await first_item.click()

#     logger.info(f"Selected {label}: {search_text}")
#     await asyncio.sleep(0.4)

async def select_autocomplete(page, input_selector: str, search_text: str, label: str):
    input_el = page.locator(input_selector)
    await input_el.click()
    await input_el.clear()
    await input_el.press_sequentially(search_text, delay=100)

    # Get the aria-owns attribute from the input — jQuery UI links input to its dropdown via this
    # e.g. aria-owns="ui-id-1" tells us which ul belongs to this input
    owned_list_id = await input_el.get_attribute("aria-owns")

    if owned_list_id:
        autocomplete_list = page.locator(f"#{owned_list_id}")
    else:
        # Fallback: scope by proximity — the visible one
        autocomplete_list = page.locator("ul.ui-autocomplete:visible").first

    await autocomplete_list.wait_for(state="visible", timeout=10_000)

    first_item = autocomplete_list.locator("li.ui-menu-item").first
    await first_item.wait_for(state="visible", timeout=5_000)
    await first_item.click()

    logger.info(f"Selected {label}: {search_text}")
    await asyncio.sleep(0.4)

async def search_trains(
    page,
    from_station: str,
    to_station: str,
    journey_date: str,  # Format: "11-May-2026"
    seat_class: str,    # e.g. "AC_B", "SNIGDHA", "S_CHAIR"
):
    """
    Fills and submits the train search form.
    
    from_station / to_station: Type partial name, wait for autocomplete, select first match.
    journey_date: Must match the site's hidden input format — "DD-Mon-YYYY" e.g. "15-May-2026"
    seat_class: Must exactly match option values in the select element.
    """
    logger.info(f"Searching trains: {from_station} → {to_station} on {journey_date} [{seat_class}]")
    
    await select_autocomplete(page, "#dest_from", from_station, "from station")
    await select_autocomplete(page, "#dest_to", to_station, "to station")

    # --- Journey Date ---
    # The visible input is readonly (datepicker only). 
    # Set the hidden input value directly via JS and trigger Angular's change detection.
    await page.evaluate(
        """
        (date) => {
            // Find the hidden input with formcontrolname="doj"
            const hiddenInput = document.querySelector('input[formcontrolname="doj"]');
            if (!hiddenInput) throw new Error('Hidden date input not found');
            
            // Angular uses __ngContext__ or nativeElement — 
            // trigger both native input event and Angular's internal update
            const nativeInputSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeInputSetter.call(hiddenInput, date);
            hiddenInput.dispatchEvent(new Event('input', { bubbles: true }));
            hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        journey_date,
    )

    # Also update the visible readonly datepicker display (cosmetic but avoids Angular mismatch)
    await page.evaluate(
        """
        (date) => {
            const visibleInput = document.querySelector('#doj');
            if (visibleInput) visibleInput.value = date;
        }
        """,
        journey_date,
    )
    logger.info(f"Set journey date: {journey_date}")
    await asyncio.sleep(0.3)

    # --- Seat Class ---
    class_select = page.locator("#choose_class")
    await class_select.wait_for(state="visible", timeout=5_000)
    await class_select.select_option(value=seat_class)
    logger.info(f"Selected class: {seat_class}")
    await asyncio.sleep(0.3)

    # --- Submit ---
    # Wait for Angular to re-enable the button (form becomes valid)
    search_btn = page.locator("#trainsearch button[type='submit']")
    try:
        await search_btn.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError:
        raise Exception(
            "Search button still disabled after filling form. "
            "Angular form validation likely failed — check station names or date format."
        )

    await search_btn.click()
    logger.info("Search submitted. Waiting for results...")

    # Wait for results to load — adjust selector after inspecting results page
    results_container = page.locator(
        "#search-result, .train-list, [class*='result'], app-trainlist"
    )
    try:
        await results_container.first.wait_for(state="visible", timeout=20_000)
        logger.success("Train results loaded.")
    except PlaywrightTimeoutError:
        await page.screenshot(path="search_error.png")
        raise Exception("Results did not load. Screenshot saved.")