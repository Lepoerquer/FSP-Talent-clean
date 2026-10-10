from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

try:
    from backend.app.core.config import settings
except ImportError:
    from app.core.config import settings

# Handling connect_args and pool for SQLite (file or in-memory)
connect_args = {}
engine_kwargs = {"echo": False}

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    engine_kwargs["connect_args"] = connect_args
    if ":memory:" in settings.DATABASE_URL:
        # StaticPool ensures the in-memory SQLite database persists across threads and sessions
        engine_kwargs["poolclass"] = StaticPool

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

# Enable foreign keys for SQLite
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables():
    """Helper to create all tables registered with Base."""
    # Ensure all models are imported so they register with metadata
    try:
        import backend.app.models  # noqa: F401
    except ImportError:
        import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Ensure added columns exist in existing SQLite databases
    if engine.url.drivername.startswith("sqlite"):
        from sqlalchemy import text
        with engine.begin() as conn:
            for table, col, col_def in [
                ("assessment_sessions", "is_demo", "BOOLEAN DEFAULT 0"),
                ("candidate_profiles", "declared_grade", "VARCHAR(50)"),
                ("candidate_profiles", "experience_years", "FLOAT"),
                ("candidate_profiles", "stack", "TEXT"),
                ("candidate_profiles", "soft_skills", "TEXT"),
                ("candidate_profiles", "roles", "TEXT"),
                ("candidate_profiles", "about_me", "TEXT"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))
                except Exception:
                    pass
