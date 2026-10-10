# Руководство по развертыванию и запуску (Deployment & Run Guide)

В данном руководстве описаны все способы сборки, запуска и проверки работоспособности платформы **FSP-Talent**: как в изолированных контейнерах Docker Compose, так и в режиме быстрой локальной разработки без Docker.

Руководство полностью согласовано с решениями сессии **Q&A от 06.10.2026** (имеющими безусловный приоритет над ТЗ) и ориентировано на аппаратный профиль **стенда жюри**.

---

## 1. Системные требования и профиль стенда жюри

На установочной сессии Q&A были озвучены точные параметры тестового стенда экспертов (п. 41, 172):
- **Оперативная память:** 32–64 ГБ RAM (потребление FSP-Talent менее 1 ГБ RAM);
- **Процессор:** порядка 8 ядер CPU (до 16);
- **GPU (видеокарта):** **ОТСУТСТВУЕТ**;
- **Время развертывания:** менее 60 секунд (холодный старт).

### Поддерживаемые операционные системы:
- **Linux:** Ubuntu 22.04 LTS / 24.04 LTS, Debian 12;
- **macOS:** Apple Silicon / Intel;
- **Windows:** Windows 10/11 с WSL2 или Docker Desktop.

### Программные зависимости (для ручного запуска без Docker):
- Python **3.12+**
- Node.js **18.x** или **20.x**, npm **10.x**
- Git 2.x

---

## 2. Способ 1: Запуск в Docker Compose (Рекомендуется для жюри)

Все сервисы платформы оркестрируются через корневой `Makefile` и `infra/docker-compose.yml`.

> [!NOTE]
> **Аутентификация и интеграция с FSP ID:**  
> Платформа использует встроенную систему аутентификации на JWT и микросервис реестра соревнований ФСП. Архитектура решения предусматривает поддержку OpenID Connect (OIDC), что позволяет при необходимости легко подключить корпоративный Keycloak Федерации (см. `docs/adr/003-auth-and-keycloak-brokering.md`).

### Состав контейнеров:
- `fsp-postgres`: СУБД PostgreSQL 16 с открытым расширением `pgvector` (порт `5432`);
- `fsp-valkey`: высокоскоростной открытый кэш Valkey 7.2 (порт `6379`);
- `fsp-mailpit`: сервер отладочной почты с веб-интерфейсом (порт `8025`);
- `fsp-mock-registry`: микросервис эмуляции спортивного реестра ФСП (порт `8001`);
- `fsp-backend`: модульный монолит FastAPI на Python 3.12 (порт `8000`);
- `fsp-frontend`: клиентский SPA React на базе Nginx (порт `3000`).

### Команды быстрого развертывания:
```bash
# 1. Клонирование репозитория и переход в корень
git clone https://github.com/Lepoerquer/FSP-Talent-clean.git
cd FSP-Talent-clean

# 2. Запуск всех сервисов в фоновом режиме (холодный старт ~30-40 сек)
docker compose -f infra/docker-compose.yml up -d --build

# Либо через Makefile:
# make up

# 3. Проверка статуса запущенных контейнеров (все должны быть Up/Healthy)
docker compose -f infra/docker-compose.yml ps

# 4. Наполнение базы эталонными демонстрационными данными (1000 кандидатов, компании, вакансии)
docker compose -f infra/docker-compose.yml exec backend python ml/synthetic_world.py
# Либо через Makefile:
# make seed
```


### 🔑 Тестовые доступы (Демо-данные)

Для быстрого входа на стенде жюри используйте предустановленные тестовые аккаунты (генерация через `make demo-reset` или `docker compose exec backend python ml/synthetic_world.py`):

| Роль | Имя | Email | Пароль | Описание профиля |
|------|-----|-------|--------|------------------|
| **Кандидат** | Анна Смирнова | `anna.smirnova@fsp-talent.dev` | `password123` | Профиль с историей ФСП, Middle Backend |
| **Кандидат** | Борис Кузнецов | `boris.kuznetsov@fsp-talent.dev` | `password123` | Профиль без участия в ФСП, Middle Backend |
| **Работодатель**| Максим Волков | `employer@fsp-talent.dev` | `password123` | Поиск сотрудников, просмотр и рассылка офферов |

### Доступные веб-интерфейсы:
- **Пользовательский интерфейс платформы:** [http://localhost:3000](http://localhost:3000)
- **Витрина алгоритмов / Экспресс-тест жюри:** [http://localhost:3000/demo](http://localhost:3000/demo)
- **Кабинет кандидата:** [http://localhost:3000/candidate](http://localhost:3000/candidate)
- **Кабинет работодателя:** [http://localhost:3000/employer](http://localhost:3000/employer)
- **Интерактивная спецификация API (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Альтернативная документация ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Эмулятор почты Mailpit (просмотр писем регистрации):** [http://localhost:8025](http://localhost:8025)
- **Эмулятор реестра спортсменов ФСП:** [http://localhost:8001/docs](http://localhost:8001/docs)

---

## 3. Автоматизированная проверка решения жюри

### Шаг 1: Прогон полного набора автоматических тестов (196 тестов)
```bash
docker compose -f infra/docker-compose.yml exec backend pytest tests -v
# Либо локально: pytest backend/tests -v
```
*Ожидаемый результат: 196 passed (100% покрытие ключевой логики, включая CAT IRT, безопасность 152-ФЗ, обратный найм и GigaChat AI).*

### Шаг 2: Проверка психометрического банка заданий на утечки и подсказки
```bash
docker compose -f infra/docker-compose.yml exec backend python ml/validation/bank_quality_check.py
# Либо через Makefile: make bank-check
```
*Проверяет отсутствие подсказок по форме (длина ответов, числа в условии) и разнообразие генерации по seed.*

### Шаг 3: Прогон математической симуляции CAT IRT и валидации подбора
```bash
docker compose -f infra/docker-compose.yml exec backend python ml/validation/cat_sim.py
docker compose -f infra/docker-compose.yml exec backend python ml/validation/matching_eval.py
# Либо через Makefile: make validate
```
*Генерирует воспроизводимые отчеты валидации без использования GPU за 20–30 секунд.*

### Шаг 4: Проверка статуса отечественного AI-ассистента GigaChat
```bash
curl -X GET http://localhost:8000/api/v1/ai/status
```
*Возвращает статус подключения к Sber GigaChat API (`configured: true`, `provider: "gigachat"`), а при отсутствии ключей прозрачно переключается на встроенный офлайн-режим (`offline_fallback`).*

### Шаг 5: Сборка единой книги технической документации в PDF
```bash
make docs-pdf
# Либо напрямую: python scripts/build_docs_pdf.py
```
*Компилирует всю техническую документацию платформы в единую книгу [docs/FSP_Talent_Documentation.pdf](docs/FSP_Talent_Documentation.pdf) с оглавлением и закладками.*

---

## 4. Способ 2: Автономный локальный запуск без Docker (Standalone Dev)

Этот способ полезен при отсутствии установленного Docker.

### Шаг 1: Запуск бэкенда (FastAPI)
```bash
# 1. Установка зависимостей
pip install -r backend/requirements.txt

# 2. Прогон тестов на SQLite in-memory
pytest backend/tests

# 3. Запуск сервера API
uvicorn backend.app.main:app --reload --port 8000
```

### Шаг 2: Запуск эмулятора реестра ФСП
В отдельном окне терминала:
```bash
uvicorn services.fsp_mock.main:app --reload --port 8001
```

### Шаг 3: Запуск клиентской части (React SPA)
В отдельном окне терминала:
```bash
cd frontend
npm install
npm run dev
```
Фронтенд запустится на [http://localhost:3000](http://localhost:3000); запросы `/api` проксируются на бэкенд (`localhost:8000`). Для входа доступны демонстрационные аккаунты из `make demo-reset` (пароль `demo123`).

---

## 5. Регламент при непредвиденных сбоях (Q&A п. 42, 175)

> [!IMPORTANT]
> **Официальный регламент Q&A:**  
> *«После дедлайна идейных изменений в коде быть не должно. Смотрят дату последних коммитов. Переподнять упавший контейнер можно, функциональную идею менять нельзя.»*

Если во время стресс-тестирования контейнер завершил работу:
```bash
# Перезапуск упавшего контейнера
docker compose -f infra/docker-compose.yml restart backend
# Либо полный перезапуск стенда
docker compose -f infra/docker-compose.yml down && docker compose -f infra/docker-compose.yml up -d
```
База данных сохраняется в томе `pgdata` (или локальном файле `fsp_talent.db`), поэтому перезапуск не приводит к потере данных.
