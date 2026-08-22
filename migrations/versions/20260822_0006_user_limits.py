"""Add optional quota and expiry fields to users and allow limit-free subscriptions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260822_0006"
down_revision = "20260822_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "quota_gb" not in user_columns:
        op.add_column("users", sa.Column("quota_gb", sa.Float(), nullable=False, server_default="0"))
    if "used_gb" not in user_columns:
        op.add_column("users", sa.Column("used_gb", sa.Float(), nullable=False, server_default="0"))
    if "expires_at" not in user_columns:
        op.add_column("users", sa.Column("expires_at", sa.DateTime(), nullable=True))

    sub_columns = {column["name"]: column for column in inspector.get_columns("subscriptions")}
    plan = sub_columns.get("plan_id")
    if plan and plan.get("nullable") is False:
        with op.batch_alter_table("subscriptions") as batch:
            batch.alter_column("plan_id", existing_type=sa.Integer(), nullable=True)
    expires = sub_columns.get("expires_at")
    if expires and expires.get("nullable") is False:
        with op.batch_alter_table("subscriptions") as batch:
            batch.alter_column("expires_at", existing_type=sa.DateTime(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    with op.batch_alter_table("users") as batch:
        if "expires_at" in user_columns:
            batch.drop_column("expires_at")
        if "used_gb" in user_columns:
            batch.drop_column("used_gb")
        if "quota_gb" in user_columns:
            batch.drop_column("quota_gb")
