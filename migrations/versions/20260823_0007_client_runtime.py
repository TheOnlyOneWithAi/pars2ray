"""Add per-client runtime limits and observed IP state."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260823_0007"
down_revision = "20260822_0006"
branch_labels = None
depends_on = None


TABLE = "client_runtime"
INDEX_SUBSCRIPTION = "ix_client_runtime_subscription_id"
INDEX_LAST_ONLINE = "ix_client_runtime_last_online"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if TABLE not in tables:
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("ip_limit", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("online_ips", sa.JSON(), nullable=False),
            sa.Column("last_online_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("subscription_id", name="uq_client_runtime_subscription"),
        )
        tables.add(TABLE)

    indexes = {index["name"] for index in inspector.get_indexes(TABLE)}
    if INDEX_SUBSCRIPTION not in indexes:
        op.create_index(INDEX_SUBSCRIPTION, TABLE, ["subscription_id"])
    if INDEX_LAST_ONLINE not in indexes:
        op.create_index(INDEX_LAST_ONLINE, TABLE, ["last_online_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if TABLE not in tables:
        return
    indexes = {index["name"] for index in inspector.get_indexes(TABLE)}
    if INDEX_LAST_ONLINE in indexes:
        op.drop_index(INDEX_LAST_ONLINE, table_name=TABLE)
    if INDEX_SUBSCRIPTION in indexes:
        op.drop_index(INDEX_SUBSCRIPTION, table_name=TABLE)
    op.drop_table(TABLE)
