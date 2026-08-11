"""Bulk discovery for Kijiji: crawls a search/category results page (with
pagination) to collect individual listing URLs, then runs each one through
the generic scraper (scraper.py) to scrape, geocode, and save it.

Unlike Facebook Marketplace (services/brightdata_scraper.py), there's no
third-party API buffering this — it drives Playwright directly against
Kijiji's own pages. That's a materially different risk/footprint than a
single ad-hoc page load, so this is deliberately paced (DELAY_SECONDS
between each listing fetch) and bounded by default (max_pages/max_listings)
rather than crawling everything available — a personal apartment-hunting
tool, not a bulk scraper.
"""

import asyncio
import re
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

# A listing detail URL, e.g.
# https://www.kijiji.ca/v-apartments-condos/city-of-toronto/<slug>/<id>
# Kijiji repeats each listing several times on a results page with a
# trailing ?imageNumber=N (its thumbnail hover-carousel) — group 1 is the
# canonical URL with that query string stripped, group 2 is the listing id
# used to dedupe.
LISTING_URL_RE = re.compile(r"^(https://www\.kijiji\.ca/v-[^?]+/(\d+))(?:\?.*)?$")

# Search/category result pages end in a "cCATEGORYlLOCATION[aSUBCATEGORY]"
# segment — pagination inserts "page-N/" immediately before it. Confirmed
# against a real page's own "next page" links (page-2, ..., page-199).
PAGE_SEGMENT_RE = re.compile(r"/(c\d+l\d+(?:a\d+)?)(/?(?:\?.*)?)$")

DEFAULT_DELAY_SECONDS = 1.5
DEFAULT_MAX_PAGES = 2
DEFAULT_MAX_LISTINGS = 30


class KijijiDiscoveryError(Exception):
    """Raised when a search results page can't be loaded/paginated at all."""


def _paginated_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url
    match = PAGE_SEGMENT_RE.search(base_url)
    if not match:
        raise KijijiDiscoveryError(f"Can't paginate this search URL: {base_url}")
    prefix = base_url[: match.start()]
    return f"{prefix}/page-{page}/{match.group(1)}{match.group(2)}"


def _extract_listing_urls(hrefs: list[str | None]) -> list[str]:
    seen: dict[str, str] = {}
    for href in hrefs:
        if not href:
            continue
        match = LISTING_URL_RE.match(href)
        if not match:
            continue
        listing_id = match.group(2)
        seen.setdefault(listing_id, match.group(1))
    return list(seen.values())


async def _listing_urls_from_page(browser: Browser, url: str) -> list[str]:
    page = await browser.new_page(user_agent=USER_AGENT)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        hrefs: list[str | None] = await page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.getAttribute('href'))"
        )
    finally:
        await page.close()
    return _extract_listing_urls(hrefs)


async def list_kijiji_listing_urls(
    search_url: str, *, max_pages: int = DEFAULT_MAX_PAGES
) -> list[str]:
    """Crawls up to max_pages of a Kijiji search/category results page and
    returns every distinct listing URL found, in the order first seen."""
    all_urls: dict[str, None] = {}
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                for page_num in range(1, max_pages + 1):
                    page_url = _paginated_url(search_url, page_num)
                    urls = await _listing_urls_from_page(browser, page_url)
                    new = [u for u in urls if u not in all_urls]
                    if not new:
                        break  # empty page, or Kijiji clamped past the last real page
                    for u in new:
                        all_urls[u] = None
                    if page_num < max_pages:
                        await asyncio.sleep(DEFAULT_DELAY_SECONDS)
            finally:
                await browser.close()
    except KijijiDiscoveryError:
        raise
    except Exception as exc:  # Playwright raises its own error hierarchy; normalize it.
        raise KijijiDiscoveryError(f"Failed to load search results at {search_url}: {exc}") from exc
    return list(all_urls.keys())


@dataclass
class KijijiDiscoverySkip:
    url: str
    reason: str


@dataclass
class KijijiDiscoveryResult:
    saved: list[Listing]
    skipped: list[KijijiDiscoverySkip]


async def discover_and_save_kijiji_listings(
    search_url: str,
    db: AsyncSession,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_listings: int = DEFAULT_MAX_LISTINGS,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
) -> KijijiDiscoveryResult:
    """Crawls a Kijiji search/category page for listing URLs, then scrapes,
    geocodes, and saves each one — the same pipeline scrape_and_save runs for
    a single URL, just fed in bulk. Shares one browser across every listing
    (see fetch_page_content) and sleeps delay_seconds between each one: this
    hits Kijiji's own pages directly with no third-party buffering it, so
    pacing requests like a person browsing is a deliberate default, not
    just a performance knob."""
    urls = (await list_kijiji_listing_urls(search_url, max_pages=max_pages))[:max_listings]

    saved: list[Listing] = []
    skipped: list[KijijiDiscoverySkip] = []

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
                    scraped = parse_scraped_listing(url, fetched, source_site=SourceSite.KIJIJI)
                    listing = await geocode_and_save(scraped, db)
                    saved.append(listing)
                except (ScraperError, DuplicateListingError) as exc:
                    skipped.append(KijijiDiscoverySkip(url, str(exc)))
                except PlaywrightError as exc:  # a single bad page shouldn't abort the whole crawl
                    skipped.append(KijijiDiscoverySkip(url, f"Failed to load: {exc}"))

                if i < len(urls) - 1:
                    await asyncio.sleep(delay_seconds)
        finally:
            await browser.close()

    return KijijiDiscoveryResult(saved=saved, skipped=skipped)
