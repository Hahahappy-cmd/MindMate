from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Use absolute path to be sure
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'mindmate.db')
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

def migrate_existing_sqlite_schema():
    """Apply the small additive migration needed by pre-Alembic databases."""
    if "journal_entries" not in inspect(engine).get_table_names():
        return

    existing = {
        column["name"] for column in inspect(engine).get_columns("journal_entries")
    }
    additions = {
        "sentiment_strength": "FLOAT",
        "analysis_confidence": "FLOAT",
        "analysis_method": "VARCHAR(64)",
        "analysis_version": "VARCHAR(32)",
        "analyzed_at": "DATETIME",
        "dominant_emotion": "VARCHAR(32)",
        "emotional_intensity": "FLOAT",
        "updated_at": "DATETIME",
    }
    with engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in existing:
                connection.execute(
                    text(f"ALTER TABLE journal_entries ADD COLUMN {name} {sql_type}")
                )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_journal_entries_user_created "
                "ON journal_entries (user_id, created_at)"
            )
        )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
