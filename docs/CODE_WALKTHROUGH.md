# Руководство по исходному коду платформы FSP-Talent (Code Walkthrough)

Данный документ представляет собой пофайловый путеводитель по исходному коду платформы с описанием ключевых функций, классов и архитектурных связей.

---

## 1. Ядро приложения (`backend/app/core/`)

### `config.py`
- **Класс `Settings` (на базе `pydantic_settings.BaseSettings`):**
  - Считывает переменные окружения из файла `.env` с безопасными дефолтными значениями.
  - Содержит ключи шифрования (`SECRET_KEY`, `ALGORITHM`), настройки срока действия токенов (`ACCESS_TOKEN_EXPIRE_MINUTES = 1440`).
  - Параметры адаптивного тестирования (`CAT_MIN_ITEMS = 12`, `CAT_MAX_ITEMS = 25`, `CAT_TARGET_SE = 0.30`, `MAX_FAMILY_EXPOSURE_RATE = 0.25`).
  - Режим аутентификации `AUTH_PROVIDER` (`"internal"` для локальной разработки и тестов, `"keycloak"` для промышленного OIDC).

### `database.py`
- Создает движок SQLAlchemy (`create_engine`).
- Автоматически адаптируется под используемую СУБД: для SQLite включает аргумент `check_same_thread = False` и пул `StaticPool`, для PostgreSQL настраивает пул соединений.
- Функция-генератор `get_db()`: обеспечивает внедрение зависимостей (Dependency Injection) сессии БД в эндпоинты FastAPI с гарантированным закрытием соединения.

### `security.py`
- Хеширование и валидация паролей: функции `get_password_hash(password)` и `verify_password(plain, hashed)` используют прямой вызов библиотеки `bcrypt`, что исключает проблемы с усечением паролей до 72 байт.
- Выпуск JWT-токенов: `create_access_token(subject, role, email, fsp_id, expires_delta)` формирует подписанный токен со стандартизированным набором утверждений (claims).
- Декодирование токенов: `decode_access_token(token)` валидирует сигнатуру и проверяет срок жизни токена.

---

## 2. Модели базы данных (`backend/app/models/`)

Все 23 сущности объединены в `backend/app/models/__init__.py`:

### `user.py`
- **`User`:** Базовый пользователь платформы. Поля: `id` (UUID), `email` (индексированный unique), `hashed_password`, `role` (`CANDIDATE`, `EMPLOYER`, `ADMIN`), `email_verified`, `is_active`.
- **`Consent`:** Журнал согласий по 152-ФЗ. Поля: `user_id`, `consent_type` (`PERSONAL_DATA`, `PROFILE_DISTRIBUTION`), `version` (`1.0`), `is_given`, `given_at`, `revoked_at`.

### `candidate.py`
- **`CandidateProfile`:** Основной профиль соискателя.
  - Контактные данные: `first_name`, `last_name`, `phone`, `telegram`, `fsp_id`.
  - Статус и грейд: `confirmed_category` (например, `"Backend · Middle"`), `confirmed_specialization`, `confirmed_grade`.
  - Психометрические метрики: `last_theta` (способность $\theta$), `last_se` (погрешность SE), `category_percentile` (перцентиль в категории).
  - Спортивные метрики: `fsp_score` ($0.0 \dots 1.0$), `is_fsp_verified`.
  - Условия поиска: `desired_salary_min`, `work_format` (`REMOTE`, `HYBRID`, `OFFICE`), `city`, `status` (`ACTIVELY_SEARCHING`, `OPEN`, `HIDDEN`).
  - Ограничение по времени: `next_grade_change_available_at` (кулдаун 90 дней).
- **`CandidateSkill`:** Навыки соискателя с указанием источника подтверждения (`confirmation_source`: `CLAIMED`, `RESUME`, `ASSESSMENT`, `FSP`).
- **`FSPAchievement`:** Подтвержденные достижения из реестра ФСП (мероприятие, дисциплина, уровень, результат, разряд).
- **`GradeHistory`:** История прохождения тестирований со сменой грейда.

### `company.py`
- **`Company`:** Профиль компании-работодателя (название, ИНН, описание, сайт, логотип).
- **`EmployerMember`:** Связь пользователей-сотрудников с компанией.
- **`Need`:** Описание потребности в специалисте. Содержит сырой текст (`raw_description`), выделенный стек (`required_skills`), зарплатный бюджет (`salary_budget_min`, `salary_budget_max`) и формат работы.
- **`SelectionSnapshot`:** Снимок поисковой выдачи по потребности. Сохраняет хэш фильтров (`query_filters_hash`) и сериализованный список кандидатов, позволяя работодателю уточнять фильтры и возвращаться назад без потери подборки.
- **`Vacancy`:** Опубликованная вакансия компании.

### `dictionary.py`
- **`Direction`:** Направление (Разработка, Data & ML, Тестирование, Инфраструктура).
- **`Specialization`:** Специализация (Backend, Frontend, QA, Data Scientist и др.).
- **`Grade`:** Грейд (Стажёр, Junior, Middle, Senior) с JSON-списком поведенческих индикаторов.
- **`Category`:** Декартово произведение `Specialization × Grade`.
- **`Skill`:** ИТ-навык с кодом и тегами.
- **`SkillSynonym`:** Таблица соответствий синонимов (`"постгрес"` → `PostgreSQL`).

### `assessment.py`
- **`ItemFamily`:** Параметризованное семейство заданий. Содержит калиброванные параметры IRT ($a_i$, $b_i$), тему (`topic`), формат задания (`CODE_OUTPUT`, `SQL`, `MCQ`), счетчик показов (`exposure_count`) и шаблон YAML.
- **`AssessmentSession`:** Сессия прохождения адаптивного теста соискателем. Отслеживает текущие $\hat{\theta}$, $\text{SE}$, статус и количество отвеченных вопросов.
- **`SessionItem`:** Конкретный экземпляр задания, сгенерированный по `seed`, ответ кандидата, время ответа и флаг правильности.

### `invitation.py`
- **`Invitation`:** Приглашение работодателя кандидату. Поля: `company_id`, `candidate_profile_id`, `need_id`, `status` (`SENT`, `VIEWED`, `ACCEPTED`, `DECLINED`, `WITHDRAWN`, `EXPIRED`), обязательные `salary_from` и `salary_to` в рублях, `message`, `contact_method`, `decline_reason`.
- **`AuditLog`:** Неизменяемый журнал аудита действий с персональными данными (раскрытие контактов, отзывы согласий).

---

## 3. Модули бизнес-логики (`backend/app/modules/`)

### `auth` и `consents`
- `auth/service.py`: функции `register_user()`, `authenticate_user()`.
- `auth/router.py`: эндпоинты `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/verify-email`, `/api/v1/auth/me`.
- `consents/service.py`: функция `give_consent()` (фиксирует согласие), `revoke_consent()` (отзывает согласие и, если отозвано распространение данных, автоматически переводит статус профиля в `HIDDEN`).

### `dictionaries`
- `dictionaries/seeds.py`: функция `seed_all_dictionaries(db)` - наполняет БД 4 направлениями, 6 специализациями, 4 грейдами и **363 навыками** с русско-английскими синонимами.
- `dictionaries/service.py`: функция `search_skills(query)` выполняет быстрый регистронезависимый поиск как по каноническому названию навыка, так и по таблице синонимов.

### `invitations`
- `invitations/fsm.py`: класс `InvitationFSM` валидирует допустимость перехода между статусами. При попытке перехода из терминального состояния выбрасывает `InvalidStateTransitionError`.
- `invitations/service.py`: 
  - `create_invitation()`: проверяет условие `salary_from <= salary_to` и `salary_from > 0`.
  - `accept_invitation()`: переводит статус в `ACCEPTED`, делает запись в `AuditLog` и формирует объект `CandidateDisclosedContacts` с реальными контактами.
  - `decline_invitation()`: фиксирует причину отказа кандидата для последующей аналитики работодателя.

### `matching`
- `matching/ranking.py`: 
  - Функция `filter_pool()`: отсекает нерелевантных кандидатов по категории, бюджету и приватности.
  - Функция `rank_candidates()`: рассчитывает итоговый балл по формуле:
    $$\text{Score} = 0.30 \cdot C + 0.25 \cdot S + 0.10 \cdot E + 0.25 \cdot T + 0.07 \cdot F + 0.03 \cdot A$$
  - Функция `generate_explanation()`: формирует 3–4 понятных текстовых тезиса для карточки кандидата.
- `matching/snapshots.py`: класс `SelectionSnapshotService` сериализует выдачу и сохраняет ее в таблицу `selection_snapshots`.

### `assessment`
- `assessment/irt.py`: математические функции `probability_2pl()`, `fisher_information_2pl()`, `estimate_theta_eap()`, `calculate_se()`.
- `assessment/cat_engine.py`: класс `CATEngine` выполняет отбор следующего вопроса по алгоритму Top-5 Randomesque с контролем лимита экспозиции ($\le 25\%$) и балансом тем.
- `assessment/grade_rules.py`: функция `determine_grade_result()` сопоставляет $\hat{\theta}$ с порогами грейдов, определяет подтверждение/повышение/понижение и устанавливает 90-дневный кулдаун.

### `fsp`
- `fsp/score.py`: функция `calculate_fsp_score()` рассчитывает спортивный рейтинг с учетом уровня турнира, результата, дисциплины и полураспада за 2 года.
- `fsp/adapter.py`: класс `FSPRegistryClient` обращается к микросервису `fsp-mock` по HTTP, а при его недоступности переключается на детерминированный локальный fallback.

---

## 4. Сервис Mock-реестра ФСП (`services/fsp-mock/`)

Автономный микросервис на FastAPI (`main.py`):
- Эндпоинт `/fsp-registry/participants/{fsp_id}/achievements` генерирует реалистичный список соревнований:
  - Чемпионат России по спортивному программированию;
  - Хакатон «Лидеры цифровой трансформации 2026»;
  - Кубок России по спортивному программированию;
  - Региональные первенства.
- Возвращает дисциплины, результаты (Победитель, Призёр), разряды (КМС, Мастер спорта).

---

## 5. Фронтенд-приложение (`frontend/src/`)

- `theme/`: фирменная палитра ФСП (`#FF0053`, `#FC3777`, `#8A83D1`, `#1C1D22`), шрифт Montserrat.
- `components/layout/`:
  - `AppHeader.tsx`: переключатель роли (Кандидат / Работодатель) и ссылка на «Демо для жюри».
  - `CandidateLayout.tsx`: сайдбар кабинета соискателя с индикатором кулдауна пересдачи.
  - `EmployerLayout.tsx`: сайдбар работодателя с квотой офферов против спама.
- `pages/`:
  - `CandidateOnboardingPage.tsx`: ветвящийся опрос и самооценка грейда.
  - `AssessmentPlayerPage.tsx`: адаптивный плеер тестирования с таймером и интерактивным кодом.
  - `CandidateCabinetPage.tsx`: подтвержденная категория, перцентиль, список входящих офферов с обязательной зарплатой в рублях.
  - `EmployerMatchingPage.tsx`: ввод потребности, карточки категорий, ранжированные анонимные кандидаты и модалка отправки оффера с валидацией вилки.
  - `DemoShowcasePage.tsx`: витрина для жюри с демонстрацией 2PL IRT кривых, сквозного сценария и формулы ранжирования.
