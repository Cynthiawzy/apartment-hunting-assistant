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
    components/
      MapView.tsx            # mapbox-gl markers + hover popups
      Sidebar.tsx             # filter inputs + listing card list
      ListingCard.tsx
      ListingModal.tsx        # full listing detail modal
    App.tsx
```

## Development Phases

1. **Local Docker Compose (Postgres/PostGIS) & Database Models** — done
2. **FastAPI Backend & PostGIS Geospatial Endpoints** — done
3. **React + Mapbox Frontend Map Interface & Filters** — done
4. Playwright Web Scraper Engine
5. LangGraph AI Agent & Twilio SMS Service
