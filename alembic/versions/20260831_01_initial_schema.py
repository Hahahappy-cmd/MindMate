"""Initial PostgreSQL-only MindMate schema."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260831_01"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("users",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("email", sa.String(320), nullable=False),
        sa.Column("username", sa.String(50), nullable=False), sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("email"), sa.UniqueConstraint("username"))
    op.create_table("journal_entries",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False), sa.Column("analysis_state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("analysis_generation", sa.String(36)), sa.Column("analysis_job_id", sa.String(128)), sa.Column("analysis_error", sa.Text()),
        sa.Column("analysis_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analysis_queued_at", sa.DateTime(timezone=True)), sa.Column("analysis_started_at", sa.DateTime(timezone=True)), sa.Column("analysis_completed_at", sa.DateTime(timezone=True)),
        sa.Column("sentiment_score", sa.Float()), sa.Column("sentiment_label", sa.String(32)), sa.Column("sentiment_strength", sa.Float()),
        sa.Column("analysis_confidence", sa.Float()), sa.Column("analysis_method", sa.String(64)), sa.Column("analysis_version", sa.String(64)),
        sa.Column("analyzed_at", sa.DateTime(timezone=True)), sa.Column("subjectivity", sa.Float()), sa.Column("word_count", sa.Integer()),
        sa.Column("emotion_data", postgresql.JSONB()), sa.Column("dominant_emotion", sa.String(32)), sa.Column("emotional_intensity", sa.Float()),
        sa.Column("emotion_model_name", sa.String(128)), sa.Column("emotion_model_version", sa.String(64)), sa.Column("emotion_score_semantics", sa.String(64)),
        sa.Column("emotion_threshold", sa.Float()), sa.Column("emotion_chunks", sa.Integer()), sa.Column("theme_embedding", postgresql.JSONB()),
        sa.Column("theme_embedding_model", sa.String(128)), sa.Column("theme_embedding_version", sa.String(64)), sa.Column("theme_embedding_hash", sa.String(64)),
        sa.Column("theme_embedded_at", sa.DateTime(timezone=True)), sa.Column("key_phrases", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.CheckConstraint("analysis_state IN ('pending','processing','completed','failed')", name="ck_journal_analysis_state"),
        sa.CheckConstraint("analysis_attempts >= 0", name="ck_journal_analysis_attempts"))
    op.create_index("ix_journal_entries_user_created", "journal_entries", ["user_id", "created_at"])
    op.create_index("ix_journal_entries_user_state_created", "journal_entries", ["user_id", "analysis_state", "created_at"])
    op.create_index("ix_journal_entries_analysis_state", "journal_entries", ["analysis_state"])
    op.create_table("password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("token", sa.String(), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    _create_refresh_sessions()


def _create_refresh_sessions():
    op.create_table("refresh_sessions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("jti_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by_hash", sa.String(64)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_refresh_sessions_user_active", "refresh_sessions", ["user_id", "revoked_at"])


def downgrade():
    op.drop_table("refresh_sessions")
    op.drop_table("password_reset_tokens")
    op.drop_table("journal_entries")
    op.drop_table("users")
