from __future__ import annotations

import enum
from datetime import date
from typing import TYPE_CHECKING

from geoalchemy2 import Geometry
from sqlalchemy import ARRAY, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.neighborhood import Neighborhood
    from app.models.outreach import OutreachRequest


class SourceSite(str, enum.Enum):
    ZILLOW = "zillow"
    APARTMENTS_COM = "apartments_com"
    CRAIGSLIST = "craigslist"
    STREETEASY = "streeteasy"
    OTHER = "other"


class ListingStatus(str, enum.Enum):
    ACTIVE = "active"
    PENDING = "pending"
    LEASED = "leased"
    INACTIVE = "inactive"


class Listing(Base, TimestampMixin):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source_site", "source_listing_id", name="uq_listing_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    source_site: Mapped[SourceSite] = mapped_column(
        SAEnum(SourceSite, name="source_site"), nullable=False
    )
    source_listing_id: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    address_line: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50))
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)

    location: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )

    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    bedrooms: Mapped[float] = mapped_column(Numeric(3, 1), nullable=False)
    bathrooms: Mapped[float] = mapped_column(Numeric(3, 1), nullable=False)
    sqft: Mapped[int | None] = mapped_column()

    available_date: Mapped[date | None] = mapped_column(Date)
    pet_friendly: Mapped[bool | None] = mapped_column()
    amenities: Mapped[list[str] | None] = mapped_column(ARRAY(String(80)))

    landlord_name: Mapped[str | None] = mapped_column(String(120))
    landlord_phone: Mapped[str | None] = mapped_column(String(20))
    landlord_email: Mapped[str | None] = mapped_column(String(255))

    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ListingStatus] = mapped_column(
        SAEnum(ListingStatus, name="listing_status"),
        nullable=False,
        default=ListingStatus.ACTIVE,
    )
    scraped_at: Mapped[date] = mapped_column(nullable=False)

    neighborhood_id: Mapped[int | None] = mapped_column(ForeignKey("neighborhoods.id"))
    neighborhood: Mapped["Neighborhood | None"] = relationship(back_populates="listings")

    outreach_requests: Mapped[list["OutreachRequest"]] = relationship(
        back_populates="listing"
    )
