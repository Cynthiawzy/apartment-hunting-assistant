"""add kijiji to source_site enum

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE source_site ADD VALUE IF NOT EXISTS 'kijiji'")


def downgrade() -> None:
    # See 0002_add_facebook_marketplace_source_site.py — Postgres has no ALTER
    # TYPE ... DROP VALUE; left as a no-op.
    pass
