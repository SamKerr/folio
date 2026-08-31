from playwright.async_api import async_playwright


async def run_doctor() -> None:
    """Launch Chromium and load a blank page to verify Playwright is working."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto("about:blank")
        finally:
            await browser.close()
