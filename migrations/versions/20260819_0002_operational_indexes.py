"""Add composite indexes for telemetry history queries."""

from alembic import op


revision = "20260819_0002"
down_revision = "20260819_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_metrics_node_measured_at", "metrics", ["node_id", "measured_at"], if_not_exists=True)
    op.create_index("ix_traffic_node_sampled_at", "traffic", ["node_id", "sampled_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_traffic_node_sampled_at", table_name="traffic")
    op.drop_index("ix_metrics_node_measured_at", table_name="metrics")
