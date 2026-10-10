"""GigaChat AI Integration Service for FSP-Talent Platform.

Complies with 152-FZ (no cross-border personal data transfers).
Supports automatic OAuth token management, structured vacancy parsing,
smart recruiter pitch generation, and technical interview questions generation.
"""

import json
import logging
import re
import time
import uuid
from typing import Any

import httpx

from backend.app.core.config import settings

logger = logging.getLogger("fsp.llm")


class GigaChatClient:
    """Async/Sync client for Sber GigaChat API with in-memory token caching."""

    OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    COMPLETIONS_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    def __init__(
        self,
        credentials: str | None = None,
        scope: str = "GIGACHAT_API_PERS",
        model: str = "GigaChat",
        verify_ssl: bool = False,
    ):
        self.credentials = credentials or settings.GIGACHAT_CREDENTIALS
        self.scope = scope or settings.GIGACHAT_SCOPE
        self.model = model or settings.GIGACHAT_MODEL
        self.verify_ssl = verify_ssl

        self._cached_token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def is_configured(self) -> bool:
        """Checks if GigaChat credentials are provided."""
        return bool(self.credentials and self.credentials.strip())

    def get_access_token(self) -> str | None:
        """Retrieves or refreshes the OAuth access token (valid for 30 minutes)."""
        if not self.is_configured:
            return None

        # Return cached token if valid (leave 60s buffer)
        now = time.time()
        if self._cached_token and now < (self._token_expires_at - 60):
            return self._cached_token

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self.credentials}",
        }
        data = {"scope": self.scope}

        for attempt in range(2):
            try:
                with httpx.Client(verify=self.verify_ssl, timeout=25.0) as client:
                    res = client.post(self.OAUTH_URL, headers=headers, data=data)
                    if res.status_code == 200:
                        payload = res.json()
                        self._cached_token = payload.get("access_token")
                        # expires_at is given in milliseconds Unix timestamp
                        exp_ms = payload.get("expires_at", (now + 1800) * 1000)
                        self._token_expires_at = exp_ms / 1000.0
                        logger.info("Successfully refreshed GigaChat OAuth token")
                        return self._cached_token
                    else:
                        logger.error(
                            "GigaChat OAuth failed with status %d: %s",
                            res.status_code,
                            res.text,
                        )
                        return None
            except Exception as e:
                logger.warning("Attempt %d: GigaChat OAuth exception: %s", attempt + 1, e)
                if attempt == 0:
                    time.sleep(1.0)
                    continue
                return None
        return None

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 1500,
        timeout: float = 25.0,
    ) -> str | None:
        """Sends a completion request to GigaChat."""
        token = self.get_access_token()
        if not token:
            return None

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            with httpx.Client(verify=self.verify_ssl, timeout=timeout) as client:
                res = client.post(self.COMPLETIONS_URL, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content")
                else:
                    logger.warning("GigaChat completion failed: %d - %s", res.status_code, res.text)
                    return None
        except Exception as e:
            logger.warning("Exception during GigaChat completion: %s", e)
            return None

    def parse_vacancy(self, text: str, title: str | None = None, timeout: float = 12.0) -> dict[str, Any] | None:
        """Extracts structured entities from vacancy text via GigaChat."""
        if not self.is_configured:
            return None

        prompt = f"""Ты — специализированный парсер IT-вакансий платформы FSP-Talent.
Проанализируй текст и верни СТРОГО один валидный JSON-объект без пояснений и без markdown-разметки:
{{
  "specialization": "BACKEND" | "FRONTEND" | "QA" | "DATA_ML" | "DEVOPS" | "MOBILE",
  "grade": "JUNIOR" | "MIDDLE" | "SENIOR" | "LEAD",
  "work_format": "REMOTE" | "HYBRID" | "OFFICE",
  "city": "город если указан, иначе null",
  "salary_from": число или null,
  "salary_to": число или null,
  "is_gross": true | false,
  "experience_years": число или null,
  "skills": ["названия технологий без лишних слов, например: Python, Docker, PostgreSQL"],
  "nice_to_have": ["плюс1", "плюс2"]
}}

Заголовок: {title or '—'}
Текст вакансии:
{text}
"""
        messages = [
            {"role": "system", "content": "Ты экспертная языковая модель для структурирования требований IT-вакансий. Возвращай исключительно чистый JSON."},
            {"role": "user", "content": prompt},
        ]

        raw = self.chat_completion(messages, temperature=0.1, timeout=timeout)
        if not raw:
            return None

        # Clean possible markdown formatting
        cleaned = re.sub(r"^```json\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            parsed = json.loads(cleaned)
            return parsed
        except Exception as e:
            logger.warning("Failed to parse GigaChat JSON response: %s (Raw: %s)", e, raw)
            return None

    def generate_candidate_pitch(
        self,
        need_title: str,
        need_grade: str,
        need_spec: str,
        candidate_grade: str,
        matched_skills: list[str],
        fsp_badge: str | None = None,
        score_percent: int = 90,
    ) -> str | None:
        """Generates an explainable recruiter summary why this candidate is a strong fit."""
        prompt = f"""Сформируй ёмкое, профессиональное и дружелюбное резюме (2-3 предложения) для рекрутера:
Вакансия: {need_title} (Специализация: {need_spec}, Грейд: {need_grade})
Кандидат: Подтвержденный грейд {candidate_grade}, соответствие профиля {score_percent}%.
Подтвержденные ключевые навыки: {', '.join(matched_skills) if matched_skills else 'базовый стек'}.
Достижения в спортивном программировании ФСП: {fsp_badge or 'не указаны'}.

Подчеркни сильные стороны и почему соискателя стоит пригласить на техническое интервью."""

        messages = [
            {"role": "system", "content": "Ты AI-ассистент рекрутера в платформе FSP-Talent. Пиши аргументированно, убедительно и коротко."},
            {"role": "user", "content": prompt},
        ]
        return self.chat_completion(messages, temperature=0.3, max_tokens=300)

    def generate_interview_questions(
        self,
        specialization: str,
        grade: str,
        skills: list[str],
        count: int = 3,
    ) -> list[dict[str, str]] | None:
        """Generates technical interview questions based on candidate stack and grade."""
        prompt = f"""Сгенерируй {count} прикладных практических вопроса для технического собеседования:
Специализация: {specialization}
Грейд: {grade}
Стек кандидата: {', '.join(skills[:6]) if skills else 'общий стек'}

Верни СТРОГО JSON-массив объектов вида:
[
  {{
    "topic": "Тема вопроса (например, Многопоточность)",
    "question": "Текст вопроса с практической ситуацией",
    "expected_answer": "Ключевые тезисы, которые должен упомянуть кандидат"
  }}
]
"""
        messages = [
            {"role": "system", "content": "Ты старший технический интервьюер. Задавай глубокие практические вопросы, проверяющие реальный инженерный опыт."},
            {"role": "user", "content": prompt},
        ]
        raw = self.chat_completion(messages, temperature=0.2, max_tokens=1000)
        if not raw:
            return None

        cleaned = re.sub(r"^```json\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
            if isinstance(data, dict) and "questions" in data:
                items = data["questions"]
            elif isinstance(data, list):
                items = data
            else:
                return None

            normalized = []
            for it in items:
                if isinstance(it, dict):
                    ans = it.get("expected_answer", "")
                    if isinstance(ans, list):
                        ans = "; ".join(str(x) for x in ans)
                    normalized.append({
                        "topic": str(it.get("topic", "Технический вопрос")),
                        "question": str(it.get("question", "")),
                        "expected_answer": str(ans),
                    })
                elif isinstance(it, str):
                    normalized.append({
                        "topic": "Технический вопрос",
                        "question": it,
                        "expected_answer": "Развернутый ответ кандидата",
                    })
            return normalized if normalized else None
        except Exception as e:
            logger.warning("Failed to parse interview questions JSON: %s", e)
            return None

    def generate_career_advice(
        self,
        specialization: str,
        grade: str,
        skills: list[str],
        experience_years: float | None = None,
        fsp_verified: bool = False,
        percentile: int | None = None,
    ) -> dict[str, Any] | None:
        """Generates personal career advice, next-grade roadmap, and FSP discipline recommendations."""
        prompt = f"""Ты — персональный AI-карьерный консультант Федерации спортивного программирования (ФСП).
Проанализируй профиль кандидата и дай экспертные рекомендации.
Специализация: {specialization}
Грейд: {grade}
Стек: {', '.join(skills[:8]) if skills else 'базовый'}
Стаж: {experience_years or 'не указан'} лет
Перцентиль теста: {percentile or '—'}
Статус ФСП: {'Верифицирован' if fsp_verified else 'Не привязан'}

Верни СТРОГО один валидный JSON-объект без пояснений:
{{
  "overall_summary": "Ёмкая оценка текущего уровня кандидата на рынке (1-2 предложения)",
  "strengths": ["Ключевое преимущество 1", "Ключевое преимущество 2", "Ключевое преимущество 3"],
  "growth_points": ["Технология или навык для перехода на следующий грейд 1", "Навык 2", "Навык 3"],
  "recommended_fsp_discipline": "Рекомендованная дисциплина (например, Программирование алгоритмическое)",
  "fsp_boost_tip": "Почему участие в этой дисциплине ФСП усилит позицию соискателя и даст буст в подборе (1-2 предложения)",
  "career_roadmap": [
    {{"step": "Этап 1: Углубление стека", "timeframe": "1-2 месяца", "action": "Изучение целевых технологий"}},
    {{"step": "Этап 2: Соревнования ФСП", "timeframe": "2-4 месяца", "action": "Участие в турнирах ФСП"}},
    {{"step": "Этап 3: Повышение грейда", "timeframe": "4-6 месяцев", "action": "Сдача квалификационного IRT-теста"}}
  ]
}}
"""
        messages = [
            {"role": "system", "content": "Ты ведущий IT-ментор и консультант Федерации спортивного программирования. Отвечай строго валидным JSON."},
            {"role": "user", "content": prompt},
        ]
        raw = self.chat_completion(messages, temperature=0.2, max_tokens=800)
        if not raw:
            return None
        cleaned = re.sub(r"^```json\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except Exception as e:
            logger.warning("Failed to parse career advice JSON: %s", e)
            return None


# Global singleton instance
llm_client = GigaChatClient()
