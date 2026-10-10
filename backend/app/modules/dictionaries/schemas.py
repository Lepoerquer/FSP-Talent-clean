from pydantic import BaseModel, ConfigDict


class DirectionBase(BaseModel):
    code: str
    name: str


class DirectionResponse(DirectionBase):
    id: str
    specializations: list["SpecializationBriefResponse"] = []

    model_config = ConfigDict(from_attributes=True)


class SpecializationBase(BaseModel):
    code: str
    name: str
    has_active_assessment: int = 1


class SpecializationBriefResponse(SpecializationBase):
    id: str
    direction_id: str

    model_config = ConfigDict(from_attributes=True)


class SpecializationResponse(SpecializationBase):
    id: str
    direction_id: str
    direction_name: str | None = None
    categories: list["CategoryBriefResponse"] = []

    model_config = ConfigDict(from_attributes=True)


class GradeBase(BaseModel):
    code: str
    name: str
    rank: int
    behavioral_indicators: list[str] | None = None


class GradeResponse(GradeBase):
    id: str

    model_config = ConfigDict(from_attributes=True)


class CategoryBriefResponse(BaseModel):
    id: str
    code: str
    display_name: str
    grade_code: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CategoryResponse(BaseModel):
    id: str
    specialization_id: str
    grade_id: str
    code: str
    display_name: str
    specialization_code: str | None = None
    specialization_name: str | None = None
    grade_code: str | None = None
    grade_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SkillSynonymResponse(BaseModel):
    id: str
    synonym: str

    model_config = ConfigDict(from_attributes=True)


class SkillResponse(BaseModel):
    id: str
    code: str
    name: str
    category_tags: list[str] | None = []
    synonyms: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class SkillSearchResponse(BaseModel):
    id: str
    code: str
    name: str
    category_tags: list[str] | None = []
    matched_by: str = "name"

    model_config = ConfigDict(from_attributes=True)


class DictionariesOverviewResponse(BaseModel):
    directions_count: int
    specializations_count: int
    grades_count: int
    categories_count: int
    skills_count: int
