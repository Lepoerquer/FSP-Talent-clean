"""End-to-End API integration tests for Invitations, Matching & Recommendations, and FSP linking."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base, get_db
from backend.app.models.candidate import CandidateProfile, CandidateSkill
from backend.app.models.company import Company, EmployerMember
from backend.app.models.dictionary import Skill
from backend.app.models.user import User
from backend.app.modules.fsp.router import router as fsp_router
from backend.app.modules.invitations.router import router as invitations_router
from backend.app.modules.matching.router import router as matching_router
from backend.app.modules.profiles.router import router as profiles_router
from backend.app.modules.auth.router import router as auth_router
from backend.app.modules.ats.router import router as ats_router
from conftest import bearer

EMPLOYER = bearer("u-emp-vk", "EMPLOYER")
CANDIDATE = bearer("u-cand-1")
JUNIOR = bearer("u-cand-2")


@pytest.fixture
def app_with_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    app = FastAPI()
    app.include_router(invitations_router, prefix="/api/v1")
    app.include_router(matching_router, prefix="/api/v1")
    app.include_router(fsp_router, prefix="/api/v1")
    app.include_router(profiles_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(ats_router, prefix="/api/v1")

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed data
    db = TestingSessionLocal()
    # Company
    comp = Company(id="comp-vk", name="VK Tech", inn="7705001122", is_verified=True)
    db.add(comp)
    db.add(User(id="u-emp-vk", email="hr@vk.example.com", role="EMPLOYER"))
    db.add(EmployerMember(user_id="u-emp-vk", company_id="comp-vk", role="OWNER"))
    # Another company that must never see or touch VK's data
    db.add(Company(id="comp-other", name="Other LLC"))
    db.add(User(id="u-emp-other", email="hr@other.example.com", role="EMPLOYER"))
    db.add(EmployerMember(user_id="u-emp-other", company_id="comp-other", role="OWNER"))

    # Candidate 1: Verified Middle Backend
    user1 = User(id="u-cand-1", email="developer.m@example.com", role="CANDIDATE")
    db.add(user1)

    cand1 = CandidateProfile(
        id="cand-middle-1",
        user_id="u-cand-1",
        first_name="Максим",
        last_name="Смирнов",
        phone="+7 (916) 555-44-33",
        telegram="@max_backend",
        confirmed_category="Backend · Middle",
        confirmed_specialization="Backend",
        confirmed_grade="MIDDLE",
        category_percentile=88,
        last_theta=1.2,
        desired_salary_min=220000,
        work_format="REMOTE",
        city="Москва",
        status="ACTIVELY_SEARCHING",
    )
    db.add(cand1)

    # Candidate 2: Junior Backend
    user2 = User(id="u-cand-2", email="junior.dev@example.com", role="CANDIDATE")
    db.add(user2)
    cand2 = CandidateProfile(
        id="cand-junior-2",
        user_id="u-cand-2",
        first_name="Анна",
        last_name="Волкова",
        confirmed_category="Backend · Junior",
        confirmed_specialization="Backend",
        confirmed_grade="JUNIOR",
        category_percentile=70,
        desired_salary_min=120000,
        work_format="REMOTE",
        city="Москва",
        status="ACTIVELY_SEARCHING",
    )
    db.add(cand2)

    # Skills
    py_skill = Skill(id="sk-1", code="PYTHON", name="Python")
    pg_skill = Skill(id="sk-2", code="POSTGRESQL", name="PostgreSQL")
    db.add_all([py_skill, pg_skill])
    db.flush()

    cs1 = CandidateSkill(candidate_profile_id=cand1.id, skill_id=py_skill.id, confirmation_source="ASSESSMENT")
    cs2 = CandidateSkill(candidate_profile_id=cand1.id, skill_id=pg_skill.id, confirmation_source="ASSESSMENT")
    db.add_all([cs1, cs2])

    db.commit()
    db.close()

    return app


@pytest.fixture
def client(app_with_db):
    return TestClient(app_with_db)


# ==============================================================================
# 1. INVITATIONS API ENDPOINTS E2E TESTS
# ==============================================================================

def test_invitation_lifecycle_e2e(client):
    """End-to-End test of invitation creation, view, accept, contact disclosure and decline."""
    # 1. Employer creates an invitation
    create_payload = {
        "candidate_profile_id": "cand-middle-1",
        "company_id": "comp-vk",
        "salary_from": 230000,
        "salary_to": 280000,
        "message": "Приглашаем в команду Backend-разработки для работы над высоконагруженными сервисами.",
        "contact_method": "TELEGRAM",
    }
    resp = client.post("/api/v1/invitations", json=create_payload, headers=EMPLOYER)
    assert resp.status_code == 201
    data = resp.json()
    inv_id = data["id"]
    assert data["status"] == "SENT"
    assert data["salary_from"] == 230000
    assert data["salary_to"] == 280000
    assert data["contacts_disclosed"] is False
    assert data["candidate_contacts"] is None  # Contacts hidden!

    # 2. Get invitations for candidate
    resp_cand = client.get("/api/v1/invitations/candidate", headers=CANDIDATE)
    assert resp_cand.status_code == 200
    assert len(resp_cand.json()) == 1
    assert resp_cand.json()[0]["id"] == inv_id

    # 3. Candidate views invitation
    resp_view = client.post(f"/api/v1/invitations/{inv_id}/view", headers=CANDIDATE)
    assert resp_view.status_code == 200
    assert resp_view.json()["status"] == "VIEWED"
    assert resp_view.json()["contacts_disclosed"] is False

    # 4. Candidate accepts invitation -> Contacts DISCLOSED!
    resp_accept = client.post(f"/api/v1/invitations/{inv_id}/accept", headers=CANDIDATE)
    assert resp_accept.status_code == 200
    accept_data = resp_accept.json()
    assert accept_data["status"] == "ACCEPTED"
    assert accept_data["contacts_disclosed"] is True
    assert accept_data["candidate_contacts"] is not None
    assert accept_data["candidate_contacts"]["first_name"] == "Максим"
    assert accept_data["candidate_contacts"]["telegram"] == "@max_backend"
    assert accept_data["candidate_contacts"]["phone"] == "+7 (916) 555-44-33"

    # 5. Employer fetches company invitations -> sees disclosed contacts
    resp_comp = client.get("/api/v1/invitations/company", headers=EMPLOYER)
    assert resp_comp.status_code == 200
    comp_invs = resp_comp.json()
    assert len(comp_invs) == 1
    assert comp_invs[0]["contacts_disclosed"] is True
    assert comp_invs[0]["candidate_contacts"]["telegram"] == "@max_backend"


def test_invitation_salary_negative_fails(client):
    """POST /api/v1/invitations must fail with 422/400 if salary_from > salary_to."""
    invalid_payload = {
        "candidate_profile_id": "cand-middle-1",
        "company_id": "comp-vk",
        "salary_from": 350000,
        "salary_to": 250000,
        "message": "Тестовое сообщение с невалидной зарплатой",
    }
    resp = client.post("/api/v1/invitations", json=invalid_payload, headers=EMPLOYER)
    assert resp.status_code in (400, 422)


def test_invitation_decline_and_withdraw_e2e(client):
    """Decline with reason and Withdraw by employer."""
    # Create first invitation to decline
    inv1 = client.post(
        "/api/v1/invitations",
        json={
            "candidate_profile_id": "cand-middle-1",
            "company_id": "comp-vk",
            "salary_from": 200000,
            "salary_to": 220000,
            "message": "Приглашение для отклонения кандидатом.",
        },
        headers=EMPLOYER,
    ).json()

    # Decline without reason fails
    resp_fail = client.post(f"/api/v1/invitations/{inv1['id']}/decline", json={}, headers=CANDIDATE)
    assert resp_fail.status_code in (400, 422)

    # Decline with reason TECH_STACK succeeds
    resp_dec = client.post(
        f"/api/v1/invitations/{inv1['id']}/decline",
        json={"decline_reason": "TECH_STACK"},
        headers=CANDIDATE,
    )
    assert resp_dec.status_code == 200
    assert resp_dec.json()["status"] == "DECLINED"
    assert resp_dec.json()["decline_reason"] == "TECH_STACK"

    # Create second invitation to withdraw
    inv2 = client.post(
        "/api/v1/invitations",
        json={
            "candidate_profile_id": "cand-junior-2",
            "company_id": "comp-vk",
            "salary_from": 120000,
            "salary_to": 150000,
            "message": "Приглашение для отзыва компанией.",
        },
        headers=EMPLOYER,
    ).json()

    # Withdraw by employer succeeds
    resp_with = client.post(f"/api/v1/invitations/{inv2['id']}/withdraw", headers=EMPLOYER)
    assert resp_with.status_code == 200
    assert resp_with.json()["status"] == "WITHDRAWN"


# ==============================================================================
# 2. MATCHING & RECOMMENDATIONS API ENDPOINTS E2E TESTS
# ==============================================================================

def test_needs_creation_and_recommendations_e2e(client):
    """Employer creates Need -> GET /needs/{id}/recommendations returns ranked candidates with explainability."""
    need_payload = {
        "title": "Middle Python Backend Engineer",
        "target_specialization": "Backend",
        "target_grade": "MIDDLE",
        "required_skills": ["Python", "PostgreSQL"],
        "salary_budget_min": 200000,
        "salary_budget_max": 270000,
        "work_format": "REMOTE",
    }
    resp_need = client.post("/api/v1/needs", json=need_payload, headers=EMPLOYER)
    assert resp_need.status_code == 201
    need_data = resp_need.json()
    need_id = need_data["id"]

    # Request recommendations
    resp_rec = client.get(f"/api/v1/needs/{need_id}/recommendations?limit=10", headers=EMPLOYER)
    assert resp_rec.status_code == 200
    rec_data = resp_rec.json()
    assert rec_data["need_id"] == need_id
    assert rec_data["total_found"] >= 1
    assert rec_data["snapshot_id"] is not None  # Automatic snapshot created!

    # Top candidate should be cand-middle-1 (exact Middle Backend match)
    top_cand = rec_data["items"][0]
    assert top_cand["candidate_id"] == "cand-middle-1"
    assert top_cand["rank"] == 1
    assert top_cand["total_score"] > 0.60
    assert len(top_cand["bullet_points"]) >= 3
    # Check explainability bullets
    assert any("Точное совпадение" in b or "Backend · Middle" in b for b in top_cand["bullet_points"])
    assert any("Стек" in b for b in top_cand["bullet_points"])
    # Anonymized card has contacts hidden
    assert top_cand["candidate_card"]["contacts_hidden"] is True


def test_search_candidates_endpoint(client):
    """GET /api/v1/search/candidates interactive filter."""
    resp = client.get("/api/v1/search/candidates?specialization=BACKEND&grade=middle&skills=Python", headers=EMPLOYER)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_found" in data
    assert len(data["items"]) >= 1


# ==============================================================================
# 3. FSP LINK API ENDPOINT E2E TESTS
# ==============================================================================

def test_fsp_link_with_consent_152_fz_e2e(client):
    """POST /api/v1/me/fsp/link links FSP achievements with consent."""
    # Consent missing -> 400 error
    resp_no_consent = client.post(
        "/api/v1/me/fsp/link",
        json={"fsp_id": "FSP-1001", "consent_given": False},
        headers=CANDIDATE,
    )
    assert resp_no_consent.status_code == 400
    assert "152" in resp_no_consent.json()["detail"]["error_code"] or "CONSENT" in resp_no_consent.json()["detail"]["error_code"]

    # Consent given -> succeeds, returns verified achievements and FSP score
    resp_linked = client.post(
        "/api/v1/me/fsp/link",
        json={"fsp_id": "FSP-1001", "consent_given": True},
        headers=CANDIDATE,
    )
    assert resp_linked.status_code == 200
    link_data = resp_linked.json()
    assert link_data["fsp_id"] == "FSP-1001"
    assert link_data["is_fsp_verified"] is True
    assert link_data["fsp_score"] > 0.0
    assert len(link_data["achievements"]) >= 1
    assert link_data["sport_rank"] == "КМС"
    assert "ФСП" in link_data["explanation_bullet"]

    # GET /status returns updated status
    resp_status = client.get("/api/v1/me/fsp/status", headers=CANDIDATE)
    assert resp_status.status_code == 200
    assert resp_status.json()["fsp_id"] == "FSP-1001"
    assert resp_status.json()["is_fsp_verified"] is True


# ==============================================================================
# 4. SNAPSHOTS API & FSP FILTER E2E TESTS
# ==============================================================================

def test_snapshots_api_and_retrieval_e2e(client):
    """GET /api/v1/needs/{need_id}/snapshots and GET /api/v1/snapshots/{snapshot_id}."""
    need_payload = {
        "title": "Middle Backend Python Team",
        "target_specialization": "Backend",
        "target_grade": "MIDDLE",
        "required_skills": ["Python"],
    }
    resp_need = client.post("/api/v1/needs", json=need_payload, headers=EMPLOYER)
    assert resp_need.status_code == 201
    need_id = resp_need.json()["id"]

    # Trigger recommendation to auto-save snapshot
    resp_rec = client.get(f"/api/v1/needs/{need_id}/recommendations?save_snapshot=true", headers=EMPLOYER)
    assert resp_rec.status_code == 200
    snapshot_id = resp_rec.json()["snapshot_id"]
    assert snapshot_id is not None

    # 1. List snapshots for need
    resp_list = client.get(f"/api/v1/needs/{need_id}/snapshots", headers=EMPLOYER)
    assert resp_list.status_code == 200
    snapshots = resp_list.json()
    assert len(snapshots) >= 1
    assert snapshots[0]["id"] == snapshot_id
    assert snapshots[0]["need_id"] == need_id
    assert snapshots[0]["total_found"] >= 1
    assert len(snapshots[0]["items"]) >= 1

    # 2. Get specific snapshot
    resp_snap = client.get(f"/api/v1/snapshots/{snapshot_id}", headers=EMPLOYER)
    assert resp_snap.status_code == 200
    snap_data = resp_snap.json()
    assert snap_data["id"] == snapshot_id
    assert snap_data["need_id"] == need_id
    assert snap_data["total_found"] >= 1
    assert len(snap_data["items"]) >= 1
    assert snap_data["items"][0]["candidate_id"] == "cand-middle-1"

    # 3. 404 on unknown need or snapshot
    resp_404_need = client.get("/api/v1/needs/unknown-need-id/snapshots", headers=EMPLOYER)
    assert resp_404_need.status_code == 404
    resp_404_snap = client.get("/api/v1/snapshots/unknown-snap-id", headers=EMPLOYER)
    assert resp_404_snap.status_code == 404

    # 4. Another company sees neither the need's snapshots nor the snapshot itself
    other = bearer("u-emp-other", "EMPLOYER")
    assert client.get(f"/api/v1/needs/{need_id}/snapshots", headers=other).status_code == 404
    assert client.get(f"/api/v1/snapshots/{snapshot_id}", headers=other).status_code == 404


def test_search_candidates_has_fsp_filter_e2e(client):
    """GET /api/v1/search/candidates?has_fsp=true filters out non-FSP candidates."""
    # Ensure cand-middle-1 has FSP verified
    client.post(
        "/api/v1/me/fsp/link",
        json={"fsp_id": "FSP-1001", "consent_given": True},
        headers=CANDIDATE,
    )

    # 1. Without filter: returns both
    resp_all = client.get("/api/v1/search/candidates?specialization=Backend", headers=EMPLOYER)
    assert resp_all.status_code == 200
    all_cands = resp_all.json()["items"]
    all_ids = [c["candidate_id"] for c in all_cands]
    assert "cand-middle-1" in all_ids
    assert "cand-junior-2" in all_ids

    # 2. With has_fsp=true: only cand-middle-1 returned
    resp_fsp = client.get("/api/v1/search/candidates?specialization=Backend&has_fsp=true", headers=EMPLOYER)
    assert resp_fsp.status_code == 200
    fsp_cands = resp_fsp.json()["items"]
    fsp_ids = [c["candidate_id"] for c in fsp_cands]
    assert "cand-middle-1" in fsp_ids
    assert "cand-junior-2" not in fsp_ids

    # 3. With has_fsp=false: only the candidate without FSP history
    resp_no_fsp = client.get("/api/v1/search/candidates?specialization=Backend&has_fsp=false", headers=EMPLOYER)
    assert [c["candidate_id"] for c in resp_no_fsp.json()["items"]] == ["cand-junior-2"]


# ==============================================================================
# 5. PROFILE & COMPANY API & STANDARDIZED PDF E2E TESTS
# ==============================================================================

def test_candidate_and_company_profiles_e2e(client):
    """GET/PUT /api/v1/me/profile and GET/PUT /api/v1/companies/me."""
    # 1. Candidate profile GET
    resp_prof = client.get("/api/v1/me/profile", headers=CANDIDATE)
    assert resp_prof.status_code == 200
    prof_data = resp_prof.json()
    assert prof_data["id"] == "cand-middle-1"
    assert prof_data["first_name"] == "Максим"
    assert prof_data["confirmed_category"] == "Backend · Middle"
    assert prof_data["city"] == "Москва"

    # 2. Candidate profile PUT
    update_payload = {
        "city": "Санкт-Петербург",
        "work_format": "HYBRID",
        "desired_salary_min": 260000,
        "telegram": "@max_updated",
        "phone": "+7 (999) 111-22-33",
    }
    resp_upd = client.put("/api/v1/me/profile", json=update_payload, headers=CANDIDATE)
    assert resp_upd.status_code == 200
    upd_data = resp_upd.json()
    assert upd_data["city"] == "Санкт-Петербург"
    assert upd_data["work_format"] == "HYBRID"
    assert upd_data["desired_salary_min"] == 260000
    assert upd_data["telegram"] == "@max_updated"

    # 3. Company profile GET
    resp_comp = client.get("/api/v1/companies/me", headers=EMPLOYER)
    assert resp_comp.status_code == 200
    comp_data = resp_comp.json()
    assert comp_data["id"] == "comp-vk"
    assert comp_data["name"] == "VK Tech"

    # 4. Company profile PUT
    comp_update = {
        "name": "VK Technology Group",
        "website": "https://vk.company",
        "description": "Крупнейшая IT-экосистема России",
        "logo_url": "https://vk.company/logo.png",
    }
    resp_comp_upd = client.put("/api/v1/companies/me", json=comp_update, headers=EMPLOYER)
    assert resp_comp_upd.status_code == 200
    updated_comp = resp_comp_upd.json()
    assert updated_comp["name"] == "VK Technology Group"
    assert updated_comp["website"] == "https://vk.company"
    assert updated_comp["description"] == "Крупнейшая IT-экосистема России"


def test_standardized_pdf_generation_e2e(client):
    """GET /api/v1/candidates/{id}/pdf and GET /api/v1/me/pdf returns valid PDF."""
    # 1. Download candidate PDF by ID
    resp_pdf = client.get("/api/v1/candidates/cand-middle-1/pdf", headers=EMPLOYER)
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"
    assert resp_pdf.content.startswith(b"%PDF-")
    assert len(resp_pdf.content) > 1000

    # 2. Download own PDF via /me/pdf
    resp_my_pdf = client.get("/api/v1/me/pdf", headers=CANDIDATE)
    assert resp_my_pdf.status_code == 200
    assert resp_my_pdf.headers["content-type"] == "application/pdf"
    assert resp_my_pdf.content.startswith(b"%PDF-")
    assert len(resp_my_pdf.content) > 1000

    # 3. 404 on invalid candidate
    resp_404 = client.get("/api/v1/candidates/non-existent-candidate-id/pdf", headers=EMPLOYER)
    assert resp_404.status_code == 404

def test_employer_challenges_e2e(client):
    # 1. Register and login employer
    r = client.post('/api/v1/auth/register', json={'email': 'chal@emp.ru', 'password': 'password', 'role': 'EMPLOYER', 'first_name': 'Chal', 'last_name': 'Emp', 'company_name': 'Chal Inc'})
    assert r.status_code == 201
    
    token = client.post('/api/v1/auth/login', json={'email': 'chal@emp.ru', 'password': 'password'}).json()['access_token']
    client.headers.update({'Authorization': f'Bearer {token}'})

    # Create company
    client.post('/api/v1/me/company', json={'title': 'Chal Inc'})
    
    # 2. Create challenge
    chal_payload = {
        'title': 'Test Challenge',
        'task_description': 'Write a function',
        'specialization': 'Backend',
        'target_grade': 'JUNIOR'
    }
    resp = client.post('/api/v1/challenges', json=chal_payload)
    assert resp.status_code == 200
    
    # 3. List challenges
    resp = client.get('/api/v1/employer/challenges')
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    
    # 4. Candidate views challenge
    client.headers.clear()
    r2 = client.post('/api/v1/auth/register', json={'email': 'cand_chal@cand.ru', 'password': 'password', 'role': 'CANDIDATE', 'first_name': 'Cand', 'last_name': 'Chal'})
    assert r2.status_code == 201
    cand_token = client.post('/api/v1/auth/login', json={'email': 'cand_chal@cand.ru', 'password': 'password'}).json()['access_token']
    client.headers.update({'Authorization': f'Bearer {cand_token}'})
    
    resp = client.get('/api/v1/candidates/me/challenges')
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    challenge_id = next(c["id"] for c in resp.json() if c["title"] == "Test Challenge")

    # 5. Candidate answers; a repeated answer replaces the first one
    assert client.post(f"/api/v1/challenges/{challenge_id}/submit", json={"solution_text": "Use a hash map"}).status_code == 200
    assert client.post(f"/api/v1/challenges/{challenge_id}/submit", json={"solution_text": "Use a hash map, O(n)"}).status_code == 200
    mine = next(c for c in client.get("/api/v1/candidates/me/challenges").json() if c["id"] == challenge_id)
    assert mine["my_answer"] == "Use a hash map, O(n)"
    assert client.post("/api/v1/challenges/unknown-id/submit", json={"solution_text": "Use a hash map"}).status_code == 404

    # 6. The employer reads the answer
    client.headers.update({"Authorization": f"Bearer {token}"})
    listed = client.get("/api/v1/employer/challenges").json()
    assert listed[0]["submissions_count"] == 1
    answers = client.get(f"/api/v1/employer/challenges/{challenge_id}/submissions").json()
    assert [(a["candidate_name"], a["answer_text"]) for a in answers] == [("Cand Chal", "Use a hash map, O(n)")]


# ==============================================================================
# 6. ACCESS RULES (ТЗ 2.1 «Ограничение доступа», 2.2 правила видимости)
# ==============================================================================

def test_candidate_data_is_never_served_to_strangers(client):
    """A candidate sees only their own profile and invitations; an employer never reads candidate contacts directly."""
    assert client.get("/api/v1/me/profile").status_code == 401
    assert client.get("/api/v1/me/profile", headers=EMPLOYER).status_code == 403
    assert client.get("/api/v1/me/profile", headers=JUNIOR).json()["id"] == "cand-junior-2"
    assert client.get("/api/v1/invitations/candidate").status_code == 401
    assert client.get("/api/v1/invitations/company").status_code == 401
    assert client.get("/api/v1/search/candidates").status_code == 401
    assert client.get("/api/v1/search/candidates", headers=CANDIDATE).status_code == 403
    assert client.get("/api/v1/candidates/cand-middle-1/pdf").status_code == 401
    assert client.get("/api/v1/candidates/cand-middle-1/pdf", headers=JUNIOR).status_code == 404


def test_only_the_invited_candidate_answers_and_only_the_sender_withdraws(client):
    inv = client.post("/api/v1/invitations", json={
        "candidate_profile_id": "cand-middle-1", "salary_from": 200000, "salary_to": 250000,
        "message": "Приглашаем обсудить роль в команде платформы.",
    }, headers=EMPLOYER).json()

    assert client.post(f"/api/v1/invitations/{inv['id']}/accept").status_code == 401
    assert client.post(f"/api/v1/invitations/{inv['id']}/accept", headers=JUNIOR).status_code == 404
    other = bearer("u-emp-other", "EMPLOYER")
    assert client.post(f"/api/v1/invitations/{inv['id']}/withdraw", headers=other).status_code == 404
    assert client.get("/api/v1/invitations/company", headers=other).json() == []

    accepted = client.post(f"/api/v1/invitations/{inv['id']}/accept", headers=CANDIDATE).json()
    assert accepted["contacts_disclosed"] is True

    # the candidate can hide the contacts again; the employer then sees the card without them
    revoked = client.post(f"/api/v1/invitations/{inv['id']}/revoke-contacts", headers=CANDIDATE)
    assert revoked.status_code == 200 and revoked.json()["status"] == "CONTACTS_REVOKED"
    seen = client.get("/api/v1/invitations/company", headers=EMPLOYER).json()[0]
    assert seen["status"] == "CONTACTS_REVOKED" and seen["candidate_contacts"] is None
    assert client.post(f"/api/v1/invitations/{inv['id']}/revoke-contacts", headers=CANDIDATE).status_code == 400


def test_application_discloses_contacts_to_the_employer(client):
    """ТЗ 2.2: contacts are disclosed once the candidate applied to the vacancy themselves."""
    need = client.post("/api/v1/needs", json={
        "title": "Junior Backend", "target_specialization": "Backend", "target_grade": "JUNIOR",
        "salary_budget_min": 100000, "salary_budget_max": 150000,
    }, headers=EMPLOYER).json()
    listed = next(n for n in client.get("/api/v1/needs").json() if n["id"] == need["id"])
    assert listed["company_name"] == "VK Tech"

    assert client.post(f"/api/v1/needs/{need['id']}/apply").status_code == 401
    assert client.post(f"/api/v1/needs/{need['id']}/apply", headers=CANDIDATE).status_code == 200
    assert client.post(f"/api/v1/needs/{need['id']}/apply", headers=CANDIDATE).status_code == 400

    application = client.get("/api/v1/invitations/company", headers=EMPLOYER).json()[0]
    assert application["status"] == "APPLIED"
    assert application["candidate_contacts"]["telegram"] == "@max_backend"
    # the candidate cannot "accept" their own application
    assert client.post(f"/api/v1/invitations/{application['id']}/accept", headers=CANDIDATE).status_code == 400


def test_employer_works_only_with_own_company(client):
    other = bearer("u-emp-other", "EMPLOYER")
    need = client.post("/api/v1/needs", json={
        "title": "Middle Backend", "target_specialization": "Backend", "target_grade": "MIDDLE",
    }, headers=EMPLOYER).json()
    assert need["company_id"] == "comp-vk"
    assert client.get(f"/api/v1/needs/{need['id']}/recommendations", headers=other).status_code == 404
    assert client.put(f"/api/v1/needs/{need['id']}", json={"title": "Hijacked"}, headers=other).status_code == 404
    assert client.post("/api/v1/needs", json={
        "title": "x", "target_specialization": "Backend", "target_grade": "MIDDLE", "company_id": "comp-vk",
    }, headers=other).status_code == 403
    assert client.get("/api/v1/companies/me", headers=other).json()["id"] == "comp-other"
    assert client.post("/api/v1/companies/comp-vk/verify-inn", json={"inn": "1234567890"}, headers=other).status_code == 403


def test_ats_export_reports_only_real_skills(client):
    data = client.post("/api/v1/ats/candidates/cand-junior-2/export", headers=EMPLOYER).json()
    assert data["verified_skills"] == []  # nothing invented for a candidate without skills
    assert client.post("/api/v1/ats/candidates/cand-junior-2/export").status_code == 401


def test_public_verification_shows_the_category_without_contacts(client):
    data = client.get("/api/v1/verify/candidates/cand-middle-1").json()
    assert data["name"] == "Максим С." and data["confirmed_category"] == "Backend · Middle"
    assert "phone" not in data and "telegram" not in data
    resp_pdf = client.get("/api/v1/verify/candidates/cand-middle-1/pdf")
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"
    assert resp_pdf.content.startswith(b"%PDF-")



def test_fsp_id_cannot_be_linked_to_two_profiles(client):
    assert client.post("/api/v1/me/fsp/link", json={"fsp_id": "FSP-1002", "consent_given": True},
                       headers=CANDIDATE).status_code == 200
    taken = client.post("/api/v1/me/fsp/link", json={"fsp_id": "FSP-1002", "consent_given": True}, headers=JUNIOR)
    assert taken.status_code == 409


def test_declared_stack_becomes_claimed_skills(client):
    resp = client.put("/api/v1/me/profile", json={"stack": "Python, PostgreSQL, НеизвестныйФреймворк"}, headers=JUNIOR)
    skills = {s["name"]: s["confirmation_source"] for s in resp.json()["skills"]}
    assert skills == {"Python": "CLAIMED", "PostgreSQL": "CLAIMED"}
    assert resp.json()["stack"] == "Python, PostgreSQL, НеизвестныйФреймворк"

    # removing a skill from the stack removes the claim, a confirmed skill is never touched
    resp = client.put("/api/v1/me/profile", json={"stack": "Python"}, headers=JUNIOR)
    assert {s["name"] for s in resp.json()["skills"]} == {"Python"}
    resp = client.put("/api/v1/me/profile", json={"stack": ""}, headers=CANDIDATE)
    assert {s["confirmation_source"] for s in resp.json()["skills"]} == {"ASSESSMENT"}
