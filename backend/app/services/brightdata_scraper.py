"""Facebook Marketplace listings via Bright Data's Web Scraper API.

We don't scrape facebook.com ourselves — Meta's Terms of Service prohibit
automated collection, and their anti-bot defenses are extensive. Bright Data
operates as a third-party data provider; per their license agreement, using
their API doesn't transfer any ToS-compliance risk away from us as the
customer, so this is only a lower-risk *technical* path (no browser automation
of our own against Meta's defenses), not a legal blank check.

API reference (https://docs.brightdata.com/api-reference/...):
  1. POST /datasets/v3/trigger?dataset_id=... -> {"snapshot_id": "..."}
  2. GET  /datasets/v3/progress/{snapshot_id}   (poll until status is ready/failed)
  3. GET  /datasets/v3/snapshot/{snapshot_id}?format=json -> [record, ...]

Field mapping is confirmed against real records (both a single non-housing
example and a real 792-result rental search): url, title, initial_price,
final_price, currency, product_id, location (usually null for discovery-mode
results — see the discovery_input.city fallback below), description,
seller_description, is_sold, discovery_input, plus category-specific fields
like condition/color/brand/car_miles that only apply to non-housing
categories and are harmlessly ignored here. There is no seller name/phone/
email field at all — Marketplace contact happens via Messenger, not a public
API field — so landlord_phone/email only ever come from whatever a seller
happened to type into the description text. Bedrooms/bathrooms/sqft aren't
dedicated fields even for real rental records, so those go through the same
regex fallback scraper.py uses for pages without JSON-LD. bathrooms is
allowed to end up None: a real, common category is "private room for rent"
in shared housing, which has no dedicated bathroom count to report.
"""

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crud.listings import DuplicateListingError
from app.models.listing import Listing, ListingStatus, SourceSite
from app.services.parsing import (
    ScrapedListing,
    derive_source_listing_id,
    extract_contact,
    parse_address,
    parse_bathrooms,
    parse_bedrooms,
    parse_price,
    parse_sqft,
)
from app.services.scraper import ScraperError, geocode_and_save

BASE_URL = "https://api.brightdata.com"
DATASET_ID = "gd_lvt9iwuh6fbcwmx1a"  # Bright Data's Facebook Marketplace collector

POLL_INTERVAL_SECONDS = 5.0
# Confirmed against a real keyword+city search: took ~4 minutes end-to-end
# (discovery has to actually crawl/search, unlike a single-URL fetch). 300s
# gives comfortable margin over that observed real-world duration.
POLL_TIMEOUT_SECONDS = 300.0
# Per-request timeout for the httpx client (connect/read per call, not
# cumulative) — polling itself is bounded by POLL_TIMEOUT_SECONDS above. Kept
# generous because the initial POST can itself block up to ~60s server-side
# before falling back to a 202 + snapshot_id.
DISCOVERY_TIMEOUT_SECONDS = 90.0

CITY_STATE_RE = re.compile(r"([A-Za-z .'\-]+?),\s*([A-Z]{2})\b")

NO_STREET_ADDRESS_PLACEHOLDER = (
    "Exact address not public (Facebook Marketplace) — contact seller via listing"
)


class BrightDataError(Exception):
    """Raised for any failure in the Bright Data request/poll/download cycle,
    or when a listing record can't be mapped to usable data."""


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


async def _trigger_snapshot(url: str, api_key: str, client: httpx.AsyncClient) -> str:
    response = await client.post(
        f"{BASE_URL}/datasets/v3/trigger",
        params={"dataset_id": DATASET_ID},
        json=[{"url": url}],
        headers=_auth_headers(api_key),
    )
    response.raise_for_status()
    data = response.json()
    snapshot_id = data.get("snapshot_id")
    if not snapshot_id:
        raise BrightDataError(f"No snapshot_id in trigger response: {data}")
    return str(snapshot_id)


async def _wait_until_ready(snapshot_id: str, api_key: str, client: httpx.AsyncClient) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        response = await client.get(
            f"{BASE_URL}/datasets/v3/progress/{snapshot_id}", headers=_auth_headers(api_key)
        )
        response.raise_for_status()
        status = str(response.json().get("status", "")).lower()

        if status in {"ready", "done", "complete", "completed"}:
            return
        if status in {"failed", "error"}:
            raise BrightDataError(f"Bright Data snapshot {snapshot_id} failed: {response.text}")
        if time.monotonic() >= deadline:
            raise BrightDataError(
                f"Timed out waiting for snapshot {snapshot_id} (last status: {status!r})"
            )
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _download_snapshot(
    snapshot_id: str, api_key: str, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    response = await client.get(
        f"{BASE_URL}/datasets/v3/snapshot/{snapshot_id}",
        params={"format": "json"},
        headers=_auth_headers(api_key),
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise BrightDataError(f"Unexpected snapshot response shape: {type(data)}")
    return data


async def fetch_marketplace_record(url: str, *, api_key: str | None = None) -> dict[str, Any]:
    """Runs the full trigger -> poll -> download cycle for a single listing URL."""
    resolved_key = api_key or get_settings().brightdata_api_key
    if not resolved_key:
        raise BrightDataError("BRIGHTDATA_API_KEY is not set")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            snapshot_id = await _trigger_snapshot(url, resolved_key, client)
            await _wait_until_ready(snapshot_id, resolved_key, client)
            records = await _download_snapshot(snapshot_id, resolved_key, client)
        except httpx.HTTPStatusError as exc:
            raise BrightDataError(
                f"Bright Data API error ({exc.response.status_code}): {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise BrightDataError(f"Bright Data request failed: {exc}") from exc

    if not records:
        raise BrightDataError(f"Bright Data returned no records for {url}")
    return records[0]


@dataclass
class DiscoveryQuery:
    """One keyword+city search. date_listed mirrors Facebook's own recency filter
    (confirmed example value: "Last 30 days"); pass whatever string Marketplace's
    UI shows for the filter you want, or omit it for no recency filter."""

    keyword: str
    city: str
    date_listed: str | None = None


async def _discovery_request(
    queries: list[DiscoveryQuery],
    api_key: str,
    limit_per_input: int | None,
    client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    params = {
        "dataset_id": DATASET_ID,
        "notify": "false",
        "include_errors": "true",
        "type": "discover_new",
        "discover_by": "keyword",
    }
    body: dict[str, Any] = {
        "input": [
            {
                "keyword": q.keyword,
                "city": q.city,
                **({"date_listed": q.date_listed} if q.date_listed else {}),
            }
            for q in queries
        ],
        "limit_per_input": limit_per_input,
    }

    response = await client.post(
        f"{BASE_URL}/datasets/v3/scrape", params=params, json=body, headers=_auth_headers(api_key)
    )
    response.raise_for_status()
    payload: Any = response.json()

    # Fast searches return records directly; slower ones return a snapshot_id to
    # poll — same trigger/progress/snapshot cycle as the single-URL variant.
    if isinstance(payload, dict) and "snapshot_id" in payload:
        snapshot_id = str(payload["snapshot_id"])
        await _wait_until_ready(snapshot_id, api_key, client)
        return await _download_snapshot(snapshot_id, api_key, client)

    if isinstance(payload, dict):
        payload = payload.get("data") or payload.get("results") or []
    if not isinstance(payload, list):
        raise BrightDataError(f"Unexpected discovery response shape: {type(payload)}")
    return payload


async def discover_marketplace_records(
    queries: list[DiscoveryQuery],
    *,
    api_key: str | None = None,
    limit_per_input: int | None = None,
) -> list[dict[str, Any]]:
    """Runs one or more keyword+city searches (batched in a single request) and
    returns the raw matching records. Unlike the single-URL variant's field
    mapping, this endpoint/body/param combination is confirmed against a real
    working example, not inferred from general docs."""
    resolved_key = api_key or get_settings().brightdata_api_key
    if not resolved_key:
        raise BrightDataError("BRIGHTDATA_API_KEY is not set")
    if not queries:
        return []

    async with httpx.AsyncClient(timeout=DISCOVERY_TIMEOUT_SECONDS) as client:
        try:
            return await _discovery_request(queries, resolved_key, limit_per_input, client)
        except httpx.HTTPStatusError as exc:
            raise BrightDataError(
                f"Bright Data API error ({exc.response.status_code}): {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise BrightDataError(f"Bright Data request failed: {exc}") from exc


def _record_text_blob(record: dict[str, Any]) -> str:
    """Flattens every string/number value in the record into one search blob, so
    the regex fallbacks can find beds/baths/price/etc. regardless of exact key names."""
    parts: list[str] = []
    for value in record.values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, int | float):
            parts.append(str(value))
        elif isinstance(value, dict):
            parts.extend(str(v) for v in value.values() if isinstance(v, str | int | float))
    return " | ".join(parts)


def _prose_text(record: dict[str, Any]) -> str:
    """Joins only known free-text fields (title/description), for regexes where a
    false-positive match on an opaque ID would be actively wrong rather than just
    a miss — phone numbers in particular, since a bare 10-digit product_id or
    timestamp fragment can look exactly like one. Beds/baths/sqft/price/address
    all require a distinguishing marker (a unit word, a "$", a comma-separated
    city/state) so they're safe to search over the full record blob instead."""
    return " ".join(
        str(record[key])
        for key in ("title", "description", "seller_description", "notes", "details")
        if record.get(key)
    )


def _resolve_price(record: dict[str, Any], blob: str) -> float | None:
    for key in ("final_price", "price", "initial_price"):
        value = record.get(key)
        if value is not None:
            try:
                return float(str(value).replace(",", "").replace("$", ""))
            except ValueError:
                continue
    return parse_price(blob)


@dataclass
class ResolvedAddress:
    address_line: str
    city: str
    state: str
    zip_code: str | None
    # Set only when address_line is the "not public" placeholder rather than a
    # real street — geocode_and_save uses this instead of the (placeholder-
    # polluted) full address string, so the geocoder gets clean "City, ST" text.
    geocode_query: str | None = None


def _resolve_address(record: dict[str, Any], blob: str) -> ResolvedAddress | None:
    """Marketplace is P2P, so a full street address is rare — falls back to
    city/state-only with an honest placeholder for the street line rather than
    fabricating one."""
    location_text = " ".join(
        str(record[key]) for key in ("location", "address") if record.get(key)
    )

    full = parse_address(location_text) or parse_address(blob)
    if full:
        address_line, city, state, zip_code = full
        return ResolvedAddress(address_line, city, state, zip_code)

    match = CITY_STATE_RE.search(location_text) or CITY_STATE_RE.search(blob)
    if match:
        city, state = match.group(1).strip(), match.group(2)
        return ResolvedAddress(
            NO_STREET_ADDRESS_PLACEHOLDER,
            city,
            state,
            None,
            geocode_query=f"{city}, {state}",
        )

    # Confirmed against real search results: the record's own `location` field
    # is frequently null for discovery-mode matches (unlike single-URL fetches,
    # where it's usually present) — but discovery_input.city tells us which city
    # this listing matched on. state is left empty here; geocode_and_save
    # resolves it from Nominatim (via geocode_query) since we don't have one.
    discovery_input = record.get("discovery_input")
    discovery_city = discovery_input.get("city") if isinstance(discovery_input, dict) else None
    if discovery_city:
        return ResolvedAddress(
            NO_STREET_ADDRESS_PLACEHOLDER,
            str(discovery_city),
            "",
            None,
            geocode_query=str(discovery_city),
        )

    return None


def _record_to_scraped_listing(record: dict[str, Any], url: str) -> ScrapedListing:
    blob = _record_text_blob(record)

    price = _resolve_price(record, blob)
    address_parts = _resolve_address(record, blob)
    bedrooms = parse_bedrooms(blob)
    bathrooms = parse_bathrooms(blob)
    sqft = parse_sqft(blob)
    phone, email = extract_contact(_prose_text(record))

    # bathrooms is intentionally excluded: "private room" / shared-housing
    # listings (common on Marketplace) often genuinely have none to report.
    required = {
        "price": price,
        "address": address_parts,
        "bedrooms": bedrooms,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise BrightDataError(
            f"Could not extract required field(s) {missing} from Bright Data record for {url}"
        )

    assert address_parts is not None and price is not None
    assert bedrooms is not None

    title = record.get("title")
    description = record.get("description") or record.get("seller_description") or title or None

    # Marketplace's API exposes no seller name/phone/email field at all — contact
    # happens via Messenger. landlord_phone/email above come only from whatever a
    # seller happened to type into the description text; there's no equivalent
    # signal for a name, so this stays None rather than guessing from prose.
    landlord_name = None

    # A listing marked sold shouldn't show as an active rental.
    status = ListingStatus.LEASED if record.get("is_sold") else ListingStatus.ACTIVE

    source_listing_id = str(record.get("product_id") or derive_source_listing_id(url))

    return ScrapedListing(
        source_site=SourceSite.FACEBOOK_MARKETPLACE,
        source_listing_id=source_listing_id,
        url=str(record.get("url") or url),
        address_line=address_parts.address_line,
        city=address_parts.city,
        state=address_parts.state,
        zip_code=address_parts.zip_code or "",
        price=price,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        sqft=sqft,
        description=description,
        landlord_name=landlord_name,
        landlord_phone=phone,
        landlord_email=email,
        status=status,
        geocode_query=address_parts.geocode_query,
    )


async def scrape_marketplace_listing(url: str, *, api_key: str | None = None) -> ScrapedListing:
    record = await fetch_marketplace_record(url, api_key=api_key)
    return _record_to_scraped_listing(record, url)


async def scrape_and_save_marketplace_listing(
    url: str, db: AsyncSession, *, api_key: str | None = None
) -> Listing:
    """Full pipeline: fetch via Bright Data, geocode, persist. Mirrors
    scraper.py::scrape_and_save so both sources save listings identically."""
    scraped = await scrape_marketplace_listing(url, api_key=api_key)
    return await geocode_and_save(scraped, db)


@dataclass
class DiscoverySkip:
    record: dict[str, Any]
    reason: str


@dataclass
class DiscoveryResult:
    saved: list[Listing]
    skipped: list[DiscoverySkip]


async def discover_and_save_marketplace_listings(
    queries: list[DiscoveryQuery],
    db: AsyncSession,
    *,
    api_key: str | None = None,
    limit_per_input: int | None = None,
) -> DiscoveryResult:
    """Searches Marketplace by keyword+city and saves every result that maps to a
    usable listing. A search naturally returns a mix of good matches, near-misses
    Bright Data still included, and the occasional error entry (include_errors is
    on) — each record is handled independently, so one bad/non-rental/duplicate
    result skips instead of failing the whole batch. Check .skipped to see why
    any given one didn't get saved."""
    records = await discover_marketplace_records(
        queries, api_key=api_key, limit_per_input=limit_per_input
    )

    saved: list[Listing] = []
    skipped: list[DiscoverySkip] = []

    for record in records:
        if not isinstance(record, dict):
            skipped.append(DiscoverySkip({"value": record}, "not a listing record"))
            continue
        if "error" in record and "url" not in record:
            skipped.append(DiscoverySkip(record, f"Bright Data error: {record.get('error')}"))
            continue

        url = str(record.get("url", ""))
        try:
            scraped = _record_to_scraped_listing(record, url)
            listing = await geocode_and_save(scraped, db)
        except (BrightDataError, DuplicateListingError, ScraperError) as exc:
            skipped.append(DiscoverySkip(record, str(exc)))
            continue

        saved.append(listing)

    return DiscoveryResult(saved=saved, skipped=skipped)
