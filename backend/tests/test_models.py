from datetime import datetime, timedelta, timezone

from backend.app.models import (
    AssessmentSession,
    AuditLog,
    CandidateProfile,
    CandidateSkill,
    Company,
    EmployerMember,
    FSPAchievement,
    GradeHistory,
    Invitation,
    InvitationStatus,
    ItemFamily,
    Need,
    SelectionSnapshot,
    SessionItem,
    ShortlistItem,
    Skill,
    User,
    Vacancy,
)


def test_models_full_lifecycle(db_session):
    # 1. Create User & Profile
    user = User(
        email="dev.coder@fsp.ru",
        hashed_password="hashed_pwd_123",
        role="CANDIDATE",
        is_active=True,
        email_verified=False,
    )
    db_session.add(user)
    db_session.flush()

    profile = CandidateProfile(
        user_id=user.id,
        first_name="Иван",
        last_name="Программистов",
        phone="+79991234567",
        telegram="@ivan_dev",
        fsp_id="FSP-2026-9999",
        status="ACTIVELY_SEARCHING",
        confirmed_category="BACKEND_MIDDLE",
        confirmed_specialization="BACKEND",
        confirmed_grade="MIDDLE",
        last_theta=1.45,
        last_se=0.25,
        category_percentile=88,
        fsp_score=0.85,
        desired_salary_min=250000,
        work_format="REMOTE",
        city="Москва",
        is_fsp_verified=True,
        hide_contacts_globally=True,
        next_grade_change_available_at=datetime.now(timezone.utc) + timedelta(days=90),
    )
    db_session.add(profile)
    db_session.flush()

    assert profile.user_id == user.id
    assert profile.user.email == "dev.coder@fsp.ru"

    # 2. Add Candidate Skills
    skill = db_session.query(Skill).filter(Skill.code == "python").first()
    assert skill is not None

    cand_skill = CandidateSkill(
        candidate_profile_id=profile.id,
        skill_id=skill.id,
        confirmation_source="ASSESSMENT",
        weight=1.5,
    )
    db_session.add(cand_skill)
    db_session.flush()

    assert len(profile.skills) == 1
    assert profile.skills[0].skill.name == "Python"

    # 3. Add Grade History & FSP Achievement
    history = GradeHistory(
        candidate_profile_id=profile.id,
        previous_grade="JUNIOR",
        new_grade="MIDDLE",
        specialization="BACKEND",
        reason="ASSESSMENT",
    )
    db_session.add(history)

    achieve = FSPAchievement(
        candidate_profile_id=profile.id,
        event_name="Всероссийский чемпионат по спортивному программированию 2025",
        event_date=datetime(2025, 11, 20),
        discipline="Спортивное программирование",
        level="ALL_RUSSIAN",
        result="PRIZE_WINNER",
        sport_category="КМС",
        calculated_weight=0.85,
    )
    db_session.add(achieve)
    db_session.flush()

    assert len(profile.grade_history) == 1
    assert len(profile.fsp_achievements) == 1

    # 4. Company, EmployerMember, Need, Snapshot, Shortlist
    emp_user = User(
        email="hr@techcorp.ru",
        hashed_password="hashed_pwd_hr",
        role="EMPLOYER",
    )
    db_session.add(emp_user)
    db_session.flush()

    company = Company(
        name="Яндекс Технологии",
        inn="7704340333",
        website="https://yandex.ru",
        description="Технологическая экосистема",
        is_verified=True,
    )
    db_session.add(company)
    db_session.flush()

    member = EmployerMember(
        user_id=emp_user.id,
        company_id=company.id,
        role="OWNER",
    )
    db_session.add(member)

    need = Need(
        company_id=company.id,
        title="Senior / Lead Python Developer",
        target_specialization="BACKEND",
        target_grade="SENIOR",
        required_skills=["python", "fastapi", "postgresql", "docker"],
        salary_budget_min=300000,
        salary_budget_max=450000,
        work_format="REMOTE",
    )
    db_session.add(need)
    db_session.flush()

    snapshot = SelectionSnapshot(
        need_id=need.id,
        query_filters_hash="hash123",
        ranked_candidates_payload={"count": 1},
    )
    db_session.add(snapshot)
    db_session.flush()

    shortlist = ShortlistItem(
        snapshot_id=snapshot.id,
        candidate_profile_id=profile.id,
        score=0.92,
        rank=1,
        explanation={"match_reasons": ["High theta", "FSP medal"]},
    )
    db_session.add(shortlist)

    vacancy = Vacancy(
        company_id=company.id,
        need_id=need.id,
        title="Python Backend Team Lead",
        description="Разработка высоконагруженных сервисов",
        specialization="BACKEND",
        grade="SENIOR",
        salary_min=350000,
        salary_max=480000,
    )
    db_session.add(vacancy)
    db_session.flush()

    # 5. Invitation with mandatory RUB salary and state machine
    invitation = Invitation(
        company_id=company.id,
        candidate_profile_id=profile.id,
        need_id=need.id,
        status=InvitationStatus.SENT.value,
        salary_from=320000,
        salary_to=400000,
        message="Здравствуйте, Иван! Приглашаем вас на позицию Senior Backend.",
        contact_method="TELEGRAM",
    )
    db_session.add(invitation)
    db_session.flush()

    assert invitation.salary_from == 320000
    assert invitation.status == InvitationStatus.SENT.value

    # 6. Assessment Models (ItemFamily, AssessmentSession, SessionItem)
    family = ItemFamily(
        code="PY_ASYNCIO_01",
        specialization="BACKEND",
        target_grade="MIDDLE",
        topic="Concurrency & AsyncIO",
        item_format="CODE_OUTPUT",
        discrimination_a=1.4,
        difficulty_b=0.8,
        exposure_count=5,
        template_yaml="question: What is output?\nanswers: [1, 2, 3]",
    )
    db_session.add(family)
    db_session.flush()

    session = AssessmentSession(
        candidate_profile_id=profile.id,
        specialization="BACKEND",
        target_grade="MIDDLE",
        current_theta=0.5,
        current_se=0.8,
        status="IN_PROGRESS",
    )
    db_session.add(session)
    db_session.flush()

    item = SessionItem(
        session_id=session.id,
        item_family_id=family.id,
        seed=42,
        rendered_question="print(await asyncio.gather(*tasks))",
        user_response="3",
        is_correct=True,
        response_time_seconds=14.2,
    )
    db_session.add(item)
    db_session.flush()

    # Verify synonym aliases work
    assert item.question == item.rendered_question
    assert item.response == item.user_response
    assert item.response_time == item.response_time_seconds

    # 7. AuditLog
    audit = AuditLog(
        user_id=user.id,
        action="TEST_VERIFICATION",
        entity_type="candidate_profile",
        entity_id=profile.id,
        details={"theta": 1.45},
    )
    db_session.add(audit)
    db_session.commit()

    assert db_session.query(AuditLog).count() >= 1
