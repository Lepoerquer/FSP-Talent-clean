"""Parameterized generators for QA Engineering item families.

All generators use stochastic parameterization and build_options from families.base
to guarantee >= 30 distinct question stems across 50 seeds and top answer share <= 35%.

Options of one item are parallel: the same form and about the same length, and the correct one
never repeats numbers or names from the stem. Why the answer is correct goes to `explanation`,
otherwise "pick the longest, most detailed option" answers the item without any knowledge.
"""

import random

from families.base import ItemRenderResult, build_options


# ==============================================================================
# 1. QA_BOUNDARY_VALUE_ANALYSIS (Grade: INTERN, b: -1.40)
# ==============================================================================

def generate_qa_boundary_value_analysis(seed: int) -> ItemRenderResult:
    """Family: QA_BOUNDARY_VALUE_ANALYSIS.

    Tests Boundary Value Analysis (BVA) for integer range inputs.
    """
    rng = random.Random(seed)
    domains = [
        ("возраст соискателя", "лет", 14, 25, 60, 80),
        ("размер скидки по промокоду", "%", 1, 10, 40, 90),
        ("длина пароля учетной записи", "символов", 6, 12, 30, 64),
        ("число участников в команде", "чел.", 2, 5, 15, 30),
        ("вес посылки для доставки", "кг", 1, 5, 25, 50),
        ("минимальная партия товара", "шт.", 5, 20, 100, 500),
        ("срок действия депозита", "мес.", 3, 6, 24, 60),
        ("объем оперативной памяти", "ГБ", 2, 8, 32, 128),
    ]
    name, unit, min_lo, min_hi, max_lo, max_hi = rng.choice(domains)
    min_v = rng.randint(min_lo, min_hi)
    max_v = rng.randint(max_lo, max_hi)
    tc_id = rng.randint(101, 999)
    is_three_point = rng.choice([False, True])

    if not is_three_point:
        question_text = (
            f"[Тест-кейс #{tc_id}] В форме валидируется поле «{name}». Согласно ТЗ, допустимым является "
            f"целочисленный диапазон от {min_v} до {max_v} {unit} включительно. "
            f"Какой набор значений представляет собой строгий классический 2-точечный анализ граничных значений (BVA)?"
        )
        correct_text = f"{min_v - 1}, {min_v}, {max_v}, {max_v + 1}"
        d1 = f"{min_v}, {(min_v + max_v) // 2}, {max_v}"
        d2 = f"{min_v - 2}, {min_v - 1}, {max_v + 1}, {max_v + 2}"
        d3 = f"{min_v + 1}, {(min_v + max_v) // 2}, {max_v - 1}"
        d4 = f"{min_v}, {min_v + 1}, {max_v - 1}, {max_v}"
        explanation = (
            f"2-точечный BVA для отрезка [{min_v}, {max_v}] проверяет саму границу и первое недопустимое значение "
            f"за ее пределами: для нижней границы ({min_v - 1}, {min_v}), для верхней ({max_v}, {max_v + 1})."
        )
    else:
        question_text = (
            f"[Тест-кейс #{tc_id}] Для поля «{name}» (валидный диапазон [{min_v}; {max_v}] {unit}) применяется "
            f"3-точечный анализ граничных значений (3-point BVA / Robust Boundary Testing). "
            f"Какая группа значений полностью покрывает нижнюю границу {min_v} {unit}?"
        )
        correct_text = f"{min_v - 1}, {min_v}, {min_v + 1}"
        d1 = f"{min_v - 2}, {min_v}, {min_v + 2}"
        d2 = f"{min_v}, {min_v + 1}, {min_v + 2}"
        d3 = f"{min_v - 2}, {min_v - 1}, {min_v}"
        d4 = f"{min_v}, {min_v + 1}, {max_v}"
        explanation = (
            f"В 3-точечной модели BVA граница {min_v} тестируется тремя значениями: "
            f"ровно на границе ({min_v}), чуть ниже ({min_v - 1}) и чуть выше ({min_v + 1})."
        )

    options, key = build_options(rng, correct_text, [d1, d2, d3, d4])
    return ItemRenderResult(
        family_code="QA_BOUNDARY_VALUE_ANALYSIS",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


# ==============================================================================
# 2. QA_EQUIVALENCE_PARTITIONING (Grade: JUNIOR, b: -0.70)
# ==============================================================================

def generate_qa_equivalence_partitioning(seed: int) -> ItemRenderResult:
    """Family: QA_EQUIVALENCE_PARTITIONING.

    Tests equivalence class partitioning principles for lengths, formats, and ranges.
    """
    rng = random.Random(seed)
    exp_len = rng.randint(4, 12)
    tc_id = rng.randint(100, 999)
    field_type = rng.choice([
        f"PIN-код карты (строго {exp_len} цифр)",
        f"SMS-код подтверждения (строго {exp_len} цифр)",
        f"идентификатор договора (строго {exp_len} знаков)",
        f"артикул номенклатуры (строго {exp_len} символов)",
        f"номер пропуска сотрудника (строго {exp_len} цифр)",
        f"номер бонусного счёта (строго {exp_len} цифр)",
    ])
    strategy = rng.choice(["range_class", "symbol_classes"])

    if strategy == "range_class":
        name, lo, hi = rng.choice([
            ("возраст участника", rng.randint(14, 18), rng.randint(60, 80)),
            ("количество товара в заказе", rng.randint(1, 5), rng.randint(50, 200)),
            ("срок кредита в месяцах", rng.randint(3, 12), rng.randint(36, 120)),
            ("размер команды", rng.randint(2, 4), rng.randint(8, 20)),
            ("оценка в баллах", rng.randint(1, 10), rng.randint(90, 100)),
        ])

        def pick(cls: str, avoid: set[int]) -> int:
            while True:
                if cls == "below":
                    value = lo - rng.randint(1, 30)
                elif cls == "valid":
                    value = rng.randint(lo + 1, hi - 1)
                else:
                    value = hi + rng.randint(1, 60)
                if value not in avoid:
                    return value

        tested_cls = rng.choice(["below", "valid", "above"])
        tested = pick(tested_cls, set())
        same = pick(tested_cls, {tested})
        other = [c for c in ("below", "valid", "above") if c != tested_cls]
        wrong = [pick(other[0], {tested, same}), pick(other[1], {tested, same})]
        # The nearest boundary on the other side is the typical mistake: it belongs to a neighbouring class
        boundary = {"below": lo, "valid": rng.choice([lo - 1, hi + 1]), "above": hi}[tested_cls]
        question_text = (
            f"[Задача тестирования #{tc_id}] Поле «{name}» принимает целые значения от {lo} до {hi} включительно. "
            f"Один тест-кейс уже проверяет значение {tested}. Какое значение относится к тому же классу "
            f"эквивалентности и поэтому не требует отдельного теста?"
        )
        correct_text = str(same)
        d1, d2, d3 = str(wrong[0]), str(wrong[1]), str(boundary)
        d4 = str(pick(other[0], {tested, same, wrong[0]}))
        explanation = (
            f"Классы: меньше {lo} (невалидный), от {lo} до {hi} (валидный), больше {hi} (невалидный). "
            f"Значения {tested} и {same} из одного класса, второй тест на этот класс избыточен."
        )
    else:
        sample_valid = "".join(str(rng.randint(1, 9)) for _ in range(exp_len))
        question_text = (
            f"[Задача тестирования #{tc_id}] Поле «{field_type}» принимает только цифровые символы длины {exp_len}. "
            f"Тестировщик анализирует разбиение на классы эквивалентности по типу символов в строке. "
            f"Какой набор тестовых данных обеспечивает полное покрытие валидного и ключевых невалидных классов?"
        )
        other_valid = "".join(str(rng.randint(1, 9)) for _ in range(exp_len))
        correct_text = f"Цифры '{sample_valid}'; латиница; спецсимволы; пробелы"
        d1 = f"Цифры '{sample_valid}'; цифры '{other_valid}'; латиница; кириллица"
        d2 = "Пустая строка; один пробел; два пробела; табуляция"
        d3 = f"Цифры '{sample_valid}'; латиница; кириллица; латиница с кириллицей"
        d4 = f"Цифры '{sample_valid}'; цифры '{other_valid}'; цифры с ведущим нулём"
        explanation = (
            "Классы эквивалентности по типам символов включают валидный класс (цифры) и репрезентативные "
            "невалидные классы: буквы, специальные символы/знаки пунктуации и пробельные символы."
        )

    options, key = build_options(rng, correct_text, [d1, d2, d3, d4])
    return ItemRenderResult(
        family_code="QA_EQUIVALENCE_PARTITIONING",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


# ==============================================================================
# 3. QA_BUG_SEVERITY_PRIORITY (Grade: JUNIOR, b: -0.40)
# ==============================================================================

def generate_qa_bug_severity_priority(seed: int) -> ItemRenderResult:
    """Family: QA_BUG_SEVERITY_PRIORITY.

    Tests distinction between Severity and Priority across various business contexts.
    """
    rng = random.Random(seed)
    category = rng.choice(["high_sev_low_prio", "low_sev_high_prio", "high_sev_high_prio", "low_sev_low_prio"])
    bug_id = rng.randint(1000, 9999)
    users_pct = rng.choice(["0.005%", "0.01%", "0.02%"])

    if category == "high_sev_low_prio":
        desc = (
            f"В архивном отчете за прошлые годы при вводе даты ранее 1900 года процесс сервера падает с критической "
            f"ошибкой 500 Crash. Данной архивной выгрузкой пользуется менее {users_pct} клиентов раз в год."
        )
        correct_text = "High Severity, Low Priority"
        d1 = "Low Severity, Low Priority"
        d2 = "High Severity, High Priority"
        d3 = "Low Severity, High Priority"
    elif category == "low_sev_high_prio":
        desc = (
            "На главной странице федерального сервиса в логотипе бренда и главном баннере допущена грубая опечатка, "
            "но все функции оформления заявок и платежей работают безупречно."
        )
        correct_text = "Low Severity, High Priority"
        d1 = "High Severity, High Priority"
        d2 = "Low Severity, Low Priority"
        d3 = "High Severity, Low Priority"
    elif category == "high_sev_high_prio":
        desc = (
            "Кнопка 'Подтвердить заказ' в корзине блокируется и выбрасывает ошибку 500 для всех пользователей, "
            "полностью останавливая продажи платформы."
        )
        correct_text = "High Severity, High Priority"
        d1 = "High Severity, Low Priority"
        d2 = "Low Severity, High Priority"
        d3 = "Low Severity, Low Priority"
    else:  # low_sev_low_prio
        desc = (
            "Во внутреннем техническом окне 'О программе' служебной админки копирайт указывает 2024 год вместо 2025. "
            "Окно доступно только дежурным администраторам."
        )
        correct_text = "Low Severity, Low Priority"
        d1 = "High Severity, Low Priority"
        d2 = "Low Severity, High Priority"
        d3 = "High Severity, High Priority"

    distractors = [d for d in [d1, d2, d3] if d != correct_text]
    options, key = build_options(rng, correct_text, distractors)
    question_text = (
        f"[Дефект BUG-{bug_id}] В баг-трекере зарегистрирован отчет:\n\n"
        f"«{desc}»\n\n"
        f"Определите корректное соотношение серьезности (Severity) и приоритета исправления (Priority):"
    )
    explanation = (
        "Severity оценивает степень разрушительности технического воздействия на систему, "
        "а Priority определяет срочность исправления бага для бизнеса и репутации продукта."
    )

    return ItemRenderResult(
        family_code="QA_BUG_SEVERITY_PRIORITY",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


# ==============================================================================
# 4. QA_API_MOCK_VS_STUB (Grade: JUNIOR, b: -0.20)
# ==============================================================================

def generate_qa_api_mock_vs_stub(seed: int) -> ItemRenderResult:
    """Family: QA_API_MOCK_VS_STUB.

    Tests difference between Test Doubles (Mock, Stub, Spy, Fake, Dummy) in Martin Fowler terminology.
    """
    rng = random.Random(seed)
    tc_id = rng.randint(200, 999)
    term_choice = rng.choice(["mock", "stub", "spy", "fake", "dummy"])

    services = [
        ("платежным шлюзом банка", "process_payment", f"суммой {rng.randint(1000, 9000)} руб."),
        ("сервисом SMS-шлюза", "send_sms", f"кодом {rng.randint(100000, 999999)}"),
        ("сервисом фискальных чеков", "create_receipt", f"номером чека #{rng.randint(1000, 5000)}"),
        ("почтовым сервером рассылок", "send_invite", "email-адресом кандидата"),
        ("внешней системой ЕГРЮЛ", "fetch_inn_data", f"ИНН {rng.randint(1000000000, 9999999999)}"),
    ]
    service_name, method_name, param_desc = rng.choice(services)

    if term_choice == "mock":
        question_text = (
            f"[Автотест #{tc_id}] В модульном тесте интеграции с {service_name} требуется верифицировать поведение: "
            f"проверить, что метод `{method_name}` был вызван ровно 1 раз с корректным {param_desc}. "
            f"Какой тип тестового дублера (Test Double по классификации Мартина Фаулера) решает эту задачу?"
        )
    elif term_choice == "stub":
        question_text = (
            f"[Автотест #{tc_id}] Тестируется оформление заказа. При обращении к {service_name} тесту требуется "
            f"всегда получать стабильный ответ с успешным статусом, при этом подсчет количества вызовов "
            f"и верификация параметров вызова в данном тесте не проводятся. Что это за тестовый дублер?"
        )
    elif term_choice == "spy":
        question_text = (
            f"[Автотест #{tc_id}] QA-инженер оборачивает компонент взаимодействия с {service_name}, "
            f"чтобы перехватывать и протоколировать историю вызовов `{method_name}` для последующих assertions "
            f"в конце тестового сценария. Какой это тип тестового дублера?"
        )
    elif term_choice == "fake":
        question_text = (
            f"[Автотест #{tc_id}] Для быстрого локального запуска автотестов репозитория тяжелая СУБД "
            f"заменяется на in-memory словарь или SQLite, которые имеют рабочую логику сохранения, "
            f"но непригодны для продакшна. Какой это тип дублера?"
        )
    else:  # dummy
        question_text = (
            f"[Автотест #{tc_id}] В метод создания сессии тестирования требуется передать объект настроек логирования, "
            f"но сам тестовый сценарий никогда не обращается к логам. Объект передается только чтобы не было ошибки компиляции/сигнатуры. "
            f"Что это за тестовый дублер?"
        )

    doubles = {"mock": "Mock", "stub": "Stub", "spy": "Spy", "fake": "Fake", "dummy": "Dummy"}
    others = [name for code, name in doubles.items() if code != term_choice]
    options, key = build_options(rng, doubles[term_choice], rng.sample(others, 3))
    explanation = (
        "Классификация тестовых дублеров: Dummy — пустышка для компиляции; Stub — поставщик готовых ответов; "
        "Spy — перехватчик истории вызовов; Mock — верификатор ожидаемого поведения; Fake — рабочая упрощенная реализация."
    )

    return ItemRenderResult(
        family_code="QA_API_MOCK_VS_STUB",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


# ==============================================================================
# 5. QA_TEST_PYRAMID (Grade: MIDDLE, b: 0.30)
# ==============================================================================

def generate_qa_test_pyramid(seed: int) -> ItemRenderResult:
    """Family: QA_TEST_PYRAMID.

    Tests Mike Cohn's Test Automation Pyramid layers, flakiness, and speed tradeoffs.
    """
    rng = random.Random(seed)
    suite_id = rng.randint(100, 999)
    total_tests = rng.randint(200, 1500)
    target_layer = rng.choice(["Unit", "Integration", "E2E", "Manual"])

    if target_layer == "Unit":
        question_text = (
            f"[Пирамида тестирования #{suite_id}] В проекте на {total_tests} автотестов формируется стратегия автоматизации. "
            f"Какой уровень тестов должен составлять самое широкое основание пирамиды Майка Кона благодаря "
            f"наивысшей скорости прогона (миллисекунды), полной изоляции и минимальной стоимости поддержки?"
        )
        correct_text = "Модульные тесты (Unit)"
        d1 = "Сквозные UI-тесты (E2E)"
        d2 = "Тесты безопасности (DAST)"
        d3 = "Приёмочные тесты (UAT)"
    elif target_layer == "E2E":
        question_text = (
            f"[Пирамида тестирования #{suite_id}] В проекте на {total_tests} автотестов анализируются затраты на CI. "
            f"Какой слой автоматизации находится на самой вершине пирамиды, требует наибольших ресурсов на разработку, "
            f"выполняется дольше всего и наиболее подвержен эффекту нестабильности (Flakiness)?"
        )
        correct_text = "Сквозные UI-тесты в браузере (E2E)"
        d1 = "Модульные тесты функций и классов (Unit)"
        d2 = "Контрактные тесты REST API"
        d3 = "Статический анализ типов и линтеры"
    elif target_layer == "Integration":
        question_text = (
            f"[Пирамида тестирования #{suite_id}] В пайплайне на {total_tests} автотестов выделяется средний слой пирамиды. "
            f"Какая ключевая задача возлагается на интеграционные тесты (Integration / Service Tests)?"
        )
        correct_text = "Проверка совместной работы модулей: сервис + БД + кэш"
        d1 = "Проверка отдельных чистых функций без внешних зависимостей"
        d2 = "Пиксельное сравнение вёрстки страниц (Visual Regression)"
        d3 = "Нагрузочное тестирование кластера под пиковым трафиком"
    else:  # Manual
        question_text = (
            f"[Пирамида тестирования #{suite_id}] В релизном цикле на {total_tests} тестов определяется роль ручного тестирования. "
            f"Какая активность направлена на выявление дефектов в неочевидных пользовательских путях за счет интуиции инженера?"
        )
        correct_text = "Исследовательское тестирование"
        d1 = "Нагрузочные автотесты на k6"
        d2 = "Замер покрытия кода (coverage)"
        d3 = "Сквозные автотесты на Playwright"

    options, key = build_options(rng, correct_text, [d1, d2, d3])
    explanation = (
        "Пирамида тестирования предписывает широкое основание быстрых Unit тестов (до 70%), "
        "средний слой интеграционных проверок (до 20%) и тонкую вершину сквозных E2E UI проверок (до 10%)."
    )

    return ItemRenderResult(
        family_code="QA_TEST_PYRAMID",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


# ==============================================================================
# 6. QA_API_STATUS_CODES (Grade: JUNIOR, b: -0.50)
# ==============================================================================

def generate_qa_api_status_codes(seed: int) -> ItemRenderResult:
    """Family: QA_API_STATUS_CODES.

    Tests REST API HTTP status codes differentiation (401 vs 403 vs 422 vs 409 vs 404 vs 429).
    """
    rng = random.Random(seed)
    req_id = f"req-{rng.randint(1000, 9999)}"
    order_id = rng.randint(100, 999)
    scenarios = [
        ("auth_missing", f"[{req_id}] Запрос к защищенному эндпоинту `/api/v1/candidates/{order_id}/pdf` без заголовка Authorization.",
         "401 Unauthorized",
         "403 Forbidden", "400 Bad Request", "404 Not Found"),
        ("forbidden_role", f"[{req_id}] Кандидат с валидным JWT пытается удалить карточку работодателя `DELETE /api/v1/companies/{order_id}`.",
         "403 Forbidden",
         "401 Unauthorized", "405 Method Not Allowed", "400 Bad Request"),
        ("validation_schema", f"[{req_id}] В `POST /api/v1/needs` передан валидный JSON, но `salary_budget_max` содержит отрицательное число.",
         "422 Unprocessable Entity",
         "400 Bad Request", "500 Internal Server Error", "403 Forbidden"),
        ("conflict_duplicate", f"[{req_id}] Попытка зарегистрировать пользователя с email 'candidate_{order_id}@mail.ru', который уже существует в базе.",
         "409 Conflict",
         "422 Unprocessable Entity", "400 Bad Request", "403 Forbidden"),
        ("rate_limit", f"[{req_id}] Клиент отправил {rng.randint(150, 500)} запросов в секунду к API поиска, превысив лимит безопасности.",
         "429 Too Many Requests",
         "503 Service Unavailable", "403 Forbidden", "400 Bad Request"),
        ("method_not_allowed", f"[{req_id}] Отправлен запрос методом DELETE на эндпоинт `GET /api/v1/dictionaries/categories`.",
         "405 Method Not Allowed",
         "404 Not Found", "400 Bad Request", "422 Unprocessable Entity"),
    ]
    _, desc, correct_val, d1, d2, d3 = rng.choice(scenarios)

    options, key = build_options(rng, correct_val, [d1, d2, d3])
    question_text = (
        f"Тестируется обработка ошибок REST API согласно спецификации RFC 9110:\n\n"
        f"«{desc}»\n\n"
        f"Какой HTTP-статус должен вернуть сервер?"
    )
    explanation = (
        "Семантика HTTP-статусов: 401 — требуется аутентификация; 403 — отказ в авторизации прав; "
        "409 — конфликт уникальности; 422 — ошибка валидации полей схемы; 429 — превышение рейт-лимита."
    )

    return ItemRenderResult(
        family_code="QA_API_STATUS_CODES",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


# ==============================================================================
# 7. QA_PERFORMANCE_TESTING (Grade: MIDDLE, b: 0.50)
# ==============================================================================

def generate_qa_performance_testing(seed: int) -> ItemRenderResult:
    """Family: QA_PERFORMANCE_TESTING.

    Tests types of non-functional performance testing (Load, Stress, Soak, Spike, Capacity).
    """
    rng = random.Random(seed)
    p_type = rng.choice(["Stress", "Spike", "Soak", "Load", "Capacity"])
    rps_val = rng.randint(400, 4500)
    hours_val = rng.choice([24, 48, 72])
    test_id = rng.randint(100, 999)

    if p_type == "Stress":
        question_text = (
            f"[Нагрузочный сценарий #{test_id}] Сервис нагружается потоком {rps_val * 3} RPS, существенно превышающим "
            f"паспортную пиковую мощность, чтобы определить точку разрушения (Breaking Point) и проверить процесс восстановления. "
            f"Какой это вид тестирования производительности?"
        )
        correct_val = "Stress Testing"
        d1 = "Load Testing"
        d2 = "Soak Testing"
        d3 = "Volume Testing"
    elif p_type == "Spike":
        question_text = (
            f"[Нагрузочный сценарий #{test_id}] Моделируется резкий мгновенный скачок нагрузки со 100 до {rps_val} RPS "
            f"за 4 секунды (имитация старта турнира ФСП) с последующим быстрым спадом до базового уровня. "
            f"Как называется этот сценарий тестирования?"
        )
        correct_val = "Spike Testing"
        d1 = "Soak Testing"
        d2 = "Capacity Testing"
        d3 = "Smoke Testing"
    elif p_type == "Soak":
        question_text = (
            f"[Нагрузочный сценарий #{test_id}] Платформа непрерывно тестируется под умеренной нагрузкой {rps_val} RPS "
            f"на протяжении {hours_val} часов подряд для выявления медленных утечек памяти (Memory Leaks) и пулов соединений. "
            f"Какой это вид тестирования?"
        )
        correct_val = "Soak Testing"
        d1 = "Stress Testing"
        d2 = "Spike Testing"
        d3 = "Smoke Testing"
    elif p_type == "Load":
        question_text = (
            f"[Нагрузочный сценарий #{test_id}] Инженер подает штатную расчетную нагрузку ({rps_val} RPS в час пик) "
            f"для подтверждения выполнения нормативов SLA (время отклика p95 < 200 мс). Какой это вид тестирования?"
        )
        correct_val = "Load Testing"
        d1 = "Stress Testing"
        d2 = "Spike Testing"
        d3 = "Fuzz Testing"
    else:  # Capacity
        question_text = (
            f"[Нагрузочный сценарий #{test_id}] Нагрузка ступенчато повышается от 100 до {rps_val * 2} RPS шагами по 150 RPS, "
            f"чтобы точно определить максимальную пропускную способность текущей инфраструктуры до начала деградации latency. "
            f"Какая цель преследуется в тесте?"
        )
        correct_val = "Capacity Testing"
        d1 = "Smoke Testing"
        d2 = "Spike Testing"
        d3 = "Soak Testing"

    options, key = build_options(rng, correct_val, [d1, d2, d3])
    explanation = (
        f"Здесь описан вид {correct_val}. "
        "Load — штатная нагрузка; Stress — сверх нормы до точки отказа; Spike — кратковременные пики; Soak — длительный прогон."
    )

    return ItemRenderResult(
        family_code="QA_PERFORMANCE_TESTING",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


# ==============================================================================
# 8. QA_SMOKE_SANITY (Grade: INTERN, b: -1.30)
# ==============================================================================

def generate_qa_smoke_sanity(seed: int) -> ItemRenderResult:
    """Family: QA_SMOKE_SANITY.

    Tests difference between Smoke, Sanity, and Regression testing strategies.
    """
    rng = random.Random(seed)
    term = rng.choice(["Smoke", "Sanity", "Regression", "Retesting", "Acceptance"])
    build_id = f"v{rng.randint(1, 5)}.{rng.randint(0, 9)}.{rng.randint(1, 99)}"
    task_id = f"TASK-{rng.randint(1000, 9999)}"

    systems = [
        ("платежного шлюза", f"хотфикс {task_id} в расчете комиссии валютных переводов"),
        ("интернет-магазина", f"хотфикс {task_id} в алгоритме применения промокода"),
        ("логистического сервиса", f"хотфикс {task_id} в геокодировании адреса доставки"),
        ("платформы FSP-Talent", f"хотфикс {task_id} в генерации стандартизированного PDF"),
        ("сервиса турниров ФСП", f"хотфикс {task_id} в подсчете FSP-score за соревнования"),
    ]
    sys_name, fix_desc = rng.choice(systems)

    if term == "Smoke":
        question_text = (
            f"[Релизная сборка {build_id}] После сборки билда сервиса {sys_name} запускается минимальный "
            f"набор критических проверок (Happy Path), подтверждающий, что ключевые сервисы стартуют и базовый флоу работает. "
            f"При падении хотя бы одного теста билд немедленно бракуется. Как называется этот этап?"
        )
        correct_val = "Smoke Testing"
        d1 = "Sanity Testing"
        d2 = "Regression Testing"
        d3 = "Re-testing"
    elif term == "Sanity":
        question_text = (
            f"[Релизная сборка {build_id}] Разработчики передали в QA {fix_desc}. "
            f"Инженер точечно глубоко проверяет именно исправленный модуль и его непосредственные зависимости, "
            f"чтобы оперативно подтвердить исправление бага. Как называется такая проверка?"
        )
        correct_val = "Sanity Testing"
        d1 = "Smoke Testing"
        d2 = "Regression Testing"
        d3 = "Re-testing"
    elif term == "Regression":
        question_text = (
            f"[Релизная сборка {build_id}] В сервис {sys_name} был добавлен новый модуль. Перед выпуском релиза "
            f"тестировщики выполняют проверку, чтобы убедиться, что новые изменения не нарушили работу старого функционала. "
            f"Как называется этот процесс?"
        )
        correct_val = "Regression Testing"
        d1 = "Smoke Testing"
        d2 = "Sanity Testing"
        d3 = "Exploratory Testing"
    elif term == "Retesting":
        question_text = (
            f"[Релизная сборка {build_id}] Тестировщик ранее завел баг-репорт по ошибке {task_id}. "
            f"После фикса разработчиком инженер запускает именно те шаги воспроизведения, которые приводили к падению, "
            f"чтобы убедиться, что дефект устранен. Как называется этот целенаправленный прогон?"
        )
        correct_val = "Re-testing"
        d1 = "Smoke Testing"
        d2 = "Sanity Testing"
        d3 = "Regression Testing"
    else:  # Acceptance
        question_text = (
            f"[Релизная сборка {build_id}] Финальный этап перед вводом сервиса {sys_name} в промышленную эксплуатацию: "
            f"проверяется соответствие системы бизнес-требованиям заказчика и сценариям конечных пользователей. "
            f"Какой это вид тестирования?"
        )
        correct_val = "Acceptance Testing"
        d1 = "Smoke Testing"
        d2 = "Stress Testing"
        d3 = "Exploratory Testing"

    options, key = build_options(rng, correct_val, [d1, d2, d3])
    explanation = (
        "Smoke тестирование проверяет систему 'в ширину' (shallow & wide), Sanity проверяет конкретные изменения 'в глубину' "
        "(deep & narrow), а Regression проверяет отсутствие побочных поломок в нетронутых модулях."
    )

    return ItemRenderResult(
        family_code="QA_SMOKE_SANITY",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


# ==============================================================================
# 9. QA_LOAD_TESTING_METRICS (Grade: SENIOR, b: 1.40)
# ==============================================================================

def generate_qa_load_testing_metrics(seed: int) -> ItemRenderResult:
    """Family: QA_LOAD_TESTING_METRICS.

    Tests deep interpretation of load testing metrics: percentiles (p95, p99),
    throughput, concurrency, thread pools, saturation, and latency degradation.
    Target grade: SENIOR (difficulty b in [1.2, 1.8]).
    """
    rng = random.Random(seed)
    p95 = rng.randint(180, 350)
    p99 = rng.randint(1200, 4500)
    avg = rng.randint(45, 95)
    rps = rng.randint(800, 3500)
    err_rate = rng.choice([0.02, 0.05, 0.1, 0.01])
    report_id = rng.randint(1000, 9999)

    # The two Little's law scenarios have numeric answers, so no single answer text dominates the family
    scenario = rng.choice([
        "latency_percentile_skew", "threadpool_saturation", "connection_leak", "littles_law_users", "littles_law_rps",
    ])

    if scenario == "latency_percentile_skew":
        question_text = (
            f"[Отчет #{report_id}] Нагрузочный тест под нагрузкой {rps} RPS показал метрики:\n"
            f"- Среднее время отклика (Average latency): {avg} мс\n"
            f"- Медиана (p50): {avg - 10} мс\n"
            f"- 95-й процентиль (p95): {p95} мс\n"
            f"- 99-й процентиль (p99): {p99} мс\n"
            f"- Доля ошибок HTTP 5xx: {err_rate}%\n\n"
            f"Как Senior QA инженер должен интерпретировать разрыв между Average ({avg} мс) и p99 ({p99} мс)?"
        )
        correct_val = "Длинный хвост задержек: каждый сотый запрос ждёт на порядок дольше, а среднее это скрывает."
        d1 = "Всё штатно: среднее укладывается в SLA, а p99 описывает единичные выбросы, их можно не учитывать."
        d2 = "p99 считается как среднее по 99% самых быстрых запросов, поэтому разрыв говорит о погрешности замера."
        d3 = "Разрыв создают сети клиентов: сервер отвечает за среднее время, а хвост возникает вне системы."
    elif scenario == "threadpool_saturation":
        question_text = (
            f"[Отчет #{report_id}] При повышении нагрузки с {rps} до {int(rps * 1.5)} RPS пропускная способность (Throughput) "
            f"перестала расти и вышла на плато, а время отклика стало расти экспоненциально (hockey stick curve) без роста CPU/RAM. "
            f"Что является наиболее вероятной причиной такого поведения?"
        )
        correct_val = "Исчерпан пул соединений или воркеров сервера: запросы стоят в очереди за свободным ресурсом."
        d1 = "Генератор нагрузки упёрся в сетевую карту и физически не может подать больше запросов."
        d2 = "На обратном прокси включилось сжатие gzip, и оно удлиняет каждый ответ пропорционально нагрузке."
        d3 = "Диск заполнен журналами доступа, и сервер замедляет запись каждого ответа в лог."
    elif scenario in ("littles_law_users", "littles_law_rps"):
        target_rps = rng.choice([40, 60, 80, 120, 160, 200])
        resp_s = rng.choice([0.5, 1.0, 1.5])
        think_s = rng.choice([1.5, 2.0, 3.0, 4.0, 5.0])
        users = round(target_rps * (resp_s + think_s))
        if scenario == "littles_law_users":
            question_text = (
                f"[Отчет #{report_id}] Сценарий нагрузки должен подать {target_rps} запросов в секунду. "
                f"Среднее время отклика сервиса {int(resp_s * 1000)} мс, пауза виртуального пользователя между "
                f"запросами (think time) {think_s:g} с. Сколько виртуальных пользователей нужно запустить?"
            )
            answer = users
            wrong = [round(target_rps * think_s), round(target_rps * resp_s), round(target_rps / (resp_s + think_s)),
                     target_rps, users * 2]
        else:
            question_text = (
                f"[Отчет #{report_id}] В закрытой модели нагрузки работают {users} виртуальных пользователей. "
                f"Среднее время отклика {int(resp_s * 1000)} мс, think time {think_s:g} с. "
                f"Какую пропускную способность (запросов в секунду) покажет тест в установившемся режиме?"
            )
            answer = target_rps
            wrong = [round(users / think_s), round(users / resp_s), users, round(users * (resp_s + think_s)),
                     target_rps * 2]
        correct_val = str(answer)
        d1, d2, d3, *extra = [str(w) for w in wrong]
        explanation = (
            f"Закон Литтла для закрытой модели: N = X × (R + Z). Здесь {users} = {target_rps} × "
            f"({resp_s:g} + {think_s:g})."
        )
    else:  # connection_leak
        hours = rng.choice([36, 48, 72])
        question_text = (
            f"[Отчет #{report_id}] При длительном тесте стабильности (Soak test, {hours} ч, {rps} RPS) "
            f"потребление памяти процессом сервиса монотонно растет на 20 МБ/час, а после {hours - 12} часов появляются ошибки Connection Refused. "
            f"Какой дефект зафиксирован тестом?"
        )
        correct_val = "Утечка соединений или файловых дескрипторов вместе с медленной утечкой памяти."
        d1 = "Штатная фрагментация памяти ОС, которая выравнивается после перезапуска."
        d2 = "Перегрев ядер процессора, из-за которого ОС отклоняет новые входящие соединения."
        d3 = "Наполнение кэша ответов в Redis, ожидаемое при длительной работе под нагрузкой."

    if scenario.startswith("littles_law"):
        options, key = build_options(rng, correct_val, [d1, d2, d3, *extra])
    else:
        options, key = build_options(rng, correct_val, [d1, d2, d3])
        explanation = (
            "Анализ нагрузочных тестов требует оценки перцентилей (Tail Latency), "
            "эффектов насыщения пулов соединений и долгосрочной стабильности файловых дескрипторов."
        )

    return ItemRenderResult(
        family_code="QA_LOAD_TESTING_METRICS",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


# ==============================================================================
# 10. QA_TEST_ARCHITECTURE_STRATEGY (Grade: SENIOR, b: 1.50)
# ==============================================================================

def generate_qa_test_architecture_strategy(seed: int) -> ItemRenderResult:
    """Family: QA_TEST_ARCHITECTURE_STRATEGY.

    Tests microservices test architecture: Consumer-Driven Contracts (Pact),
    Chaos Engineering, Ephemeral Test Environments, and Test Data Management.
    Target grade: SENIOR (difficulty b in [1.2, 1.8]).
    """
    rng = random.Random(seed)
    n_services = rng.randint(25, 60)
    n_deploys = rng.randint(10, 50)
    strategy_id = rng.randint(100, 999)
    topic = rng.choice(["contract_testing", "chaos_engineering", "test_data_ephemeral", "service_virtualization", "shift_left_security"])

    if topic == "contract_testing":
        question_text = (
            f"[Архитектура #{strategy_id}] В распределенной платформе из {n_services} микросервисов с частотой релизов "
            f"{n_deploys} раз в день сквозные E2E тесты стали узким местом. Какой архитектурный подход позволяет "
            f"независимо валидировать совместимость API между сервисами-потребителями и сервисами-провайдерами до деплоя?"
        )
        correct_val = "Контрактные тесты (Pact): провайдер проверяет в своём CI контракт потребителя."
        d1 = "Увеличить таймауты E2E-тестов на Playwright, чтобы они реже падали на стендах."
        d2 = "Заменить интеграционные проверки ручным регрессом на staging перед релизом."
        d3 = "Поднимать полную копию всех сервисов для каждого разработчика и гонять E2E."
    elif topic == "chaos_engineering":
        question_text = (
            f"[Архитектура #{strategy_id}] Для подтверждения отказоустойчивости кластера из {n_services} сервисов "
            f"инженер внедряет практику, которая намеренно вносит сетевые задержки, убивает поды в Kubernetes и имитирует сетевые сбои "
            f"для проверки способности системы к самовосстановлению. Как называется эта методология?"
        )
        correct_val = "Chaos Engineering"
        d1 = "Fuzz Testing"
        d2 = "Static Code Analysis"
        d3 = "Penetration Testing"
    elif topic == "test_data_ephemeral":
        question_text = (
            f"[Архитектура #{strategy_id}] При параллельном запуске сотен тестов в CI для {n_services} микросервисов "
            f"возникает проблема взаимного загрязнения данных и дедлоков в тестовой БД. Какая стратегия считается отраслевым стандартом?"
        )
        correct_val = "Testcontainers: каждый поток CI поднимает свою чистую БД с сидом и удаляет её."
        d1 = "Одна общая тестовая БД для всех потоков CI с очисткой таблиц перед каждым тестом."
        d2 = "Все интеграционные тесты запускаются последовательно в один поток по ночам."
        d3 = "СУБД в тестах не используется: обращения к данным заменяются моками."
    elif topic == "service_virtualization":
        question_text = (
            f"[Архитектура #{strategy_id}] Сервис зависит от дорогостоящих внешних API третьих сторон с лимитами RPS "
            f"и нестабильной доступностью в тестовом контуре. Какое архитектурное решение позволяет изолированно "
            f"тестировать сервис с имитацией задержек, сбоев и граничных ответов внешних систем?"
        )
        correct_val = "Виртуализация сервисов (WireMock): эмуляция внешних API с задержками и сбоями."
        d1 = "Не тестировать интеграции с внешними API и проверять их только в проде."
        d2 = "Запускать автотесты напрямую против боевого API провайдера с отдельным ключом."
        d3 = "Переключить внешние сервисы на ручное подтверждение по SMS на время тестов."
    else:  # shift_left_security
        question_text = (
            f"[Архитектура #{strategy_id}] Команда стремится выявлять уязвимости безопасности (OWASP Top 10) "
            f"на максимально ранних этапах SDLC до выкатки на staging для {n_services} сервисов. "
            f"Какой подход решает эту задачу?"
        )
        correct_val = "DevSecOps: SAST, SCA и DAST запускаются в CI на каждый pull request."
        d1 = "Внешний пентест раз в год после всех релизов, без сканеров между ними."
        d2 = "Безопасностью занимается служба поддержки, разбирая жалобы."
        d3 = "HTTPS в тестовых средах отключается, чтобы быстрее шли сборка и тесты."

    options, key = build_options(rng, correct_val, [d1, d2, d3])
    explanation = (
        "Современная тестовая архитектура микросервисов базируется на контрактах (CDC / Pact), "
        "эфемерных контейнеризированных средах (Testcontainers) и верификации отказоустойчивости через Chaos Engineering."
    )

    return ItemRenderResult(
        family_code="QA_TEST_ARCHITECTURE_STRATEGY",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )
