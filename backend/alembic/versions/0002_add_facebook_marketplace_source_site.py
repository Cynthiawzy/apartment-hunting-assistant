"""add facebook_marketplace to source_site enum

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres allows adding an enum value inside a transaction (PG12+), but the
    # new value can't be *used* (e.g. in an INSERT) until this transaction commits.
    # This migration only adds it, so that's not an issue here.
    op.execute("ALTER TYPE source_site ADD VALUE IF NOT EXISTS 'facebook_marketplace'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Removing an enum value requires
    # rebuilding the type, which is unsafe if any row already uses it. Left as a
    # no-op; if you need to fully reverse this, drop and recreate `source_site`
    # after confirming no listings reference 'facebook_marketplace'.
    pass
