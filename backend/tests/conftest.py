import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure project root is in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in [root_dir, backend_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token
from backend.app.main import app
from backend.app.modules.dictionaries.service import seed_dictionaries


def bearer(user_id: str, role: str = "CANDIDATE", email: str | None = None) -> dict[str, str]:
    """Authorization header of a signed-in user (the user row must exist in the database the app reads)."""
    token = create_access_token(subject=user_id, role=role, email=email or f"{user_id}@example.com")
    return {"Authorization": f"Bearer {token}"}

# Dedicated in-memory SQLite database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        seed_dictionaries(db)
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def candidate_headers(db_session):
    """A fresh candidate (user and profile) and the Authorization header to act as them."""
    import uuid

    from backend.app.models.candidate import CandidateProfile
    from backend.app.models.user import User

    uid = f"user-{uuid.uuid4().hex[:8]}"
    db_session.add(User(id=uid, email=f"{uid}@example.com", role="CANDIDATE", email_verified=True))
    db_session.add(CandidateProfile(id=f"cand-{uid}", user_id=uid, status="ACTIVELY_SEARCHING"))
    db_session.commit()
    return bearer(uid)
