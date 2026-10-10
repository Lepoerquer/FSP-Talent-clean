# Справочник API платформы FSP-Talent (API Reference)

Все методы платформы сгруппированы под префиксом `/api/v1` и строго документированы по спецификации OpenAPI 3.1.

Интерактивная документация доступна при запущенном бэкенде:
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **JSON Спецификация:** [docs/openapi/openapi.json](openapi/openapi.json)

### Правила доступа

Доступ определяется JWT-токеном (`Authorization: Bearer <TOKEN>`), а не идентификаторами в запросе:

| Кто | Что доступно |
|---|---|
| Без входа | регистрация и вход, справочники, список открытых вакансий `GET /needs`, разбор текста вакансии, экспресс-тест (`POST /assessments/demo/start` или `is_express: true`), публичная проверка PDF-профиля `GET /verify/candidates/{id}` |
| Кандидат | только свой профиль, PDF, грейд, ФСП, свои приглашения и отклики, регулярные задания; квалификационный тест только для своего профиля |
| Работодатель | только своя компания: потребности, подборки и снимки, банк кандидатов, приглашения и отклики, задания и ответы на них, ATS |

Чужой объект отвечает `404`, действие не своей роли - `403`, запрос без токена - `401`. Контакты кандидата работодатель получает только по принятому приглашению или по отклику самого кандидата (ТЗ 2.2).

---

## 1. Аутентификация и пользователи (`/api/v1/auth`)

### Регистрация кандидата или работодателя
```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "ivan.petrov@example.com",
    "password": "SecurePassword123!",
    "role": "CANDIDATE"
  }'
```
**Ответ `201 Created`:**
```json
{
  "user_id": "8f4e2b02-53b1-4f12-a1e4-399a9cfb1821",
  "email": "ivan.petrov@example.com",
  "role": "CANDIDATE",
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "email_verified": false
}
```

### Вход в систему (Логин)
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "ivan.petrov@example.com",
    "password": "SecurePassword123!"
  }'
```

---

## 2. Согласия по 152-ФЗ (`/api/v1/consents`)

### Предоставление согласия на распространение профиля
```bash
curl -X POST "http://localhost:8000/api/v1/consents/give" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "consent_type": "PROFILE_DISTRIBUTION",
    "version": "1.0"
  }'
```

### Отзыв согласия (автоматически исключает профиль из поиска работодателей)
```bash
curl -X POST "http://localhost:8000/api/v1/consents/revoke" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "consent_type": "PROFILE_DISTRIBUTION"
  }'
```

---

## 3. Справочники (`/api/v1/dictionaries`)

### Поиск навыков с поддержкой русских и английских синонимов
```bash
curl -X GET "http://localhost:8000/api/v1/dictionaries/skills?q=постгрес"
```
**Ответ `200 OK`:**
```json
[
  {
    "id": "3b29c91f-0b92-491c-8b83-e02cf3091910",
    "code": "postgresql",
    "name": "PostgreSQL",
    "category_tags": ["database", "sql", "backend"]
  }
]
```

### Обзор направлений и специализаций
```bash
curl -X GET "http://localhost:8000/api/v1/dictionaries/overview"
```

---

## 4. Адаптивное тестирование CAT IRT (`/api/v1/assessments`)

### Старт сессии адаптивного тестирования
```bash
curl -X POST "http://localhost:8000/api/v1/assessments/start" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "specialization_code": "backend",
    "self_assessed_grade": "MIDDLE",
    "primary_language": "Python"
  }'
```
**Ответ `201 Created`:**
```json
{
  "session_id": "761c3ab1-52d3-4f93-84eb-c93d9392e219",
  "status": "IN_PROGRESS",
  "current_theta": 0.5,
  "current_se": 1.0,
  "items_count": 0
}
```

### Получение следующего динамического изоморфного вопроса
```bash
curl -X GET "http://localhost:8000/api/v1/assessments/761c3ab1-52d3-4f93-84eb-c93d9392e219/next" \
  -H "Authorization: Bearer <TOKEN>"
```

### Отправка ответа кандидата (пересчет $\theta$ и $\text{SE}$)
```bash
curl -X POST "http://localhost:8000/api/v1/assessments/761c3ab1-52d3-4f93-84eb-c93d9392e219/answer" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "item_family_id": "019d...",
    "seed": 4219,
    "user_response": "2",
    "response_time_seconds": 24.5
  }'
```

### Завершение тестирования и расчет грейда
```bash
curl -X POST "http://localhost:8000/api/v1/assessments/761c3ab1-52d3-4f93-84eb-c93d9392e219/finish" \
  -H "Authorization: Bearer <TOKEN>"
```
**Ответ `200 OK` (Грейд подтвержден):**
```json
{
  "session_id": "761c3ab1-52d3-4f93-84eb-c93d9392e219",
  "final_theta": 0.84,
  "final_se": 0.28,
  "is_confirmed": true,
  "confirmed_grade": "MIDDLE",
  "confirmed_category": "Backend · Middle",
  "percentile": 86,
  "recommendation": "GRADE_CONFIRMED",
  "next_grade_change_available_at": "2027-01-05T12:00:00Z"
}
```

### Просмотр статуса категории, истории попыток и кулдауна (`/api/v1/me/grade`)
```bash
curl -X GET "http://localhost:8000/api/v1/me/grade?candidate_profile_id=cand-001" \
  -H "Authorization: Bearer <TOKEN>"
```

---

## 5. Интеграция с Федерацией спортивного программирования (`/api/v1/me/fsp`)

### Привязка FSP ID и верификация достижений
```bash
curl -X POST "http://localhost:8000/api/v1/me/fsp/link" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "fsp_id": "FSP-1001",
    "consent_given": true
  }'
```
**Ответ `200 OK`:**
```json
{
  "fsp_id": "FSP-1001",
  "is_fsp_verified": true,
  "fsp_score": 0.82,
  "badge": "Победитель соревнований ФСП",
  "description": "Призёр Чемпионата России по спортивному программированию (Продуктовое программирование). Спортивный разряд: КМС.",
  "sport_rank": "КМС",
  "achievements": [
    {
      "id": "ach-001",
      "event_name": "Чемпионат России по спортивному программированию 2025",
      "discipline": "Продуктовое программирование",
      "level": "ALL_RUSSIAN",
      "result": "PRIZE_WINNER",
      "calculated_weight": 0.80
    }
  ]
}
```

### Проверка статуса FSP ID
```bash
curl -X GET "http://localhost:8000/api/v1/me/fsp/status" \
  -H "Authorization: Bearer <TOKEN>"
```

---

## 6. Подбор кандидатов работодателем (`/api/v1/needs`)

### Гибридный интеллектуальный разбор вакансии из текста (`/api/v1/needs/parse`)
```bash
curl -X POST "http://localhost:8000/api/v1/needs/parse" \
  -H "Authorization: Bearer <EMPLOYER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Ищем сильного Middle Python бэкендера в финтех. Стек: FastAPI, PostgreSQL, Docker, Redis. Зарплата от 250 000 до 300 000 руб на руки, удаленка.",
    "title": "Backend Developer",
    "provider": "auto"
  }'
```
**Ответ `200 OK` (AI-First GigaChat со встроенным обогащением по реестру ФСП и фолбэком):**
```json
{
  "specialization": {"value": "BACKEND", "confidence": 0.95, "evidence": ["GigaChat AI (семантический анализ роли)"]},
  "grade": {"value": "MIDDLE", "confidence": 0.95, "evidence": ["GigaChat AI (анализ требований к опыту и роли)"]},
  "work_format": {"value": "REMOTE", "confidence": 0.90, "evidence": ["GigaChat AI (формат работы)"]},
  "city": {"value": null, "confidence": 0.0, "evidence": []},
  "skills": [
    {"name": "Python", "code": "python", "evidence": "Python", "nice_to_have": false},
    {"name": "FastAPI", "code": "fastapi", "evidence": "FastAPI", "nice_to_have": false},
    {"name": "PostgreSQL", "code": "postgresql", "evidence": "PostgreSQL", "nice_to_have": false},
    {"name": "Docker", "code": "docker", "evidence": "Docker", "nice_to_have": false},
    {"name": "Redis", "code": "redis", "evidence": "Redis", "nice_to_have": false}
  ],
  "nice_to_have": [],
  "salary_from": 250000,
  "salary_to": 300000,
  "salary_type": "NET",
  "is_gross": false,
  "salary_evidence": "GigaChat AI",
  "experience_years": 3,
  "parser_source": "gigachat",
  "ai_available": true,
  "engine_badge": "GigaChat AI (152-ФЗ)"
}
```
**Параметры `provider`:**
- `"auto"` (по умолчанию) — AI-First разбор через GigaChat API (152-ФЗ) со 100% бесшовным фолбэком на локальный NLP при задержке сети/таймауте;
- `"gigachat"` — обработка через нейросеть GigaChat;
- `"rules"` — мгновенный локальный NLP-парсер с морфологической лемматизацией (без обращения к внешним LLM).


### Создание потребности в специалисте
```bash
curl -X POST "http://localhost:8000/api/v1/needs" \
  -H "Authorization: Bearer <EMPLOYER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "company_id": "comp-001",
    "title": "Backend Python Middle Разработчик",
    "raw_description": "Финтех проект, разработка транзакционного API.",
    "target_specialization": "Backend",
    "target_grade": "MIDDLE",
    "required_skills": ["Python", "FastAPI", "PostgreSQL"],
    "salary_budget_min": 250000,
    "salary_budget_max": 320000,
    "work_format": "REMOTE"
  }'
```

### Получение ранжированной объяснимой подборки кандидатов
```bash
curl -X GET "http://localhost:8000/api/v1/needs/comp-001/recommendations" \
  -H "Authorization: Bearer <EMPLOYER_TOKEN>"
```
**Ответ `200 OK` (Фрагмент выдачи с учетом статуса грейда):**
```json
{
  "need_id": "comp-001",
  "recommended_categories": [
    {
      "category_code": "BACKEND_MIDDLE",
      "display_name": "Backend · Middle",
      "match_rate": 1.0,
      "candidates_count": 84
    }
  ],
  "ranked_candidates": [
    {
      "candidate_id": "cand-001",
      "display_label": "Кандидат #RU-8841",
      "category": "Backend · Middle",
      "is_grade_confirmed": true,
      "grade_badge": "Грейд подтвержден",
      "score": 0.892,
      "test_percentile": 87,
      "has_fsp_achievements": true,
      "contacts_hidden": true,
      "explanation_points": [
        "Категория Backend · Middle - точное совпадение",
        "Стек: 3 из 3 навыков подтверждены независимым тестированием",
        "Результат теста: 87-й перцентиль в категории",
        "ФСП: Призёр чемпионата России по спортивному программированию"
      ]
    },
    {
      "candidate_id": "cand-005",
      "display_label": "Кандидат #RU-3102",
      "category": "Backend · Middle",
      "is_grade_confirmed": false,
      "grade_badge": "Грейд не подтверждён",
      "score": 0.624,
      "test_percentile": 42,
      "has_fsp_achievements": false,
      "contacts_hidden": true,
      "explanation_points": [
        "Категория: статус 'Грейд не подтверждён' (понижен в выдаче)",
        "Стек: 2 из 3 указаны в резюме",
        "Тест: 42-й перцентиль (рекомендуется дополнительная проверка)"
      ]
    }
  ]
}
```

---

## 7. Приглашения и раскрытие контактов (`/api/v1/invitations`)

### Отправка приглашения (Обязательная зарплатная вилка в рублях)
```bash
curl -X POST "http://localhost:8000/api/v1/invitations" \
  -H "Authorization: Bearer <EMPLOYER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_profile_id": "cand-001",
    "need_id": "need-001",
    "salary_from": 280000,
    "salary_to": 320000,
    "salary_type": "NET",
    "message": "Здравствуйте! Ваш результат теста и стек отлично подходят нашему проекту.",
    "contact_method": "TELEGRAM"
  }'
```

### Принятие оффера кандидатом (Раскрытие контактов)
```bash
curl -X POST "http://localhost:8000/api/v1/invitations/inv-001/accept" \
  -H "Authorization: Bearer <CANDIDATE_TOKEN>"
```
**Ответ `200 OK`:**
```json
{
  "id": "inv-001",
  "status": "ACCEPTED",
  "contacts_disclosed": true,
  "candidate_contacts": {
    "first_name": "Анна",
    "last_name": "Смирнова",
    "email": "anna.smirnova@fsp-talent.dev",
    "phone": "+7 999 123-45-67",
    "telegram": "@anna_smirnova_dev"
  }
}
```

### Отклонение оффера кандидатом с указанием причины
```bash
curl -X POST "http://localhost:8000/api/v1/invitations/inv-001/decline" \
  -H "Authorization: Bearer <CANDIDATE_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "decline_reason": "SALARY"
  }'
```

### Отзыв доступа к контактам кандидатом
```bash
curl -X POST "http://localhost:8000/api/v1/invitations/inv-001/revoke-contacts" \
  -H "Authorization: Bearer <CANDIDATE_TOKEN>"
```
Принятое приглашение переходит в статус `CONTACTS_REVOKED`: работодатель снова видит карточку без контактов.

### Отклик кандидата на вакансию
```bash
curl -X POST "http://localhost:8000/api/v1/needs/need-001/apply" \
  -H "Authorization: Bearer <CANDIDATE_TOKEN>"
```
Создаёт запись со статусом `APPLIED` в `GET /invitations/company` работодателя; контакты кандидата видны сразу (ТЗ 2.2).

---

## 8. Стандартизированный экспорт PDF с QR-кодом и публичная верификация (`/api/v1/candidates/{id}/pdf`, `/api/v1/verify/candidates/{id}`)

### Скачивание PDF-профиля
```bash
curl -X GET "http://localhost:8000/api/v1/candidates/cand-001/pdf" \
  -H "Authorization: Bearer <TOKEN>" \
  --output "fsp_verified_candidate_cand-001.pdf"
```
Возвращает стандартизированный PDF-профиль (без контактов) самому кандидату и работодателям; профиль, скрытый кандидатом, работодателю не отдаётся. В правом верхнем углу документа размещается QR-код, ведущий на публичную страницу онлайн-верификации (`/verify/candidates/:id`).

### Публичная онлайн-проверка кандидата по QR-коду (152-ФЗ)
Эндпоинт доступен **без авторизации** для мгновенной валидации подлинности резюме организаторами турниров или работодателями:
```bash
curl "http://localhost:8000/api/v1/verify/candidates/cand-001"
```
**Ответ `200 OK`:**
```json
{
  "candidate_id": "cand-001",
  "name": "Иван П.",
  "confirmed_category": "Backend · Middle",
  "grade_status": "CONFIRMED",
  "is_fsp_verified": true,
  "category_percentile": 87,
  "confirmed_specialization": "BACKEND",
  "confirmed_grade": "MIDDLE",
  "declared_grade": "MIDDLE",
  "city": "Москва",
  "work_format": "REMOTE",
  "experience_years": 3.5,
  "confirmed_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
  "fsp_achievements_count": 2,
  "fsp_disciplines": ["Продуктовое программирование"],
  "verification_hash": "84B6F1C02D1A9E37",
  "checked_at": "2026-10-10T14:30:00Z"
}
```
*Особенности безопасности:* В соответствии со 152-ФЗ персональные каналы связи (телефон, email, telegram) не отдаются в открытый доступ. Защиту подлинности обеспечивает 16-символьный SHA-256 цифровой штамп `verification_hash`. Адрес в QR задаётся переменной окружения `PUBLIC_BASE_URL`.

---

## 9. Дополнительные (заявленные) специализации (`/api/v1/me/specializations`)

Категорию и грейд присваивает только тест; дополнительные специализации - заявление кандидата (`is_confirmed: false`) и в подборе не участвуют.

### Получение списка заявленных специализаций
```bash
curl -X GET "http://localhost:8000/api/v1/me/specializations" \
  -H "Authorization: Bearer <CANDIDATE_TOKEN>"
```

### Добавление дополнительной специализации к профилю
```bash
curl -X POST "http://localhost:8000/api/v1/me/specializations" \
  -H "Authorization: Bearer <CANDIDATE_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "specialization": "DATA_ML",
    "grade": "MIDDLE"
  }'
```

---

## 10. Регулярные задания работодателей (`/api/v1/challenges`, `/api/v1/employer/challenges`, `/api/v1/candidates/me/challenges`)

### Публикация задания работодателем
```bash
curl -X POST "http://localhost:8000/api/v1/challenges" \
  -H "Authorization: Bearer <EMPLOYER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Оптимизация SQL-запроса в высоконагруженной БД",
    "task_description": "Переписать аналитический запрос с window-функциями для снижения времени выполнения с 12с до 150мс.",
    "specialization": "BACKEND",
    "target_grade": "MIDDLE",
    "task_type": "OPEN_ENDED",
    "time_limit_minutes": 60
  }'
```

### Задания для кандидата и ответ на задание
```bash
curl "http://localhost:8000/api/v1/candidates/me/challenges" -H "Authorization: Bearer <CANDIDATE_TOKEN>"
curl -X POST "http://localhost:8000/api/v1/challenges/<challenge_id>/submit" \
  -H "Authorization: Bearer <CANDIDATE_TOKEN>" -H "Content-Type: application/json" \
  -d '{"solution_text": "Индекс (tenant_id, status, created_at DESC): равенства впереди, сортировка последней."}'
```
Сначала идут задания по специализации кандидата; у отвеченных заданий есть `my_answer`. Повторная отправка заменяет ответ и обновляет актуальность профиля.

### Задания компании и ответы кандидатов
```bash
curl "http://localhost:8000/api/v1/employer/challenges" -H "Authorization: Bearer <EMPLOYER_TOKEN>"
curl "http://localhost:8000/api/v1/employer/challenges/<challenge_id>/submissions" -H "Authorization: Bearer <EMPLOYER_TOKEN>"
```
Ответы приходят с именем и категорией кандидата, без контактов: открытые задания оценивает работодатель (Q&A, строка 2).

---

## 11. Интеграция с ATS (`/api/v1/ats`)

### Синхронизация вакансий из внешней ATS (Huntflow / Potok / E-Staff)
```bash
curl -X POST "http://localhost:8000/api/v1/ats/vacancies/sync" \
  -H "Authorization: Bearer <EMPLOYER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "ats_system": "HUNTFLOW",
    "external_vacancy_id": "huntflow-req-4091",
    "title": "Senior Golang Developer",
    "specialization": "BACKEND",
    "grade_min": "SENIOR",
    "salary_min": 300000,
    "salary_max": 420000
  }'
```

### Экспорт кандидата в формате ATS
```bash
curl -X GET "http://localhost:8000/api/v1/ats/candidates/cand-001/export?format=json" \
  -H "Authorization: Bearer <EMPLOYER_TOKEN>"
```

---

## 12. Внутренний чат платформы (`/api/v1/chat`)

### Отправка сообщения
```bash
curl -X POST "http://localhost:8000/api/v1/chat/messages" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "receiver_id": "user-employer-001",
    "message": "Добрый день! Готов обсудить технические детали проекта."
  }'
```

### Получение истории сообщений
```bash
curl -X GET "http://localhost:8000/api/v1/chat/messages?with_user_id=user-employer-001" \
  -H "Authorization: Bearer <TOKEN>"
```

---

## 13. Отечественный AI-ассистент GigaChat (`/api/v1/ai`, `/api/v1/needs/ai`) - 152-ФЗ

### 13.1 Проверка статуса ИИ (`GET /api/v1/ai/status`)
Возвращает информацию о подключенном провайдере (GigaChat API) и состоянии авторизации токенов:
```bash
curl -X GET "http://localhost:8000/api/v1/ai/status"
```
**Пример ответа (200 OK):**
```json
{
  "provider": "gigachat",
  "is_configured": true,
  "model": "GigaChat",
  "scope": "GIGACHAT_API_PERS",
  "status": "ready"
}
```

### 13.2 Генерация AI-питча кандидата для работодателя (`POST /api/v1/needs/ai/pitch`)
Генерирует ёмкое аргументированное резюме соискателя на базе подтверждённого адаптивным тестом грейда, навыков и спортивных достижений ФСП:
```bash
curl -X POST "http://localhost:8000/api/v1/needs/ai/pitch" \
  -H "Content-Type: application/json" \
  -d '{
    "need_id": "need-backend-001",
    "candidate_id": "cand-001",
    "score_percent": 94
  }'
```
**Пример ответа (200 OK):**
```json
{
  "candidate_id": "cand-001",
  "pitch": "Опытный Senior Python Backend-разработчик с подтвержденным грейдом и соответствием 94%. Подтвержден глубокий стек FastAPI, PostgreSQL и Docker. Финалист Чемпионата России по спортивному программированию ФСП с 1 взрослым разрядом, демонстрирующий сильные алгоритмические навыки.",
  "provider": "gigachat"
}
```

### 13.3 Генерация вопросов к техническому собеседованию (`POST /api/v1/needs/ai/interview-questions`)
Создает прикладные практические задачи и критерии оценки ответа под конкретную специализацию и стек соискателя:
```bash
curl -X POST "http://localhost:8000/api/v1/needs/ai/interview-questions" \
  -H "Content-Type: application/json" \
  -d '{
    "specialization": "BACKEND",
    "grade": "MIDDLE",
    "skills": ["Python", "FastAPI", "PostgreSQL"],
    "count": 2
  }'
```
**Пример ответа (200 OK):**
```json
{
  "specialization": "BACKEND",
  "grade": "MIDDLE",
  "questions": [
    {
      "topic": "Оптимизация запросов PostgreSQL",
      "question": "Сервис под нагрузкой начал деградировать на аналитических запросах. Каков ваш алгоритм поиска узких мест и оптимизации?",
      "expected_answer": "Использование EXPLAIN ANALYZE; проверка индексов и последовательных сканов; профилирование через pg_stat_statements; настройка пула соединений."
    },
    {
      "topic": "Асинхронность и конкурентность в FastAPI",
      "question": "В эндпоинте FastAPI требуется вызвать синхронную CPU-bound функцию. Как предотвратить блокировку Event Loop?",
      "expected_answer": "Использование run_in_threadpool из starlette.concurrency или вынос задачи в фоновые воркеры Celery / ProcessPoolExecutor."
    }
  ],
  "provider": "gigachat"
}
```

### 13.4 Персональный AI-Карьерный консультант ФСП (`POST /api/v1/needs/ai/career-advice`)
Анализирует профиль соискателя (текущий грейд, стек подтвержденных навыков, результаты адаптивного теста IRT CAT, спортивные достижения ФСП) и генерирует персональную дорожную карту роста до целевого грейда, точки роста и рекомендации по дисциплинам Федерации спортивного программирования:
```bash
curl -X POST "http://localhost:8000/api/v1/needs/ai/career-advice" \
  -H "Content-Type: application/json" \
  -d '{
    "specialization": "BACKEND",
    "grade": "MIDDLE",
    "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
    "experience_years": 3.0,
    "fsp_verified": true,
    "percentile": 87
  }'
```
**Пример ответа (200 OK):**
```json
{
  "specialization": "BACKEND",
  "grade": "MIDDLE",
  "overall_summary": "Уверенный специалист уровня Middle с отличным подтвержденным стеком в Backend-разработке и соревновательным бэкграундом ФСП (87-й перцентиль). Для перехода на грейд Senior рекомендуется усилить архитектурные компетенции распределенных систем и отказоустойчивости.",
  "strengths": [
    "Глубокое знание асинхронного стека Python и реляционных баз данных",
    "Высокая скорость алгоритмического мышления, подтвержденная участием в турнирах ФСП",
    "Высокий перцентиль адаптивного тестирования CAT (топ 13% в категории)"
  ],
  "growth_points": [
    "Проектирование highload-архитектур и шардирование баз данных",
    "Паттерны распределенных транзакций (Saga, Outbox pattern)",
    "Опыт менторинга и декомпозиции сложных эпиков"
  ],
  "recommended_fsp_discipline": "Продуктовое программирование",
  "fsp_boost_tip": "Участие в дисциплине 'Продуктовое программирование' позволит прокачать навыки быстрой командной архитектурной проработки сервисов за ограниченное время, что напрямую ускорит переход на грейд Senior.",
  "career_roadmap": [
    {
      "step": "Шаг 1: Углубление в системный дизайн и распределенные очереди",
      "timeframe": "1-2 месяца",
      "action": "Освоить продвинутые сценарии Kafka/RabbitMQ, изучить распределенный трейсинг (OpenTelemetry) и паттерны идемпотентности."
    },
    {
      "step": "Шаг 2: Участие в хакатонах и турнирах ФСП",
      "timeframe": "2-4 месяца",
      "action": "Принять участие в региональном этапе Чемпионата России ФСП в дисциплине 'Продуктовое программирование' в роли тимлида."
    },
    {
      "step": "Шаг 3: Сдача сертификации на Senior",
      "timeframe": "4-6 месяцев",
      "action": "Пройти повторное адаптивное тестирование платформы FSP-Talent на категорию Backend · Senior."
    }
  ],
  "provider": "gigachat"
}
```
