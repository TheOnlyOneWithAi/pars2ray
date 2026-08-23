"""Add per-client runtime limits and observed IP state."""

from alembic import op
import sqlalchemy as sa

revision = "20260823_0007"
down_revision = "20260822_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_runtime",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ip_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("online_ips", sa.JSON(), nullable=False),
        sa.Column("last_online_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("subscription_id", name="uq_client_runtime_subscription"),
    )
    op.create_index("ix_client_runtime_subscription_id", "client_runtime", ["subscription_id"])
    op.create_index("ix_client_runtime_last_online", "client_runtime", ["last_online_at"])


def downgrade() -> None:
    op.drop_index("ix_client_runtime_last_online", table_name="client_runtime")
    op.drop_index("ix_client_runtime_subscription_id", table_name="client_runtime")
    op.drop_table("client_runtime")
