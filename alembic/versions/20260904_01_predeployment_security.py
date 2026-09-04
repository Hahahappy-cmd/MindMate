"""Pre-deployment token-family and reset-token security.

Revision ID: 20260904_01
Revises: 20260831_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260904_01"
down_revision = "20260831_01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("refresh_sessions", sa.Column("family_id", sa.String(36), nullable=True))
    op.execute("UPDATE refresh_sessions SET family_id = gen_random_uuid()::text WHERE family_id IS NULL")
    op.alter_column("refresh_sessions", "family_id", nullable=False)
    op.create_index("ix_refresh_sessions_family_id", "refresh_sessions", ["family_id"])

    op.add_column("password_reset_tokens", sa.Column("token_hash", sa.String(64), nullable=True))
    # Existing plaintext reset credentials are deliberately invalidated during migration.
    op.execute("DELETE FROM password_reset_tokens")
    op.alter_column("password_reset_tokens", "token_hash", nullable=False)
    op.create_unique_constraint("uq_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"])
    op.add_column("password_reset_tokens", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("password_reset_tokens_token_key", "password_reset_tokens", type_="unique")
    op.drop_column("password_reset_tokens", "token")
    op.drop_column("password_reset_tokens", "used")


def downgrade():
    op.add_column("password_reset_tokens", sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("password_reset_tokens", sa.Column("token", sa.String(), nullable=True))
    op.execute("DELETE FROM password_reset_tokens")
    op.alter_column("password_reset_tokens", "token", nullable=False)
    op.create_unique_constraint("password_reset_tokens_token_key", "password_reset_tokens", ["token"])
    op.drop_column("password_reset_tokens", "used_at")
    op.drop_constraint("uq_password_reset_tokens_token_hash", "password_reset_tokens", type_="unique")
    op.drop_column("password_reset_tokens", "token_hash")
    op.drop_index("ix_refresh_sessions_family_id", table_name="refresh_sessions")
    op.drop_column("refresh_sessions", "family_id")
