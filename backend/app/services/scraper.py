import json
from datetime import UTC, datetime
from typing import Any

from playwright.async_api import async_playwright
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.listings import create_listing
from app.models.listing import Listing, SourceSite
from app.schemas.listing import ListingCreate
from app.services.geocoding import geocode_address
from app.services.parsing import (
    ScrapedListing,
    derive_source_listing_id,
    extract_contact,
    infer_source_site,
    parse_address,
    parse_bathrooms,
    parse_bedrooms,
    parse_price,
    parse_sqft,
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

JSONLD_LISTING_TYPES = {
    "apartment",
    "house",
    "product",
    "realestatelisting",
    "singlefamilyresidence",
    "residence",
    "accommodation",
}


class ScraperError(Exception):
    """Raised when a listing page can't be loaded or required fields can't be extracted."""


def _extract_json_ld(raw_scripts: list[str]) -> dict[str, Any] | None:
    """Looks for schema.org listing markup, which most real estate sites embed for SEO."""
    for raw in raw_scripts:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            type_field = candidate.get("@type", "")
            types = type_field if isinstance(type_field, list) else [type_field]
            if any(str(t).lower() in JSONLD_LISTING_TYPES for t in types):
                return candidate
    return None


def _coerce_price_from_jsonld(data: dict[str, Any]) -> float | None:
    offers = data.get("offers")
    for source in (offers if isinstance(offers, dict) else None, data):
        if source and "price" in source:
            try:
                return float(str(source["price"]).replace(",", ""))
            except ValueError:
                continue
    return None


def _coerce_address_from_jsonld(data: dict[str, Any]) -> tuple[str, str, str, str] | None:
    address = data.get("address")
    if not isinstance(address, dict):
        return None
    street, city = address.get("streetAddress"), address.get("addressLocality")
    state, zip_code = address.get("addressRegion"), address.get("postalCode")
    if street and city and state and zip_code:
        return str(street), str(city), str(state), str(zip_code)
    return None


def _coerce_sqft_from_jsonld(data: dict[str, Any]) -> int | None:
    floor_size = data.get("floorSize")
    if isinstance(floor_size, dict) and "value" in floor_size:
        try:
            return int(float(str(floor_size["value"])))
        except ValueError:
            return None
    return None


def _jsonld_number(data: dict[str, Any] | None, *keys: str) -> float | None:
    if not data:
        return None
    for key in keys:
        if key in data:
            try:
                return float(data[key])
            except (TypeError, ValueError):
                continue
    return None


async def scrape_listing(url: str, *, source_site: SourceSite | None = None) -> ScrapedListing:
    """Loads a listing page with Playwright and extracts structured data.

    Tries schema.org JSON-LD first (common on real estate sites for SEO), then
    falls back to heuristic text parsing of the rendered page. Raises
    ScraperError if required fields (price, address, beds, baths) can't be
    found by either method — incomplete data is never silently saved.
    """
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent=USER_AGENT)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                title = await page.title()
                raw_scripts: list[str] = await page.eval_on_selector_all(
                    'script[type="application/ld+json"]', "els => els.map(e => e.textContent)"
                )
                body_text = await page.inner_text("body")
            finally:
                await browser.close()
    except Exception as exc:  # Playwright raises its own error hierarchy; normalize it.
        raise ScraperError(f"Failed to load {url}: {exc}") from exc

    listing_data = _extract_json_ld(raw_scripts)

    price = (_coerce_price_from_jsonld(listing_data) if listing_data else None) or parse_price(
        body_text
    )
    address_parts = (
        _coerce_address_from_jsonld(listing_data) if listing_data else None
    ) or parse_address(body_text)
    sqft = (_coerce_sqft_from_jsonld(listing_data) if listing_data else None) or parse_sqft(
        body_text
    )

    description = None
    if listing_data and isinstance(listing_data.get("description"), str):
        description = listing_data["description"]

    bedrooms = _jsonld_number(listing_data, "numberOfBedrooms", "numberOfRooms")
    if bedrooms is None:
        bedrooms = parse_bedrooms(body_text)

    bathrooms = _jsonld_number(listing_data, "numberOfBathroomsTotal", "numberOfBathrooms")
    if bathrooms is None:
        bathrooms = parse_bathrooms(body_text)

    phone, email = extract_contact(body_text)

    # bathrooms is intentionally excluded: shared-housing "private room"
    # listings often genuinely have none to report.
    required = {
        "price": price,
        "address": address_parts,
        "bedrooms": bedrooms,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise ScraperError(f"Could not extract required field(s) {missing} from {url}")

    assert address_parts is not None and price is not None
    assert bedrooms is not None
    address_line, city, state, zip_code = address_parts

    body_excerpt = body_text.strip()[:1000] or None
    final_description = description or body_excerpt
    # Don't prepend the title if the body excerpt already starts with it (common
    # when falling back to raw body text, since it usually includes the <h1>).
    if title and (not final_description or not final_description.startswith(title)):
        final_description = f"{title}\n\n{final_description}" if final_description else title

    return ScrapedListing(
        source_site=source_site or infer_source_site(url),
        source_listing_id=derive_source_listing_id(url),
        url=url,
        address_line=address_line,
        city=city,
        state=state,
        zip_code=zip_code,
        price=price,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        sqft=sqft,
        description=final_description,
        landlord_name=None,
        landlord_phone=phone,
        landlord_email=email,
    )


async def geocode_and_save(scraped: ScrapedListing, db: AsyncSession) -> Listing:
    """Shared tail of every scraping pipeline: geocode the address, build the
    final ListingCreate (which needs real coordinates), and persist it. Used by
    both the Playwright scraper and the Bright Data client (services/brightdata_scraper.py)
    so every source builds/saves listings identically."""
    geocode_query = scraped.geocode_query or scraped.full_address
    coordinates = await geocode_address(geocode_query)
    if coordinates is None:
        raise ScraperError(f"Could not geocode address: {geocode_query!r}")

    # Some sources (e.g. Facebook Marketplace) don't reliably provide a zip, or
    # even a state — fall back to whatever Nominatim resolved for the geocoded
    # point. state must end up exactly 2 chars (ListingCreate's schema) or the
    # save below fails validation, so an unresolvable state is a real error,
    # not silently defaulted to something wrong.
    zip_code = scraped.zip_code or coordinates.postal_code or ""
    state = scraped.state if len(scraped.state) == 2 else coordinates.region_code
    if not state or len(state) != 2:
        raise ScraperError(
            f"Could not resolve a valid 2-letter state/province for {scraped.city!r} "
            f"(got {scraped.state!r} from source, {coordinates.region_code!r} from geocoding)"
        )

    payload = ListingCreate(
        source_site=scraped.source_site,
        source_listing_id=scraped.source_listing_id,
        url=scraped.url,
        address_line=scraped.address_line,
        unit=scraped.unit,
        city=scraped.city,
        state=state,
        zip_code=zip_code,
        latitude=coordinates.latitude,
        longitude=coordinates.longitude,
        price=scraped.price,
        bedrooms=scraped.bedrooms,
        bathrooms=scraped.bathrooms,
        sqft=scraped.sqft,
        pet_friendly=None,
        amenities=None,
        landlord_name=scraped.landlord_name,
        landlord_phone=scraped.landlord_phone,
        landlord_email=scraped.landlord_email,
        description=scraped.description,
        status=scraped.status,
        scraped_at=datetime.now(UTC).date(),
        neighborhood_id=None,
    )

    return await create_listing(db, payload)


async def scrape_and_save(
    url: str, db: AsyncSession, *, source_site: SourceSite | None = None
) -> Listing:
    """Full pipeline: scrape the page, geocode the address, and persist the listing."""
    scraped = await scrape_listing(url, source_site=source_site)
    return await geocode_and_save(scraped, db)
