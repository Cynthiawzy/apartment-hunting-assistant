"""initial schema: postgis extension, neighborhoods, listings, users, outreach_requests

Revision ID: 0001
Revises:
Create Date: 2026-08-05

"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    source_site_enum = PGEnum(
        "zillow", "apartments_com", "craigslist", "streeteasy", "other",
        name="source_site",
        create_type=False,
    )
    listing_status_enum = PGEnum(
        "active", "pending", "leased", "inactive",
        name="listing_status",
        create_type=False,
    )
    outreach_status_enum = PGEnum(
        "draft", "sent", "delivered", "failed", "responded",
        name="outreach_status",
        create_type=False,
    )
    source_site_enum.create(op.get_bind(), checkfirst=True)
    listing_status_enum.create(op.get_bind(), checkfirst=True)
    outreach_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "neighborhoods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("city", sa.String(120), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column(
            "boundary",
            geoalchemy2.Geometry(geometry_type="POLYGON", srid=4326),
            nullable=False,
        ),
        sa.Column("median_rent_studio", sa.Numeric(10, 2), nullable=True),
        sa.Column("median_rent_1br", sa.Numeric(10, 2), nullable=True),
        sa.Column("median_rent_2br", sa.Numeric(10, 2), nullable=True),
        sa.Column("median_rent_3br", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    # GeoAlchemy2 auto-creates a GIST index (idx_neighborhoods_boundary) for this column.

    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_site", source_site_enum, nullable=False),
        sa.Column("source_listing_id", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("address_line", sa.String(255), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("city", sa.String(120), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("zip_code", sa.String(10), nullable=False),
        sa.Column(
            "location",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("bedrooms", sa.Numeric(3, 1), nullable=False),
        sa.Column("bathrooms", sa.Numeric(3, 1), nullable=False),
        sa.Column("sqft", sa.Integer(), nullable=True),
        sa.Column("available_date", sa.Date(), nullable=True),
        sa.Column("pet_friendly", sa.Boolean(), nullable=True),
        sa.Column("amenities", sa.ARRAY(sa.String(80)), nullable=True),
        sa.Column("landlord_name", sa.String(120), nullable=True),
        sa.Column("landlord_phone", sa.String(20), nullable=True),
        sa.Column("landlord_email", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", listing_status_enum, nullable=False, server_default="active"),
        sa.Column("scraped_at", sa.Date(), nullable=False),
        sa.Column(
            "neighborhood_id", sa.Integer(), sa.ForeignKey("neighborhoods.id"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source_site", "source_listing_id", name="uq_listing_source"),
    )
    # GeoAlchemy2 auto-creates a GIST index (idx_listings_location) for the location column.
    op.create_index("ix_listings_neighborhood_id", "listings", ["neighborhood_id"])
    op.create_index("ix_listings_price", "listings", ["price"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("budget_min", sa.Numeric(10, 2), nullable=False),
        sa.Column("budget_max", sa.Numeric(10, 2), nullable=False),
        sa.Column("min_bedrooms", sa.Numeric(3, 1), nullable=True),
        sa.Column("max_bedrooms", sa.Numeric(3, 1), nullable=True),
        sa.Column("desired_move_in_date", sa.Date(), nullable=True),
        sa.Column(
            "home_location",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("search_radius_meters", sa.Integer(), nullable=False, server_default="1600"),
        sa.Column("preferred_neighborhood_ids", sa.ARRAY(sa.Integer()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    # GeoAlchemy2 auto-creates a GIST index (idx_users_home_location) for this column.

    op.create_table(
        "outreach_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("listings.id"), nullable=False),
        sa.Column("status", outreach_status_enum, nullable=False, server_default="draft"),
        sa.Column("message_body", sa.Text(), nullable=False),
        sa.Column("twilio_sid", sa.String(64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_outreach_requests_user_id", "outreach_requests", ["user_id"])
    op.create_index("ix_outreach_requests_listing_id", "outreach_requests", ["listing_id"])


def downgrade() -> None:
    op.drop_table("outreach_requests")
    op.drop_table("users")
    op.drop_table("listings")
    op.drop_table("neighborhoods")

    sa.Enum(name="outreach_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="listing_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="source_site").drop(op.get_bind(), checkfirst=True)
