"""Add encrypted subscription token storage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260822_0005"
down_revision = "20260822_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("subscriptions")}
    if "token_enc" not in columns:
        op.add_column("subscriptions", sa.Column("token_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("subscriptions")}
    if "token_enc" in columns:
        op.drop_column("subscriptions", "token_enc")
