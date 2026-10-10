"""Integration tests for Profiles API, Standardized PDF generation, and Selection Snapshots."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.v1.api import api_router
from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token
from backend.app.models.candidate import CandidateProfile, CandidateSkill, FSPAchievement
from backend.app.models.company import Company, EmployerMember, Need
from backend.app.models.dictionary import Skill
from backend.app.models.user import User


@pytest.fixture
def test_app():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed data
    db = TestingSession()

    # 1. Users
    user_cand = User(id="u-cand-alice", email="alice@test.ru", role="CANDIDATE", is_active=True)
    user_emp = User(id="u-emp-bob", email="bob@company.ru", role="EMPLOYER", is_active=True)
    db.add_all([user_cand, user_emp])
    db.flush()

    # 2. Candidate profile
    cand = CandidateProfile(
        id="cand-alice-profile",
        user_id="u-cand-alice",
        first_name="Алиса",
        last_name="Яковлева",
        phone="+7 (903) 123-45-67",
        telegram="@alice_dev",
        city="Москва",
        work_format="REMOTE",
        desired_salary_min=240000,
        confirmed_category="Backend · Middle",
        confirmed_specialization="Backend",
        confirmed_grade="MIDDLE",
        category_percentile=92,
        last_theta=1.65,
        fsp_id="FSP-2002",
        fsp_score=0.85,
        is_fsp_verified=True,
        status="ACTIVELY_SEARCHING",
    )
    db.add(cand)

    # Candidate 2: without FSP
    user_cand2 = User(id="u-cand-dmitry", email="dmitry@test.ru", role="CANDIDATE", is_active=True)
    db.add(user_cand2)
    db.flush()

    cand2 = CandidateProfile(
        id="cand-dmitry-profile",
        user_id="u-cand-dmitry",
        first_name="Дмитрий",
        last_name="Орлов",
        confirmed_category="Backend · Junior",
        confirmed_specialization="Backend",
        confirmed_grade="JUNIOR",
        category_percentile=60,
        desired_salary_min=130000,
        work_format="REMOTE",
        city="Казань",
        status="ACTIVELY_SEARCHING",
    )
    db.add(cand2)

    # 3. Company & Employer
    comp = Company(
        id="comp-tech",
        name="Технологии Будущего",
        inn="7701234567",
        website="https://techfuture.ru",
        description="Разработка высоконагруженных платформ",
        is_verified=True,
    )
    db.add(comp)
    db.flush()

    emp_member = EmployerMember(
        id="member-bob",
        user_id="u-emp-bob",
        company_id="comp-tech",
        role="OWNER",
    )
    db.add(emp_member)

    # 4. Skills & Achievements
    py_skill = Skill(id="sk-py", code="PYTHON", name="Python")
    go_skill = Skill(id="sk-go", code="GO", name="Go / Golang")
    db.add_all([py_skill, go_skill])
    db.flush()

    cs1 = CandidateSkill(candidate_profile_id=cand.id, skill_id=py_skill.id, confirmation_source="ASSESSMENT", weight=1.0)
    cs2 = CandidateSkill(candidate_profile_id=cand.id, skill_id=go_skill.id, confirmation_source="FSP", weight=1.0)
    db.add_all([cs1, cs2])

    ach = FSPAchievement(
        candidate_profile_id=cand.id,
        event_name="Чемпионат России по спортивному программированию 2025",
        discipline="Алгоритмическое программирование",
        level="Всероссийский",
        result="1 место",
        sport_category="Мастер спорта",
        calculated_weight=0.95,
    )
    db.add(ach)

    # 5. Need
    need = Need(
        id="need-backend-1",
        company_id="comp-tech",
        title="Senior / Middle Go Backend Developer",
        target_specialization="Backend",
        target_grade="MIDDLE",
        required_skills=["Python", "Go / Golang"],
        salary_budget_min=200000,
        salary_budget_max=300000,
        work_format="REMOTE",
        is_active=True,
    )
    db.add(need)

    db.commit()
    db.close()

    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


@pytest.fixture
def cand_token():
    return create_access_token(subject="u-cand-alice", role="CANDIDATE", email="alice@test.ru", fsp_id="FSP-2002")


@pytest.fixture
def emp_token():
    return create_access_token(subject="u-emp-bob", role="EMPLOYER", email="bob@company.ru")


# ==============================================================================
# TESTS
# ==============================================================================

def test_get_me_profile_with_jwt(client, cand_token):
    """GET /api/v1/me/profile returns authenticated candidate profile data."""
    headers = {"Authorization": f"Bearer {cand_token}"}
    resp = client.get("/api/v1/me/profile", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "cand-alice-profile"
    assert data["first_name"] == "Алиса"
    assert data["last_name"] == "Яковлева"
    assert data["confirmed_category"] == "Backend · Middle"
    assert data["category_percentile"] == 92
    assert data["is_fsp_verified"] is True
    assert data["fsp_score"] == 0.85
    assert len(data["skills"]) == 2
    assert len(data["fsp_achievements"]) == 1
    assert data["fsp_achievements"][0]["sport_category"] == "Мастер спорта"


def test_put_me_profile_updates_contacts_and_salary(client, cand_token):
    """PUT /api/v1/me/profile updates candidate contacts, city, work format, and salary with Gross/Net."""
    headers = {"Authorization": f"Bearer {cand_token}"}
    payload = {
        "phone": "+7 (999) 777-66-55",
        "telegram": "@alice_lead",
        "city": "Нижний Новгород",
        "work_format": "OFFICE",
        "desired_salary_min": 320000,
        "salary_type": "GROSS",
        "is_gross": True,
    }
    resp = client.put("/api/v1/me/profile", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["phone"] == "+7 (999) 777-66-55"
    assert data["telegram"] == "@alice_lead"
    assert data["city"] == "Нижний Новгород"
    assert data["work_format"] == "OFFICE"
    assert data["desired_salary_min"] == 320000
    assert data["salary_type"] == "GROSS"
    assert data["is_gross"] is True
    assert "Гросс" in data["salary_display"] or "до вычета" in data["salary_display"]


def test_get_and_put_company_profile(client, emp_token):
    """GET and PUT /api/v1/companies/me for authenticated company employer."""
    headers = {"Authorization": f"Bearer {emp_token}"}
    # GET
    resp = client.get("/api/v1/companies/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "comp-tech"
    assert data["name"] == "Технологии Будущего"
    assert data["inn"] == "7701234567"

    # PUT
    update_data = {
        "name": "Технологии Будущего Групп",
        "description": "Обновленное описание компании",
        "website": "https://techfuture.group",
    }
    resp_put = client.put("/api/v1/companies/me", json=update_data, headers=headers)
    assert resp_put.status_code == 200
    updated = resp_put.json()
    assert updated["name"] == "Технологии Будущего Групп"
    assert updated["website"] == "https://techfuture.group"
    assert updated["description"] == "Обновленное описание компании"


def test_standardized_pdf_generation_content_and_headers(client, cand_token, emp_token):
    """GET /api/v1/candidates/{id}/pdf and /api/v1/me/pdf returns valid PDF stream."""
    # 1. Download by ID (an employer looking at the candidate card)
    resp = client.get("/api/v1/candidates/cand-alice-profile/pdf", headers={"Authorization": f"Bearer {emp_token}"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "fsp_candidate_" in resp.headers.get("content-disposition", "")
    assert resp.content.startswith(b"%PDF-")
    assert len(resp.content) > 10000

    # 2. Download own PDF with JWT
    headers = {"Authorization": f"Bearer {cand_token}"}
    resp_me = client.get("/api/v1/me/pdf", headers=headers)
    assert resp_me.status_code == 200
    assert resp_me.headers["content-type"] == "application/pdf"
    assert resp_me.content.startswith(b"%PDF-")
    assert len(resp_me.content) > 10000


def test_snapshots_api_workflow(client, emp_token):
    """Workflow: create recommendations -> snapshots saved -> list snapshots -> fetch snapshot."""
    client.headers.update({"Authorization": f"Bearer {emp_token}"})
    # 1. Request recommendations with save_snapshot=True
    resp_rec = client.get("/api/v1/needs/need-backend-1/recommendations?save_snapshot=true")
    assert resp_rec.status_code == 200
    rec_json = resp_rec.json()
    snap_id = rec_json["snapshot_id"]
    assert snap_id is not None
    assert rec_json["total_found"] >= 1

    # 2. List snapshots
    resp_list = client.get("/api/v1/needs/need-backend-1/snapshots")
    assert resp_list.status_code == 200
    snapshots = resp_list.json()
    assert len(snapshots) >= 1
    assert snapshots[0]["id"] == snap_id
    assert snapshots[0]["need_id"] == "need-backend-1"
    assert snapshots[0]["total_found"] >= 1
    assert len(snapshots[0]["items"]) >= 1

    # 3. Retrieve specific snapshot (returning to snapshot without loss of selection)
    resp_get = client.get(f"/api/v1/snapshots/{snap_id}")
    assert resp_get.status_code == 200
    snapshot_detail = resp_get.json()
    assert snapshot_detail["id"] == snap_id
    assert snapshot_detail["need_id"] == "need-backend-1"
    assert len(snapshot_detail["items"]) >= 1
    # Check top candidate in saved snapshot is cand-alice-profile
    assert snapshot_detail["items"][0]["candidate_id"] == "cand-alice-profile"
    assert snapshot_detail["items"][0]["total_score"] > 0.5


def test_candidate_search_has_fsp_filter(client, emp_token):
    """GET /api/v1/search/candidates with and without has_fsp query parameter."""
    client.headers.update({"Authorization": f"Bearer {emp_token}"})
    # All candidates
    resp_all = client.get("/api/v1/search/candidates?specialization=Backend")
    assert resp_all.status_code == 200
    items_all = resp_all.json()["items"]
    cand_ids_all = {item["candidate_id"] for item in items_all}
    assert "cand-alice-profile" in cand_ids_all
    assert "cand-dmitry-profile" in cand_ids_all

    # Filter with has_fsp=true
    resp_fsp = client.get("/api/v1/search/candidates?specialization=Backend&has_fsp=true")
    assert resp_fsp.status_code == 200
    items_fsp = resp_fsp.json()["items"]
    cand_ids_fsp = {item["candidate_id"] for item in items_fsp}
    assert "cand-alice-profile" in cand_ids_fsp
    assert "cand-dmitry-profile" not in cand_ids_fsp
