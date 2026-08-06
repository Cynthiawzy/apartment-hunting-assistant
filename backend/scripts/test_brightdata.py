"""Manual test script for the Bright Data Facebook Marketplace scraper.

Requires BRIGHTDATA_API_KEY in .env (see README.md > Phase 4 > Facebook
Marketplace via Bright Data). Preview modes fetch + map data without touching
the database, so you can sanity-check the field mapping before trusting it to
save anything — start there.

Usage (run from backend/):
    uv run python scripts/test_brightdata.py preview-url <listing_url>
    uv run python scripts/test_brightdata.py save-url <listing_url>
    uv run python scripts/test_brightdata.py preview-search <keyword> <city> [date_listed]
    uv run python scripts/test_brightdata.py save-search <keyword> <city> [date_listed]

Examples:
    uv run python scripts/test_brightdata.py preview-search "studio" "Toronto" "Last 30 days"
    uv run python scripts/test_brightdata.py preview-url "https://www.facebook.com/marketplace/item/.../"
"""

import asyncio
import sys
from dataclasses import asdict

from app.core.database import AsyncSessionLocal
from app.services.brightdata_scraper import (
    BrightDataError,
    DiscoveryQuery,
    discover_and_save_marketplace_listings,
    discover_marketplace_records,
    fetch_marketplace_record,
    scrape_and_save_marketplace_listing,
    scrape_marketplace_listing,
)
from app.services.parsing import ScrapedListing


def _print_scraped(scraped: ScrapedListing) -> None:
    for key, value in asdict(scraped).items():
        print(f"  {key}: {value!r}")


async def preview_url(url: str) -> None:
    print("Raw record from Bright Data:")
    record = await fetch_marketplace_record(url)
    print(f"  {record}\n")

    print("Mapped to ScrapedListing:")
    scraped = await scrape_marketplace_listing(url)
    _print_scraped(scraped)


async def save_url(url: str) -> None:
    async with AsyncSessionLocal() as db:
        listing = await scrape_and_save_marketplace_listing(url, db)
    print(f"Saved listing id={listing.id}: {listing.address_line}, {listing.city} — ${listing.price}")


async def preview_search(keyword: str, city: str, date_listed: str | None) -> None:
    query = DiscoveryQuery(keyword=keyword, city=city, date_listed=date_listed)
    records = await discover_marketplace_records([query])
    print(f"Bright Data returned {len(records)} raw record(s) for {query}\n")
    for i, record in enumerate(records, 1):
        print(f"--- record {i} ---")
        print(f"  {record}\n")


async def save_search(keyword: str, city: str, date_listed: str | None) -> None:
    query = DiscoveryQuery(keyword=keyword, city=city, date_listed=date_listed)
    async with AsyncSessionLocal() as db:
        result = await discover_and_save_marketplace_listings([query], db)
    print(f"Saved {len(result.saved)}, skipped {len(result.skipped)}\n")
    for listing in result.saved:
        print(f"  SAVED id={listing.id}: {listing.address_line}, {listing.city} — ${listing.price}")
    for skip in result.skipped:
        print(f"  SKIPPED: {skip.reason}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    command, *rest = args
    try:
        if command == "preview-url" and len(rest) == 1:
            asyncio.run(preview_url(rest[0]))
        elif command == "save-url" and len(rest) == 1:
            asyncio.run(save_url(rest[0]))
        elif command == "preview-search" and len(rest) in (2, 3):
            asyncio.run(preview_search(rest[0], rest[1], rest[2] if len(rest) == 3 else None))
        elif command == "save-search" and len(rest) in (2, 3):
            asyncio.run(save_search(rest[0], rest[1], rest[2] if len(rest) == 3 else None))
        else:
            print(__doc__)
            sys.exit(1)
    except BrightDataError as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
