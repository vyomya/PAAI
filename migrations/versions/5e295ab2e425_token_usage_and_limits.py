"""token usage and limits

Revision ID: 5e295ab2e425
Revises: fa247bbc5be9
Create Date: 2026-09-22 23:07:51.875303

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5e295ab2e425'
down_revision: Union[str, Sequence[str], None] = 'fa247bbc5be9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "token_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("model", sa.String(60), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_token_usage_user_id", "token_usage", ["user_id"])
    op.create_index("ix_token_usage_user_created", "token_usage", ["user_id", "created_at"])
    op.create_index("ix_token_usage_session_id", "token_usage", ["session_id"])
    op.add_column("users", sa.Column("token_limit", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "token_limit")
    op.drop_table("token_usage")
