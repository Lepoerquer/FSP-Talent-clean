from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    from backend.app.models.dictionary import (
        Category,
        Direction,
        Grade,
        Skill,
        SkillSynonym,
        Specialization,
    )
    from backend.app.modules.dictionaries.seeds import (
        DIRECTIONS_DATA,
        GRADES_DATA,
        SKILLS_DATA,
        SPECIALIZATIONS_DATA,
    )
except ImportError:
    from app.models.dictionary import (
        Category,
        Direction,
        Grade,
        Skill,
        SkillSynonym,
        Specialization,
    )
    from app.modules.dictionaries.seeds import (
        DIRECTIONS_DATA,
        GRADES_DATA,
        SKILLS_DATA,
        SPECIALIZATIONS_DATA,
    )


def seed_dictionaries(db: Session) -> dict[str, int]:
    """Idempotently seed directions, specializations, grades, categories, and skills."""
    stats = {
        "directions_created": 0,
        "specializations_created": 0,
        "grades_created": 0,
        "categories_created": 0,
        "skills_created": 0,
        "synonyms_created": 0,
    }

    # 1. Seed Directions
    direction_map: dict[str, Direction] = {}
    for d_item in DIRECTIONS_DATA:
        existing = db.query(Direction).filter(Direction.code == d_item["code"]).first()
        if not existing:
            existing = Direction(code=d_item["code"], name=d_item["name"])
            db.add(existing)
            db.flush()
            stats["directions_created"] += 1
        direction_map[d_item["code"]] = existing

    # 2. Seed Specializations
    spec_map: dict[str, Specialization] = {}
    for s_item in SPECIALIZATIONS_DATA:
        dir_obj = direction_map.get(s_item["direction_code"])
        if not dir_obj:
            continue
        existing = db.query(Specialization).filter(Specialization.code == s_item["code"]).first()
        if not existing:
            existing = Specialization(
                direction_id=dir_obj.id,
                code=s_item["code"],
                name=s_item["name"],
                has_active_assessment=s_item.get("has_active_assessment", 1),
            )
            db.add(existing)
            db.flush()
            stats["specializations_created"] += 1
        spec_map[s_item["code"]] = existing

    # 3. Seed Grades
    grade_map: dict[str, Grade] = {}
    for g_item in GRADES_DATA:
        existing = db.query(Grade).filter(Grade.code == g_item["code"]).first()
        if not existing:
            existing = Grade(
                code=g_item["code"],
                name=g_item["name"],
                rank=g_item["rank"],
                behavioral_indicators=g_item["behavioral_indicators"],
            )
            db.add(existing)
            db.flush()
            stats["grades_created"] += 1
        else:
            # Update behavioral indicators if present
            existing.behavioral_indicators = g_item["behavioral_indicators"]
            db.flush()
        grade_map[g_item["code"]] = existing

    # 4. Seed Categories (Specialization x Grade cartesian product)
    for spec_code, spec_obj in spec_map.items():
        for grade_code, grade_obj in grade_map.items():
            cat_code = f"{spec_code}_{grade_code}"
            display_name = f"{spec_obj.name} · {grade_obj.name}"
            existing = db.query(Category).filter(Category.code == cat_code).first()
            if not existing:
                cat = Category(
                    specialization_id=spec_obj.id,
                    grade_id=grade_obj.id,
                    code=cat_code,
                    display_name=display_name,
                )
                db.add(cat)
                stats["categories_created"] += 1

    # 5. Seed Skills & Synonyms
    for sk_item in SKILLS_DATA:
        existing_skill = db.query(Skill).filter(Skill.code == sk_item["code"]).first()
        if not existing_skill:
            existing_skill = Skill(
                code=sk_item["code"],
                name=sk_item["name"],
                category_tags=sk_item.get("tags", []),
            )
            db.add(existing_skill)
            db.flush()
            stats["skills_created"] += 1

        # Seed Synonyms
        existing_synonyms = {
            s.synonym.lower()
            for s in db.query(SkillSynonym).filter(SkillSynonym.skill_id == existing_skill.id).all()
        }
        for syn in sk_item.get("synonyms", []):
            if syn.lower() not in existing_synonyms:
                syn_obj = SkillSynonym(
                    skill_id=existing_skill.id,
                    synonym=syn,
                )
                db.add(syn_obj)
                stats["synonyms_created"] += 1
                existing_synonyms.add(syn.lower())

    db.commit()
    return stats


def get_directions(db: Session) -> list[Direction]:
    return db.query(Direction).order_by(Direction.name).all()


def get_specializations(db: Session) -> list[Specialization]:
    return db.query(Specialization).order_by(Specialization.name).all()


def get_grades(db: Session) -> list[Grade]:
    return db.query(Grade).order_by(Grade.rank).all()


def get_categories(db: Session, specialization_code: str | None = None) -> list[Category]:
    query = db.query(Category)
    if specialization_code:
        query = query.join(Specialization).filter(Specialization.code == specialization_code.upper())
    return query.all()


def get_category_by_code(db: Session, code: str) -> Category | None:
    return db.query(Category).filter(Category.code == code).first()


def search_skills(db: Session, query_str: str, limit: int = 20) -> list[dict[str, Any]]:
    query_clean = query_str.strip().lower()
    if not query_clean:
        skills = db.query(Skill).limit(limit).all()
        return [
            {
                "id": s.id,
                "code": s.code,
                "name": s.name,
                "category_tags": s.category_tags or [],
                "matched_by": "default",
            }
            for s in skills
        ]

    # Direct name match
    name_matches = (
        db.query(Skill)
        .filter(func.lower(Skill.name).contains(query_clean))
        .limit(limit)
        .all()
    )

    results = []
    seen_ids = set()
    for s in name_matches:
        results.append({
            "id": s.id,
            "code": s.code,
            "name": s.name,
            "category_tags": s.category_tags or [],
            "matched_by": "name",
        })
        seen_ids.add(s.id)

    # Synonym matches if space remains
    if len(results) < limit:
        syn_matches = (
            db.query(SkillSynonym)
            .filter(func.lower(SkillSynonym.synonym).contains(query_clean))
            .limit(limit)
            .all()
        )
        for syn in syn_matches:
            if syn.skill_id not in seen_ids:
                skill = db.query(Skill).filter(Skill.id == syn.skill_id).first()
                if skill:
                    results.append({
                        "id": skill.id,
                        "code": skill.code,
                        "name": skill.name,
                        "category_tags": skill.category_tags or [],
                        "matched_by": f"synonym: {syn.synonym}",
                    })
                    seen_ids.add(skill.id)
            if len(results) >= limit:
                break

    return results


def get_dictionaries_overview(db: Session) -> dict[str, int]:
    return {
        "directions_count": db.query(Direction).count(),
        "specializations_count": db.query(Specialization).count(),
        "grades_count": db.query(Grade).count(),
        "categories_count": db.query(Category).count(),
        "skills_count": db.query(Skill).count(),
    }
