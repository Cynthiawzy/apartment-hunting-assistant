"""Shared parsing helpers and the source-agnostic ScrapedListing type.

Used by every scraping source (Playwright in scraper.py, the Bright Data API
client in brightdata_scraper.py, and any future source) so heuristic text
parsing and the intermediate data shape stay consistent across all of them.
"""

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.models.listing import ListingStatus, SourceSite

PHONE_RE = re.compile(r"(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PRICE_RE = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)\s*(?:/\s*mo(?:nth)?)?", re.IGNORECASE)
BEDS_RE = re.compile(r"\b(studio)\b|(\d+(?:\.\d+)?)\s*(?:bd|beds?|bedrooms?)\b", re.IGNORECASE)
BATHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:ba|baths?|bathrooms?)\b", re.IGNORECASE)
SQFT_RE = re.compile(r"([\d,]{2,6})\s*(?:sq\.?\s*ft\.?|sqft|square feet)", re.IGNORECASE)
ADDRESS_RE = re.compile(
    r"(?P<address_line>[\w.\-#' ]+?),\s*(?P<city>[A-Za-z .'\-]+?),\s*"
    r"(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)"
)

DOMAIN_TO_SOURCE_SITE: dict[str, SourceSite] = {
    "zillow.com": SourceSite.ZILLOW,
    "apartments.com": SourceSite.APARTMENTS_COM,
    "craigslist.org": SourceSite.CRAIGSLIST,
    "streeteasy.com": SourceSite.STREETEASY,
    "facebook.com": SourceSite.FACEBOOK_MARKETPLACE,
}


@dataclass
class ScrapedListing:
    """Everything scraped from a listing page except geocoded coordinates (a
    separate, explicitly non-scraping concern — see geocoding.py and
    scraper.py::geocode_and_save)."""

    source_site: SourceSite
    source_listing_id: str
    url: str
    address_line: str
    city: str
    state: str
    zip_code: str
    price: float
    bedrooms: float
    # None for listings with no dedicated bathroom count to report (e.g.
    # "private room" / shared-housing listings, common on Facebook Marketplace).
    bathrooms: float | None
    description: str | None
    landlord_name: str | None
    landlord_phone: str | None
    landlord_email: str | None
    unit: str | None = None
    sqft: int | None = None
    status: ListingStatus = ListingStatus.ACTIVE
    # Set this when address_line isn't a real, geocodable street address (e.g. an
    # honest "not public" placeholder) — geocode_and_save uses it instead of
    # full_address, so descriptive placeholder text never gets sent to the
    # geocoder as if it were part of a real address.
    geocode_query: str | None = None

    @property
    def full_address(self) -> str:
        return f"{self.address_line}, {self.city}, {self.state} {self.zip_code}"


def infer_source_site(url: str) -> SourceSite:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for domain, site in DOMAIN_TO_SOURCE_SITE.items():
        if host == domain or host.endswith("." + domain):
            return site
    return SourceSite.OTHER


def derive_source_listing_id(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    segments = [s for s in path.split("/") if s]
    if segments and re.search(r"\d", segments[-1]):
        return segments[-1]
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def parse_price(text: str) -> float | None:
    match = PRICE_RE.search(text)
    return float(match.group(1).replace(",", "")) if match else None


def parse_bedrooms(text: str) -> float | None:
    match = BEDS_RE.search(text)
    if not match:
        return None
    return 0.0 if match.group(1) else float(match.group(2))


def parse_bathrooms(text: str) -> float | None:
    match = BATHS_RE.search(text)
    return float(match.group(1)) if match else None


def parse_sqft(text: str) -> int | None:
    match = SQFT_RE.search(text)
    return int(match.group(1).replace(",", "")) if match else None


def parse_address(text: str) -> tuple[str, str, str, str] | None:
    match = ADDRESS_RE.search(text)
    if not match:
        return None
    return (
        match.group("address_line").strip(),
        match.group("city").strip(),
        match.group("state"),
        match.group("zip"),
    )


def extract_contact(text: str) -> tuple[str | None, str | None]:
    phone_match = PHONE_RE.search(text)
    email_match = EMAIL_RE.search(text)
    return (
        phone_match.group(0) if phone_match else None,
        email_match.group(0) if email_match else None,
    )
