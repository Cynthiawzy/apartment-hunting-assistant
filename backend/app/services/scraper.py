import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, async_playwright
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.listings import create_listing
from app.models.listing import Listing, SourceSite
from app.schemas.listing import ListingCreate
from app.services.geocoding import geocode_address
from app.services.parsing import (
    NO_STREET_ADDRESS_PLACEHOLDER,
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


# Kijiji's schema.org JSON-LD only lists ~4 preview images even when a
# listing has many more — the rest only load into the DOM after clicking the
# gallery's "+N" expand control. Confirmed against a real listing: JSON-LD
# gave 4 images, but the full gallery (after clicking "+9") had 12 distinct
# photos. Same underlying photo can appear at multiple resolutions
# (thumbnail vs. full-size) with the same UUID in its CDN path — dedupe on
# that and keep the highest-resolution ("640") variant.
KIJIJI_GALLERY_EXPAND_SELECTOR = '[data-testid="gallery-carousel-button"]'
KIJIJI_GALLERY_IMAGE_SELECTOR = (
    '[data-testid="gallery-thumbnail"] img, [data-testid="gallery-slide-image"]'
)
KIJIJI_IMAGE_UUID_RE = re.compile(r"/images/[0-9a-f]{2}/([0-9a-f-]{36})")


async def _kijiji_gallery_images(page: Page) -> list[str] | None:
    expand_button = page.locator(KIJIJI_GALLERY_EXPAND_SELECTOR).first
    if await expand_button.count() > 0:
        try:
            await expand_button.click(timeout=3000)
            await page.wait_for_timeout(800)
        except PlaywrightError:
            pass  # fall through and use whatever thumbnails are already in the DOM

    srcs: list[str] = await page.eval_on_selector_all(
        KIJIJI_GALLERY_IMAGE_SELECTOR, "els => els.map(e => e.currentSrc || e.src || '')"
    )
    by_uuid: dict[str, str] = {}
    for src in srcs:
        # Excludes non-photo media the same gallery can surface (e.g. a
        # YouTube video-tour thumbnail) — only the listing's own CDN photos.
        if "media.kijiji.ca" not in src:
            continue
        match = KIJIJI_IMAGE_UUID_RE.search(src)
        if not match:
            continue
        uuid = match.group(1)
        if uuid not in by_uuid or "640" in src:
            by_uuid[uuid] = src
    return list(by_uuid.values()) or None


# Craigslist's photo strip only eagerly loads the first slide at full
# resolution (e.g. ".../00A0A_16FuSOMdhjP_05603M_600x450.jpg") — the rest sit
# in the DOM as small nav thumbnails (".../..._50x50c.jpg") until the slider
# is clicked. Confirmed against a real listing: swapping just the trailing
# "_WxHc.jpg" size suffix for "_600x450.jpg" on a thumbnail URL (same image
# id, no interaction needed) returns a real, valid full-size photo.
CRAIGSLIST_IMAGE_SRC_RE = re.compile(r"images\.craigslist\.org/\w+_\d+x\d+c?\.jpg", re.IGNORECASE)
CRAIGSLIST_THUMB_SUFFIX_RE = re.compile(r"_\d+x\d+c?\.jpg$", re.IGNORECASE)


async def _craigslist_gallery_images(page: Page) -> list[str] | None:
    srcs: list[str] = await page.eval_on_selector_all("img", "els => els.map(e => e.src)")
    seen: dict[str, str] = {}
    for src in srcs:
        if not CRAIGSLIST_IMAGE_SRC_RE.search(src):
            continue
        full_size = CRAIGSLIST_THUMB_SUFFIX_RE.sub("_600x450.jpg", src)
        # Same photo can appear twice (thumbnail strip + the eagerly-loaded
        # first slide) — key on the URL with the size suffix stripped so
        # both collapse to one entry.
        key = CRAIGSLIST_THUMB_SUFFIX_RE.sub("", src)
        seen[key] = full_size
    return list(seen.values()) or None


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
    if isinstance(address, str):
        # Some sites (e.g. Kijiji) put a single formatted string here instead
        # of a structured PostalAddress — same "street, city, ST/PROV zip"
        # shape parse_address already handles for body text, just via JSON-LD
        # instead of free text.
        return parse_address(address)
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


def _coerce_images_from_jsonld(data: dict[str, Any]) -> list[str] | None:
    """schema.org's `image` can be a single URL string, an array of URL
    strings, a single ImageObject, or an array of ImageObjects — normalizes
    all four shapes to a flat list of URL strings."""
    image = data.get("image")
    if image is None:
        return None
    candidates = image if isinstance(image, list) else [image]

    urls: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.startswith("http"):
            urls.append(candidate)
        elif isinstance(candidate, dict):
            # contentUrl (schema.org: "actual bytes of the media object") checked
            # first — confirmed necessary against real data: Kijiji's ImageObject
            # sets `url` to the *listing page's* URL (not the image) and puts the
            # real photo CDN URL in `contentUrl` instead.
            url = candidate.get("contentUrl") or candidate.get("url")
            if isinstance(url, str) and url.startswith("http"):
                urls.append(url)
    return urls or None


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


def _coerce_bedrooms_from_jsonld(data: dict[str, Any] | None) -> float | None:
    """numberOfBedrooms is usually a plain number, but some sites (e.g. Kijiji)
    use descriptive strings instead — "Bachelor/Studio" or "1 + Den" — that
    _jsonld_number's float() can't parse. Handles those without changing
    behavior for the plain-numeric case every other field still uses."""
    if not data:
        return None
    for key in ("numberOfBedrooms", "numberOfRooms"):
        value = data.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
        text = str(value)
        if re.search(r"bachelor|studio", text, re.IGNORECASE):
            return 0.0
        match = re.search(r"\d+(?:\.\d+)?", text)
        if match:
            return float(match.group(0))
    return None


@dataclass
class FetchedPage:
    title: str
    raw_scripts: list[str]
    body_text: str
    # Set only for Kijiji (see _kijiji_gallery_images) — takes priority over
    # whatever _coerce_images_from_jsonld finds in raw_scripts, since it's a
    # strict superset in practice (JSON-LD's handful of preview images are
    # also present in the full DOM gallery).
    dom_images: list[str] | None = None
    # Set only for Craigslist — its JSON-LD Apartment block has no
    # description field at all, so without this, parse_scraped_listing's
    # fallback (the first 1000 chars of the whole page's visible text) picks
    # up nav/breadcrumb clutter ("CL / boston > / housing > / apartments...")
    # instead of the actual posting. #postingbody is a stable, well-known
    # selector for the real text.
    dom_description: str | None = None


async def fetch_page_content(page: Page, url: str) -> FetchedPage:
    """Loads a URL in an already-open Playwright page and pulls out the raw
    material parse_scraped_listing needs. Split out from scrape_listing so a
    bulk crawl (e.g. kijiji_discovery.py) can share one browser/page across
    many listings instead of paying Chromium's launch cost per listing."""
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    title = await page.title()
    raw_scripts: list[str] = await page.eval_on_selector_all(
        'script[type="application/ld+json"]', "els => els.map(e => e.textContent)"
    )
    body_text = await page.inner_text("body")

    dom_images = None
    dom_description = None
    site = infer_source_site(url)
    if site == SourceSite.KIJIJI:
        dom_images = await _kijiji_gallery_images(page)
    elif site == SourceSite.CRAIGSLIST:
        dom_images = await _craigslist_gallery_images(page)
        posting_body = page.locator("#postingbody").first
        if await posting_body.count() > 0:
            dom_description = (await posting_body.inner_text()).strip() or None

    return FetchedPage(title, raw_scripts, body_text, dom_images, dom_description)


def parse_scraped_listing(
    url: str,
    fetched: FetchedPage,
    *,
    source_site: SourceSite | None = None,
) -> ScrapedListing:
    """Turns already-fetched page content into a ScrapedListing. Tries
    schema.org JSON-LD first (common on real estate sites for SEO), then
    falls back to heuristic text parsing of the rendered page. Raises
    ScraperError if required fields (price, address, beds, baths) can't be
    found by either method — incomplete data is never silently saved.
    """
    title, raw_scripts, body_text = fetched.title, fetched.raw_scripts, fetched.body_text
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
    elif fetched.dom_description:
        description = fetched.dom_description

    images = fetched.dom_images or (
        _coerce_images_from_jsonld(listing_data) if listing_data else None
    )

    bedrooms = _coerce_bedrooms_from_jsonld(listing_data)
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
        images=images,
        description=final_description,
        landlord_name=None,
        landlord_phone=phone,
        landlord_email=email,
    )


async def scrape_listing(url: str, *, source_site: SourceSite | None = None) -> ScrapedListing:
    """Loads a listing page with its own dedicated Playwright browser and
    parses it. For scraping many URLs in one run, prefer sharing a single
    browser across fetch_page_content calls instead (see kijiji_discovery.py)
    — launching a fresh Chromium process per listing doesn't scale."""
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent=USER_AGENT)
                fetched = await fetch_page_content(page, url)
            finally:
                await browser.close()
    except Exception as exc:  # Playwright raises its own error hierarchy; normalize it.
        raise ScraperError(f"Failed to load {url}: {exc}") from exc

    return parse_scraped_listing(url, fetched, source_site=source_site)


async def geocode_and_save(scraped: ScrapedListing, db: AsyncSession) -> Listing:
    """Shared tail of every scraping pipeline: geocode the address, build the
    final ListingCreate (which needs real coordinates), and persist it. Used by
    both the Playwright scraper and the Bright Data client (services/brightdata_scraper.py)
    so every source builds/saves listings identically."""
    geocode_query = scraped.geocode_query or scraped.full_address
    coordinates = await geocode_address(geocode_query)

    address_line = scraped.address_line
    if coordinates is None and scraped.geocode_fallback_query:
        coordinates = await geocode_address(scraped.geocode_fallback_query)
        if coordinates is not None:
            # The precise attempt (e.g. a cross-street intersection) didn't
            # resolve, so the address_line describing it (e.g. "Near X & Y")
            # would now be inconsistent with the coarser point we actually
            # got — don't display precision the stored coordinates don't have.
            address_line = NO_STREET_ADDRESS_PLACEHOLDER

    if coordinates is None:
        # Last-resort city-level attempt, generic across every source (not
        # just ones that set geocode_fallback_query explicitly) — confirmed
        # necessary against real data: Nominatim doesn't resolve "28
        # Brookledge St, Dorchester, MA" at all (Dorchester is a Boston
        # neighborhood, not its own municipality in OSM's addressing), but
        # "Dorchester, MA" alone resolves fine.
        city_level_query = f"{scraped.city}, {scraped.state}" if scraped.state else scraped.city
        if city_level_query not in (geocode_query, scraped.geocode_fallback_query):
            coordinates = await geocode_address(city_level_query)
            if coordinates is not None:
                address_line = NO_STREET_ADDRESS_PLACEHOLDER
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
        address_line=address_line,
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
        images=scraped.images,
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
