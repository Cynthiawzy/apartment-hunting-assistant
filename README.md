# Apartment Hunting AI Agent

An AI-assisted apartment hunting platform: a geospatial map dashboard, a listing scraper/normalizer, and a LangGraph agent that drafts and sends landlord viewing requests via SMS.

See [CLAUDE.md](./CLAUDE.md) for the full tech stack and coding conventions.

## Phase 1: Database Layer

Sets up PostGIS-backed Postgres and the core SQLAlchemy 2.0 models: `Neighborhood`, `Listing`, `User`, `OutreachRequest`.

### Prerequisites

- Docker Desktop (running)
- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Setup

```bash
cp .env.example .env   # fill in secrets as needed for later phases

# start Postgres/PostGIS
docker compose up -d

# install backend deps
cd backend
uv sync

# apply migrations
uv run alembic upgrade head
```

### Verify

```bash
docker compose exec db psql -U apartment_hunter -d apartment_hunting -c "\dt"
docker compose exec db psql -U apartment_hunter -d apartment_hunting -c "SELECT PostGIS_Version();"
```

### Project Layout

```
backend/
  app/
    core/       # settings, async DB session
    models/     # SQLAlchemy 2.0 ORM models (PostGIS geometry columns via GeoAlchemy2)
    schemas/    # Pydantic v2 request/response schemas
    api/        # FastAPI routers
    main.py     # FastAPI app, CORS
  alembic/      # migrations (0001 creates the postgis extension + all tables)
docker-compose.yml  # local Postgres/PostGIS
```

## Phase 2: FastAPI Backend & Geospatial Endpoints

`GET /api/listings/nearby` uses `ST_DWithin`/`ST_Distance` (cast to `geography` for accurate meter-based radius) to find active listings within a radius of a lat/lng, sorted by distance. `GET /api/listings/` supports the same optional geo filter plus `budget_max`/`min_beds`. `POST /api/listings/` creates a listing from lat/lng (stored as a PostGIS point).

### Run the API

```bash
cd backend
uv run uvicorn app.main:app --reload
# docs at http://127.0.0.1:8000/docs
```

## Phase 3: React + Mapbox Frontend

`MapView` renders one marker per listing (a price bubble); hovering shows a popup with price/address, clicking a marker or a sidebar listing card opens `ListingModal` with full details. `Sidebar` filter inputs (budget, beds, baths, radius) are debounced (400ms) and drive a `useListings` hook that refetches `GET /api/listings/`. Radius filtering uses the current map center, tracked via the map's `moveend` event.

**Marker clustering** (`utils/cluster.ts`): listings whose on-screen pixel distance is within 45px get grouped into a numbered blue bubble instead of overlapping price markers — genuinely necessary given many scraped listings share identical city-center coordinates (see Phase 4's Facebook Marketplace notes). Pixel-based rather than a fixed geo-distance, so it's naturally zoom-aware without extra recomputation logic — re-clustered on the map's `moveend` (which fires for both pan and zoom). Clicking a cluster opens a popup listing every listing in it (price + address); clicking a row opens the same `ListingModal` as an individual marker.

**Listing photos**: `ListingCard` shows a thumbnail (first image, or a placeholder icon if the listing has none) and `ListingModal` shows a horizontally scrollable photo strip across the top. Backed by a `listings.images: text[]` column populated by whichever scraper found the listing — schema.org JSON-LD `image` for the generic Playwright scraper (string, array, or ImageObject, all normalized to a flat URL list), Bright Data's `images` field for Facebook Marketplace. `null` when a source has no photos.

### Setup

```bash
cd frontend
npm install
cp .env.example .env   # set VITE_MAPBOX_ACCESS_TOKEN to a real Mapbox token
npm start              # http://localhost:5173
```

Without a valid `VITE_MAPBOX_ACCESS_TOKEN`, the map pane shows a placeholder message instead of tiles — everything else (filters, listing cards, modal) still works.

### Conserving Mapbox free-tier usage during development

Mapbox's free tier bills "map loads" — each time `mapboxgl.Map()` initializes and finishes loading a style. Marker updates, hovering, and filter changes never recreate the map, so they're free; the main driver of usage during dev is repeatedly reloading the page or editing `MapView.tsx` (which remounts it via HMR). Two `.env` toggles help:

- `VITE_MAPBOX_ENABLED=false` — skip live map loads entirely (shows a placeholder) while working on anything that isn't map-specific. Your real token stays in `.env`; just flip this back to `true` when you need the map.
- `VITE_USE_MOCK_LISTINGS=true` — serve listings from a static fixture (`src/mocks/listings.ts`, filtered/sorted client-side) instead of the backend, so you can iterate on the whole UI without the backend, Docker, or Postgres running at all.

Combine both to work on Sidebar/filters/modal UI with zero network calls of any kind.

### Project Layout

```
frontend/
  src/
    api/listings.ts        # fetch wrapper for GET /api/listings/ (or mock fixture)
    mocks/listings.ts       # static fixture + client-side filtering for VITE_USE_MOCK_LISTINGS
    hooks/useListings.ts    # debounced fetch-on-filter-change
    types/listing.ts        # Listing, ListingFilters, FilterDraft
    utils/cluster.ts         # pixel-distance marker clustering
    components/
      MapView.tsx            # mapbox-gl markers + hover popups + clustering
      Sidebar.tsx             # filter inputs + listing card list
      ListingCard.tsx
      ListingModal.tsx        # full listing detail modal
    App.tsx
```

## Phase 4: Playwright Web Scraper

`app/services/scraper.py` loads a listing page with Playwright and extracts price, address, bed/bath count, sqft, description, and contact info. It tries schema.org JSON-LD first (most real estate sites embed this for SEO — `@type: Apartment/House/Product` with `offers.price`, `numberOfBedrooms`, an `address` object, etc.), then falls back to regex-based heuristic parsing of the rendered page text. If neither method can find price/address/beds/baths, it raises `ScraperError` rather than saving incomplete data.

Because `ListingCreate` requires real coordinates, `scrape_listing()` returns an intermediate `ScrapedListing` (no lat/lng yet) rather than a full `ListingCreate`. The orchestrator `scrape_and_save(url, db)` then:
1. geocodes the scraped address via `app/services/geocoding.py` (free Nominatim/OpenStreetMap API, self-rate-limited to ~1 req/sec per their usage policy, with the required custom `User-Agent`)
2. builds the final `ListingCreate`
3. saves it via `app/crud/listings.py::create_listing` — the same shared function `POST /api/listings/` uses, so the API and the scraper can never drift apart on insert logic

Duplicate scrapes (same `source_site` + `source_listing_id`, derived from the URL) raise `DuplicateListingError` instead of erroring or silently duplicating.

```python
from app.core.database import AsyncSessionLocal
from app.services.scraper import scrape_and_save

async with AsyncSessionLocal() as db:
    listing = await scrape_and_save("https://example.com/listing/123", db)
```

**Scope note:** real listing sites (Zillow, Apartments.com) run anti-bot protection this scraper doesn't attempt to defeat — no CAPTCHA-solving, no fingerprint spoofing, just a standard desktop User-Agent. It was verified against local HTML fixtures (with and without JSON-LD) rather than live sites, both to avoid ToS/anti-bot issues during development and because scraping real estate sites' actual markup requires per-site adapters that are easy to add on top of this (pass `source_site=` explicitly, or extend `_extract_json_ld`/the heuristic regexes) once you have real target pages to test against.

### Facebook Marketplace via Bright Data

`app/services/brightdata_scraper.py` fetches Marketplace listings through [Bright Data's Web Scraper API](https://brightdata.com/products/web-scraper/facebook/marketplace) instead of scraping facebook.com directly — Meta's ToS prohibits automated collection and their anti-bot defenses are extensive, so this avoids running our own browser automation against those defenses. **Using Bright Data doesn't transfer ToS-compliance risk away from you as their customer** (their license agreement makes that explicit) — it's a lower technical-risk path, not a legal blank check. Needs `BRIGHTDATA_API_KEY` in `.env` (your own paid account — free tier is 5K records/month).

There are two ways to fetch data; **[bulk discovery](#bulk-discovery-discover_bykeyword) below is the one this project actually uses** — it's what fits an apartment-hunting agent that needs to build up a catalog on its own, and it's the one verified against 768 real listings.

Shares `ScrapedListing`/regex parsing (`app/services/parsing.py`) and the geocode+save tail (`scraper.py::geocode_and_save`) with the Playwright scraper, so both sources build and persist listings identically.

<details>
<summary>Single-URL fetch (built, working for common cases, but <strong>not used by this project</strong> — kept for reference)</summary>

```python
from app.core.database import AsyncSessionLocal
from app.services.brightdata_scraper import scrape_and_save_marketplace_listing

async with AsyncSessionLocal() as db:
    listing = await scrape_and_save_marketplace_listing(
        "https://www.facebook.com/marketplace/item/.../", db
    )
```

Fetches one listing you already have the URL for (e.g. a "paste a link" feature), rather than searching. **Known gap, left unfixed since this path isn't used**: unlike discovery-mode results, a single-URL fetch has no `discovery_input` (the searched city) to fall back on, so it fails on listings whose own `location` field is null — confirmed by testing the same real listing both ways: it succeeded via discovery search, then failed via single-URL fetch with `Could not extract required field(s) ['address']`. Fixable by accepting an optional city/state hint parameter if this path becomes needed later.

</details>

**Confirmed record schema** (verified against a real example record): `url`, `title`, `initial_price`/`final_price`, `currency`, `product_id`, `location` (`"City, ST"`), `description`, `seller_description`, `is_sold`, plus category-specific fields (`condition`, `color`, `brand`, `car_miles`, ...) that only apply to non-housing categories and are harmlessly ignored. There is **no seller name/phone/email field at all** — Marketplace contact happens via Messenger — so `landlord_phone`/`landlord_email` only ever come from whatever a seller happened to type into the description text, and `landlord_name` is always `None`. `is_sold: true` maps to `ListingStatus.LEASED` instead of `ACTIVE`. Bedrooms/bathrooms/sqft aren't confirmed as dedicated fields for the rentals category specifically, so those go through the same regex fallback the Playwright scraper uses for pages without JSON-LD.

**Marketplace is peer-to-peer**, so listings rarely expose a full street address (sellers share that after contact) — this can't be fixed (it's a platform-level privacy choice, not a scraper gap), but real listing text often contains usable location signal we were previously discarding. Address resolution tries, in order:
1. A real street address near the known city (`"105 George Street, Toronto"` — found in real data; the strict "street, city, ST zip" pattern missed it since Marketplace text never has a trailing state+zip, and Canadian postal codes like `L9A 4G2` don't match a US zip pattern anyway)
2. A cross-street intersection with a location-indicating trigger word (`"near Bathurst and Eglinton"`, `"@ Warden/Lawrence"`) — **verified against real Nominatim behavior, not assumed**: intersections only reliably geocode using `"&"` as the separator (`"and"` mostly doesn't work), and even then only ~50% of real intersections resolve (depends on whether OSM has that one indexed). Deliberately requires a trigger word (`near`/`at`/`@`/`corner of`) immediately before the pattern — bare `"X and Y"` is far too common in ordinary listing text (`"heat and water included"`, `"1 bed and 1 bath"`) to use safely on its own.
3. Plain city-level geocoding with an honest placeholder ("Exact address not public…") for the street line

Because intersection geocoding is unreliable, every precise attempt carries a `geocode_fallback_query` (the plain city) that `geocode_and_save` tries if the precise one fails — **and swaps `address_line` back to the honest placeholder when that happens**, so a displayed "Near X & Y" is never left dangling on coordinates that are actually just the city center (caught by testing against real data, not obvious from the code alone).

**No, we can't extract Facebook's own "approximate location" map data.** Facebook's listing page renders an interactive approximate-location map, but that's Facebook's own frontend data — confirmed exhaustively (every key across a real 792-record dataset) that Bright Data's Marketplace scraper does not expose any latitude/longitude/coordinates field at all, only the plain-text `location` field ("City, ST") covered above. This isn't something extraction logic can work around; the data simply isn't in what this third-party scraper returns.

**A real, confirmed mislabeling bug this surfaced:** a "Toronto" search returns listings from a wide surrounding region — 24 distinct cities showed up in real `location` values from one search alone — so defaulting every listing with no other location signal to the searched city was systematically wrong for listings actually located elsewhere. `_find_known_city` matches known municipality names mentioned in the listing's own text (e.g. "Brampton's most desirable areas," "Prime Hamilton Location," "Pickering's most prestigious neighborhoods") — even without a formatted ", ON" suffix — and takes priority over the searched-city fallback.

The city list is sourced from authoritative municipality lists (GTA, Hamilton, Niagara Region, Waterloo Region, Simcoe County — the metro area a Toronto search realistically spans), not accumulated one miss at a time. It's split into two tiers by confirmed false-positive risk: a striking number of Ontario town names are also common English words or personal names (`"Cambridge dictionary"`, `"contact Barrie"`, `"Milton Friedman"`, `"Aurora borealis"` all matched during testing) — those require a location trigger word (`near`/`at`/`in`) immediately before them, same pattern as intersection detection. A few (King, Tiny, Lincoln, Midland) are excluded even from that gated tier, since e.g. "King Street" is itself a common, real Toronto address that gating alone wouldn't disambiguate from King Township.

Backfilling the existing dataset with this fix corrected 5 of 27 listings that had been mislabeled with the wrong city (2 Hamilton, 2 Pickering, 1 Brampton — including one with a full, geocodable street address that only became extractable once the correct city was known).

### Bulk discovery (`discover_by=keyword`)

The single-URL variant above only fits an "add this one listing I found" flow. For actual bulk collection, `discover_marketplace_records`/`discover_and_save_marketplace_listings` hit `POST /datasets/v3/scrape` with `type=discover_new&discover_by=keyword` — confirmed against a real working request, including its request body shape (`{"input": [...], "limit_per_input": ...}`, notably **not** the bare-array format the single-URL `/trigger` endpoint uses):

```python
from app.core.database import AsyncSessionLocal
from app.services.brightdata_scraper import DiscoveryQuery, discover_and_save_marketplace_listings

queries = [
    DiscoveryQuery(keyword="studio", city="Toronto", date_listed="Last 30 days"),
    DiscoveryQuery(keyword="1 bed 1 bath", city="Toronto", date_listed="Last 30 days"),
]
async with AsyncSessionLocal() as db:
    result = await discover_and_save_marketplace_listings(queries, db)
    # result.saved: list[Listing], result.skipped: list[DiscoverySkip] (record + reason)
```

A search naturally returns a mix of good matches, non-rentals, duplicates, and (with `include_errors=true`) the occasional no-results error entry — each record is handled independently, so one bad result skips instead of failing the whole batch.

**Real-world timing:** a single keyword+city search took ~4 minutes end-to-end (discovery has to actually crawl/search, not just fetch a cached page) — `POLL_TIMEOUT_SECONDS` is set to 300s to comfortably cover that.

**Verified against a real production search** ("studio" in Toronto, last 30 days — 792 results, 768 successful + 24 login-redirect errors from Bright Data):
- 503/768 (65%) mapped successfully end-to-end, including a real geocode+save test on a sample (real Toronto coordinates, `state` correctly resolved to "ON")
- **Found and fixed a real, high-impact bug this way**: the record's own `location` field is null for most *discovery-mode* results (unlike single-URL fetches, where it's usually present) — without a fix, most real search results would've been skipped entirely for "no address." Added a fallback to `discovery_input.city` (the city you searched for) plus a new Nominatim-based state/province resolution (`ISO3166-2-lvl4`, e.g. `"CA-ON"` → `"ON"`), since we often only have a bare city name, not "City, ST".
- The other 265 failures were "private room for rent" (shared housing) listings with no dedicated bathroom count to report — `bathrooms` is now nullable end-to-end (DB column, model, `ListingCreate`/`ListingResponse`, both scrapers, frontend types/display) rather than rejecting these. `min_bathrooms` filtering correctly excludes listings with unknown bathroom count (`NULL >= x` is never true in SQL, mirrored in the frontend mock filter) rather than guessing they qualify.
- Smaller known gap: a few real results were in Chinese, which the English-only regex fallback can't parse at all.
- Also caught and fixed two earlier bugs during this same testing pass: a bare 10-digit `product_id` initially misdetected as a phone number, and the "address not public" placeholder text initially leaking into the geocoding query itself (so city/state-only addresses failed to geocode at all until fixed).

### Manual testing

`backend/scripts/test_brightdata.py` — preview modes (`preview-search`, `preview-url`) fetch and map without touching the database; save modes (`save-search`, `save-url`) run the full pipeline. `*-search` is the primary path (see above); `*-url` exercises the unused single-URL fetch. See the script's docstring for usage.

## Development Phases

1. **Local Docker Compose (Postgres/PostGIS) & Database Models** — done
2. **FastAPI Backend & PostGIS Geospatial Endpoints** — done
3. **React + Mapbox Frontend Map Interface & Filters** — done
4. **Playwright Web Scraper Engine** — done
5. LangGraph AI Agent & Twilio SMS Service
