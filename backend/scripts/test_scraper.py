"""Manual test script for the generic Playwright scraper (scraper.py) — the
direct-website path (Kijiji, Craigslist, StreetEasy, etc.), as opposed to
Facebook Marketplace's Bright Data path (see test_brightdata.py).

preview/list modes fetch + parse without touching the database, so you can
sanity-check the field mapping before trusting it to save anything.

Usage (run from backend/):
    uv run python scripts/test_scraper.py preview <listing_url>
    uv run python scripts/test_scraper.py save <listing_url>
    uv run python scripts/test_scraper.py list-kijiji <search_url> [max_pages]
    uv run python scripts/test_scraper.py save-kijiji <search_url> [max_pages] [max_listings]
    uv run python scripts/test_scraper.py list-craigslist <search_url> [max_scrolls]
    uv run python scripts/test_scraper.py save-craigslist <search_url> [max_scrolls] [max_listings]

Examples:
    uv run python scripts/test_scraper.py preview "https://www.kijiji.ca/v-apartments-condos/city-of-toronto/.../1740239384"
    uv run python scripts/test_scraper.py list-kijiji "https://www.kijiji.ca/b-apartments-condos/city-of-toronto/c37l1700273" 2
    uv run python scripts/test_scraper.py save-kijiji "https://www.kijiji.ca/b-apartments-condos/city-of-toronto/c37l1700273" 2 30
    uv run python scripts/test_scraper.py list-craigslist "https://boston.craigslist.org/search/apa" 6
    uv run python scripts/test_scraper.py save-craigslist "https://boston.craigslist.org/search/apa" 6 30
"""

import asyncio
import sys
from dataclasses import asdict

from app.core.database import AsyncSessionLocal
from app.services.craigslist_discovery import (
    CraigslistDiscoveryError,
    discover_and_save_craigslist_listings,
    list_craigslist_listing_urls,
)
from app.services.kijiji_discovery import (
    KijijiDiscoveryError,
    discover_and_save_kijiji_listings,
    list_kijiji_listing_urls,
)
from app.services.scraper import ScraperError, scrape_and_save, scrape_listing


async def preview(url: str) -> None:
    scraped = await scrape_listing(url)
    for key, value in asdict(scraped).items():
        print(f"  {key}: {value!r}")


async def save(url: str) -> None:
    async with AsyncSessionLocal() as db:
        listing = await scrape_and_save(url, db)
        print(
            f"Saved listing id={listing.id}: {listing.address_line}, "
            f"{listing.city} — ${listing.price}"
        )


async def list_kijiji(search_url: str, max_pages: int) -> None:
    urls = await list_kijiji_listing_urls(search_url, max_pages=max_pages)
    print(f"Found {len(urls)} distinct listing(s) across up to {max_pages} page(s):\n")
    for url in urls:
        print(f"  {url}")


async def save_kijiji(search_url: str, max_pages: int, max_listings: int) -> None:
    async with AsyncSessionLocal() as db:
        result = await discover_and_save_kijiji_listings(
            search_url, db, max_pages=max_pages, max_listings=max_listings
        )
        # Printed inside the session block, not after — each geocode_and_save
        # commit during the loop expires every object already in the session
        # (SQLAlchemy's default expire_on_commit), so accessing e.g.
        # listing.address_line on an earlier result after the session closes
        # raises DetachedInstanceError. Confirmed by a real crash on a 150+
        # listing batch.
        print(f"Saved {len(result.saved)}, skipped {len(result.skipped)}\n")
        for listing in result.saved:
            print(f"  SAVED id={listing.id}: {listing.address_line}, {listing.city} — ${listing.price}")
    for skip in result.skipped:
        print(f"  SKIPPED {skip.url}: {skip.reason}")


async def list_craigslist(search_url: str, max_scrolls: int) -> None:
    urls = await list_craigslist_listing_urls(search_url, max_scrolls=max_scrolls)
    print(f"Found {len(urls)} distinct listing(s) after {max_scrolls} scroll(s):\n")
    for url in urls:
        print(f"  {url}")


async def save_craigslist(search_url: str, max_scrolls: int, max_listings: int) -> None:
    async with AsyncSessionLocal() as db:
        result = await discover_and_save_craigslist_listings(
            search_url, db, max_scrolls=max_scrolls, max_listings=max_listings
        )
        print(f"Saved {len(result.saved)}, skipped {len(result.skipped)}\n")
        for listing in result.saved:
            print(f"  SAVED id={listing.id}: {listing.address_line}, {listing.city} — ${listing.price}")
    for skip in result.skipped:
        print(f"  SKIPPED {skip.url}: {skip.reason}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    command, *rest = args
    try:
        if command == "preview" and len(rest) == 1:
            asyncio.run(preview(rest[0]))
        elif command == "save" and len(rest) == 1:
            asyncio.run(save(rest[0]))
        elif command == "list-kijiji" and len(rest) in (1, 2):
            max_pages = int(rest[1]) if len(rest) == 2 else 2
            asyncio.run(list_kijiji(rest[0], max_pages))
        elif command == "save-kijiji" and len(rest) in (1, 2, 3):
            max_pages = int(rest[1]) if len(rest) >= 2 else 2
            max_listings = int(rest[2]) if len(rest) == 3 else 30
            asyncio.run(save_kijiji(rest[0], max_pages, max_listings))
        elif command == "list-craigslist" and len(rest) in (1, 2):
            max_scrolls = int(rest[1]) if len(rest) == 2 else 6
            asyncio.run(list_craigslist(rest[0], max_scrolls))
        elif command == "save-craigslist" and len(rest) in (1, 2, 3):
            max_scrolls = int(rest[1]) if len(rest) >= 2 else 6
            max_listings = int(rest[2]) if len(rest) == 3 else 30
            asyncio.run(save_craigslist(rest[0], max_scrolls, max_listings))
        else:
            print(__doc__)
            sys.exit(1)
    except (ScraperError, KijijiDiscoveryError, CraigslistDiscoveryError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
