.PHONY: help up down test test-backend lint seed validate validate-matching bank-check demo-reset docs-pdf clean

help:
	@echo "Доступные команды платформы FSP-Talent:"
	@echo "  make up          - Запуск всех сервисов в Docker Compose"
	@echo "  make down        - Остановка сервисов"
	@echo "  make test        - Запуск всех юнит и синтетических тестов"
	@echo "  make lint        - Проверка кода линтерами (ruff, flake8)"
	@echo "  make seed        - Генерация синтетической базы (1000 кандидатов, компании, вакансии)"
	@echo "  make validate    - Полный прогон валидации тестирования и подбора с формированием отчета"
	@echo "  make validate-matching - Только валидация подбора (P@10, nDCG@10 против BM25, абляции)"
	@echo "  make bank-check  - Валидация банка семейств заданий на изоморфность и ключи"
	@echo "  make demo-reset  - Сброс базы данных к эталонному демо-состоянию для жюри"
	@echo "  make docs-pdf    - Сборка единой книги технической документации в формате PDF"

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

test:
	python -m pytest backend/tests -v

test-backend:
	python -m pytest backend/tests -v

lint:
	ruff check backend ml services assessment-bank

seed:
	python ml/synthetic/generator.py

validate:
	python ml/validation/cat_sim.py
	python ml/validation/matching_eval.py

validate-matching:
	python ml/validation/matching_eval.py

bank-check:
	python assessment-bank/validator.py

demo-reset:
	python backend/scripts/demo_reset.py

docs-pdf:
	python scripts/build_docs_pdf.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
