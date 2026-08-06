"""apple health integration tables

Revision ID: a1b2c3d4e5f6
Revises: 8f9c28b008e4
Create Date: 2026-08-05 19:20:19.221000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "8f9c28b008e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_sync_token",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("api_sync_token", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_api_sync_token_prefix"), ["prefix"], unique=False)
        batch_op.create_index("ix_api_sync_token_user", ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_api_sync_token_user_id"), ["user_id"], unique=False)

    op.create_table(
        "health_import_batch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("records_inserted", sa.Integer(), nullable=False),
        sa.Column("records_updated", sa.Integer(), nullable=False),
        sa.Column("records_skipped", sa.Integer(), nullable=False),
        sa.Column("records_invalid", sa.Integer(), nullable=False),
        sa.Column("records_conflict", sa.Integer(), nullable=False),
        sa.Column("date_start", sa.Date(), nullable=True),
        sa.Column("date_end", sa.Date(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("health_import_batch", schema=None) as batch_op:
        batch_op.create_index("ix_health_import_batch_user", ["user_id", "created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_health_import_batch_user_id"), ["user_id"], unique=False)

    op.create_table(
        "imported_health_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("resource_type", sa.String(length=24), nullable=False),
        sa.Column("external_key", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("imported_payload", sa.Text(), nullable=False),
        sa.Column("local_resource_type", sa.String(length=24), nullable=False),
        sa.Column("local_resource_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["health_import_batch.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", "resource_type", "external_key", name="uq_imported_health_record"),
    )
    with op.batch_alter_table("imported_health_record", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_imported_health_record_batch_id"), ["batch_id"], unique=False)
        batch_op.create_index("ix_imported_health_record_user_type", ["user_id", "provider", "resource_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_imported_health_record_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("imported_health_record", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_imported_health_record_user_id"))
        batch_op.drop_index("ix_imported_health_record_user_type")
        batch_op.drop_index(batch_op.f("ix_imported_health_record_batch_id"))
    op.drop_table("imported_health_record")

    with op.batch_alter_table("health_import_batch", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_health_import_batch_user_id"))
        batch_op.drop_index("ix_health_import_batch_user")
    op.drop_table("health_import_batch")

    with op.batch_alter_table("api_sync_token", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_api_sync_token_user_id"))
        batch_op.drop_index("ix_api_sync_token_user")
        batch_op.drop_index(batch_op.f("ix_api_sync_token_prefix"))
    op.drop_table("api_sync_token")
