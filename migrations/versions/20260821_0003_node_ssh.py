"""Store encrypted SSH provisioning metadata for managed nodes."""

from alembic import op
import sqlalchemy as sa

revision = "20260821_0003"
down_revision = "20260819_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("ssh_config_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("nodes", "ssh_config_enc")
