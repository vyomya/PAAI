"""google tester access

Revision ID: fa247bbc5be9
Revises: 0564687ffa4e
Create Date: 2026-09-21 13:19:33.934126

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fa247bbc5be9'
down_revision: Union[str, Sequence[str], None] = '0564687ffa4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "google_testers",
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_google_testers_status", "google_testers", ["status"])


def downgrade() -> None:
    op.drop_index("ix_google_testers_status", table_name="google_testers")
    op.drop_table("google_testers")