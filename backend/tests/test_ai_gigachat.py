"""Tests for GigaChat AI Integration and Fallback Mechanisms."""

from backend.app.models.candidate import CandidateProfile


def test_ai_status_endpoint(client):
    res = client.get("/api/v1/ai/status")
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] in ("gigachat", "offline")
    assert isinstance(data["is_configured"], bool)
    assert data["status"] in ("ready", "auth_error", "configured_offline")


def test_ai_interview_questions_generation(client):
    payload = {
        "specialization": "BACKEND",
        "grade": "MIDDLE",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "count": 2,
    }
    res = client.post("/api/v1/needs/ai/interview-questions", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["specialization"] == "BACKEND"
    assert data["grade"] == "MIDDLE"
    assert len(data["questions"]) >= 2
    for q in data["questions"]:
        assert "topic" in q
        assert "question" in q
        assert "expected_answer" in q


def test_ai_pitch_fallback_or_live(client, db_session):
    # 1. Non-existent candidate returns 404
    res = client.post("/api/v1/needs/ai/pitch", json={"candidate_id": "non-existent-id"})
    assert res.status_code == 404

    # 2. Existing candidate generates pitch (live or fallback)
    from backend.app.models.user import User

    uid = "user-ai-test-1"
    user = User(id=uid, email="ai-test@example.com", role="CANDIDATE", email_verified=True)
    db_session.add(user)
    db_session.commit()

    cand = CandidateProfile(
        id="cand-ai-test-1",
        user_id=uid,
        first_name="Иван",
        confirmed_grade="MIDDLE",
        confirmed_specialization="BACKEND",
    )
    db_session.add(cand)
    db_session.commit()

    res = client.post("/api/v1/needs/ai/pitch", json={"candidate_id": cand.id})
    assert res.status_code == 200
    data = res.json()
    assert data["candidate_id"] == cand.id
    assert "pitch" in data
    assert len(data["pitch"]) > 10


def test_ai_career_advice_generation(client):
    payload = {
        "specialization": "BACKEND",
        "grade": "MIDDLE",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "experience_years": 2.0,
        "fsp_verified": True,
        "percentile": 82,
    }
    res = client.post("/api/v1/needs/ai/career-advice", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["specialization"] == "BACKEND"
    assert data["grade"] == "MIDDLE"
    assert len(data["overall_summary"]) > 10
    assert len(data["strengths"]) >= 2
    assert len(data["growth_points"]) >= 2
    assert "recommended_fsp_discipline" in data
    assert "fsp_boost_tip" in data
    assert len(data["career_roadmap"]) >= 2


def test_candidate_public_verification(client, db_session):
    from backend.app.models.user import User

    uid = "user-verify-test-1"
    user = User(id=uid, email="verify@example.com", role="CANDIDATE", email_verified=True)
    db_session.add(user)
    db_session.commit()

    cand = CandidateProfile(
        id="cand-verify-test-1",
        user_id=uid,
        first_name="Алексей",
        last_name="Смирнов",
        confirmed_grade="SENIOR",
        confirmed_specialization="BACKEND",
        is_fsp_verified=True,
        fsp_score=8.5,
        category_percentile=94,
    )
    db_session.add(cand)
    db_session.commit()

    res = client.get(f"/api/v1/verify/candidates/{cand.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["candidate_id"] == cand.id
    assert data["is_fsp_verified"] is True
    assert data["confirmed_grade"] == "SENIOR"
    assert data["category_percentile"] == 94
    assert data["verification_hash"] is not None
    assert len(data["verification_hash"]) == 16  # 16-hex short digest for readable verification seal


def test_hybrid_parser_ai_first_and_fallback(client):
    # 1. Test explicit rule-based mode
    payload_rules = {
        "text": "Ищем Middle Python разработчика со знанием Django и PostgreSQL. Удаленно.",
        "title": "Backend Developer",
        "provider": "rules",
    }
    res = client.post("/api/v1/needs/parse", json=payload_rules)
    assert res.status_code == 200
    data = res.json()
    assert data["parser_source"] == "rule_based"
    assert data["specialization"]["value"] == "BACKEND"
    assert data["grade"]["value"] == "MIDDLE"
    assert any(s["code"] in ("django", "postgresql", "python") for s in data["skills"])

    # 2. Test auto mode (AI-first)
    payload_auto = {
        "text": "Ищем Middle Python разработчика со знанием Django и PostgreSQL. Удаленно.",
        "title": "Backend Developer",
        "provider": "auto",
    }
    res = client.post("/api/v1/needs/parse", json=payload_auto)
    assert res.status_code == 200
    data = res.json()
    assert data["parser_source"] in ("gigachat", "rule_based")
    assert data["specialization"]["value"] == "BACKEND"
    assert data["grade"]["value"] == "MIDDLE"
    assert "engine_badge" in data


