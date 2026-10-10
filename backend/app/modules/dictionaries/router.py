
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

try:
    from backend.app.core.database import get_db
    from backend.app.modules.dictionaries import service
    from backend.app.modules.dictionaries.schemas import (
        CategoryResponse,
        DictionariesOverviewResponse,
        DirectionResponse,
        GradeResponse,
        SkillSearchResponse,
        SpecializationResponse,
    )
except ImportError:
    from app.core.database import get_db
    from app.modules.dictionaries import service
    from app.modules.dictionaries.schemas import (
        CategoryResponse,
        DictionariesOverviewResponse,
        DirectionResponse,
        GradeResponse,
        SkillSearchResponse,
        SpecializationResponse,
    )

router = APIRouter(prefix="/dictionaries", tags=["Dictionaries"])


@router.get("/overview", response_model=DictionariesOverviewResponse)
def get_dictionaries_overview(db: Session = Depends(get_db)):
    """Return overview counts of all registered dictionary entities."""
    return service.get_dictionaries_overview(db)


@router.post("/seed", status_code=status.HTTP_200_OK)
def trigger_seed_dictionaries(db: Session = Depends(get_db)):
    """Seed directions, specializations, grades, categories, and 300+ skills with synonyms."""
    stats = service.seed_dictionaries(db)
    return {"message": "Dictionaries seeded successfully", "stats": stats}


@router.get("/directions", response_model=list[DirectionResponse])
def get_directions(db: Session = Depends(get_db)):
    """Get all directions with nested specializations."""
    return service.get_directions(db)


@router.get("/specializations", response_model=list[SpecializationResponse])
def get_specializations(db: Session = Depends(get_db)):
    """Get all IT specializations."""
    specializations = service.get_specializations(db)
    result = []
    for spec in specializations:
        result.append(
            SpecializationResponse(
                id=spec.id,
                direction_id=spec.direction_id,
                direction_name=spec.direction.name if spec.direction else None,
                code=spec.code,
                name=spec.name,
                has_active_assessment=spec.has_active_assessment,
                categories=[
                    {
                        "id": c.id,
                        "code": c.code,
                        "display_name": c.display_name,
                        "grade_code": c.grade.code if c.grade else None,
                    }
                    for c in spec.categories
                ],
            )
        )
    return result


@router.get("/grades", response_model=list[GradeResponse])
def get_grades(db: Session = Depends(get_db)):
    """Get all professional grades with behavioral indicators."""
    return service.get_grades(db)


@router.get("/categories", response_model=list[CategoryResponse])
def get_categories(
    specialization: str | None = Query(None, description="Filter by specialization code, e.g. BACKEND"),
    db: Session = Depends(get_db),
):
    """Get all candidate categories (Specialization x Grade)."""
    categories = service.get_categories(db, specialization_code=specialization)
    result = []
    for cat in categories:
        result.append(
            CategoryResponse(
                id=cat.id,
                specialization_id=cat.specialization_id,
                grade_id=cat.grade_id,
                code=cat.code,
                display_name=cat.display_name,
                specialization_code=cat.specialization.code if cat.specialization else None,
                specialization_name=cat.specialization.name if cat.specialization else None,
                grade_code=cat.grade.code if cat.grade else None,
                grade_name=cat.grade.name if cat.grade else None,
            )
        )
    return result


@router.get("/skills", response_model=list[SkillSearchResponse])
def search_skills(
    q: str | None = Query("", description="Search term for skill name or synonym (e.g. 'питон' or 'postgres')"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Search skills by name or synonym with typo/translit tolerance."""
    return service.search_skills(db, query_str=q, limit=limit)
