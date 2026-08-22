"""Store encrypted SSH provisioning metadata for managed nodes."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260821_0003"
down_revision = "20260819_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("nodes")}
    if "ssh_config_enc" not in columns:
        op.add_column("nodes", sa.Column("ssh_config_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("nodes")}
    if "ssh_config_enc" in columns:
        op.drop_column("nodes", "ssh_config_enc")
