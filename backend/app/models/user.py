from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from geoalchemy2 import Geometry
from sqlalchemy import ARRAY, Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.outreach import OutreachRequest


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(20))

    budget_min: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    budget_max: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    min_bedrooms: Mapped[float | None] = mapped_column(Numeric(3, 1))
    max_bedrooms: Mapped[float | None] = mapped_column(Numeric(3, 1))
    desired_move_in_date: Mapped[date | None] = mapped_column(Date)

    home_location: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326)
    )
    search_radius_meters: Mapped[int] = mapped_column(Integer, nullable=False, default=1600)

    preferred_neighborhood_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))

    outreach_requests: Mapped[list["OutreachRequest"]] = relationship(back_populates="user")
