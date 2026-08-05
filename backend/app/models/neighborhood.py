from __future__ import annotations

from typing import TYPE_CHECKING

from geoalchemy2 import Geometry
from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.listing import Listing


class Neighborhood(Base, TimestampMixin):
    __tablename__ = "neighborhoods"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)

    boundary: Mapped[str] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=False
    )

    median_rent_studio: Mapped[float | None] = mapped_column(Numeric(10, 2))
    median_rent_1br: Mapped[float | None] = mapped_column(Numeric(10, 2))
    median_rent_2br: Mapped[float | None] = mapped_column(Numeric(10, 2))
    median_rent_3br: Mapped[float | None] = mapped_column(Numeric(10, 2))

    listings: Mapped[list["Listing"]] = relationship(back_populates="neighborhood")
