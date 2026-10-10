"""Demo Database Reset and Seeding Script for FSP-Talent.

Used by `make demo-reset` to instantly reset and restore the database
to an authentic state for presentation and jury evaluation:
- Drops and recreates all database tables.
- Seeds all platform dictionaries (Directions, Specializations, Grades, Categories, 360+ Skills).
- Synchronizes CAT Item Families from assessment-bank.
- Seeds reference demo accounts:
    1. Candidate WITH FSP history: Анна Смирнова (FSP-1002, Verified, CAT theta=1.45, Middle Backend)
    2. Candidate WITHOUT FSP history: Борис Кузнецов (No FSP, High CAT theta=1.58, Middle Backend)
    3. Verified Employers:
       - ООО «Ромашка» (fictional) + Active Need for Middle Python Backend Developer
       - Федерация спортивного программирования (ФСП) + Active Need for Platform Engineer
    4. Active Invitations with salary transparency demonstrating Reverse Hiring FSM.
    5. Regular employer challenges that candidates see in their cabinet.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Ensure UTF-8 stdout encoding on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 1. Path configuration to support standalone and package invocation
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(BACKEND_DIR)
BANK_DIR = os.path.join(REPO_ROOT, "assessment-bank")

for path in [REPO_ROOT, BACKEND_DIR, BANK_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from backend.app.core.database import Base, SessionLocal, create_all_tables, engine
    from backend.app.core.security import get_password_hash
    from backend.app.models.candidate import (
        CandidateProfile,
        CandidateSkill,
        FSPAchievement,
        GradeHistory,
    )
    from backend.app.models.company import Company, EmployerChallenge, EmployerMember, Need
    from backend.app.models.dictionary import Skill
    from backend.app.models.invitation import Invitation, InvitationStatus
    from backend.app.models.user import Consent, User
    from backend.app.modules.assessment.service import sync_item_families_to_db
    from backend.app.modules.dictionaries.service import seed_dictionaries
except ImportError:
    from app.core.database import Base, SessionLocal, create_all_tables, engine
    from app.core.security import get_password_hash
    from app.models.candidate import (
        CandidateProfile,
        CandidateSkill,
        FSPAchievement,
        GradeHistory,
    )
    from app.models.company import Company, EmployerChallenge, EmployerMember, Need
    from app.models.dictionary import Skill
    from app.models.invitation import Invitation, InvitationStatus
    from app.models.user import Consent, User
    from app.modules.assessment.service import sync_item_families_to_db
    from app.modules.dictionaries.service import seed_dictionaries


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def reset_and_seed_database() -> None:
    print("=" * 70)
    print(">>> FSP-Talent Platform: Resetting and Seeding Demo Database")
    print("=" * 70)

    # 1. Drop and Recreate All Tables
    print("[1/5] Dropping existing database tables...")
    Base.metadata.drop_all(bind=engine)

    print("[2/5] Creating fresh database tables from SQLAlchemy metadata...")
    create_all_tables()

    db = SessionLocal()
    try:
        # 2. Seed Standard Dictionaries
        print("[3/5] Seeding core platform dictionaries (Directions, Specs, Grades, Skills)...")
        dict_stats = seed_dictionaries(db)
        print(f"      + Directions: {dict_stats['directions_created']}")
        print(f"      + Specializations: {dict_stats['specializations_created']}")
        print(f"      + Grades: {dict_stats['grades_created']}")
        print(f"      + Categories: {dict_stats['categories_created']}")
        print(f"      + Skills: {dict_stats['skills_created']}")

        # Sync Assessment Item Families
        print("      + Syncing assessment item families from assessment-bank...")
        try:
            sync_item_families_to_db(db)
            print("      [OK] Assessment families synchronized successfully.")
        except Exception as e:
            print(f"      ! Assessment families sync note: {e}")

        # Quick skill lookup helper
        skills_cache: dict[str, Skill] = {s.name.lower(): s for s in db.query(Skill).all()}

        def get_or_create_skill(name: str) -> Skill:
            norm = name.strip().lower()
            if norm in skills_cache:
                return skills_cache[norm]
            code = norm.upper().replace(" ", "_").replace("-", "_")
            new_skill = Skill(code=code, name=name.strip())
            db.add(new_skill)
            db.flush()
            skills_cache[norm] = new_skill
            return new_skill

        print("[4/5] Creating reference demo accounts and profiles...")

        # ------------------------------------------------------------------
        # CANDIDATE 1: Анна Смирнова (Кандидат С историей ФСП)
        # ------------------------------------------------------------------
        anna_user = User(
            id="demo-user-anna",
            email="anna@fsp-talent.ru",
            hashed_password=get_password_hash("demo123"),
            role="CANDIDATE",
            is_active=True,
            email_verified=True,
        )
        db.add(anna_user)
        db.flush()

        # 152-FZ Consents
        db.add_all([
            Consent(user_id=anna_user.id, consent_type="PERSONAL_DATA", version="1.0", is_given=True),
            Consent(user_id=anna_user.id, consent_type="PROFILE_DISTRIBUTION", version="1.0", is_given=True),
        ])

        anna_profile = CandidateProfile(
            id="demo-cand-anna",
            user_id=anna_user.id,
            first_name="Анна",
            last_name="Смирнова",
            phone="+7 (999) 111-22-33",
            telegram="@anna_fsp",
            fsp_id="FSP-1002",
            is_fsp_verified=True,
            fsp_score=0.88,
            confirmed_category="Backend · Middle",
            confirmed_specialization="BACKEND",
            confirmed_grade="MIDDLE",
            last_theta=1.45,
            last_se=0.26,
            category_percentile=91,
            desired_salary_min=230000,
            work_format="REMOTE",
            city="Москва",
            status="ACTIVELY_SEARCHING",
            hide_contacts_globally=True,
        )
        db.add(anna_profile)
        db.flush()

        # FSP Achievements for Anna
        anna_achievements = [
            FSPAchievement(
                candidate_profile_id=anna_profile.id,
                event_name="Чемпионат России по спортивному программированию 2025",
                event_date=datetime(2025, 11, 20, 10, 0, 0, tzinfo=timezone.utc),
                discipline="Продуктовое программирование",
                level="ALL_RUSSIAN",
                result="WINNER",
                sport_category="КМС",
                calculated_weight=0.85,
            ),
            FSPAchievement(
                candidate_profile_id=anna_profile.id,
                event_name="Хакатон «Лидеры цифровой трансформации» (ЛЦТ) 2025",
                event_date=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
                discipline="Продуктовое программирование",
                level="ALL_RUSSIAN",
                result="PRIZE_WINNER",
                sport_category="1 разряд",
                calculated_weight=0.70,
            ),
        ]
        db.add_all(anna_achievements)

        # Anna's Verified Skills
        anna_skills_data = [
            ("Python", "ASSESSMENT", 1.0),
            ("PostgreSQL", "ASSESSMENT", 1.0),
            ("FastAPI", "RESUME", 1.0),
            ("Docker", "CLAIMED", 1.0),
            ("Redis", "CLAIMED", 1.0),
            ("Алгоритмы и структуры данных", "FSP", 1.0),
        ]
        for sk_name, source, weight in anna_skills_data:
            sk_obj = get_or_create_skill(sk_name)
            db.add(
                CandidateSkill(
                    candidate_profile_id=anna_profile.id,
                    skill_id=sk_obj.id,
                    confirmation_source=source,
                    weight=weight,
                )
            )

        db.add(
            GradeHistory(
                candidate_profile_id=anna_profile.id,
                previous_grade="JUNIOR",
                new_grade="MIDDLE",
                specialization="BACKEND",
                reason="ASSESSMENT",
            )
        )

        print("      [OK] Created Candidate with FSP: Анна Смирнова (anna@fsp-talent.ru)")

        # ------------------------------------------------------------------
        # CANDIDATE 2: Борис Кузнецов (Кандидат БЕЗ истории ФСП)
        # ------------------------------------------------------------------
        boris_user = User(
            id="demo-user-boris",
            email="boris@fsp-talent.ru",
            hashed_password=get_password_hash("demo123"),
            role="CANDIDATE",
            is_active=True,
            email_verified=True,
        )
        db.add(boris_user)
        db.flush()

        db.add_all([
            Consent(user_id=boris_user.id, consent_type="PERSONAL_DATA", version="1.0", is_given=True),
            Consent(user_id=boris_user.id, consent_type="PROFILE_DISTRIBUTION", version="1.0", is_given=True),
        ])

        boris_profile = CandidateProfile(
            id="demo-cand-boris",
            user_id=boris_user.id,
            first_name="Борис",
            last_name="Кузнецов",
            phone="+7 (999) 444-55-66",
            telegram="@boris_dev",
            fsp_id=None,
            is_fsp_verified=False,
            fsp_score=0.0,  # Fair assessment without FSP penalty
            confirmed_category="Backend · Middle",
            confirmed_specialization="BACKEND",
            confirmed_grade="MIDDLE",
            last_theta=1.58,  # Exceptional IRT CAT test result
            last_se=0.24,
            category_percentile=94,
            desired_salary_min=240000,
            work_format="REMOTE",
            city="Санкт-Петербург",
            status="ACTIVELY_SEARCHING",
            hide_contacts_globally=True,
        )
        db.add(boris_profile)
        db.flush()

        # Boris's Skills
        boris_skills_data = [
            ("Python", "ASSESSMENT", 1.0),
            ("PostgreSQL", "ASSESSMENT", 1.0),
            ("FastAPI", "RESUME", 1.0),
            ("SQLAlchemy", "RESUME", 1.0),
            ("Redis", "CLAIMED", 1.0),
            ("Docker", "CLAIMED", 1.0),
        ]
        for sk_name, source, weight in boris_skills_data:
            sk_obj = get_or_create_skill(sk_name)
            db.add(
                CandidateSkill(
                    candidate_profile_id=boris_profile.id,
                    skill_id=sk_obj.id,
                    confirmation_source=source,
                    weight=weight,
                )
            )

        db.add(
            GradeHistory(
                candidate_profile_id=boris_profile.id,
                previous_grade="JUNIOR",
                new_grade="MIDDLE",
                specialization="BACKEND",
                reason="ASSESSMENT",
            )
        )

        print("      [OK] Created Candidate without FSP: Борис Кузнецов (boris@fsp-talent.ru)")

        # ------------------------------------------------------------------
        # EMPLOYER 1: ООО «Ромашка» (вымышленная компания)
        # ------------------------------------------------------------------
        romashka_comp = Company(
            id="demo-comp-romashka",
            name="ООО «Ромашка»",
            inn="7704340310",
            website=None,
            description="Вымышленная продуктовая ИТ-компания для демонстрации: платформа поиска и рекомендаций для онлайн-ритейла.",
            is_verified=True,
        )
        db.add(romashka_comp)
        db.flush()

        romashka_recruiter = User(
            id="demo-user-romashka",
            email="recruiter@techprom.ru",
            hashed_password=get_password_hash("demo123"),
            role="EMPLOYER",
            is_active=True,
            email_verified=True,
        )
        db.add(romashka_recruiter)
        db.flush()

        db.add(
            EmployerMember(
                company_id=romashka_comp.id,
                user_id=romashka_recruiter.id,
                role="OWNER",
            )
        )

        romashka_need = Need(
            id="demo-need-romashka-backend",
            company_id=romashka_comp.id,
            title="Middle Python Backend Developer (поисковые сервисы)",
            target_specialization="BACKEND",
            target_grade="MIDDLE",
            required_skills=["Python", "PostgreSQL", "FastAPI"],
            salary_budget_min=220000,
            salary_budget_max=300000,
            work_format="REMOTE",
            raw_description=(
                "Команда инфраструктуры поиска «Ромашки» ищет Middle Backend разработчика на Python. "
                "Стек: Python, FastAPI, PostgreSQL, Redis. Опыт участия в турнирах ФСП является существенным преимуществом."
            ),
            is_active=True,
        )
        db.add(romashka_need)
        db.flush()

        print("      [OK] Created Employer: ООО «Ромашка» + Active Middle Backend Need")

        # ------------------------------------------------------------------
        # EMPLOYER 2: Федерация спортивного программирования (ФСП)
        # ------------------------------------------------------------------
        fsp_comp = Company(
            id="demo-comp-fsp",
            name="Федерация спортивного программирования (ФСП)",
            inn="7701123456",
            website="https://fsp-russia.ru",
            description="Общероссийская общественная организация по развитию спортивного программирования в Российской Федерации.",
            is_verified=True,
        )
        db.add(fsp_comp)
        db.flush()

        fsp_recruiter = User(
            id="demo-user-fsp",
            email="hr@fsp-russia.ru",
            hashed_password=get_password_hash("demo123"),
            role="EMPLOYER",
            is_active=True,
            email_verified=True,
        )
        db.add(fsp_recruiter)
        db.flush()

        db.add(
            EmployerMember(
                company_id=fsp_comp.id,
                user_id=fsp_recruiter.id,
                role="OWNER",
            )
        )

        fsp_need = Need(
            id="demo-need-fsp-backend",
            company_id=fsp_comp.id,
            title="Backend Engineer платформы турниров ФСП",
            target_specialization="BACKEND",
            target_grade="MIDDLE",
            required_skills=["Python", "PostgreSQL", "Docker", "Алгоритмы и структуры данных"],
            salary_budget_min=200000,
            salary_budget_max=280000,
            work_format="REMOTE",
            raw_description=(
                "Разработка ядра проверяющей системы соревнований ФСП. Требуются отличные знания алгоритмов, "
                "асинхронного Python и реляционных баз данных."
            ),
            is_active=True,
        )
        db.add(fsp_need)
        db.flush()

        print("      [OK] Created Employer: Федерация спортивного программирования (ФСП) + Active Need")

        # ------------------------------------------------------------------
        # INVITATIONS: Демонстрация воронки обратного найма (Reverse Hiring FSM)
        # ------------------------------------------------------------------
        print("[5/5] Generating demo invitation workflow items...")

        # 1. «Ромашка» пригласила Анну (статус SENT, контакты скрыты до ответа)
        inv_anna = Invitation(
            id="demo-inv-romashka-anna",
            company_id=romashka_comp.id,
            candidate_profile_id=anna_profile.id,
            need_id=romashka_need.id,
            status=InvitationStatus.SENT.value,
            salary_from=250000,
            salary_to=290000,
            message=(
                "Здравствуйте, Анна! Ваша верифицированная квалификация Backend Middle и подтвержденные достижения ФСП "
                "идеально подходят для инфраструктурной команды поиска «Ромашки». Будем рады обсудить задачи!"
            ),
            contact_method="TELEGRAM",
            sent_at=utcnow() - timedelta(hours=2),
            expires_at=utcnow() + timedelta(days=12),
        )
        db.add(inv_anna)

        # 2. ФСП пригласила Бориса (статус SENT, честный отбор по тесту без дискриминации)
        inv_boris = Invitation(
            id="demo-inv-fsp-boris",
            company_id=fsp_comp.id,
            candidate_profile_id=boris_profile.id,
            need_id=fsp_need.id,
            status=InvitationStatus.SENT.value,
            salary_from=240000,
            salary_to=270000,
            message=(
                "Здравствуйте, Борис! Ваш результат независимого тестирования (94-й процентиль по специализации) "
                "и стек точно совпадают с требованиями к инженеру платформы проверяющей системы ФСП."
            ),
            contact_method="TELEGRAM",
            sent_at=utcnow() - timedelta(hours=1),
            expires_at=utcnow() + timedelta(days=13),
        )
        db.add(inv_boris)

        # REGULAR CHALLENGES: короткие задания работодателей (п. 2.1 ТЗ), их видят кандидаты в кабинете
        db.add_all([
            EmployerChallenge(
                id="demo-challenge-romashka-index",
                company_id=romashka_comp.id,
                title="Составной индекс для выборки заказов",
                task_description=(
                    "Запрос `WHERE tenant_id = 42 AND status = 'ACTIVE' ORDER BY created_at DESC LIMIT 50` "
                    "выполняется через Seq Scan. Предложите индекс PostgreSQL и объясните порядок колонок."
                ),
                specialization="BACKEND",
                target_grade="MIDDLE",
                task_type="ARCHITECTURE",
                time_limit_minutes=20,
            ),
            EmployerChallenge(
                id="demo-challenge-fsp-rate-limit",
                company_id=fsp_comp.id,
                title="Ограничение частоты отправок решений",
                task_description=(
                    "Проверяющая система принимает до 10 отправок в минуту от участника. Предложите алгоритм "
                    "ограничения (скользящее окно или token bucket) и где хранить состояние при нескольких экземплярах API."
                ),
                specialization="BACKEND",
                target_grade="SENIOR",
                task_type="ALGORITHM",
                time_limit_minutes=30,
            ),
        ])

        db.commit()

        print("=" * 70)
        print(">>> SUCCESS: Demo database successfully reset and seeded!")
        print("    Candidates:")
        print("      - anna@fsp-talent.ru / demo123 (Анна Смирнова, FSP-1002, Middle, θ=1.45, 91%)")
        print("      - boris@fsp-talent.ru / demo123 (Борис Кузнецов, Без ФСП, Middle, θ=1.58, 94%)")
        print("    Employers:")
        print("      - recruiter@techprom.ru / demo123 (ООО «Ромашка», 1 вакансия, 1 задание)")
        print("      - hr@fsp-russia.ru / demo123 (Федерация спортивного программирования, 1 вакансия, 1 задание)")
        print("=" * 70)

    except Exception as exc:
        db.rollback()
        print(f"!!! Error resetting demo database: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    reset_and_seed_database()
