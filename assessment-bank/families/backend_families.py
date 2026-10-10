"""Parameterized generators for Backend item families."""

import random
import sqlite3

from families.base import ItemRenderResult, build_options


def generate_py_mutable_default(seed: int) -> ItemRenderResult:
    """Family: PY_MUTABLE_DEFAULT.

    Tests Python's mutable default arguments trap.
    Different list initializers, appended items, and function names are sampled.
    """
    rng = random.Random(seed)
    func_names = ["append_item", "add_element", "collect_data", "register_event", "track_item"]
    var_names = ["item", "entry", "element", "val", "record"]
    list_param_names = ["target_list", "items", "container", "buffer", "accumulator"]

    fn = rng.choice(func_names)
    var_name = rng.choice(var_names)
    list_name = rng.choice(list_param_names)

    # Initial default list: [] or [x]
    has_init = rng.choice([False, True])
    init_val = rng.randint(10, 50) if has_init else None
    default_repr = f"[{init_val}]" if has_init else "[]"

    # Number of calls: 2 or 3
    val1 = rng.randint(1, 9)
    val2 = rng.randint(11, 19)
    val3 = rng.randint(21, 29)

    code = (
        f"def {fn}({var_name}, {list_name}={default_repr}):\n"
        f"    {list_name}.append({var_name})\n"
        f"    return {list_name}\n\n"
        f"r1 = {fn}({val1})\n"
        f"r2 = {fn}({val2})\n"
        f"r3 = {fn}({val3}, [])\n"
        f"r4 = {fn}({val2 * 2})\n"
        f"print(r4)"
    )

    # Actual Python behavior:
    # default list is shared across calls that don't pass an explicit list!
    shared_list = [init_val] if has_init else []
    # call 1:
    shared_list.append(val1)
    # call 2:
    shared_list.append(val2)
    # call 3 passes [], so shared_list is not modified
    # call 4:
    shared_list.append(val2 * 2)
    correct_val = str(shared_list)

    # Distractors
    distractor_clean = str([init_val, val2 * 2] if has_init else [val2 * 2])
    distractor_all = str(([init_val] if has_init else []) + [val1, val2, val3, val2 * 2])
    distractor_last_two = str(([init_val] if has_init else []) + [val2, val2 * 2])

    options_pool = [
        ("A", correct_val),
        ("B", distractor_clean),
        ("C", distractor_all),
        ("D", distractor_last_two),
    ]
    # Shuffle options deterministically
    rng.shuffle(options_pool)
    keys = ["A", "B", "C", "D"]
    final_options = {}
    correct_key = "A"
    for i, (_, text) in enumerate(options_pool):
        key = keys[i]
        final_options[key] = text
        if text == correct_val:
            correct_key = key

    question_text = (
        "Что будет выведено в консоль в результате выполнения следующего Python-кода?"
    )
    explanation = (
        f"В Python значения аргументов по умолчанию вычисляются один раз при определении функции. "
        f"Список `{list_name}` является изменяемым объектом (mutable) и разделяется между всеми вызовами, "
        f"где он не передан явно. Вызов с явным `[]` не затронул общий список. Итоговый вывод: {correct_val}."
    )

    return ItemRenderResult(
        family_code="PY_MUTABLE_DEFAULT",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=final_options,
        correct_answer=correct_key,
        explanation=explanation,
        item_format="CODE_OUTPUT",
    )


def generate_sql_null_having_join(seed: int) -> ItemRenderResult:
    """Family: SQL_NULL_HAVING_JOIN.

    Tests SQL LEFT JOIN with a filter in ON, COUNT(column) ignoring NULL and HAVING on the aggregate.
    The key is computed by running the query in SQLite on the data described in the stem.
    """
    rng = random.Random(seed)
    domains = [
        ("users", "orders", "user_id", "status", "пользователя"),
        ("authors", "books", "author_id", "genre", "автора"),
        ("departments", "employees", "dept_id", "position", "отдела"),
        ("projects", "tasks", "project_id", "priority", "проекта"),
        ("customers", "payments", "customer_id", "status", "клиента"),
        ("drivers", "trips", "driver_id", "rating", "водителя"),
        ("categories", "products", "category_id", "brand", "категории"),
        ("courses", "lessons", "course_id", "topic", "курса"),
    ]
    tbl_a, tbl_b, fk, col_b, ent_sg = rng.choice(domains)
    target_id = rng.randint(10, 99)
    min_count = rng.randint(1, 3)
    # About a third of the instances return no rows, so "empty result" is not the usual answer
    if rng.random() < 0.3:
        non_null = rng.randint(0, min_count - 1)
    else:
        non_null = rng.randint(min_count, min_count + 3)
    nulls = rng.randint(0, 3)
    total_linked = non_null + nulls

    code = (
        f"SELECT a.id, COUNT(b.{fk}) AS item_count\n"
        f"FROM {tbl_a} a\n"
        f"LEFT JOIN {tbl_b} b ON a.id = b.{fk} AND b.{col_b} IS NOT NULL\n"
        f"WHERE a.id = {target_id}\n"
        f"GROUP BY a.id\n"
        f"HAVING COUNT(b.{fk}) >= {min_count};"
    )
    db = sqlite3.connect(":memory:")
    db.execute(f"CREATE TABLE {tbl_a} (id INTEGER PRIMARY KEY)")
    db.execute(f"CREATE TABLE {tbl_b} (id INTEGER PRIMARY KEY, {fk} INTEGER, {col_b} TEXT)")
    db.execute(f"INSERT INTO {tbl_a} (id) VALUES (?)", (target_id,))
    rows = [(target_id, "x")] * non_null + [(target_id, None)] * nulls
    db.executemany(f"INSERT INTO {tbl_b} ({fk}, {col_b}) VALUES (?, ?)", rows)
    result = db.execute(code).fetchall()
    db.close()

    empty = "Пустой результат: 0 строк"

    def row(count: object) -> str:
        return f"Одна строка: id={target_id}, item_count={count}"

    correct_text = row(result[0][1]) if result else empty
    def records(n: int) -> str:
        if n % 10 == 1 and n % 100 != 11:
            return f"{n} запись"
        if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
            return f"{n} записи"
        return f"{n} записей"

    if total_linked == 0:
        data_desc = f"Для {ent_sg} с id={target_id} в таблице `{tbl_b}` нет ни одной записи."
    else:
        data_desc = (
            f"Для {ent_sg} с id={target_id} в таблице `{tbl_b}` {records(total_linked)}, "
            f"и в {nulls} из них поле `{col_b}` равно NULL."
        )
    question_text = f"{data_desc}\nЧто вернёт запрос?"
    # Typical mistakes: ignoring HAVING, counting NULL rows, COUNT(*) semantics on an outer join row, NULL aggregate
    distractors = [empty, row(non_null), row(total_linked), row(0), row(1), row("NULL"), row(non_null + 1)]
    options, key = build_options(rng, correct_text, rng.sample(distractors, len(distractors)))
    explanation = (
        f"Условие `b.{col_b} IS NOT NULL` стоит в ON, поэтому присоединяются только записи без NULL: {non_null}. "
        f"COUNT(b.{fk}) считает только не-NULL значения и даёт {non_null}; "
        f"HAVING {non_null} >= {min_count} {'выполняется' if result else 'не выполняется'}."
    )

    return ItemRenderResult(
        family_code="SQL_NULL_HAVING_JOIN",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="SQL",
    )


def generate_algo_complexity_loop(seed: int) -> ItemRenderResult:
    """Family: ALGO_COMPLEXITY_LOOP.

    Tests worst-case asymptotic time complexity analysis of nested loops.
    """
    rng = random.Random(seed)
    case_type = rng.choice(["n_log_n", "n_squared", "log_n", "linear", "n_cubic"])
    fn_name = rng.choice(["calc_metrics", "process_matrix", "aggregate_data", "run_pipeline", "compute_weights"])

    if case_type == "n_log_n":
        mult = rng.choice([2, 3, 4, 5])
        step = rng.choice([1, 2])
        code = (
            f"def {fn_name}(n: int):\n"
            f"    total = 0\n"
            f"    i = 1\n"
            f"    while i < n:\n"
            f"        for j in range(0, n, {step}):\n"
            f"            total += i * j\n"
            f"        i *= {mult}\n"
            f"    return total"
        )
        correct_answer_text = "O(n log n)"
        reasoning = f"внешний цикл выполняет log_{mult}(n) итераций, внутренний — линейный по n"
        distractors = ["O(n²)", "O(n)", "O(log n)", "O(n² log n)"]
    elif case_type == "n_squared":
        step = rng.choice([1, 2])
        offset = rng.randint(1, 5)
        code = (
            f"def {fn_name}(n: int):\n"
            f"    total = 0\n"
            f"    for i in range(n):\n"
            f"        for j in range(i, n, {step}):\n"
            f"            total += (i + j) * {offset}\n"
            f"    return total"
        )
        correct_answer_text = "O(n²)"
        reasoning = f"внутренний цикл в сумме делает около n·(n+1)/(2·{step}) итераций — арифметическая прогрессия"
        distractors = ["O(n log n)", "O(n)", "O(2ⁿ)", "O(n³)"]
    elif case_type == "log_n":
        div = rng.choice([2, 3, 4, 5])
        add = rng.randint(1, 4)
        code = (
            f"def {fn_name}(n: int):\n"
            f"    steps = 0\n"
            f"    val = n\n"
            f"    while val > 1:\n"
            f"        val //= {div}\n"
            f"        steps += {add}\n"
            f"    return steps"
        )
        correct_answer_text = "O(log n)"
        reasoning = f"val делится на {div} на каждой итерации, поэтому шагов log_{div}(n)"
        distractors = ["O(n)", "O(n log n)", "O(1)", "O(√n)"]
    elif case_type == "linear":
        step1 = rng.choice([2, 3, 4])
        step2 = rng.choice([3, 5])
        code = (
            f"def {fn_name}(n: int):\n"
            f"    total = 0\n"
            f"    for i in range(0, n, {step1}):\n"
            f"        total += i\n"
            f"    for j in range(0, n, {step2}):\n"
            f"        total += j\n"
            f"    return total"
        )
        correct_answer_text = "O(n)"
        reasoning = f"два последовательных цикла дают n/{step1} + n/{step2} итераций"
        distractors = ["O(n²)", "O(log n)", "O(n log n)", "O(1)"]
    else:  # n_cubic
        mult = rng.randint(2, 4)
        code = (
            f"def {fn_name}(n: int):\n"
            f"    total = 0\n"
            f"    for i in range(n):\n"
            f"        for j in range(n):\n"
            f"            for k in range(n):\n"
            f"                total += (i + j + k) * {mult}\n"
            f"    return total"
        )
        correct_answer_text = "O(n³)"
        reasoning = "три вложенных цикла, каждый от 0 до n"
        distractors = ["O(n²)", "O(n log n)", "O(3ⁿ)", "O(n)"]

    options, key = build_options(rng, correct_answer_text, distractors)
    question_text = (
        f"Определите асимптотическую временную сложность (Time Complexity) приведенной функции `{fn_name}` в худшем случае (Worst Case):"
    )
    explanation = f"{correct_answer_text}: {reasoning}."

    return ItemRenderResult(
        family_code="ALGO_COMPLEXITY_LOOP",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="COMPLEXITY",
    )


def generate_http_async_coroutine(seed: int) -> ItemRenderResult:
    """Family: HTTP_ASYNC_COROUTINE.

    Tests asyncio concurrency with gather vs sequential await.
    """
    rng = random.Random(seed)
    t1 = rng.randint(2, 7)
    t2 = rng.randint(2, 7)
    while t1 == t2:
        t2 = rng.randint(2, 7)
    is_gather = rng.choice([True, False])
    tag1 = rng.choice(["fetch_user", "load_cache", "query_db", "ping_api", "task_a"])
    tag2 = rng.choice(["fetch_orders", "load_config", "write_log", "send_metrics", "task_b"])

    if is_gather:
        code = (
            "import asyncio\nimport time\n\n"
            f"async def worker(tag: str, delay: int):\n"
            f"    await asyncio.sleep(delay)\n"
            f"    return f'{{tag}}:{{delay}}'\n\n"
            f"async def main():\n"
            f"    t0 = time.monotonic()\n"
            f"    res = await asyncio.gather(worker('{tag1}', {t1}), worker('{tag2}', {t2}))\n"
            f"    elapsed = round(time.monotonic() - t0)\n"
            f"    print(elapsed, res)\n\n"
            f"asyncio.run(main())"
        )
        expected_elapsed = max(t1, t2)
        correct_out = f"{expected_elapsed} ['{tag1}:{t1}', '{tag2}:{t2}']"
    else:
        code = (
            "import asyncio\nimport time\n\n"
            f"async def worker(tag: str, delay: int):\n"
            f"    await asyncio.sleep(delay)\n"
            f"    return f'{{tag}}:{{delay}}'\n\n"
            f"async def main():\n"
            f"    t0 = time.monotonic()\n"
            f"    r1 = await worker('{tag1}', {t1})\n"
            f"    r2 = await worker('{tag2}', {t2})\n"
            f"    elapsed = round(time.monotonic() - t0)\n"
            f"    print(elapsed, [r1, r2])\n\n"
            f"asyncio.run(main())"
        )
        expected_elapsed = t1 + t2
        correct_out = f"{expected_elapsed} ['{tag1}:{t1}', '{tag2}:{t2}']"

    sum_time = t1 + t2
    max_time = max(t1, t2)
    distractor_1 = f"{sum_time if is_gather else max_time} ['{tag1}:{t1}', '{tag2}:{t2}']"
    distractor_2 = f"0 ['{tag1}:{t1}', '{tag2}:{t2}']"
    distractor_3 = f"{max_time} ['{tag2}:{t2}', '{tag1}:{t1}']"
    distractor_4 = f"{min(t1, t2)} ['{tag1}:{t1}', '{tag2}:{t2}']"

    options, key = build_options(rng, correct_out, [distractor_1, distractor_2, distractor_3, distractor_4])

    question_text = (
        "Каков будет результат выполнения следующей асинхронной программы на Python (приближенное время и вывод)?"
    )
    explanation = (
        f"При `asyncio.gather` корутины выполняются конкурентно в Event Loop, и общее время равно max({t1}, {t2}) = {max_time} сек. "
        f"При последовательном `await` корутины блокируют выполнение функции `main`, общее время {t1} + {t2} = {sum_time} сек."
    )

    return ItemRenderResult(
        family_code="HTTP_ASYNC_COROUTINE",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="CODE_OUTPUT",
    )


def generate_py_generator_yield(seed: int) -> ItemRenderResult:
    """Family: PY_GENERATOR_YIELD.

    Tests Python generator lazy evaluation and next() state.
    """
    rng = random.Random(seed)
    start = rng.randint(10, 60)
    step = rng.randint(3, 15)
    factor = rng.choice([1, 2, 3])
    fn_name = rng.choice(["counter_gen", "step_stream", "pipeline_gen", "number_sequence"])

    code = (
        f"def {fn_name}(start, step):\n"
        f"    val = start\n"
        f"    while True:\n"
        f"        yield val\n"
        f"        val = val * {factor} + step\n\n"
        f"g = {fn_name}({start}, {step})\n"
        f"a = next(g)\n"
        f"b = next(g)\n"
        f"c = next(g)\n"
        f"print(a, b, c)"
    )

    v1 = start
    v2 = v1 * factor + step
    v3 = v2 * factor + step
    correct_val = f"{v1} {v2} {v3}"
    distractor_1 = f"{v1} {v1} {v1}"
    distractor_2 = f"{v2} {v3} {v3 * factor + step}"
    distractor_3 = f"{v1} {v2} {v1}"
    distractor_4 = f"{v1} {v1 + step} {v1 + 2 * step}"

    options, key = build_options(rng, correct_val, [distractor_1, distractor_2, distractor_3, distractor_4])

    question_text = f"Что выведет данный код с генератором `{fn_name}` в Python?"
    explanation = (
        f"Первый вызов next() возвращает начальное значение val={v1} и приостанавливает выполнение. "
        f"Второй вызов возобновляет цикл, вычисляет val={v1}*{factor}+{step}={v2} и возвращает его. "
        f"Третий вызов дает {v3}."
    )

    return ItemRenderResult(
        family_code="PY_GENERATOR_YIELD",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="CODE_OUTPUT",
    )


def generate_sql_window_rank(seed: int) -> ItemRenderResult:
    """Family: SQL_WINDOW_RANK.

    Tests difference between ROW_NUMBER, RANK, and DENSE_RANK when ties occur.
    Options are the `pos` sequences in descending order of the column, so a tie never makes the key ambiguous.
    """
    rng = random.Random(seed)
    # ROW_NUMBER always gives 1, 2, 3, 4: it is drawn less often so that sequence does not dominate the family
    func = rng.choices(["ROW_NUMBER", "RANK", "DENSE_RANK"], weights=[1, 2, 2])[0]
    tbl = rng.choice(["employees", "candidates", "gamers", "sales_reps", "students"])
    col = rng.choice(["score", "points", "salary", "rating", "bonus"])

    pattern = rng.choice(["tie_top", "tie_mid", "tie_bot", "triple_top", "two_ties"])
    s1 = rng.randint(85, 100)
    s2 = rng.randint(60, 84)
    s3 = rng.randint(30, 59)
    scores_arr = {
        "tie_top": [s1, s1, s2, s3],
        "tie_mid": [s1, s2, s2, s3],
        "tie_bot": [s1, s2, s3, s3],
        "triple_top": [s1, s1, s1, s2],
        "two_ties": [s1, s1, s2, s2],
    }[pattern]

    def positions(name: str) -> list[int]:
        result = []
        for i, value in enumerate(scores_arr):
            if name == "ROW_NUMBER":
                result.append(i + 1)
            elif name == "RANK":
                result.append(scores_arr.index(value) + 1)
            else:
                result.append(len(set(scores_arr[: scores_arr.index(value) + 1])))
        return result

    def fmt(seq: list[int]) -> str:
        return ", ".join(str(x) for x in seq)

    code = (
        f"/* Таблица {tbl}: {col} = {scores_arr} */\n"
        f"SELECT name, {col}, {func}() OVER (ORDER BY {col} DESC) AS pos\n"
        f"FROM {tbl};"
    )
    correct_val = fmt(positions(func))
    distractors = [fmt(positions(other)) for other in ("ROW_NUMBER", "RANK", "DENSE_RANK") if other != func]
    # Typical slips: ranks starting from 0, and a gap counted after the tie but not before it
    distractors += [fmt([x - 1 for x in positions(func)]), fmt([1, 2, 2, 3]), fmt([1, 1, 2, 2]), fmt([1, 2, 3, 3])]
    options, key = build_options(rng, correct_val, distractors)

    question_text = (
        f"Какие значения в колонке `pos` вернёт запрос для строк таблицы `{tbl}` "
        f"в порядке убывания {col} ({scores_arr})?"
    )
    descriptions = {
        "ROW_NUMBER": "нумерует строки подряд, даже при равных значениях",
        "RANK": "даёт равным значениям одинаковый ранг и пропускает следующие номера",
        "DENSE_RANK": "даёт равным значениям одинаковый ранг без пропусков",
    }
    explanation = f"{func} {descriptions[func]}: {correct_val}."

    return ItemRenderResult(
        family_code="SQL_WINDOW_RANK",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="SQL",
    )


def generate_py_decorator_execution(seed: int) -> ItemRenderResult:
    """Family: PY_DECORATOR_EXECUTION.

    Tests Python decorator wrapping and call order.
    """
    rng = random.Random(seed)
    tags1 = ["Alpha", "Trace", "Start", "Prefix", "LogA", "Audit", "Init"]
    tags2 = ["Beta", "Metrics", "Finish", "Suffix", "LogB", "End", "Done"]
    tag1 = f"{rng.choice(tags1)}_{rng.randint(1, 9)}"
    tag2 = f"{rng.choice(tags2)}_{rng.randint(1, 9)}"
    fn_name = rng.choice(["greet", "process", "fetch_data", "run_task", "calc_res"])
    base_val = f"Data_{rng.randint(10, 99)}"

    code = (
        f"def deco1(fn):\n"
        f"    def wrapper():\n"
        f"        return '{tag1} ' + fn()\n"
        f"    return wrapper\n\n"
        f"def deco2(fn):\n"
        f"    def wrapper():\n"
        f"        return fn() + ' {tag2}'\n"
        f"    return wrapper\n\n"
        f"@deco1\n"
        f"@deco2\n"
        f"def {fn_name}():\n"
        f"    return '{base_val}'\n\n"
        f"print({fn_name}())"
    )

    correct_val = f"{tag1} {base_val} {tag2}"
    d1 = f"{base_val} {tag1} {tag2}"
    d2 = f"{tag1} {tag2} {base_val}"
    d3 = f"{tag2} {base_val} {tag1}"
    d4 = base_val

    options, key = build_options(rng, correct_val, [d1, d2, d3, d4])

    question_text = "Что выведет данный код с декораторами функций в Python?"
    explanation = (
        f"@deco1 оборачивает результат @deco2({fn_name}). При вызове сначала deco1 добавляет префикс '{tag1}', "
        f"затем вызывается {fn_name}() возвращая '{base_val}', затем deco2 добавляет суффикс '{tag2}'."
    )

    return ItemRenderResult(
        family_code="PY_DECORATOR_EXECUTION",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="CODE_OUTPUT",
    )


def generate_backend_index_scan(seed: int) -> ItemRenderResult:
    """Family: BACKEND_INDEX_SCAN.

    Tests understanding of B-Tree indexing and query plan scan types.
    """
    rng = random.Random(seed)
    tbls = ["users", "orders", "transactions", "products", "shipments", "customers", "invoices", "events"]
    cols = ["created_at", "email", "status", "salary", "phone_number", "tracking_code", "category"]
    tbl = rng.choice(tbls)
    col = rng.choice(cols)
    val = f"val_{rng.randint(10, 99)}"

    pattern = rng.choice(["func_lower", "like_leading_wildcard", "math_expression", "substring"])
    if pattern == "func_lower":
        non_sargable = f"SELECT * FROM {tbl} WHERE LOWER({col}) = '{val}';"
        reason = f"вызов функции LOWER({col}) нарушает sargability стандартного B-Tree индекса"
    elif pattern == "like_leading_wildcard":
        non_sargable = f"SELECT * FROM {tbl} WHERE {col} LIKE '%{val}';"
        reason = "символ подстановки '%' в начале шаблона исключает поиск по дереву"
    elif pattern == "math_expression":
        offset = rng.randint(5, 50)
        target = rng.randint(100, 500)
        non_sargable = f"SELECT * FROM {tbl} WHERE {col} + {offset} = {target};"
        reason = f"арифметическое выражение над индексированной колонкой `{col}` требует вычисления для каждой строки"
    else:  # substring
        non_sargable = f"SELECT * FROM {tbl} WHERE SUBSTR({col}, 1, 3) = '{val[:3]}';"
        reason = f"вызов функции SUBSTR({col}, ...) делает индекс по `{col}` недоступным"

    sargable_1 = f"SELECT * FROM {tbl} WHERE {col} = '{val}';"
    sargable_2 = f"SELECT * FROM {tbl} WHERE {col} LIKE '{val}%';"
    sargable_3 = f"SELECT * FROM {tbl} WHERE {col} BETWEEN '100' AND '500';"
    sargable_4 = f"SELECT * FROM {tbl} WHERE {col} IN ('{val}', 'alt_{val}');"

    options, key = build_options(rng, non_sargable, [sargable_1, sargable_2, sargable_3, sargable_4])

    question_text = (
        f"В таблице `{tbl}` с 5 000 000 записей создан B-Tree индекс по полю `{col}`. "
        f"Какой из следующих запросов НЕ сможет эффективно использовать индекс для прямого поиска по дереву (Index Scan / Seek) "
        f"и вероятнее всего приведет к полному сканированию таблицы (Seq Scan)?"
    )
    explanation = (
        f"Запрос `{non_sargable}` приведет к Seq Scan, так как {reason}. "
        f"Остальные запросы являются sargable (search-argument-able) и используют B-Tree индекс."
    )

    return ItemRenderResult(
        family_code="BACKEND_INDEX_SCAN",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="SQL",
    )


def generate_py_list_comprehension_scope(seed: int) -> ItemRenderResult:
    """Family: PY_LIST_COMPREHENSION_SCOPE.

    Tests Python list comprehension scope vs for-loop variable leakage.
    """
    rng = random.Random(seed)
    limit = rng.randint(3, 7)
    code = (
        f"x = 100\n"
        f"evens = [x * 2 for x in range({limit})]\n"
        f"print(x)"
    )
    correct_val = "100 (в Python 3 списковое включение имеет собственную локальную область видимости)"
    d1 = f"{limit - 1} (переменная цикла перезаписывает глобальную x)"
    d2 = f"{(limit - 1) * 2}"
    d3 = "Ошибка NameError: имя x конфликтует"

    options_pool = [correct_val, d1, d2, d3]
    rng.shuffle(options_pool)
    keys = ["A", "B", "C", "D"]
    options = {}
    correct_key = "A"
    for i, opt in enumerate(options_pool):
        key = keys[i]
        options[key] = opt
        if opt == correct_val:
            correct_key = key

    return ItemRenderResult(
        family_code="PY_LIST_COMPREHENSION_SCOPE",
        seed=seed,
        question_text="Что выведет данный Python-код в консоль?",
        code_snippet=code,
        options=options,
        correct_answer=correct_key,
        explanation="В Python 3 генераторы списков выполняются в изолированной области видимости функции, не затирая внешнюю x.",
        item_format="CODE_OUTPUT",
    )


def generate_sql_transaction_isolation(seed: int) -> ItemRenderResult:
    """Family: SQL_TRANSACTION_ISOLATION.

    Tests ANSI SQL transaction isolation levels anomalies.
    """
    rng = random.Random(seed)
    iso = rng.choice(["Read Committed", "Repeatable Read", "Read Uncommitted"])
    if iso == "Read Committed":
        question_text = "Какой феномен транзакций ДОПУСКАЕТСЯ уровнем изоляции Read Committed в реляционных СУБД?"
        correct_val = "Non-repeatable Read (неповторяющееся чтение при изменении строки другой транзакцией)"
        d1 = "Dirty Read (грязное чтение незафиксированных данных)"
        d2 = "Lost Update (потерянные обновления)"
        d3 = "Никакие аномалии не допускаются"
    elif iso == "Repeatable Read":
        question_text = "Какую аномалию чтения гарантированно предотвращает уровень изоляции Repeatable Read (по стандарту ANSI SQL)?"
        correct_val = "Non-repeatable Read (повторное чтение одной и той же строки вернет неизменные данные)"
        d1 = "Phantom Read (фантомные строки в выборках по предикату)"
        d2 = "Serialization Failure"
        d3 = "Deadlock"
    else:
        question_text = "Какую главную проблему допускает слабейший уровень изоляции Read Uncommitted?"
        correct_val = "Dirty Read (чтение 'грязных' данных, которые могут быть отменены ROLLBACK)"
        d1 = "Строгая блокировка таблицы на чтение"
        d2 = "Автоматический переход в Read Only режим"
        d3 = "Снижение пропускной способности СУБД"

    options_pool = [correct_val, d1, d2, d3]
    rng.shuffle(options_pool)
    keys = ["A", "B", "C", "D"]
    options = {}
    correct_key = "A"
    for i, opt in enumerate(options_pool):
        key = keys[i]
        options[key] = opt
        if opt == correct_val:
            correct_key = key

    return ItemRenderResult(
        family_code="SQL_TRANSACTION_ISOLATION",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=correct_key,
        explanation=f"Анализ уровней изоляции транзакций: {correct_val}.",
        item_format="SQL",
    )


def generate_algo_binary_search_bisect(seed: int) -> ItemRenderResult:
    """Family: ALGO_BINARY_SEARCH_BISECT.

    Tests binary search worst-case operations count.
    """
    rng = random.Random(seed)
    n_elements = rng.choice([1024, 2048, 4096, 8192, 16384])
    import math
    steps = int(math.log2(n_elements)) + 1
    question_text = (
        f"В отсортированном массиве из {n_elements} элементов выполняется классический бинарный поиск (Binary Search). "
        f"Какое максимальное число сравнений элементов потребуется в худшем случае (Worst-case) для нахождения элемента или вывода о его отсутствии?"
    )
    correct_val = f"Не более {steps} сравнений (потолок log₂(N) + 1)"
    d1 = f"Не более {n_elements // 2} сравнений"
    d2 = f"Не более {steps * 2} сравнений"
    d3 = f"Ровно {steps - 2} сравнений"

    options_pool = [correct_val, d1, d2, d3]
    rng.shuffle(options_pool)
    keys = ["A", "B", "C", "D"]
    options = {}
    correct_key = "A"
    for i, opt in enumerate(options_pool):
        key = keys[i]
        options[key] = opt
        if opt == correct_val:
            correct_key = key

    return ItemRenderResult(
        family_code="ALGO_BINARY_SEARCH_BISECT",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=correct_key,
        explanation=f"Бинарный поиск делит отрезок пополам на каждой итерации: log₂({n_elements}) = {steps - 1}, с округлением вверх до {steps}.",
        item_format="COMPLEXITY",
    )


def generate_http_idempotent_methods(seed: int) -> ItemRenderResult:
    """Family: HTTP_IDEMPOTENT_METHODS.

    Tests HTTP method semantics (Safe vs Idempotent).
    """
    rng = random.Random(seed)
    question_text = (
        "Согласно стандарту HTTP/1.1 (RFC 9110), метод называется идемпотентным (Idempotent), "
        "если повторное выполнение одного и того же запроса приводит к такому же состоянию сервера, как и однократное. "
        "Какой из перечисленных HTTP-методов НЕ является идемпотентным?"
    )
    correct_val = "POST (создает новый подчиненный ресурс при каждом повторе)"
    d1 = "PUT (заменяет целевой ресурс полностью, повтор оставляет то же состояние)"
    d2 = "DELETE (удаляет ресурс, повтор оставляет ресурс удаленным)"
    d3 = "GET (безопасный метод только для чтения)"

    options_pool = [correct_val, d1, d2, d3]
    rng.shuffle(options_pool)
    keys = ["A", "B", "C", "D"]
    options = {}
    correct_key = "A"
    for i, opt in enumerate(options_pool):
        key = keys[i]
        options[key] = opt
        if opt == correct_val:
            correct_key = key

    return ItemRenderResult(
        family_code="HTTP_IDEMPOTENT_METHODS",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=correct_key,
        explanation="Методы GET, HEAD, PUT, DELETE являются идемпотентными. Метод POST неидемпотентен.",
        item_format="MCQ",
    )


def generate_py_context_manager_exit(seed: int) -> ItemRenderResult:
    """Family: PY_CONTEXT_MANAGER_EXIT.

    Tests Python context manager __exit__ exception handling.
    """
    rng = random.Random(seed)
    suppress = rng.choice([True, False])
    ret_val = "True" if suppress else "False"
    code = (
        "class SafeContext:\n"
        "    def __enter__(self):\n"
        "        return self\n"
        f"    def __exit__(self, exc_type, exc_val, exc_tb):\n"
        f"        return {ret_val}\n\n"
        "with SafeContext():\n"
        "    raise ValueError('Oops')\n"
        "print('Done')"
    )
    if suppress:
        correct_val = "Код выведет 'Done' без падения программы (возврат True из __exit__ подавляет исключение)"
        d1 = "Программа упадет с ValueError: Oops"
        d2 = "Код завершится ошибкой синтаксиса"
        d3 = "Будет выведено None"
    else:
        correct_val = "Программа упадет с ValueError: Oops (возврат False/None из __exit__ передает ошибку наружу)"
        d1 = "Код выведет 'Done'"
        d2 = "Исключение превратится в Warning"
        d3 = "Контекстный менеджер не закроется"

    options_pool = [correct_val, d1, d2, d3]
    rng.shuffle(options_pool)
    keys = ["A", "B", "C", "D"]
    options = {}
    correct_key = "A"
    for i, opt in enumerate(options_pool):
        key = keys[i]
        options[key] = opt
        if opt == correct_val:
            correct_key = key

    return ItemRenderResult(
        family_code="PY_CONTEXT_MANAGER_EXIT",
        seed=seed,
        question_text="Что произойдет при выполнении данного Python-кода?",
        code_snippet=code,
        options=options,
        correct_answer=correct_key,
        explanation="Если метод __exit__ возвращает True, Python подавляет возникшее в блоке with исключение.",
        item_format="CODE_OUTPUT",
    )


def generate_sql_group_by_aggregate(seed: int) -> ItemRenderResult:
    """Family: SQL_GROUP_BY_AGGREGATE.

    Tests difference between WHERE and HAVING clause filtering.
    """
    rng = random.Random(seed)
    min_sal = rng.randint(50, 100) * 1000
    code = (
        f"SELECT dept_id, AVG(salary) AS avg_sal\n"
        f"FROM employees\n"
        f"WHERE salary > {min_sal}\n"
        f"GROUP BY dept_id\n"
        f"HAVING COUNT(*) >= 5;"
    )
    question_text = (
        "В приведенном SQL-запросе в каком порядке СУБД логически фильтрует данные через секции WHERE и HAVING?"
    )
    correct_val = f"Сначала WHERE отсекает сотрудников с salary <= {min_sal}, затем группировка, затем HAVING фильтрует группы с >= 5 оставшимися строками."
    d1 = "Сначала HAVING фильтрует все отделы, а затем WHERE отбирает зарплаты."
    d2 = "WHERE и HAVING объединяются через логическое И до группировки."
    d3 = "Агрегатная функция AVG вычисляется до применения условия WHERE."

    options_pool = [correct_val, d1, d2, d3]
    rng.shuffle(options_pool)
    keys = ["A", "B", "C", "D"]
    options = {}
    correct_key = "A"
    for i, opt in enumerate(options_pool):
        key = keys[i]
        options[key] = opt
        if opt == correct_val:
            correct_key = key

    return ItemRenderResult(
        family_code="SQL_GROUP_BY_AGGREGATE",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=correct_key,
        explanation="Порядок выполнения SQL: FROM -> WHERE -> GROUP BY -> HAVING -> SELECT -> ORDER BY.",
        item_format="SQL",
    )


def generate_backend_redis_data_types(seed: int) -> ItemRenderResult:
    """Family: BACKEND_REDIS_DATA_TYPES.

    Tests Redis data structures (Sorted Sets vs Hashes vs Sets).
    """
    rng = random.Random(seed)
    scenario = rng.choice(["leaderboard", "unique_ips", "user_session"])
    if scenario == "leaderboard":
        question_text = "В бэкенде реализуется лидерборд игроков с мгновенным получением топ-100 по очкам. Какая структура данных Redis идеально подходит для этой задачи?"
        correct_val = "Sorted Set (ZSET) — хранит элементы с числовым score и логарифмической сложностью выборки диапазона"
        d1 = "List (LPUSH / LRANGE)"
        d2 = "Hash (HSET)"
        d3 = "String (SET / GET)"
    elif scenario == "unique_ips":
        question_text = "Для антифрод-системы требуется подсчитывать уникальные IP-адреса посетителей за сутки с минимальным потреблением ОЗУ. Что эффективнее?"
        correct_val = "HyperLogLog (PFADD / PFCOUNT) — вероятностная структура со стабильным размером 12 КБ"
        d1 = "List"
        d2 = "String"
        d3 = "Stream"
    else:
        question_text = "Для кэширования профиля пользователя (имя, почта, статус) с возможностью атомарно читать и менять отдельные поля, что использовать?"
        correct_val = "Hash (HSET / HGET / HMGET)"
        d1 = "Sorted Set"
        d2 = "HyperLogLog"
        d3 = "Pub/Sub"

    options_pool = [correct_val, d1, d2, d3]
    rng.shuffle(options_pool)
    keys = ["A", "B", "C", "D"]
    options = {}
    correct_key = "A"
    for i, opt in enumerate(options_pool):
        key = keys[i]
        options[key] = opt
        if opt == correct_val:
            correct_key = key

    return ItemRenderResult(
        family_code="BACKEND_REDIS_DATA_TYPES",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=correct_key,
        explanation=f"Оптимальный выбор структуры данных Redis: {correct_val}.",
        item_format="MCQ",
    )


def generate_py_list_slicing_stride(seed: int) -> ItemRenderResult:
    """Family: PY_LIST_SLICING_STRIDE.

    Tests Python list slicing with stride (step), start, stop, and negative indexes.
    Target grade: INTERN (difficulty b in [-1.8, -1.2]).
    """
    rng = random.Random(seed)
    length = rng.randint(7, 10)
    nums = [rng.randint(10, 99) for _ in range(length)]

    pattern = rng.choice(["pos_stride", "start_stop_stride", "neg_stride_rev", "start_neg_stride"])

    if pattern == "pos_stride":
        stride = rng.choice([2, 3])
        start = rng.randint(0, 2)
        slice_expr = f"{start}::{stride}" if start > 0 else f"::{stride}"
        eval_slice = slice(start, None, stride)
    elif pattern == "start_stop_stride":
        stride = rng.choice([2, 3])
        start = rng.randint(0, 2)
        end = rng.randint(length - 3, length - 1)
        slice_expr = f"{start}:{end}:{stride}"
        eval_slice = slice(start, end, stride)
    elif pattern == "neg_stride_rev":
        slice_expr = "::-1"
        eval_slice = slice(None, None, -1)
    else:  # start_neg_stride
        start = rng.randint(4, length - 1)
        stride = rng.choice([-1, -2])
        slice_expr = f"{start}::{stride}"
        eval_slice = slice(start, None, stride)

    result_list = nums[eval_slice]
    correct_val = str(result_list)

    d1 = str(nums[slice(eval_slice.start or 0, eval_slice.stop, 1 if (eval_slice.step or 1) > 0 else -1)])
    d2 = str(nums[::-1] if eval_slice.step and eval_slice.step > 0 else nums[::2])
    d3 = str(result_list[:-1] if len(result_list) > 1 else nums[1:3])
    alt_start = (eval_slice.start or 0) + 1
    d4 = str(nums[alt_start::(eval_slice.step or 1)])

    distractors = [d for d in [d1, d2, d3, d4] if d != correct_val]
    while len(distractors) < 3:
        fake = nums.copy()
        rng.shuffle(fake)
        distractors.append(str(fake[:len(result_list)]))

    options, key = build_options(rng, correct_val, distractors)

    code = (
        f"nums = {nums}\n"
        f"print(nums[{slice_expr}])"
    )
    question_text = "Что будет выведено в консоль в результате выполнения следующего среза списка в Python?"
    explanation = (
        f"Срез `nums[{slice_expr}]` извлекает элементы списка начиная с позиции {eval_slice.start} "
        f"до {eval_slice.stop} с шагом {eval_slice.step}. Полученный результат: {correct_val}."
    )
    return ItemRenderResult(
        family_code="PY_LIST_SLICING_STRIDE",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="CODE_OUTPUT",
    )


def generate_py_dict_operations(seed: int) -> ItemRenderResult:
    """Family: PY_DICT_OPERATIONS.

    Tests basic Python dictionary operations: .get(key, default), key assignment, and membership.
    Target grade: INTERN (difficulty b in [-1.8, -1.2]).
    """
    rng = random.Random(seed)
    fruit_pool = ["apple", "banana", "orange", "mango", "lemon", "peach", "cherry", "grape"]
    chosen_keys = rng.sample(fruit_pool, 4)
    k1, k2, k3, missing_k = chosen_keys

    v1 = rng.randint(10, 40)
    v2 = rng.randint(50, 90)
    v3 = rng.randint(100, 200)
    default_v = rng.randint(1, 9)
    extra_add = rng.randint(5, 15)

    op_type = rng.choice(["get_with_default", "get_existing_default", "overwrite_and_get"])

    if op_type == "get_with_default":
        code = (
            f"inventory = {{'{k1}': {v1}, '{k2}': {v2}, '{k3}': {v3}}}\n"
            f"res = inventory.get('{missing_k}', {default_v})\n"
            f"print(res)"
        )
        correct_val = str(default_v)
        distractors = ["None", "KeyError", str(v1), str(0)]
        explanation = (
            f"Метод `dict.get(key, default)` возвращает значение `default` ({default_v}), "
            f"если указанный ключ '{missing_k}' отсутствует в словаре, не вызывая KeyError."
        )
    elif op_type == "get_existing_default":
        code = (
            f"inventory = {{'{k1}': {v1}, '{k2}': {v2}, '{k3}': {v3}}}\n"
            f"res = inventory.get('{k2}', {default_v})\n"
            f"print(res)"
        )
        correct_val = str(v2)
        distractors = [str(default_v), "None", str(v1), str(v2 + default_v)]
        explanation = (
            f"Так как ключ '{k2}' уже присутствует в словаре со значением {v2}, "
            f"метод `dict.get('{k2}', {default_v})` возвращает {v2}, а дефолтное значение {default_v} игнорируется."
        )
    else:  # overwrite_and_get
        code = (
            f"inventory = {{'{k1}': {v1}, '{k2}': {v2}}}\n"
            f"inventory['{k1}'] = inventory.get('{k1}', 0) + {extra_add}\n"
            f"inventory['{missing_k}'] = inventory.get('{missing_k}', {default_v})\n"
            f"print(inventory['{k1}'], inventory['{missing_k}'])\n"
        )
        correct_val = f"{v1 + extra_add} {default_v}"
        distractors = [
            f"{v1} {default_v}",
            f"{v1 + extra_add} None",
            f"{extra_add} {default_v}",
            f"{v1 + extra_add} 0",
        ]
        explanation = (
            f"При первом присваивании значение ключа '{k1}' перезаписывается на {v1} + {extra_add} = {v1 + extra_add}. "
            f"При втором присваивании для отсутствующего ключа '{missing_k}' берется дефолт {default_v}."
        )

    options, key = build_options(rng, correct_val, distractors)
    question_text = "Что выведет следующий фрагмент Python-кода со словарем?"
    return ItemRenderResult(
        family_code="PY_DICT_OPERATIONS",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="CODE_OUTPUT",
    )



