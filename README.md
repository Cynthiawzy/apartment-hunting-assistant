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
  alembic/      # migrations (0001 creates the postgis extension + all tables)
docker-compose.yml  # local Postgres/PostGIS
```

## Development Phases

1. **Local Docker Compose (Postgres/PostGIS) & Database Models** — done
2. FastAPI Backend & PostGIS Geospatial Endpoints (`ST_DWithin` radius search)
3. React + Mapbox Frontend Map Interface & Filters
4. Playwright Web Scraper Engine
5. LangGraph AI Agent & Twilio SMS Service
