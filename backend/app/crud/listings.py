from geoalchemy2.elements import WKTElement
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing import Listing
from app.schemas.listing import ListingCreate


class DuplicateListingError(Exception):
    """Raised when a listing with the same (source_site, source_listing_id) already exists."""


def make_point(latitude: float, longitude: float) -> WKTElement:
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


async def create_listing(db: AsyncSession, payload: ListingCreate) -> Listing:
    """Insert a listing from a validated ListingCreate. Shared by the API layer and the scraper."""
    listing = Listing(
        source_site=payload.source_site,
        source_listing_id=payload.source_listing_id,
        url=payload.url,
        address_line=payload.address_line,
        unit=payload.unit,
        city=payload.city,
        state=payload.state,
        zip_code=payload.zip_code,
        location=make_point(payload.latitude, payload.longitude),
        price=payload.price,
        bedrooms=payload.bedrooms,
        bathrooms=payload.bathrooms,
        sqft=payload.sqft,
        available_date=payload.available_date,
        pet_friendly=payload.pet_friendly,
        amenities=payload.amenities,
        images=payload.images,
        landlord_name=payload.landlord_name,
        landlord_phone=payload.landlord_phone,
        landlord_email=payload.landlord_email,
        description=payload.description,
        status=payload.status,
        scraped_at=payload.scraped_at,
        neighborhood_id=payload.neighborhood_id,
    )
    db.add(listing)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateListingError(
            f"Listing already exists for {payload.source_site}/{payload.source_listing_id}"
        ) from exc
    await db.refresh(listing)
    return listing
