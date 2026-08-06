"""make bathrooms optional

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # "Private room for rent" listings (shared housing, common on Facebook
    # Marketplace) have no dedicated bathroom count to report — it's shared
    # with the household, not a specific number.
    op.alter_column("listings", "bathrooms", existing_type=sa.Numeric(3, 1), nullable=True)


def downgrade() -> None:
    op.alter_column("listings", "bathrooms", existing_type=sa.Numeric(3, 1), nullable=False)
