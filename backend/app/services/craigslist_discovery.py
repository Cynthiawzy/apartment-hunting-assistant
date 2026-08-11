"""Bulk discovery for Craigslist: loads a search results page and scrolls it
(triggering the same infinite-scroll batch loading a real user's browsing
would) to collect individual listing URLs, then runs each one through the
generic scraper (scraper.py) to scrape, geocode, and save it.

Craigslist's modern search UI has no classic "?page=N"/"?s=120" pagination —
results load via virtualized batches as the page scrolls (confirmed against
a real search page: ~200 result cards render initially, ~300 after six
scroll-and-wait cycles). Mirrors kijiji_discovery.py's structure/pacing
otherwise: no third-party API buffering this, so it's deliberately paced and
bounded by default rather than crawling everything available.
"""

import asyncio
from dataclasses import dataclass

from playwright.async_api import Browser, async_playwright
from playwright.async_api import Error as PlaywrightError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.listings import DuplicateListingError
from app.models.listing import Listing, SourceSite
from app.services.scraper import (
    USER_AGENT,
    ScraperError,
    fetch_page_content,
    geocode_and_save,
    parse_scraped_listing,
)

# Individual result cards on a search page; the real detail link is the
# nested <a class="main">, not the card div itself. Confirmed against a real
# search page's rendered DOM.
LISTING_LINK_SELECTOR = ".gallery-card a.main"

DEFAULT_DELAY_SECONDS = 1.5
DEFAULT_MAX_SCROLLS = 6
DEFAULT_SCROLL_WAIT_SECONDS = 0.6
DEFAULT_MAX_LISTINGS = 30


class CraigslistDiscoveryError(Exception):
    """Raised when a search results page can't be loaded at all."""


async def _listing_urls_from_search_page(browser: Browser, url: str, max_scrolls: int) -> list[str]:
    page = await browser.new_page(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900})
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)
        for _ in range(max_scrolls):
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(int(DEFAULT_SCROLL_WAIT_SECONDS * 1000))

        hrefs: list[str] = await page.eval_on_selector_all(
            LISTING_LINK_SELECTOR, "els => els.map(e => e.href)"
        )
    finally:
        await page.close()
    return list(dict.fromkeys(hrefs))  # dedupe, preserve first-seen order


async def list_craigslist_listing_urls(
    search_url: str, *, max_scrolls: int = DEFAULT_MAX_SCROLLS
) -> list[str]:
    """Loads a Craigslist search results page, scrolls it to trigger more
    batches to load, and returns every distinct listing URL found."""
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                return await _listing_urls_from_search_page(browser, search_url, max_scrolls)
            finally:
                await browser.close()
    except Exception as exc:  # Playwright raises its own error hierarchy; normalize it.
        raise CraigslistDiscoveryError(
            f"Failed to load search results at {search_url}: {exc}"
        ) from exc


@dataclass
class CraigslistDiscoverySkip:
    url: str
    reason: str


@dataclass
class CraigslistDiscoveryResult:
    saved: list[Listing]
    skipped: list[CraigslistDiscoverySkip]


async def discover_and_save_craigslist_listings(
    search_url: str,
    db: AsyncSession,
    *,
    max_scrolls: int = DEFAULT_MAX_SCROLLS,
    max_listings: int = DEFAULT_MAX_LISTINGS,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
) -> CraigslistDiscoveryResult:
    """Crawls a Craigslist search page for listing URLs, then scrapes,
    geocodes, and saves each one — the same pipeline scrape_and_save runs for
    a single URL, just fed in bulk. Shares one browser across every listing
    and sleeps delay_seconds between each one: this hits Craigslist's own
    pages directly with no third-party buffering it, so pacing requests like
    a person browsing is a deliberate default, not just a performance knob."""
    urls = (await list_craigslist_listing_urls(search_url, max_scrolls=max_scrolls))[
        :max_listings
    ]

    saved: list[Listing] = []
    skipped: list[CraigslistDiscoverySkip] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            for i, url in enumerate(urls):
                try:
                    page = await browser.new_page(user_agent=USER_AGENT)
                    try:
                        fetched = await fetch_page_content(page, url)
                    finally:
                        await page.close()
                    scraped = parse_scraped_listing(
                        url, fetched, source_site=SourceSite.CRAIGSLIST
                    )
                    listing = await geocode_and_save(scraped, db)
                    saved.append(listing)
                except (ScraperError, DuplicateListingError) as exc:
                    skipped.append(CraigslistDiscoverySkip(url, str(exc)))
                except PlaywrightError as exc:  # a single bad page shouldn't abort the crawl
                    skipped.append(CraigslistDiscoverySkip(url, f"Failed to load: {exc}"))

                if i < len(urls) - 1:
                    await asyncio.sleep(delay_seconds)
        finally:
            await browser.close()

    return CraigslistDiscoveryResult(saved=saved, skipped=skipped)
