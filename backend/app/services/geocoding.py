import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Nominatim's usage policy (https://operations.osmfoundation.org/policies/nominatim/)
# requires a descriptive User-Agent and caps the public instance at ~1 request/second.
USER_AGENT = "apartment-hunting-ai-agent/0.1 (personal apartment search tool)"
MIN_REQUEST_INTERVAL_SECONDS = 1.0

_rate_limit_lock = asyncio.Lock()
_last_request_at: float = 0.0


class GeocodingError(Exception):
    """Raised when the geocoding request itself fails (network/HTTP error)."""


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float
    postal_code: str | None = None
    # 2-letter state/province code (from Nominatim's "ISO3166-2-lvl4", e.g. "CA-ON" -> "ON").
    # Only reliably present for admin-boundary results (city/region queries), not
    # always for full street addresses, so treat as a fallback, not a given.
    region_code: str | None = None


async def _wait_for_rate_limit() -> None:
    global _last_request_at
    async with _rate_limit_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        _last_request_at = time.monotonic()


async def geocode_address(
    address: str, client: httpx.AsyncClient | None = None
) -> Coordinates | None:
    """Forward-geocodes a free-text address via the free Nominatim (OpenStreetMap) API.

    Returns None if no match was found. Raises GeocodingError on request failure.
    Self-rate-limits to Nominatim's ~1 req/sec public-instance policy.
    """
    await _wait_for_rate_limit()

    params = {"q": address, "format": "jsonv2", "limit": "1", "addressdetails": "1"}
    headers = {"User-Agent": USER_AGENT}

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=10.0)
    try:
        response = await http_client.get(NOMINATIM_URL, params=params, headers=headers)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GeocodingError(f"Nominatim request failed for {address!r}: {exc}") from exc
    finally:
        if owns_client:
            await http_client.aclose()

    results = response.json()
    if not results:
        return None

    top = results[0]
    address_details: dict[str, Any] = top.get("address") or {}
    postal_code = address_details.get("postcode")
    iso_region = address_details.get("ISO3166-2-lvl4")  # e.g. "CA-ON" or "US-MA"
    region_code = iso_region.split("-")[-1] if iso_region and "-" in iso_region else None

    return Coordinates(
        latitude=float(top["lat"]),
        longitude=float(top["lon"]),
        postal_code=postal_code,
        region_code=region_code,
    )
