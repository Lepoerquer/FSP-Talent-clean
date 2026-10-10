"""Need / vacancy text parser (R2-07): free text -> structured employer request (plan 4.4).

Dictionary + rules, no ML model:
- skills: names and synonyms from the skills dictionary, with Russian case endings, a stop-list of
  synonyms that are ordinary words, and longest-match resolution of overlapping mentions;
  mentions after "будет плюсом", "желательно" and similar markers go to nice-to-have;
- specialization: role keywords (the title outside parentheses weighs most) plus tags of found skills;
- grade: grade word in the title, then required experience, then grade words in the text;
- work format, city and salary: patterns.

Every field carries the text it was derived from, so the employer can check and edit the structure.
"""

import logging
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any

from backend.app.modules.dictionaries.seeds import SKILLS_DATA

logger = logging.getLogger("fsp.need_parser")

# ==========================================
# Text helpers
# ==========================================

_WORD_CHARS = r"\w+#"
_CYRILLIC = re.compile(r"[а-я]", re.IGNORECASE)
_VOWEL_ENDINGS = tuple("аяоеёыиуюйь")
# Two-letter case endings; anything else at the end of a word is part of the stem ("джунит", "формик")
_ENDINGS2 = ("ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие", "ов", "ев", "ей", "ом", "ем", "ам", "ям", "ах", "ях", "ия", "ью")


def normalize_text(text: str) -> str:
    """Same length as the input (so spans map back), ё -> е, unusual spaces -> space."""
    return text.replace("ё", "е").replace("Ё", "Е").replace(" ", " ").replace(" ", " ")


def _stem_pattern(word: str) -> str:
    """Regex for a Cyrillic word with any of its case endings."""
    head, sep, last = word.rpartition("-")
    target = last if sep else word
    stem = target
    if len(target) >= 6 and target.endswith(_ENDINGS2):
        stem = target[:-2]
    elif target.endswith(_VOWEL_ENDINGS):
        stem = target[:-1]
    if len(stem) < 4:  # a short stem matches unrelated words: "руби" would match "руб." and "рублей"
        return re.escape(word)
    prefix = re.escape(head + sep) if sep else ""
    return prefix + re.escape(stem) + r"[а-я]{0,4}"


def _surface_pattern(surface: str) -> str:
    words = surface.split()
    parts = [_stem_pattern(w) if _CYRILLIC.search(w) and len(w) >= 4 else re.escape(w) for w in words]
    return r"\s+".join(parts)


def _bounded(pattern: str) -> str:
    return rf"(?<![{_WORD_CHARS}]){pattern}(?![{_WORD_CHARS}])"


# ==========================================
# Skills dictionary index
# ==========================================

# Synonyms that are ordinary words in vacancy texts, or too short to be safe
IGNORED_SURFACES = {
    "каналы", "клик", "стили", "кролик", "токио", "скала", "лара", "рельсы", "алхимия", "эликсир", "чакра", "рей",
    "си", "ява", "го", "es", "ws", "py", "ng", "rn", "ув", "тф", "д3", "к6", "iac", "compose", "арго", "локи",
    "темпо", "мимир", "танос", "хрома", "престо", "трино", "пакт", "комбайн", "нест", "нода", "лида", "стек елк",
    "блок", "вектор", "графики", "чарты", "провайдер", "экспресс", "медиатор", "лора", "чеков",
    "backend", "frontend", "mobile", "android testing", "ios testing",
}
# Surfaces that are common English words unless written as a name
CASE_SENSITIVE_SURFACES = {"C", "Go", "Gin", "Chi", "Echo", "Ray", "Combine", "Swift", "Next", "Rust", "Helm", "SOLID"}
# Second words dropped to get the short form people write: "Allure Report" -> "Allure"
GENERIC_SUFFIXES = {"report", "webdriver", "proxy", "sdk"}


@dataclass(frozen=True)
class SkillEntry:
    code: str
    name: str
    tags: tuple[str, ...]


def _surfaces(item: dict[str, Any]) -> set[str]:
    name = item["name"]
    forms = {name}
    without_parens = re.sub(r"\s*\(.*?\)", "", name).strip()
    forms.add(without_parens)
    for inner in re.findall(r"\((.*?)\)", name):
        if "," not in inner and len(inner.split()) <= 2:
            forms.add(inner)
    for part in re.split(r"\s+/\s+", without_parens):
        forms.add(part)
        words = part.split()
        if len(words) == 2 and words[1].lower() in GENERIC_SUFFIXES:
            forms.add(words[0])
    for form in list(forms):
        if form.lower().startswith("apache "):
            forms.add(form[len("apache "):])
        if re.fullmatch(r"[\w]+\.js", form, re.IGNORECASE):
            forms.add(form[:-3])
    forms.update(item["synonyms"])
    return {f.strip() for f in forms if f.strip() and f.strip().lower() not in IGNORED_SURFACES}


@lru_cache(maxsize=1)
def skill_index() -> tuple[list[tuple[re.Pattern[str], SkillEntry, bool]], dict[str, SkillEntry]]:
    """Compiled surface patterns: (pattern, skill, case_sensitive), longest surfaces first."""
    owners: dict[str, list[SkillEntry]] = {}
    for item in SKILLS_DATA:
        entry = SkillEntry(item["code"], item["name"], tuple(item["tags"]))
        for surface in _surfaces(item):
            owners.setdefault(normalize_text(surface), []).append(entry)

    patterns = []
    for surface, entries in owners.items():
        if len(entries) > 1:
            # the same surface for several skills: keep the skill that is literally named so exactly
            named = [e for e in entries if e.name.strip().lower() == surface.lower()]
            if len(named) != 1:
                # fallback: check without parens
                named = [e for e in entries if re.sub(r"\s*\(.*?\)", "", e.name).strip().lower() == surface.lower()]
                if len(named) != 1:
                    continue
            entries = named
        case_sensitive = surface in CASE_SENSITIVE_SURFACES
        if len(surface) <= 2 and not case_sensitive and surface.lower() not in {"js", "ts", "pg"}:
            continue
        flags = 0 if case_sensitive else re.IGNORECASE
        patterns.append((len(surface), re.compile(_bounded(_surface_pattern(surface)), flags), entries[0], case_sensitive))
    patterns.sort(key=lambda p: -p[0])
    by_name = {item["name"]: SkillEntry(item["code"], item["name"], tuple(item["tags"])) for item in SKILLS_DATA}
    return [(p, e, cs) for _, p, e, cs in patterns], by_name


# ==========================================
# Result structure
# ==========================================

@dataclass
class ParsedField:
    value: Any = None
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)


@dataclass
class SkillMention:
    name: str
    code: str
    evidence: str
    nice_to_have: bool = False


@dataclass
class ParsedNeed:
    specialization: ParsedField
    grade: ParsedField
    work_format: ParsedField
    city: ParsedField
    skills: list[SkillMention]
    nice_to_have: list[SkillMention]
    salary_from: int | None = None
    salary_to: int | None = None
    salary_type: str | None = None
    is_gross: bool | None = None
    salary_evidence: str | None = None
    experience_years: int | None = None
    specialization_scores: dict[str, float] = field(default_factory=dict)

    @property
    def required_skill_names(self) -> list[str]:
        return [s.name for s in self.skills]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ==========================================
# Skills and nice-to-have
# ==========================================

PLUS_MARKERS = re.compile(
    r"(будет\s+(?:большим\s+)?плюсом|плюсом\s+будет|будет\s+преимуществ|преимуществом\s+будет|желательн|приветству|"
    r"nice\s+to\s+have|is\s+a\s+plus|\bплюс(?:ом)?\b|\bдополнительно\b)",
    re.IGNORECASE,
)
HEADER = re.compile(r"^\s*([^:\n]{2,40}):\s*(.*)$")
BULLET = re.compile(r"^\s*[-–—•*·]\s*")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+(?=[А-ЯA-Z])")


def _segments(text: str) -> list[tuple[int, int, bool]]:
    """(start, end, nice_to_have) spans covering the text.

    A header such as "Будет плюсом:" makes the following bullets nice-to-have; inside any line a
    sentence with a marker ("Желательно знание Appium.") is nice-to-have on its own.
    """
    spans = []
    pos = 0
    section_plus = False
    for line in text.split("\n"):
        start = pos
        pos += len(line) + 1
        if not line.strip():
            continue
        if BULLET.match(line):
            spans.append((start, start + len(line), section_plus or bool(PLUS_MARKERS.search(line))))
            continue
        header = HEADER.match(line)
        if header:
            section_plus = bool(PLUS_MARKERS.search(header.group(1)))
            body_start = start + header.start(2)
            spans.append((start, body_start, section_plus))
        else:
            section_plus = False
            body_start = start
        offset = body_start
        for sentence in SENTENCE_SPLIT.split(text[body_start:start + len(line)]):
            if not sentence:
                continue
            idx = text.find(sentence, offset)
            spans.append((idx, idx + len(sentence), section_plus or bool(PLUS_MARKERS.search(sentence))))
            offset = idx + len(sentence)
    return spans


def extract_skills(text: str) -> tuple[list[SkillMention], list[SkillMention]]:
    norm = normalize_text(text)
    patterns, _ = skill_index()
    taken = [False] * len(norm)
    found: list[tuple[int, SkillMention]] = []
    for pattern, entry, _cs in patterns:
        for m in pattern.finditer(norm):
            if any(taken[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            found.append((m.start(), SkillMention(entry.name, entry.code, text[m.start():m.end()])))

    segments = _segments(norm)
    required: dict[str, SkillMention] = {}
    nice: dict[str, SkillMention] = {}
    for start, mention in sorted(found, key=lambda x: x[0]):
        is_plus = next((plus for s, e, plus in segments if s <= start < e), False)
        if is_plus:
            mention.nice_to_have = True
            nice.setdefault(mention.name, mention)
        else:
            required.setdefault(mention.name, mention)
    # a skill both required and "nice" is required
    return list(required.values()), [m for name, m in nice.items() if name not in required]


# ==========================================
# Specialization
# ==========================================

SPEC_KEYWORDS: dict[str, list[str]] = {
    "BACKEND": [r"back-?end\w*", r"бэк-?енд\w*", r"бек-?енд\w*", r"серверн\w*", r"full-?stack\w*", r"фулл?-?ст[эе]к\w*",
                r"(?:python|java|go|golang|php|node\.?js|c#|\.net|kotlin|scala|ruby|rust|c\+\+)[- ]?(?:разработчик\w*|developer|engineer|программист\w*)"],
    "FRONTEND": [r"front-?end\w*", r"фронт-?енд\w*", r"фронтенд\w*", r"верстальщик\w*", r"full-?stack\w*", r"фулл?-?ст[эе]к\w*", r"web-?(?:developer|разработчик\w*|программист\w*)",
                 r"(?:react|vue|angular|javascript|typescript)[- ]?(?:разработчик\w*|developer)"],
    "QA": [r"qa", r"тестир\w*", r"автотест\w*", r"автоматизатор\w*", r"quality\s+assurance", r"sdet"],
    "DATA_ML": [r"data\s+scien\w*", r"дата[- ]?сайентист\w*", r"ml", r"machine\s+learning", r"машинн\w*\s+обучени\w*",
                r"nlp", r"computer\s+vision", r"компьютерн\w*\s+зрени\w*", r"нейросет\w*", r"data\s+engineer\w*", r"ml-инженер\w*"],
    "DEVOPS": [r"devops\w*", r"девопс\w*", r"sre", r"инфраструктур\w*", r"platform\s+engineer\w*"],
    "MOBILE": [r"ios", r"android", r"андроид\w*", r"mobile", r"мобильн\w*", r"flutter"],
}
SPEC_PATTERNS = {spec: [re.compile(_bounded(p), re.IGNORECASE) for p in pats] for spec, pats in SPEC_KEYWORDS.items()}
TAG_TO_SPEC = {"backend": "BACKEND", "frontend": "FRONTEND", "qa": "QA", "testing": "QA", "automation": "QA",
               "data": "DATA_ML", "ml": "DATA_ML", "devops": "DEVOPS", "mobile": "MOBILE", "ios": "MOBILE",
               "android": "MOBILE"}
TITLE_WEIGHT, QUALIFIER_WEIGHT, TEXT_WEIGHT, SKILL_TAG_WEIGHT = 3.0, 1.0, 1.0, 0.5


def detect_specialization(title: str, text: str, skills: list[SkillMention]) -> tuple[ParsedField, dict[str, float]]:
    _, by_name = skill_index()
    role = re.sub(r"\(.*?\)", " ", title)            # "QA-инженер (мобильные приложения)": the role is outside
    qualifiers = " ".join(re.findall(r"\((.*?)\)", title))
    scores = dict.fromkeys(SPEC_PATTERNS, 0.0)
    evidence: dict[str, list[str]] = {spec: [] for spec in SPEC_PATTERNS}
    for spec, patterns in SPEC_PATTERNS.items():
        for source, weight in ((role, TITLE_WEIGHT), (qualifiers, QUALIFIER_WEIGHT), (text, TEXT_WEIGHT)):
            for p in patterns:
                for m in p.finditer(normalize_text(source)):
                    scores[spec] += weight
                    evidence[spec].append(m.group(0))
    for mention in skills:
        specs = {TAG_TO_SPEC[t] for t in by_name[mention.name].tags if t in TAG_TO_SPEC}
        for spec in specs:
            scores[spec] += SKILL_TAG_WEIGHT / len(specs)
            evidence[spec].append(mention.name)
    total = sum(scores.values())
    best = max(scores, key=scores.get)
    if total == 0:
        return ParsedField(), scores
    return ParsedField(best, round(scores[best] / total, 2), evidence[best][:6]), {k: round(v, 2) for k, v in scores.items()}


# ==========================================
# Grade and experience
# ==========================================

GRADE_WORDS = [
    ("SENIOR", r"senior\w*|сеньор\w*|синьор\w*|старш\w*|ведущ\w*|lead|лид|тимлид\w*|team\s?lead|principal|руководител\w*"),
    ("MIDDLE", r"middle\w*|мидл\w*"),
    ("JUNIOR", r"junior\w*|джун\w*|младш\w*"),
    ("INTERN", r"intern\w*|стажер\w*|стажировк\w*|trainee|начинающ\w*|выпускник\w*|без\s+опыта"),
]
GRADE_PATTERN = re.compile("|".join(f"(?P<{g}>{_bounded(p)})" for g, p in GRADE_WORDS), re.IGNORECASE)
EXPERIENCE_PATTERNS = [
    re.compile(r"опыт\w*(?:\s+[а-я\w-]+){0,4}?\s+(?:от|не\s+менее|более|свыше)\s+(\d{1,2})\s*(?:-?х\s+)?(?:лет|года?)\b", re.IGNORECASE),
    re.compile(r"(\d{1,2})\+?\s*(?:лет|года?)\s+(?:коммерческого\s+)?опыт", re.IGNORECASE),
    re.compile(r"(\d{1,2})\+?\s+years?", re.IGNORECASE),
]


def years_to_grade(years: int) -> str:
    if years < 1:
        return "INTERN"
    if years < 3:
        return "JUNIOR"
    if years < 5:
        return "MIDDLE"
    return "SENIOR"


def detect_experience(text: str) -> tuple[int | None, str | None]:
    for p in EXPERIENCE_PATTERNS:
        m = p.search(text)
        if m:
            return int(m.group(1)), m.group(0)
    return None, None


def detect_grade(title: str, text: str, years: int | None, years_evidence: str | None) -> ParsedField:
    title_hits = [(m.lastgroup, m.group(0)) for m in GRADE_PATTERN.finditer(normalize_text(title))]
    if title_hits:
        grade, word = title_hits[0]
        # "Middle/Senior" names two grades: the first one, with less confidence
        return ParsedField(grade, 0.9 if len({g for g, _ in title_hits}) == 1 else 0.6, [w for _, w in title_hits])
    if years is not None:
        return ParsedField(years_to_grade(years), 0.75, [years_evidence])
    text_hits = [(m.lastgroup, m.group(0)) for m in GRADE_PATTERN.finditer(normalize_text(text))]
    if text_hits:
        order = list(dict.fromkeys(g for g, _ in text_hits))
        counts = {g: sum(1 for h, _ in text_hits if h == g) for g in order}
        grade = max(order, key=lambda g: (counts[g], -order.index(g)))  # most frequent, then earliest
        return ParsedField(grade, 0.5, [w for g, w in text_hits if g == grade][:3])
    return ParsedField()


# ==========================================
# Work format and city
# ==========================================

REMOTE = re.compile(r"удал[её]нн\w*|удал[её]нк\w*|удал[её]нно|remote|дистанционн\w*|из\s+любого\s+города|из\s+любой\s+точки", re.IGNORECASE)
HYBRID = re.compile(
    r"гибрид\w*|hybrid|частично\s+удал\w*|можно\s+работать\s+из\s+дома|"
    r"(?:один|два|три|1|2|3)\s+дн\w*\s+в\s+неделю\s+(?:можно\s+)?(?:работать\s+)?(?:из\s+дома|удал\w*)",
    re.IGNORECASE,
)
OFFICE = re.compile(r"\bв\s+офисе\b|\bофис\w*|\boffice\b|on-?site", re.IGNORECASE)

CITIES = {
    "Москва": r"москв\w*",
    "Санкт-Петербург": r"санкт-петербург\w*|петербург\w*|спб|питер\w*",
    "Новосибирск": r"новосибирск\w*",
    "Екатеринбург": r"екатеринбург\w*",
    "Казань": r"казан[ьи]",
    "Нижний Новгород": r"нижн\w+\s+новгород\w*",
    "Томск": r"томск\w*",
    "Самара": r"самар[аеуы]",
    "Иннополис": r"иннополис\w*",
    "Пермь": r"перм[ьи]",
    "Омск": r"омск\w*",
    "Краснодар": r"краснодар\w*",
    "Ростов-на-Дону": r"ростов\w*(?:-на-дону)?",
    "Уфа": r"уф[аеуы]",
    "Челябинск": r"челябинск\w*",
    "Красноярск": r"красноярск\w*",
    "Воронеж": r"воронеж\w*",
    "Владивосток": r"владивосток\w*",
    "Калининград": r"калининград\w*",
    "Тюмень": r"тюмен[ьи]",
    "Ярославль": r"ярославл[ьея]",
}
CITY_PATTERNS = {city: re.compile(_bounded(p), re.IGNORECASE) for city, p in CITIES.items()}


def detect_work_format(text: str) -> ParsedField:
    norm = normalize_text(text)
    hybrid = HYBRID.search(norm)
    if hybrid:
        return ParsedField("HYBRID", 0.9, [hybrid.group(0)])
    remote, office = REMOTE.search(norm), OFFICE.search(norm)
    if remote and office:
        lo, hi = sorted((remote.start(), office.start()))
        between = norm[lo:hi + 1]
        if re.search(r"\bили\b|\bor\b", between, re.IGNORECASE):
            return ParsedField("REMOTE", 0.7, [norm[lo:max(remote.end(), office.end())]])
        return ParsedField("HYBRID", 0.6, [remote.group(0), office.group(0)])
    if remote:
        return ParsedField("REMOTE", 0.9, [remote.group(0)])
    if office:
        return ParsedField("OFFICE", 0.8, [office.group(0)])
    return ParsedField()


def detect_city(text: str, work_format: str | None) -> ParsedField:
    if work_format == "REMOTE":
        return ParsedField()  # a city in a remote vacancy is usually a time zone or a head office
    norm = normalize_text(text)
    hits = sorted(((m.start(), city, m.group(0)) for city, p in CITY_PATTERNS.items() for m in p.finditer(norm)))
    if not hits:
        return ParsedField()
    _, city, word = hits[0]
    return ParsedField(city, 0.8, [word])


# ==========================================
# Salary
# ==========================================

SALARY_CONTEXT = re.compile(r"зарплат\w*|\bз/?п\b|\bзп\b|оклад\w*|доход\w*|вилк\w*|компенсаци\w*|₽|\bруб\w*|\brub\b|\bтыс|\d\s*[кk]\b", re.IGNORECASE)
AMOUNT = r"(\d{1,3}(?:[ ]\d{3})+|\d+(?:[.,]\d+)?)"
UNIT = r"\s*(тыс\w*\.?|т\.?\s?р\.?|k|к)?"
RANGE = re.compile(rf"(?:от\s+)?{AMOUNT}{UNIT}\s*(?:[-–—]|до)\s*{AMOUNT}{UNIT}", re.IGNORECASE)
SINGLE = re.compile(rf"\b(от|до|from|up\s+to)\s+{AMOUNT}{UNIT}", re.IGNORECASE)
NOT_MONEY = re.compile(r"^\s*(?:лет|года?|years?|дн\w*|сотрудник\w*|человек|%)", re.IGNORECASE)


def _amount(number: str, unit: str | None) -> int | None:
    value = float(number.replace(" ", "").replace(",", "."))
    if unit or value < 1000:
        value *= 1000
    value = int(round(value))
    return value if 10_000 <= value <= 5_000_000 else None


def detect_salary(text: str) -> tuple[int | None, int | None, str | None]:
    norm = normalize_text(text)
    for sentence in re.split(r"(?<=[.!?])\s+(?=[А-ЯA-Z])|\n", norm):
        if not SALARY_CONTEXT.search(sentence):
            continue
        m = RANGE.search(sentence)
        if m and not NOT_MONEY.match(sentence[m.end():]):
            unit = m.group(4) or m.group(2)
            lo, hi = _amount(m.group(1), unit), _amount(m.group(3), unit)
            if lo and hi and lo <= hi:
                return lo, hi, m.group(0).strip()
        for s in SINGLE.finditer(sentence):
            if NOT_MONEY.match(sentence[s.end():]):
                continue
            value = _amount(s.group(2), s.group(3))
            if value:
                if s.group(1).lower() in ("от", "from"):
                    return value, None, s.group(0).strip()
                return None, value, s.group(0).strip()
    return None, None, None


GROSS_MARKERS = re.compile(r"\b(?:гросс|gross|до\s+вычета|до\s+налог\w*)\b", re.IGNORECASE)
NET_MARKERS = re.compile(r"\b(?:нетто|net|на\s+руки|чистыми)\b", re.IGNORECASE)


def detect_salary_type(text: str) -> tuple[str | None, bool | None]:
    """Detects whether salary is specified as Gross (до вычета) or Net (на руки)."""
    norm = normalize_text(text)
    if GROSS_MARKERS.search(norm):
        return "GROSS", True
    if NET_MARKERS.search(norm):
        return "NET", False
    return None, None


# ==========================================
# Entry point
# ==========================================

def parse_need(text: str, title: str | None = None) -> ParsedNeed:
    """Parse a free-text employer need or vacancy into a structure the employer then edits."""
    title = title or ""
    full = f"{title}\n{text}" if title else text
    skills, nice = extract_skills(full)
    years, years_evidence = detect_experience(normalize_text(full))
    specialization, scores = detect_specialization(title, text, skills)
    
    # R4-04 Fix: Remove context-only mentions that are not actual required skills
    def is_relevant(m: SkillMention) -> bool:
        ev = m.evidence.lower()
        # Drop iOS/Android if they are just mentioned as platforms to test/support, not SDKs
        if ev in ("ios", "android", "айос", "андроид"):
            # They are skills for MOBILE. For QA/Backend/Frontend, they are usually just platforms.
            if specialization.value in ("QA", "BACKEND", "FRONTEND", "DEVOPS"):
                return False
        # Drop microservices if it's just "мы делаем микросервисы" for DevOps/QA
        if m.name == "Микросервисная архитектура" and "микросервис" in ev:
            if specialization.value in ("DEVOPS", "QA", "FRONTEND", "MOBILE"):
                return False
        return True

    skills = [s for s in skills if is_relevant(s)]
    nice = [s for s in nice if is_relevant(s)]
    
    work_format = detect_work_format(full)
    salary_from, salary_to, salary_evidence = detect_salary(full)
    salary_type, is_gross = detect_salary_type(full)
    return ParsedNeed(
        specialization=specialization,
        grade=detect_grade(title, text, years, years_evidence),
        work_format=work_format,
        city=detect_city(full, work_format.value),
        skills=skills,
        nice_to_have=nice,
        salary_from=salary_from,
        salary_to=salary_to,
        salary_type=salary_type,
        is_gross=is_gross,
        salary_evidence=salary_evidence,
        experience_years=years,
        specialization_scores=scores,
    )


# ==========================================
# Hybrid AI-First Parser (GigaChat + NLP Rules Fallback)
# ==========================================

def _clean_skill_token(token: str) -> str:
    """Strip common russian filler words like 'опыт с', 'знание', 'очередями', etc."""
    cleaned = re.sub(
        r"^(?:опыт\s+(?:работы\s+)?с|опыт\s+в|знание|понимание|навыки|владение|использование|стек|очередями|кэшированием|базами\s+данных|фреймворком|библиотекой)\s+",
        "",
        token.strip(),
        flags=re.IGNORECASE,
    ).strip()
    return cleaned or token.strip()


def resolve_skills_from_ai(raw_skills: list[Any], nice_to_have: bool = False) -> list[dict[str, Any]]:
    """Canonically resolves raw AI skills list into standardized platform SkillMention structures."""
    resolved = []
    seen = set()
    for raw in raw_skills:
        if not raw or not isinstance(raw, str):
            continue
        token = _clean_skill_token(raw)
        if not token or token.lower() in seen:
            continue

        matched_item = None
        # 1. Exact match on name or code
        for item in SKILLS_DATA:
            if token.lower() == item["name"].lower() or token.lower() == item["code"].lower():
                matched_item = item
                break
            if any(syn and token.lower() == syn.lower() for syn in item.get("synonyms", [])):
                matched_item = item
                break

        # 2. Substring/word boundary match inside token
        if not matched_item:
            for item in SKILLS_DATA:
                for term in [item["name"]] + item.get("synonyms", []):
                    if term and len(term) >= 3 and re.search(r"\b" + re.escape(term) + r"\b", token, re.IGNORECASE):
                        matched_item = item
                        break
                if matched_item:
                    break

        if matched_item:
            if matched_item["name"].lower() not in seen:
                seen.add(matched_item["name"].lower())
                seen.add(token.lower())
                resolved.append({
                    "name": matched_item["name"],
                    "code": matched_item["code"],
                    "evidence": raw.strip(),
                    "nice_to_have": nice_to_have,
                })
        else:
            seen.add(token.lower())
            clean_code = re.sub(r"[^a-zA-Z0-9_]+", "_", token.lower()).strip("_") or "skill"
            resolved.append({
                "name": token,
                "code": clean_code,
                "evidence": raw.strip(),
                "nice_to_have": nice_to_have,
            })
    return resolved


def parse_need_hybrid(text: str, title: str | None = None, provider: str = "auto") -> dict[str, Any]:
    """Hybrid parser (AI-first with deterministic NLP rules fallback):
    1. If provider != 'rules' and GigaChat is configured, attempt LLM extraction via Sber GigaChat (152-FZ).
    2. If GigaChat extraction succeeds, map fields, canonically resolve skills against SKILLS_DATA,
       fill any missing gaps from deterministic rule-based analysis, and return with parser_source='gigachat'.
    3. If GigaChat is unavailable, fails, times out, or provider == 'rules', fall back cleanly to
       deterministic rule-based parser with parser_source='rule_based'.
    """
    from backend.app.core.llm import llm_client

    # Always compute rule-based parse as baseline / gap-filler (<1ms execution)
    rule_parsed = parse_need(text, title)
    rule_dict = rule_parsed.to_dict()
    rule_dict["parser_source"] = "rule_based"
    rule_dict["ai_available"] = bool(llm_client.is_configured)
    rule_dict["engine_badge"] = "Внутренний NLP-парсер (правила)"

    if provider == "rules" or not llm_client.is_configured:
        return rule_dict

    try:
        ai_res = llm_client.parse_vacancy(text, title, timeout=12.0)
        if not ai_res or not isinstance(ai_res, dict):
            logger.info("GigaChat returned empty response, using rule-based parser fallback.")
            return rule_dict

        ai_skills = resolve_skills_from_ai(ai_res.get("skills", []), False)
        ai_nice = resolve_skills_from_ai(ai_res.get("nice_to_have", []), True)

        final_skills = ai_skills if ai_skills else rule_dict.get("skills", [])
        final_nice = ai_nice if ai_nice else rule_dict.get("nice_to_have", [])

        # Specialization
        spec_val = ai_res.get("specialization")
        valid_specs = {"BACKEND", "FRONTEND", "QA", "DATA_ML", "DEVOPS", "MOBILE"}
        if spec_val and str(spec_val).upper() in valid_specs:
            spec_obj = {
                "value": str(spec_val).upper(),
                "confidence": 0.95,
                "evidence": ["GigaChat AI (семантический анализ роли)"],
            }
        else:
            spec_obj = rule_dict.get("specialization", {"value": None, "confidence": 0.0, "evidence": []})

        # Grade
        grade_val = ai_res.get("grade")
        valid_grades = {"INTERN", "JUNIOR", "MIDDLE", "SENIOR", "LEAD"}
        if grade_val and str(grade_val).upper() in valid_grades:
            grade_obj = {
                "value": str(grade_val).upper(),
                "confidence": 0.95,
                "evidence": ["GigaChat AI (анализ требований к опыту и роли)"],
            }
        else:
            grade_obj = rule_dict.get("grade", {"value": None, "confidence": 0.0, "evidence": []})

        # Work format
        fmt_val = ai_res.get("work_format")
        valid_fmts = {"REMOTE", "HYBRID", "OFFICE"}
        if fmt_val and str(fmt_val).upper() in valid_fmts:
            fmt_obj = {
                "value": str(fmt_val).upper(),
                "confidence": 0.90,
                "evidence": ["GigaChat AI (формат работы)"],
            }
        else:
            fmt_obj = rule_dict.get("work_format", {"value": None, "confidence": 0.0, "evidence": []})

        # City
        city_val = ai_res.get("city")
        if city_val and str(city_val).strip() and str(city_val).strip().lower() != "null":
            city_obj = {
                "value": str(city_val).strip(),
                "confidence": 0.85,
                "evidence": ["GigaChat AI"],
            }
        else:
            city_obj = rule_dict.get("city", {"value": None, "confidence": 0.0, "evidence": []})

        # Salary
        sal_from = ai_res.get("salary_from") or rule_dict.get("salary_from")
        sal_to = ai_res.get("salary_to") or rule_dict.get("salary_to")
        is_gross = ai_res.get("is_gross")
        if is_gross is None:
            is_gross = rule_dict.get("is_gross", False)
        sal_type = "GROSS" if is_gross else (rule_dict.get("salary_type") or "NET")

        exp_years = ai_res.get("experience_years") or rule_dict.get("experience_years")

        return {
            "specialization": spec_obj,
            "grade": grade_obj,
            "work_format": fmt_obj,
            "city": city_obj,
            "skills": final_skills,
            "nice_to_have": final_nice,
            "salary_from": sal_from,
            "salary_to": sal_to,
            "salary_type": sal_type,
            "is_gross": is_gross,
            "salary_evidence": rule_dict.get("salary_evidence") or "GigaChat AI",
            "experience_years": exp_years,
            "specialization_scores": rule_dict.get("specialization_scores", {}),
            "parser_source": "gigachat",
            "ai_available": True,
            "engine_badge": "GigaChat AI (152-ФЗ)",
        }
    except Exception as e:
        logger.warning("GigaChat hybrid parsing failed, falling back to rule parser: %s", e)
        return rule_dict
