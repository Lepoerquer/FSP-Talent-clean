"""Tests for the need / vacancy text parser (R2-07) and API route prefixes."""

import os
import sys

import pytest

from backend.app.main import app
from backend.app.modules.matching.need_parser import parse_need

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ml", "validation"))
import need_parsing_eval  # noqa: E402


def test_gold_structures_regression():
    gold = need_parsing_eval.load_gold()
    for split in ("dev", "holdout"):
        result = need_parsing_eval.evaluate([g for g in gold if g["set"] == split])
        assert result["core_fields_all_correct"] == 1.0
        assert result["skills"]["recall"] >= 0.95
        assert result["skills"]["precision"] >= 0.85


@pytest.mark.parametrize(
    ("text", "present", "absent"),
    [
        ("Пишем на Django и MongoDB, зарплата 200 тыс. руб.", {"Django", "MongoDB"}, {"Go (Golang)", "Ruby"}),
        ("Нужен JavaScript и React", {"JavaScript", "React"}, {"Java"}),
        ("Сервисы на питоне, очереди в кафке", {"Python", "Apache Kafka"}, set()),
    ],
)
def test_skill_extraction(text, present, absent):
    names = set(parse_need(text).required_skill_names)
    assert present <= names
    assert not (absent & names)


def test_nice_to_have_header_and_inline_marker():
    parsed = parse_need("Требования:\n— Python\nБудет плюсом:\n— Docker\nЖелательно знание Redis.", "Python-разработчик")
    assert parsed.required_skill_names == ["Python"]
    assert {s.name for s in parsed.nice_to_have} == {"Docker", "Redis"}


def test_grade_format_city_salary():
    parsed = parse_need("Опыт от 6 лет. Офис в Петербурге. Зарплата от 150 до 200 тыс. руб.", "Python-разработчик")
    assert parsed.grade.value == "SENIOR"
    assert (parsed.work_format.value, parsed.city.value) == ("OFFICE", "Санкт-Петербург")
    assert (parsed.salary_from, parsed.salary_to) == (150000, 200000)
    assert parse_need("Можно работать удалённо или в офисе в Казани.").work_format.value == "REMOTE"


def test_module_routes_are_mounted_once_under_api_v1(client):
    paths = set(app.openapi()["paths"].keys())
    assert not any(p.startswith("/api/v1/api/") for p in paths)
    assert {"/api/v1/needs", "/api/v1/needs/parse", "/api/v1/invitations", "/api/v1/me/fsp/link"} <= paths
    res = client.post("/api/v1/needs/parse", json={"title": "Middle Go-разработчик", "text": "Стек: Go, PostgreSQL. Удалённо."})
    assert res.status_code == 200
    body = res.json()
    assert body["specialization"]["value"] == "BACKEND" and body["grade"]["value"] == "MIDDLE"
