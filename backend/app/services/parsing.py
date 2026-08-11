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

# Requires at least one separator between the digit groups (dash/dot/space,
# or parens around the area code) — a bare 10-digit run with no formatting
# at all is deliberately NOT matched. Confirmed necessary against real data:
# Kijiji listing pages show "Ad ID 1740239384" near the top, and an
# all-optional-separator version of this regex matched that instead of the
# real phone number ("647-821-9779") later in the description.
PHONE_RE = re.compile(r"(\+?1[-.\s])?(\(\d{3}\)[-.\s]?|\d{3}[-.\s])\d{3}[-.\s]\d{4}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PRICE_RE = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)\s*(?:/\s*mo(?:nth)?)?", re.IGNORECASE)
BEDS_RE = re.compile(r"\b(studio)\b|(\d+(?:\.\d+)?)\s*(?:bd|beds?|bedrooms?)\b", re.IGNORECASE)
BATHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:ba|baths?|bathrooms?)\b", re.IGNORECASE)
# "ft2"/"ft²" (no space, no "sq") added for Craigslist's compact
# "1200ft2" notation — confirmed against a real listing where the existing
# alternatives all missed it.
SQFT_RE = re.compile(
    r"([\d,]{2,6})\s*(?:sq\.?\s*ft\.?|sqft|square feet|ft2|ft²)\b", re.IGNORECASE
)
ADDRESS_RE = re.compile(
    r"(?P<address_line>[\w.\-#' ]+?),\s*(?P<city>[A-Za-z .'\-]+?),\s*"
    r"(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)"
)
# Canadian format: "street, city, PROVINCE, A1A 1A1" — a 4th comma-separated
# segment (US addresses run state+zip together with just a space) and a
# letter-digit-letter-digit-letter-digit postal code instead of a 5-digit zip.
# Confirmed against real Kijiji listings, which publish addresses this way.
# The optional "Unit/Suite/Apt N," clause absorbs a unit segment between
# street and city when present — confirmed necessary against real data: a
# real listing's full address was "50 Glenrose Ave, Unit 4, Toronto, ON,
# M4T 1K4" (5 comma-separated parts), and without this, address_line's
# non-greedy match anchored on "Unit 4" instead of the real street, since
# "Unit 4" alone satisfies the 4-group shape just as well.
CA_ADDRESS_RE = re.compile(
    r"(?P<address_line>[\w.\-#' ]+?),\s*(?:(?:Unit|Suite|Apt\.?)\s*[\w-]+,\s*)?"
    r"(?P<city>[A-Za-z .'\-]+?),\s*"
    r"(?P<state>[A-Z]{2}),?\s*(?P<zip>[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d)",
    re.IGNORECASE,
)

# Real street addresses either lead with a civic number ("1 Claude Avenue")
# or, when the number is omitted (common on Kijiji/Marketplace for privacy),
# end in a recognizable street-type suffix ("Neapolitan Dr"). Rejects the
# alternative confirmed against real data: some Kijiji listings give no
# street at all, just "Toronto, Etobicoke, ON M8Y 0A1" — with nothing to
# validate against, ADDRESS_RE/CA_ADDRESS_RE happily (and wrongly) captured
# "Toronto" as if it were the street name.
_STREET_SUFFIX_RE = re.compile(
    r"\b(street|st|avenue|ave|road|rd|drive|dr|boulevard|blvd|lane|ln|way|"
    r"court|ct|place|pl|crescent|cres|circuit|cir|trail|terrace|square|sq|"
    r"gate|grove|path|walk|close|parkway|pkwy|highway|hwy)\.?$",
    re.IGNORECASE,
)


def _looks_like_street(address_line: str) -> bool:
    stripped = address_line.strip()
    return bool(re.match(r"^\d", stripped)) or bool(_STREET_SUFFIX_RE.search(stripped))


def _strip_marketing_prefix(address_line: str) -> str:
    """Titles sometimes tack the real street onto a "N Bed M Bath - " teaser
    with no comma in between (confirmed against a real listing: "1 Bed 1
    Bath - 50 Glenrose Ave, Unit 4, Toronto, ON M4T 1K4") — comma-free, so it
    gets swallowed into the address_line capture along with the real street.
    Real street names don't use " - " (space-hyphen-space); keep only the
    text after the last one, if present."""
    if " - " in address_line:
        return address_line.rsplit(" - ", 1)[1].strip()
    return address_line

# Shared across sources (not just Bright Data) — geocode_and_save swaps a
# listing's address_line to this whenever a more precise geocode attempt
# (e.g. a cross-street intersection) fails and it has to fall back to a
# plain city-level point, so the displayed address never implies more
# precision than the stored coordinates actually have.
NO_STREET_ADDRESS_PLACEHOLDER = "Exact address not public — contact seller via listing"

DOMAIN_TO_SOURCE_SITE: dict[str, SourceSite] = {
    "zillow.com": SourceSite.ZILLOW,
    "apartments.com": SourceSite.APARTMENTS_COM,
    "craigslist.org": SourceSite.CRAIGSLIST,
    "streeteasy.com": SourceSite.STREETEASY,
    "facebook.com": SourceSite.FACEBOOK_MARKETPLACE,
    "kijiji.ca": SourceSite.KIJIJI,
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
    images: list[str] | None = None
    status: ListingStatus = ListingStatus.ACTIVE
    # Set this when address_line isn't a real, geocodable street address (e.g. an
    # honest "not public" placeholder) — geocode_and_save uses it instead of
    # full_address, so descriptive placeholder text never gets sent to the
    # geocoder as if it were part of a real address.
    geocode_query: str | None = None
    # A second, less precise query to try if geocode_query fails to resolve
    # (e.g. an intersection Nominatim doesn't have indexed) — lets a "try for
    # more precision" attempt safely fall back rather than rejecting the whole
    # listing just because the *better* query didn't pan out.
    geocode_fallback_query: str | None = None

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
    for pattern in (ADDRESS_RE, CA_ADDRESS_RE):
        for match in pattern.finditer(text):
            address_line = _strip_marketing_prefix(match.group("address_line").strip())
            if not _looks_like_street(address_line):
                continue
            return (address_line, match.group("city").strip(), match.group("state"), match.group("zip"))
    return None


def extract_contact(text: str) -> tuple[str | None, str | None]:
    phone_match = PHONE_RE.search(text)
    email_match = EMAIL_RE.search(text)
    return (
        phone_match.group(0) if phone_match else None,
        email_match.group(0) if email_match else None,
    )
