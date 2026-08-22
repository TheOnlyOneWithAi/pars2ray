"""Add encrypted custom configuration storage to subscriptions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260822_0004"
down_revision = "20260821_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("subscriptions")}
    if "config_enc" not in columns:
        op.add_column("subscriptions", sa.Column("config_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("subscriptions")}
    if "config_enc" in columns:
        op.drop_column("subscriptions", "config_enc")
