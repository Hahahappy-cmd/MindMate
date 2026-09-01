"""Print non-sensitive PostgreSQL schema diagnostics for local development."""

from sqlalchemy import inspect, text

from app.database import engine


def main() -> None:
    inspector = inspect(engine)
    with engine.connect() as connection:
        server_version = connection.execute(text("SHOW server_version")).scalar_one()
        migration = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()

    print(f"Database dialect: {engine.dialect.name}")
    print(f"PostgreSQL version: {server_version}")
    print(f"Alembic revision: {migration or 'not applied'}")
    print(f"Tables: {', '.join(sorted(inspector.get_table_names()))}")


if __name__ == "__main__":
    main()
