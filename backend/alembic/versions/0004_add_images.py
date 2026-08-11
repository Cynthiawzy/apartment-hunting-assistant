"""add images to listings

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Text, not a length-capped varchar (like amenities uses) — real CDN photo
    # URLs (e.g. Facebook's) routinely run past 300 characters.
    op.add_column("listings", sa.Column("images", sa.ARRAY(sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "images")
