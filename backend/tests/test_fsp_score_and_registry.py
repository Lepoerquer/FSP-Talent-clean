"""Unit tests for FSP Score calculation engine, Adapter, and Mock Registry Service."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.modules.fsp.adapter import FSPRegistryClient
from backend.app.modules.fsp.score import (
    calculate_achievement_weight,
    calculate_decay,
    calculate_fsp_score,
    format_fsp_ranking_bullet,
)

mock_path = Path(__file__).resolve().parents[2] / "services" / "fsp-mock" / "main.py"
spec = importlib.util.spec_from_file_location("fsp_mock_service", str(mock_path))
fsp_mock_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fsp_mock_mod)
fsp_mock_app = fsp_mock_mod.app


# ==============================================================================
# 1. FSP SCORE FORMULA AND NORMALIZATION TESTS
# ==============================================================================

def test_candidate_without_fsp_history_receives_zero_and_neutral_badge():
    """Candidate with NO FSP history receives score 0.0 and neutral badge.

    CRITICAL: Never blocks, never penalizes, never errors.
    """
    res = calculate_fsp_score(achievements=[], sport_rank=None)
    assert res["raw_score"] == 0.0
    assert res["normalized_score"] == 0.0
    assert res["badge"] == "Без спортивной истории"
    assert res["has_history"] is False
    assert res["achievements_count"] == 0

    bullet = format_fsp_ranking_bullet(res["normalized_score"], achievements=[])
    assert "нейтральный профиль" in bullet


def test_achievement_weight_calculation():
    """Check formula components: Level * Result * Discipline * Decay.
    Per Q&A: Level (1.0) and Discipline (1.0) are equal, Result separates winner (1.0) from participant (0.2).
    """
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ev_date = datetime(2025, 12, 1, tzinfo=timezone.utc)  # very recent, ~0.08 years

    w = calculate_achievement_weight(
        level="ALL_RUSSIAN",      # 1.0 (all competitions equally valid)
        result="WINNER",           # 1.0
        discipline="Продуктовое программирование",  # 1.0 (all disciplines equally valid)
        event_date=ev_date,
        now=now,
    )
    # Expected: 1.0 * 1.0 * 1.0 * decay(~0.98) ~ 0.97-0.99
    assert 0.95 <= w <= 1.00


def test_qa_disciplines_and_competitions_equality_no_internal_hierarchy():
    """Q&A requirement: 'Ранжировать дисциплины не надо: все соревнования равно важны,
    внутренний рейтинг чемпионат России выше хакатона давать не советуют'.
    """
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ev_date = datetime(2025, 12, 1, tzinfo=timezone.utc)

    # Russian Championship vs Hackathon with same result
    w_champ = calculate_achievement_weight("ALL_RUSSIAN", "WINNER", "Алгоритмическое программирование", ev_date, now)
    w_hack = calculate_achievement_weight("REGIONAL", "WINNER", "Продуктовое программирование", ev_date, now)
    assert w_champ == w_hack  # Exactly equal!

    # Different disciplines with same result and level
    w_algo = calculate_achievement_weight("ALL_RUSSIAN", "PRIZE_WINNER", "Алгоритмическое программирование", ev_date, now)
    w_prod = calculate_achievement_weight("ALL_RUSSIAN", "PRIZE_WINNER", "Продуктовое программирование", ev_date, now)
    w_sec = calculate_achievement_weight("ALL_RUSSIAN", "PRIZE_WINNER", "Робототехника", ev_date, now)
    assert w_algo == w_prod == w_sec


def test_qa_results_differentiate_winner_vs_participant():
    """Q&A requirement: 'Учитывать число соревнований и результативность
    (победитель/призер vs участник отбора), чтобы нельзя было набить профиль одними онлайн-явками'.
    """
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ev_date = datetime(2025, 12, 1, tzinfo=timezone.utc)

    w_winner = calculate_achievement_weight("ALL_RUSSIAN", "WINNER", "Продуктовое программирование", ev_date, now)
    w_part = calculate_achievement_weight("ALL_RUSSIAN", "PARTICIPANT", "Продуктовое программирование", ev_date, now)

    # Winner gets 5x higher weight than mere participant
    assert w_winner >= 4.5 * w_part

    # Profile with 1 win vs profile with 1 attendance
    res_winner = calculate_fsp_score([{"event_name": "ЛЦТ", "level": "ALL_RUSSIAN", "result": "WINNER", "discipline": "Продуктовое", "event_date": ev_date}], now=now)
    res_part = calculate_fsp_score([{"event_name": "ЛЦТ", "level": "ALL_RUSSIAN", "result": "PARTICIPANT", "discipline": "Продуктовое", "event_date": ev_date}], now=now)

    assert res_winner["normalized_score"] > res_part["normalized_score"] * 2
    assert "Победитель" in res_winner["badge"]
    assert "Участник" in res_part["badge"]


def test_sport_category_bonus_and_normalization():
    """Verify log-scale normalization maps to range [0.0, 1.0]."""
    achievements = [
        {
            "event_name": "Чемпионат России по спортивному программированию",
            "level": "ALL_RUSSIAN",
            "result": "WINNER",
            "discipline": "Продуктовое программирование",
            "sport_category": "КМС",
        },
        {
            "event_name": "Хакатон ЛЦТ",
            "level": "ALL_RUSSIAN",
            "result": "PRIZE_WINNER",
            "discipline": "Продуктовое программирование",
            "sport_category": "1 разряд",
        },
    ]

    res = calculate_fsp_score(achievements=achievements, sport_rank="КМС")
    assert 0.0 < res["normalized_score"] <= 1.0
    assert res["badge"] == "Победитель соревнований ФСП"
    assert res["has_history"] is True
    assert res["achievements_count"] == 2

    bullet = format_fsp_ranking_bullet(res["normalized_score"], achievements=achievements, sport_rank="КМС")
    assert "победитель" in bullet.lower() or "призёр" in bullet.lower()
    assert "кмс" in bullet.lower()


def test_decay_reduces_old_achievements():
    """Achievements from 4 years ago have lower decay than recent ones."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    recent_date = datetime(2025, 6, 1, tzinfo=timezone.utc)
    old_date = datetime(2021, 6, 1, tzinfo=timezone.utc)

    d_recent = calculate_decay(recent_date, now)
    d_old = calculate_decay(old_date, now)

    assert d_recent > d_old
    assert d_recent > 0.8
    assert d_old < 0.5


# ==============================================================================
# 2. MOCK FSP REGISTRY SERVICE TESTS
# ==============================================================================

def test_fsp_mock_service_endpoints():
    """Test the standalone mock registry FastAPI service."""
    client = TestClient(fsp_mock_app)

    # 1. Health check
    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    assert resp_health.json()["status"] == "ok"

    # 2. Lookup known athlete FSP-1001 (Winner of Чемпионат России and ЛЦТ)
    resp_1001 = client.get("/fsp-registry/participants/FSP-1001/achievements")
    assert resp_1001.status_code == 200
    data_1001 = resp_1001.json()
    assert data_1001["fsp_id"] == "FSP-1001"
    assert data_1001["current_sport_rank"] == "КМС"
    assert len(data_1001["achievements"]) >= 2

    # Check realistic competitions present
    event_names = [a["event_name"] for a in data_1001["achievements"]]
    assert any("Чемпионат России" in name for name in event_names)
    assert any("Лидеры цифровой трансформации" in name or "ЛЦТ" in name for name in event_names)

    # 3. Lookup known athlete FSP-1002 (Master of sports)
    resp_1002 = client.get("/fsp-registry/participants/FSP-1002/achievements")
    assert resp_1002.status_code == 200
    assert resp_1002.json()["current_sport_rank"] == "Мастер спорта"

    # 4. Lookup synthetic dynamic athlete
    resp_synth = client.get("/fsp-registry/participants/FSP-7777/achievements")
    assert resp_synth.status_code == 200
    assert resp_synth.json()["fsp_id"] == "FSP-7777"

    # 5. Non-existent athlete FSP-NONE returns 404
    resp_404 = client.get("/fsp-registry/participants/FSP-NONE/achievements")
    assert resp_404.status_code == 404
    assert resp_404.json()["detail"]["error_code"] == "FSP_PARTICIPANT_NOT_FOUND"


# ==============================================================================
# 3. FSP CLIENT ADAPTER TESTS
# ==============================================================================

def test_fsp_adapter_fallback():
    """FSP client gracefully falls back to mock dataset if HTTP service is offline."""
    adapter = FSPRegistryClient(base_url="http://invalid-non-existent-host:9999")
    data = adapter.get_participant_achievements_sync("FSP-1001")
    assert data is not None
    assert data["fsp_id"] == "FSP-1001"
    assert data["current_sport_rank"] == "КМС"
