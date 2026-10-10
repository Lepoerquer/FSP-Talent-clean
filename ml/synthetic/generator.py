"""Synthetic world for FSP-Talent: candidates, companies and employer needs (plan 6.1).

Latent ("true") and observed attributes are generated separately. Validation compares what the
platform computes from observed data with ground truth derived from latent data only, so the
ranking cannot peek at the answer.

Candidates
  latent:   specialization track, true theta and grade, true skill mastery, true sport level
  observed: survey (specialization, declared grade, conditions); grade confirmed by the real CAT
            engine on an item bank; skills with confirmation sources (test, resume, claimed);
            FSP achievements scored by the production FSP-score; resume text, part of which is
            stuffed with keywords
Needs
  structured employer request (specialization, grade, stack, format, city, budget) plus text:
  hand-written reference needs from ml/data/reference_needs.json, the rest from templates.

Usage:
  python ml/synthetic/generator.py [--candidates 1000] [--needs 50] [--seed 2026]
"""

import argparse
import json
import math
import os
import random
import sys
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
BANK_DIR = os.path.join(PROJECT_ROOT, "assessment-bank")
for p in [PROJECT_ROOT, BANK_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from families.registry import list_all_families

from backend.app.modules.assessment.cat_engine import (
    MAX_ITEMS,
    MIN_ITEMS,
    ItemCandidate,
    select_next_item,
    should_stop_assessment,
)
from backend.app.modules.assessment.grade_rules import (
    FOLLOW_UP_MAX_ITEMS,
    FOLLOW_UP_MIN_ITEMS,
    GRADE_ORDER,
    GRADE_START_THETA,
    classify_theta_to_grade,
    evaluate_assessment_result,
    format_category,
    get_start_theta,
)
from backend.app.modules.assessment.irt import (
    calculate_category_percentile,
    estimate_theta_eap,
    probability_2pl,
)
from backend.app.modules.fsp.score import calculate_fsp_score

REFERENCE_NEEDS_PATH = os.path.join(PROJECT_ROOT, "ml", "data", "reference_needs.json")
OUTPUT_DIR = os.path.join(CURRENT_DIR, "output")

FIRST_NAMES_M = ["Александр", "Дмитрий", "Максим", "Иван", "Сергей", "Андрей", "Михаил", "Артем", "Никита", "Алексей"]
FIRST_NAMES_F = ["Анна", "Мария", "Елена", "Дарья", "Анастасия", "Полина", "Екатерина", "Ольга", "Виктория", "София"]
LAST_NAMES_M = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов", "Новиков", "Федоров"]
LAST_NAMES_F = ["Иванова", "Смирнова", "Кузнецова", "Попова", "Васильева", "Петрова", "Соколова", "Михайлова", "Новикова", "Федорова"]

CITIES = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Нижний Новгород", "Томск", "Самара", "Иннополис"]
CITY_WEIGHTS = [0.32, 0.18, 0.08, 0.08, 0.10, 0.07, 0.05, 0.06, 0.06]
UNIVERSITIES = [
    "МГУ им. М.В. Ломоносова (ВМК)",
    "МФТИ (ФПМИ)",
    "НИУ ВШЭ (ФКН)",
    "Университет ИТМО (КТ)",
    "СПбГУ (МатМех)",
    "МГТУ им. Н.Э. Баумана (ИУ)",
    "УрФУ (ИРИТ-РТФ)",
    "НГУ (ФИТ)",
    "Университет Иннополис",
]

DIRECTIONS = {"BACKEND": "Разработка", "FRONTEND": "Разработка", "QA": "Тестирование", "DATA_ML": "Data & ML"}

# Stack tracks inside each specialization. Skill names are canonical names from the skills dictionary.
# "tested" skills are confirmed by the track's test once the grade is confirmed.
TRACKS: dict[str, dict[str, dict[str, Any]]] = {
    "BACKEND": {
        "python": {"title": "Python-разработчик", "tested": ["Python", "PostgreSQL"],
                   "core": ["Python", "Django", "FastAPI", "PostgreSQL", "SQLAlchemy"],
                   "extra": ["Redis", "Celery", "Docker", "Apache Kafka", "AsyncIO", "RabbitMQ"]},
        "java": {"title": "Java-разработчик", "tested": ["Java", "PostgreSQL"],
                 "core": ["Java", "Spring Boot", "Hibernate", "PostgreSQL", "Maven"],
                 "extra": ["Apache Kafka", "Docker", "Kubernetes (K8s)", "Redis", "Gradle", "RabbitMQ"]},
        "go": {"title": "Go-разработчик", "tested": ["Go (Golang)", "PostgreSQL"],
               "core": ["Go (Golang)", "gRPC", "PostgreSQL", "Docker", "Redis"],
               "extra": ["Apache Kafka", "Kubernetes (K8s)", "Prometheus", "ClickHouse", "Nginx"]},
        "node": {"title": "Node.js-разработчик", "tested": ["Node.js", "TypeScript"],
                 "core": ["Node.js", "TypeScript", "NestJS", "PostgreSQL", "MongoDB"],
                 "extra": ["Redis", "Docker", "GraphQL", "Express.js", "RabbitMQ"]},
    },
    "FRONTEND": {
        "react": {"title": "React-разработчик", "tested": ["JavaScript", "React"],
                  "core": ["JavaScript", "TypeScript", "React", "Redux", "CSS3"],
                  "extra": ["Next.js", "Webpack", "Jest", "Storybook", "Tailwind CSS", "HTML5"]},
        "vue": {"title": "Vue-разработчик", "tested": ["JavaScript", "Vue.js"],
                "core": ["JavaScript", "TypeScript", "Vue.js", "Pinia", "CSS3"],
                "extra": ["Nuxt.js", "Vite", "Jest", "SASS / SCSS", "Vuex", "HTML5"]},
        "angular": {"title": "Angular-разработчик", "tested": ["TypeScript", "Angular"],
                    "core": ["TypeScript", "Angular", "RxJS", "CSS3", "JavaScript"],
                    "extra": ["Jest", "Webpack", "SASS / SCSS", "Storybook", "HTML5"]},
    },
    "QA": {
        "manual": {"title": "QA-инженер (ручное тестирование)", "tested": ["Manual Testing", "Test Design Techniques"],
                   "core": ["Manual Testing", "Test Design Techniques", "Test Cases & Checklists", "Postman / Newman", "REST API"],
                   "extra": ["Charles Proxy / Fiddler", "MySQL", "Git (GitFlow, Trunk-Based)", "OpenAPI / Swagger", "Apache JMeter"]},
        "python_auto": {"title": "QA Automation (Python)", "tested": ["Pytest", "Test Design Techniques"],
                        "core": ["Python", "Pytest", "Selenium WebDriver", "REST API", "Allure Report"],
                        "extra": ["Playwright", "Docker", "GitLab CI/CD", "Locust", "Postman / Newman"]},
        "java_auto": {"title": "QA Automation (Java)", "tested": ["JUnit", "Test Design Techniques"],
                      "core": ["Java", "JUnit", "REST Assured", "Selenium WebDriver", "Allure Report"],
                      "extra": ["Maven", "GitLab CI/CD", "Docker", "Apache JMeter", "Playwright"]},
    },
    "DATA_ML": {
        "classic_ml": {"title": "Data Scientist", "tested": ["Python", "Scikit-Learn"],
                       "core": ["Python", "Pandas", "Scikit-Learn", "CatBoost", "NumPy"],
                       "extra": ["SciPy", "XGBoost", "LightGBM", "ClickHouse", "Apache Airflow", "MLflow"]},
        "deep_learning": {"title": "ML-инженер (Deep Learning)", "tested": ["Python", "PyTorch"],
                          "core": ["Python", "PyTorch", "NumPy", "Hugging Face Transformers", "OpenCV"],
                          "extra": ["TensorFlow", "Docker", "MLflow", "spaCy", "Keras"]},
        "data_eng": {"title": "ML/Data-инженер", "tested": ["Python", "Pandas"],
                     "core": ["Python", "Apache Spark", "Apache Airflow", "ClickHouse", "PySpark"],
                     "extra": ["Apache Kafka", "dbt (data build tool)", "Apache Hadoop & HDFS", "Docker", "Pandas"]},
    },
}
SPECIALIZATIONS = list(TRACKS)

# A skill is truly mastered at this latent level; relevance and "true skills" use it
MASTERY_THRESHOLD = 0.5

# Population: same as ml/validation/cat_sim.py (grade shares, spread around the grade band centre)
GRADE_MIX = {"INTERN": 0.15, "JUNIOR": 0.35, "MIDDLE": 0.35, "SENIOR": 0.15}
THETA_SD_WITHIN_GRADE = 0.5
# Self-assessment noise: 75% accurate, 15% overestimate by one grade, 10% underestimate
SELF_ASSESSMENT = [(0, 0.75), (1, 0.15), (-1, 0.10)]

SALARY_RANGES = {
    "INTERN": (40_000, 80_000),
    "JUNIOR": (90_000, 160_000),
    "MIDDLE": (170_000, 290_000),
    "SENIOR": (300_000, 500_000),
}
GRADE_WORD = {"INTERN": "Стажёр", "JUNIOR": "Junior", "MIDDLE": "Middle", "SENIOR": "Senior"}
GRADE_YEARS = {"INTERN": (0, 0), "JUNIOR": (1, 2), "MIDDLE": (3, 5), "SENIOR": (6, 12)}

FSP_PARTICIPATION = 0.35
# Correlation of sport results with theta: weak by design (plan 6.1)
FSP_THETA_CORRELATION = 0.35
FSP_EVENTS = [
    "Чемпионат России по спортивному программированию",
    "Кубок Федерации спортивного программирования",
    "Всероссийские студенческие игры по алгоритмическому программированию",
    "Региональный этап чемпионата ФСП",
    "Всероссийский хакатон по продуктовому программированию",
]
FSP_DISCIPLINES = ["Продуктовое программирование", "Алгоритмическое программирование",
                   "Программирование систем информационной безопасности", "Робототехника"]

COMPANY_NAMES = ["Ромашка", "Василёк", "Колокольчик", "Одуванчик", "Подсолнух", "Незабудка", "Ландыш", "Клевер",
                 "Лютик", "Шиповник", "Вереск", "Тюльпан", "Фиалка", "Сирень", "Жасмин", "Пион", "Астра",
                 "Лаванда", "Чабрец", "Мята"]
INDUSTRIES = {
    "финтех": "платёжный сервис",
    "ритейл": "интернет-магазин",
    "логистика": "сервис доставки",
    "edtech": "образовательную платформу",
    "медтех": "сервис записи к врачу",
    "госсектор": "портал госуслуг региона",
    "телеком": "личный кабинет абонента",
    "геймдев": "платформу онлайн-игр",
}
DUTIES = {
    "BACKEND": ["проектировать и развивать API", "оптимизировать запросы к базе данных",
                "разбивать монолит на сервисы", "писать интеграции с внешними системами"],
    "FRONTEND": ["разрабатывать интерфейсы личного кабинета", "развивать дизайн-систему",
                 "ускорять загрузку страниц", "интегрироваться с REST API"],
    "QA": ["тестировать новые функции по требованиям", "развивать автотесты",
           "проверять API и интеграции", "участвовать в разборе инцидентов"],
    "DATA_ML": ["строить и валидировать модели", "готовить признаки и датасеты",
                "выводить модели в прод и следить за качеством", "проводить A/B-эксперименты"],
}
NEED_TEMPLATES = [
    "{company} ({industry}) ищет специалиста на позицию «{title}». Развиваем {product}. Задачи: {duty}. "
    "Стек: {stack}. Будет плюсом: {plus}. {format_text}",
    "В команду, которая делает {product}, нужен {title_lower}. Чем предстоит заниматься: {duty}. "
    "Ожидаем уверенное знание {stack}. {format_text} Компания {company}.",
    "Открыта вакансия «{title}». Мы — {company}, {industry}. Работаем над продуктом: {product}. "
    "Требования: {stack}; плюсом будет {plus}. {format_text}",
]
FORMAT_TEXT = {
    "REMOTE": "Работа полностью удалённая.",
    "HYBRID": "Гибридный формат, офис в городе {city}.",
    "OFFICE": "Работа в офисе, город {city}.",
}


def _years_ru(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} год"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} года"
    return f"{n} лет"


# ==========================================
# Data model
# ==========================================

@dataclass
class SyntheticCandidate:
    id: str
    index: int
    # latent
    specialization: str
    track: str
    true_theta: float
    true_grade: str
    mastery: dict[str, float]
    sport_level: float | None
    # observed
    first_name: str
    last_name: str
    email: str
    phone: str
    telegram: str
    declared_grade: str
    city: str
    work_format: str
    desired_salary_min: int
    status: str
    days_since_update: int
    confirmed_grade: str | None
    theta_hat: float
    theta_se: float
    category_percentile: int
    test_sessions: int
    skills: dict[str, str]  # skill name -> confirmation source
    has_resume: bool
    keyword_stuffer: bool
    resume_text: str
    fsp_id: str | None = None
    fsp_achievements: list[dict[str, Any]] = field(default_factory=list)
    sport_rank: str | None = None
    fsp_score: float = 0.0

    @property
    def true_skills(self) -> set[str]:
        return {s for s, m in self.mastery.items() if m >= MASTERY_THRESHOLD}

    @property
    def confirmed_category(self) -> str | None:
        if not self.confirmed_grade:
            return None
        return format_category(self.specialization, self.confirmed_grade)

    def to_dict(self) -> dict[str, Any]:
        latent_keys = {"specialization", "track", "true_theta", "true_grade", "mastery", "sport_level"}
        data = asdict(self)
        latent = {k: data.pop(k) for k in latent_keys}
        latent["true_skills"] = sorted(self.true_skills)
        data["specialization"] = self.specialization  # the survey answer is observed too
        data["confirmed_category"] = self.confirmed_category
        return {"latent": latent, "observed": data}


@dataclass
class SyntheticNeed:
    id: str
    company_id: str
    company_name: str
    title: str
    raw_description: str
    target_specialization: str
    target_grade: str
    track: str
    required_skills: list[str]
    work_format: str
    city: str | None
    salary_budget_max: int
    source: str  # "reference" (hand-written) or "template"
    split: str = ""  # "dev" or "test"


# ==========================================
# Generator
# ==========================================

def registry_item_pool() -> list[ItemCandidate]:
    return [
        ItemCandidate(
            id=f.code, code=f.code, specialization=f.specialization, target_grade=f.target_grade,
            topic=f.topic, discrimination_a=f.discrimination_a, difficulty_b=f.difficulty_b,
        )
        for f in list_all_families()
    ]


class SyntheticWorldGenerator:
    """Generates candidates, companies and needs from one seed.

    Independent random streams keep worlds comparable: the latent population is identical for any
    item bank or keyword-stuffing rate, only the affected observations change.
    """

    def __init__(
        self,
        seed: int = 2026,
        item_pool: list[ItemCandidate] | None = None,
        keyword_stuffing_rate: float = 0.25,
    ):
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.cat_rng = random.Random(seed + 1)
        self.stuff_rng = random.Random(seed + 2)
        self.keyword_stuffing_rate = keyword_stuffing_rate
        self.reference_time = datetime(2026, 10, 1, tzinfo=timezone.utc)

        pool = item_pool if item_pool is not None else registry_item_pool()
        self.pools = {spec: [it for it in pool if it.specialization == spec] for spec in SPECIALIZATIONS}
        self.truth = {it.id: (it.discrimination_a, it.difficulty_b) for it in pool}
        self.sessions_by_spec: Counter[str] = Counter()

    # ---------- latent ----------

    def _sample_theta(self) -> float:
        grades, weights = zip(*GRADE_MIX.items())
        grade = self.rng.choices(grades, weights=weights)[0]
        return float(np.clip(self.np_rng.normal(GRADE_START_THETA[grade], THETA_SD_WITHIN_GRADE), -3.0, 3.5))

    def _skill_level(self, theta: float, offset: float) -> float:
        return float(np.clip(1.0 / (1.0 + math.exp(-1.4 * (theta - offset))) + self.np_rng.normal(0.0, 0.1), 0.0, 1.0))

    def _sample_mastery(self, spec: str, track: str, theta: float) -> dict[str, float]:
        tr = TRACKS[spec][track]
        mastery: dict[str, float] = {}
        for skill in tr["core"]:
            mastery[skill] = self._skill_level(theta, self.rng.uniform(-1.8, -0.6))
        for skill in tr["extra"]:
            if self.rng.random() < 0.55:
                mastery[skill] = max(mastery.get(skill, 0.0), self._skill_level(theta, self.rng.uniform(-0.6, 1.2)))
        if self.rng.random() < 0.25:  # some experience in a second track of the same specialization
            other = self.rng.choice([t for t in TRACKS[spec] if t != track])
            for skill in self.rng.sample(TRACKS[spec][other]["core"], k=2):
                mastery[skill] = max(mastery.get(skill, 0.0), self._skill_level(theta, self.rng.uniform(0.0, 1.5)))
        return mastery

    def _declare_grade(self, true_grade: str) -> str:
        shifts, weights = zip(*SELF_ASSESSMENT)
        idx = GRADE_ORDER.index(true_grade) + self.rng.choices(shifts, weights=weights)[0]
        return GRADE_ORDER[min(max(idx, 0), len(GRADE_ORDER) - 1)]

    # ---------- observed: assessment ----------

    def _run_cat(self, spec: str, grade: str, theta: float, history: set[str],
                 prior: tuple[float, float] | None = None):
        """One adaptive session on the configured bank with the production engine.

        prior: the previous posterior for an offered follow-up test, which is also shorter (as on the platform).
        """
        self.sessions_by_spec[spec] += 1
        theta_hat, se = prior if prior else (get_start_theta(grade), 1.0)
        min_items, max_items = (FOLLOW_UP_MIN_ITEMS, FOLLOW_UP_MAX_ITEMS) if prior else (MIN_ITEMS, MAX_ITEMS)
        prior_mean, prior_sd = (prior[0], max(prior[1], 0.1)) if prior else (0.0, 1.0)
        administered: set[str] = set()
        topics: list[str] = []
        responses: list[int] = []
        params: list[tuple[float, float]] = []
        while not should_stop_assessment(len(responses), se, min_items=min_items, max_items=max_items)[0]:
            item = select_next_item(
                pool=self.pools[spec], current_theta=theta_hat, administered_item_ids=administered,
                administered_topics=topics, specialization=spec, history_item_ids=history,
                spec_session_count=self.sessions_by_spec[spec], rng=self.cat_rng,
            )
            if item is None:
                break
            administered.add(item.id)
            topics.append(item.topic)
            item.exposure_count += 1
            a, b = self.truth[item.id]
            responses.append(1 if self.cat_rng.random() < float(probability_2pl(theta, a, b)) else 0)
            params.append((item.discrimination_a, item.difficulty_b))
            theta_hat, se = estimate_theta_eap(responses, params, prior_mean=prior_mean, prior_sd=prior_sd)
        return theta_hat, se, administered, evaluate_assessment_result(grade, theta_hat, se, now=self.reference_time)

    def _certify(self, spec: str, declared: str, theta: float) -> tuple[str | None, float, float, int]:
        """Platform flow (plan 4.3): test on the declared grade, then the offered tests one grade up or down.

        An offered test is short and continues the previous measurement; half of the candidates accept an
        offer to go up, everyone takes the offer to go down. A failed attempt keeps the grade already confirmed.
        """
        history: set[str] = set()
        theta_hat, se, seen, ev = self._run_cat(spec, declared, theta, history)
        history |= seen
        grade = ev.confirmed_grade if ev.is_confirmed else None
        sessions = 1
        last_theta, last_se = theta_hat, se
        for _ in range(len(GRADE_ORDER) - 1):
            offered = ev.recommendation in ("OFFER_HIGHER_GRADE", "OFFER_LOWER_GRADE") and ev.suggested_grade != ev.target_grade
            if not offered or (ev.recommendation == "OFFER_HIGHER_GRADE" and self.cat_rng.random() >= 0.5):
                break
            last_theta, last_se, seen, ev = self._run_cat(spec, ev.suggested_grade, theta, history, prior=(last_theta, last_se))
            history |= seen
            sessions += 1
            if ev.is_confirmed:
                grade, theta_hat, se = ev.confirmed_grade, last_theta, last_se
            elif grade is None:
                theta_hat, se = last_theta, last_se
        return grade, theta_hat, se, sessions

    # ---------- observed: skills, FSP, resume ----------

    def _observed_skills(self, spec: str, track: str, mastery: dict[str, float],
                         confirmed: bool) -> tuple[dict[str, str], bool, bool, list[str], list[str]]:
        claimed = sorted(
            s for s, m in mastery.items()
            if (m >= MASTERY_THRESHOLD and self.rng.random() < 0.92) or (0.3 <= m < MASTERY_THRESHOLD and self.rng.random() < 0.35)
        )
        spec_skills = sorted({s for tr in TRACKS[spec].values() for s in tr["core"] + tr["extra"]})
        if self.rng.random() < 0.15:  # claims a few skills they do not have
            unknown = [s for s in spec_skills if mastery.get(s, 0.0) < 0.3 and s not in claimed]
            claimed += self.rng.sample(unknown, k=min(len(unknown), self.rng.randint(2, 3)))
        has_resume = self.rng.random() < 0.7

        stuffer = has_resume and self.stuff_rng.random() < self.keyword_stuffing_rate
        stuffed: list[str] = []
        if stuffer:
            pool = [s for s in spec_skills if s not in claimed]
            stuffed = self.stuff_rng.sample(pool, k=min(len(pool), self.stuff_rng.randint(5, 8)))

        source = "RESUME" if has_resume else "CLAIMED"
        skills = {s: source for s in claimed}
        skills.update({s: "RESUME" for s in stuffed})  # the resume parser extracts stuffed keywords too
        if confirmed:
            for s in TRACKS[spec][track]["tested"]:
                skills[s] = "ASSESSMENT"
        return skills, has_resume, stuffer, claimed, stuffed

    def _fsp_profile(self, theta: float) -> tuple[float | None, list[dict[str, Any]], str | None]:
        if self.rng.random() >= FSP_PARTICIPATION:
            return None, [], None
        z = (theta - 0.5) / 1.05
        level = FSP_THETA_CORRELATION * z + math.sqrt(1 - FSP_THETA_CORRELATION ** 2) * float(self.np_rng.normal())
        events = []
        for _ in range(self.rng.randint(1, 4)):
            r = level + float(self.np_rng.normal(0.0, 0.6))
            result = "WINNER" if r > 1.3 else "PRIZE_WINNER" if r > 0.6 else "FINALIST" if r > -0.2 else "PARTICIPANT"
            r = level + float(self.np_rng.normal(0.0, 0.6))
            lvl = "INTERNATIONAL" if r > 1.2 else "ALL_RUSSIAN" if r > 0.2 else "INTERREGIONAL" if r > -0.5 else "REGIONAL"
            date = self.reference_time - timedelta(days=self.rng.randint(30, 4 * 365))
            events.append({
                "event_name": self.rng.choice(FSP_EVENTS),
                "discipline": self.rng.choice(FSP_DISCIPLINES),
                "level": lvl,
                "result": result,
                "event_date": date.isoformat(),
            })
        rank = "Мастер спорта" if level > 1.6 else "КМС" if level > 0.9 else "1 разряд" if level > 0.3 else None
        return level, events, rank

    def _resume_text(self, spec: str, track: str, declared: str, true_grade: str, claimed: list[str],
                     stuffed: list[str], has_resume: bool, last_name: str, first_name: str) -> str:
        title = f"{GRADE_WORD[declared]} {TRACKS[spec][track]['title']}"
        if not has_resume:
            # profile form only: title and listed skills
            return f"{title}. Навыки: {', '.join(claimed)}."
        lo, hi = GRADE_YEARS[true_grade]
        years = self.rng.randint(lo, hi)
        lines = [
            f"{last_name} {first_name}. {title}.",
            f"Опыт коммерческой работы: {_years_ru(years)}." if years else "Без коммерческого опыта, учебные и пет-проекты.",
            f"Ключевые навыки: {', '.join(claimed)}.",
        ]
        for _ in range(2):
            used = self.rng.sample(claimed, k=min(2, len(claimed)))
            product = self.rng.choice(list(INDUSTRIES.values()))
            duty = self.rng.choice(DUTIES[spec])
            if used:
                lines.append(f"Проект: {product} — {duty}, использовал {' и '.join(used)}.")
        if stuffed:
            lines.append(f"Также работал с: {', '.join(stuffed + self.stuff_rng.sample(claimed, k=min(3, len(claimed))))}.")
        lines.append(f"Образование: {self.rng.choice(UNIVERSITIES)}.")
        return "\n".join(lines)

    # ---------- candidates ----------

    def generate_candidate(self, index: int) -> SyntheticCandidate:
        rng = self.rng
        female = rng.random() < 0.35
        first = rng.choice(FIRST_NAMES_F if female else FIRST_NAMES_M)
        last = rng.choice(LAST_NAMES_F if female else LAST_NAMES_M)

        spec = rng.choice(SPECIALIZATIONS)
        track = rng.choice(list(TRACKS[spec]))
        theta = self._sample_theta()
        true_grade = classify_theta_to_grade(theta)
        mastery = self._sample_mastery(spec, track, theta)
        declared = self._declare_grade(true_grade)

        lo, hi = SALARY_RANGES[declared]
        desired = int(round(rng.uniform(lo, lo + 0.75 * (hi - lo)), -4))
        work_format = rng.choices(["REMOTE", "HYBRID", "OFFICE"], weights=[0.50, 0.35, 0.15])[0]
        city = rng.choices(CITIES, weights=CITY_WEIGHTS)[0]
        status = rng.choices(["ACTIVELY_SEARCHING", "OPEN", "HIDDEN"], weights=[0.55, 0.37, 0.08])[0]
        days_since_update = int(self.np_rng.exponential(40.0))

        confirmed_grade, theta_hat, se, sessions = self._certify(spec, declared, theta)
        skills, has_resume, stuffer, claimed, stuffed = self._observed_skills(spec, track, mastery, confirmed_grade is not None)

        sport_level, events, sport_rank = self._fsp_profile(theta)
        fsp_score = 0.0
        if events:
            fsp_score = calculate_fsp_score(events, sport_rank, now=self.reference_time)["normalized_score"]

        return SyntheticCandidate(
            id=str(uuid.UUID(int=self.rng.getrandbits(128))),
            index=index,
            specialization=spec,
            track=track,
            true_theta=round(theta, 4),
            true_grade=true_grade,
            mastery={s: round(m, 3) for s, m in mastery.items()},
            sport_level=None if sport_level is None else round(sport_level, 3),
            first_name=first,
            last_name=last,
            email=f"candidate{index}@example.com",
            phone=f"+7 (900) 000-{index // 100:02d}-{index % 100:02d}",
            telegram=f"@candidate_{index}",
            declared_grade=declared,
            city=city,
            work_format=work_format,
            desired_salary_min=desired,
            status=status,
            days_since_update=days_since_update,
            confirmed_grade=confirmed_grade,
            theta_hat=round(theta_hat, 4),
            theta_se=round(se, 4),
            category_percentile=calculate_category_percentile(theta_hat),
            test_sessions=sessions,
            skills=skills,
            has_resume=has_resume,
            keyword_stuffer=stuffer,
            resume_text=self._resume_text(spec, track, declared, true_grade, claimed, stuffed, has_resume, last, first),
            fsp_id=f"FSP-{index:06d}" if events else None,
            fsp_achievements=events,
            sport_rank=sport_rank,
            fsp_score=fsp_score,
        )

    def generate_population(self, n: int = 1000) -> list[SyntheticCandidate]:
        return [self.generate_candidate(i) for i in range(1, n + 1)]

    # ---------- companies and needs ----------

    def generate_companies(self, n: int = 20) -> list[dict[str, str]]:
        industries = list(INDUSTRIES)
        return [
            {"id": f"company-{i + 1:02d}", "name": f"ООО «{name}»", "industry": industries[i % len(industries)]}
            for i, name in enumerate(COMPANY_NAMES[:n])
        ]

    def _templated_need(self, company: dict[str, str]) -> SyntheticNeed:
        rng = self.rng
        spec = rng.choice(SPECIALIZATIONS)
        track = rng.choice(list(TRACKS[spec]))
        grade = rng.choices(GRADE_ORDER, weights=[0.05, 0.30, 0.45, 0.20])[0]
        tr = TRACKS[spec][track]
        required = [tr["core"][0]] + rng.sample(tr["core"][1:], k=2) + rng.sample(tr["extra"], k=rng.randint(0, 1))
        plus = rng.choice([s for s in tr["extra"] if s not in required])
        work_format = rng.choices(["REMOTE", "HYBRID", "OFFICE"], weights=[0.45, 0.35, 0.20])[0]
        city = None if work_format == "REMOTE" else rng.choices(CITIES, weights=CITY_WEIGHTS)[0]
        lo, hi = SALARY_RANGES[grade]
        budget = int(round(rng.uniform((lo + hi) / 2, hi * 1.1), -4))

        title = f"{GRADE_WORD[grade]} {tr['title']}"
        text = rng.choice(NEED_TEMPLATES).format(
            company=company["name"], industry=company["industry"], product=INDUSTRIES[company["industry"]],
            title=title, title_lower=title[0].lower() + title[1:], duty=rng.choice(DUTIES[spec]),
            stack=", ".join(required), plus=plus,
            format_text=FORMAT_TEXT[work_format].format(city=city),
        )
        return SyntheticNeed(
            id="", company_id=company["id"], company_name=company["name"], title=title, raw_description=text,
            target_specialization=spec, target_grade=grade, track=track, required_skills=required,
            work_format=work_format, city=city, salary_budget_max=budget, source="template",
        )

    def generate_needs(self, n: int, companies: list[dict[str, str]]) -> list[SyntheticNeed]:
        with open(REFERENCE_NEEDS_PATH, encoding="utf-8") as f:
            reference = json.load(f)
        needs = []
        for i, ref in enumerate(reference[:n]):
            company = companies[i % len(companies)]
            needs.append(SyntheticNeed(id="", company_id=company["id"], company_name=company["name"],
                                       source="reference", **ref))
        while len(needs) < n:
            needs.append(self._templated_need(self.rng.choice(companies)))
        for i, need in enumerate(needs):
            need.id = f"need-{i + 1:03d}"

        # dev/test split stratified by specialization: weights are tuned on dev, reported on test
        for spec in SPECIALIZATIONS:
            group = [nd for nd in needs if nd.target_specialization == spec]
            self.rng.shuffle(group)
            for j, need in enumerate(group):
                need.split = "dev" if j % 2 == 0 else "test"
        return needs

    def generate_world(self, n_candidates: int = 1000, n_needs: int = 50) -> dict[str, Any]:
        candidates = self.generate_population(n_candidates)
        companies = self.generate_companies()
        needs = self.generate_needs(n_needs, companies)
        return {"candidates": candidates, "companies": companies, "needs": needs}


def describe_world(world: dict[str, Any]) -> dict[str, Any]:
    cands: list[SyntheticCandidate] = world["candidates"]
    confirmed = [c for c in cands if c.confirmed_grade]
    unverified = [(c, s) for c in cands for s, src in c.skills.items() if src in ("RESUME", "CLAIMED")]
    return {
        "candidates": len(cands),
        "needs": len(world["needs"]),
        "companies": len(world["companies"]),
        "with_fsp": sum(1 for c in cands if c.fsp_achievements) / len(cands),
        "hidden": sum(1 for c in cands if c.status == "HIDDEN") / len(cands),
        "with_resume": sum(1 for c in cands if c.has_resume) / len(cands),
        "keyword_stuffers": sum(1 for c in cands if c.keyword_stuffer) / len(cands),
        "false_unverified_skill_share": (sum(1 for c, s in unverified if c.mastery.get(s, 0.0) < MASTERY_THRESHOLD)
                                         / len(unverified)) if unverified else 0.0,
        "grade_confirmed": len(confirmed) / len(cands),
        "confirmed_grade_accuracy": (sum(1 for c in confirmed if c.confirmed_grade == c.true_grade) / len(confirmed)) if confirmed else 0.0,
        "declared_grade_accuracy": sum(1 for c in cands if c.declared_grade == c.true_grade) / len(cands),
        "fsp_theta_correlation": float(np.corrcoef(
            [c.true_theta for c in cands if c.fsp_achievements], [c.fsp_score for c in cands if c.fsp_achievements]
        )[0, 1]) if sum(1 for c in cands if c.fsp_achievements) > 2 else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic FSP-Talent world")
    parser.add_argument("--candidates", type=int, default=1000)
    parser.add_argument("--needs", type=int, default=50)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    world = SyntheticWorldGenerator(seed=args.seed).generate_world(args.candidates, args.needs)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    payload = {
        "candidates.json": [c.to_dict() for c in world["candidates"]],
        "companies.json": world["companies"],
        "needs.json": [asdict(n) for n in world["needs"]],
    }
    for name, data in payload.items():
        with open(os.path.join(OUTPUT_DIR, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    print(json.dumps(describe_world(world), ensure_ascii=False, indent=2))
    print(f"Saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
