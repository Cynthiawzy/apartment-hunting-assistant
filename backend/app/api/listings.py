from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2 import Geography
from pydantic import ValidationError
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.crud.listings import DuplicateListingError, make_point
from app.crud.listings import create_listing as crud_create_listing
from app.models.listing import Listing, ListingStatus
from app.schemas.listing import ListingCreate, ListingFilter, ListingResponse

router = APIRouter(prefix="/api/listings", tags=["listings"])


def _to_response(
    listing: Listing, latitude: float, longitude: float, distance_km: float | None = None
) -> ListingResponse:
    return ListingResponse(
        id=listing.id,
        source_site=listing.source_site,
        source_listing_id=listing.source_listing_id,
        url=listing.url,
        address_line=listing.address_line,
        unit=listing.unit,
        city=listing.city,
        state=listing.state,
        zip_code=listing.zip_code,
        latitude=latitude,
        longitude=longitude,
        price=float(listing.price),
        bedrooms=float(listing.bedrooms),
        bathrooms=float(listing.bathrooms) if listing.bathrooms is not None else None,
        sqft=listing.sqft,
        available_date=listing.available_date,
        pet_friendly=listing.pet_friendly,
        amenities=listing.amenities,
        images=listing.images,
        landlord_name=listing.landlord_name,
        landlord_phone=listing.landlord_phone,
        landlord_email=listing.landlord_email,
        description=listing.description,
        status=listing.status,
        scraped_at=listing.scraped_at,
        neighborhood_id=listing.neighborhood_id,
        distance_km=distance_km,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
    )


async def _query_listings(
    db: AsyncSession,
    *,
    budget_max: float | None,
    min_beds: float | None,
    min_bathrooms: float | None,
    latitude: float | None,
    longitude: float | None,
    radius_km: float | None,
    limit: int,
    offset: int,
) -> list[ListingResponse]:
    lat_col = func.ST_Y(Listing.location).label("latitude")
    lng_col = func.ST_X(Listing.location).label("longitude")

    distance_expr: ColumnElement[Any] | None = None
    columns: list[Any] = [Listing, lat_col, lng_col]

    if latitude is not None and longitude is not None and radius_km is not None:
        origin = make_point(latitude, longitude)
        origin_geography = func.cast(origin, Geography)
        location_geography = func.cast(Listing.location, Geography)

        distance_expr = func.ST_Distance(location_geography, origin_geography) / 1000.0
        columns.append(distance_expr.label("distance_km"))

    stmt = select(*columns).where(Listing.status == ListingStatus.ACTIVE)

    if budget_max is not None:
        stmt = stmt.where(Listing.price <= budget_max)
    if min_beds is not None:
        stmt = stmt.where(Listing.bedrooms >= min_beds)
    if min_bathrooms is not None:
        stmt = stmt.where(Listing.bathrooms >= min_bathrooms)

    if latitude is not None and longitude is not None and radius_km is not None:
        stmt = stmt.where(
            func.ST_DWithin(location_geography, origin_geography, radius_km * 1000)
        ).order_by(distance_expr)

    stmt = stmt.limit(limit).offset(offset)

    rows = (await db.execute(stmt)).all()
    return [
        _to_response(row[0], row[1], row[2], row[3] if distance_expr is not None else None)
        for row in rows
    ]


@router.post("/", response_model=ListingResponse, status_code=status.HTTP_201_CREATED)
async def create_listing(
    payload: ListingCreate, db: AsyncSession = Depends(get_db)
) -> ListingResponse:
    try:
        listing = await crud_create_listing(db, payload)
    except DuplicateListingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _to_response(listing, payload.latitude, payload.longitude)


@router.get("/", response_model=list[ListingResponse])
async def list_listings(
    budget_max: float | None = Query(default=None, gt=0),
    min_beds: float | None = Query(default=None, ge=0),
    min_bathrooms: float | None = Query(default=None, ge=0),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float | None = Query(default=None, gt=0, le=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[ListingResponse]:
    try:
        filters = ListingFilter(
            budget_max=budget_max,
            min_beds=min_beds,
            min_bathrooms=min_bathrooms,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
        )
    except ValidationError as exc:
        errors = [
            {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
        ]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors
        ) from exc

    return await _query_listings(
        db,
        budget_max=filters.budget_max,
        min_beds=filters.min_beds,
        min_bathrooms=filters.min_bathrooms,
        latitude=filters.latitude,
        longitude=filters.longitude,
        radius_km=filters.radius_km,
        limit=limit,
        offset=offset,
    )


@router.get("/nearby", response_model=list[ListingResponse])
async def nearby_listings(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(..., gt=0, le=100),
    budget_max: float | None = Query(default=None, gt=0),
    min_beds: float | None = Query(default=None, ge=0),
    min_bathrooms: float | None = Query(default=None, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[ListingResponse]:
    return await _query_listings(
        db,
        budget_max=budget_max,
        min_beds=min_beds,
        min_bathrooms=min_bathrooms,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        limit=limit,
        offset=0,
    )
