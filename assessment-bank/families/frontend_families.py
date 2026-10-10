"""Parameterized generators for Frontend item families."""

import random

from families.base import ItemRenderResult, build_options


def generate_js_event_loop_microtask(seed: int) -> ItemRenderResult:
    """Family: JS_EVENT_LOOP_MICROTASK.

    Tests JavaScript Event Loop execution order (synchronous, microtasks, macrotasks).
    """
    rng = random.Random(seed)
    n1 = rng.randint(1, 4)
    n2 = rng.randint(5, 9)
    n3 = rng.randint(10, 14)
    n4 = rng.randint(15, 19)

    code = (
        f"console.log({n1});\n\n"
        f"setTimeout(() => {{\n"
        f"  console.log({n2});\n"
        f"}}, 0);\n\n"
        f"Promise.resolve().then(() => {{\n"
        f"  console.log({n3});\n"
        f"}});\n\n"
        f"console.log({n4});"
    )

    # Correct execution order:
    # 1. Synchronous: n1, n4
    # 2. Microtask queue (Promise.then): n3
    # 3. Macrotask/Task queue (setTimeout): n2
    correct_out = f"{n1}, {n4}, {n3}, {n2}"
    distractor_1 = f"{n1}, {n2}, {n3}, {n4}"  # Linear order
    distractor_2 = f"{n1}, {n4}, {n2}, {n3}"  # Macrotask before microtask
    distractor_3 = f"{n3}, {n1}, {n4}, {n2}"  # Promise before sync

    options_pool = [correct_out, distractor_1, distractor_2, distractor_3]
    rng.shuffle(options_pool)

    keys = ["A", "B", "C", "D"]
    options = {}
    correct_key = "A"
    for i, opt in enumerate(options_pool):
        key = keys[i]
        options[key] = opt
        if opt == correct_out:
            correct_key = key

    question_text = (
        "В каком порядке будут выведены числа в консоль браузера при выполнении следующего JavaScript-кода?"
    )
    explanation = (
        "Сначала синхронно выполняется основной стек вызовов (логи 1 и 4). Затем обрабатывается очередь "
        "микрозадач (Microtask Queue) от Promise.then (лог 3). И только после очистки стека и микрозадач "
        "Event Loop берет задачу из очереди макрозадач (setTimeout, лог 2)."
    )

    return ItemRenderResult(
        family_code="JS_EVENT_LOOP_MICROTASK",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=correct_key,
        explanation=explanation,
        item_format="CODE_OUTPUT",
    )


def generate_react_hook_dependency(seed: int) -> ItemRenderResult:
    """Family: REACT_HOOK_DEPENDENCY.

    Tests React useEffect stale closures, dependency array, and state batching.
    """
    rng = random.Random(seed)
    hook_type = rng.choice(["stale_closure_interval", "state_batching_updater"])
    var_name = rng.choice(["count", "step", "score", "index", "points"])
    init_val = rng.randint(0, 5)

    if hook_type == "stale_closure_interval":
        delay = rng.choice([1000, 500, 2000])
        code = (
            f"function Counter() {{\n"
            f"  const [{var_name}, set{var_name.capitalize()}] = useState({init_val});\n\n"
            f"  useEffect(() => {{\n"
            f"    const timer = setInterval(() => {{\n"
            f"      set{var_name.capitalize()}({var_name} + 1);\n"
            f"    }}, {delay});\n"
            f"    return () => clearInterval(timer);\n"
            f"  }}, []); // пустой массив зависимостей\n\n"
            f"  return <div>{{{var_name}}}</div>;\n"
            f"}}"
        )
        correct_text = f"Покажет {init_val + 1} и больше не изменится"
        distractor_1 = f"Будет расти: {init_val + 1}, {init_val + 2}, {init_val + 3}, …"
        distractor_2 = f"Останется {init_val} и не изменится"
        distractor_3 = "Упадёт с ошибкой «Maximum update depth exceeded»"
    else:  # state_batching_updater
        d1 = rng.randint(1, 3)
        d2 = rng.randint(1, 3)
        d3 = rng.randint(2, 5)
        final_val = init_val + d2 + d3
        code = (
            f"function Counter() {{\n"
            f"  const [{var_name}, set{var_name.capitalize()}] = useState({init_val});\n\n"
            f"  const handleClick = () => {{\n"
            f"    set{var_name.capitalize()}({var_name} + {d1});\n"
            f"    set{var_name.capitalize()}({var_name} + {d2});\n"
            f"    set{var_name.capitalize()}(prev => prev + {d3});\n"
            f"  }};\n\n"
            f"  return <button onClick={{handleClick}}>{{{var_name}}}</button>;\n"
            f"}}"
        )
        correct_text = f"Станет {final_val}"
        # Typical mistakes: every call adds up, the updater wipes the earlier calls, only the last plain call counts
        distractor_1 = f"Станет {init_val + d1 + d2 + d3}"
        distractor_2 = f"Станет {init_val + d3}"
        distractor_3 = f"Станет {init_val + d2}"
        extra = [f"Станет {init_val + d1 + d3}", f"Станет {final_val + 1}", f"Станет {init_val}"]

    fallbacks = extra if hook_type == "state_batching_updater" else []
    options, key = build_options(rng, correct_text, [distractor_1, distractor_2, distractor_3, *fallbacks])
    if hook_type == "stale_closure_interval":
        question_text = f"Что будет показывать компонент после монтирования (начальное `{var_name}` = {init_val})?"
    else:
        question_text = f"Каким станет `{var_name}` после одного клика по кнопке (начальное значение {init_val})?"
    explanation = (
        "В React замыкания в useEffect без зависимостей захватывают значения пропсов/состояния на момент монтирования. "
        "А при вызовах set-функций значения из одного рендера батчатся, тогда как функциональные апдейтеры `prev => ...` "
        "гарантированно получают самое свежее промежуточное состояние очереди обновления."
    )

    return ItemRenderResult(
        family_code="REACT_HOOK_DEPENDENCY",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="CODE_ERROR",
    )


def generate_css_specificity_calc(seed: int) -> ItemRenderResult:
    """Family: CSS_SPECIFICITY_CALC.

    Tests the cascade: !important beats specificity, higher specificity beats order,
    and with equal specificity the later rule wins. Which rule decides varies between instances.
    """
    rng = random.Random(seed)
    colors = ["red", "blue", "green", "purple", "orange", "teal"]
    rng.shuffle(colors)
    c1, c2, c3, c4 = colors[:4]

    el_id = rng.choice(["main-title", "header-text", "hero-banner", "card-label"])
    el_cls = rng.choice(["highlight", "active-text", "primary", "styled"])
    cls_b = rng.choice(["accent", "muted", "wide", "bold"])
    tag = rng.choice(["h1", "p", "div", "span"])
    rule = rng.choice(["important", "specificity", "order"])

    def block(selector: str, color: str, important: bool = False) -> str:
        return f"{selector} {{\n  color: {color}{' !important' if important else ''};\n}}\n\n"

    if rule in ("important", "specificity"):
        css = (block(f"{tag}#{el_id}", c1) + block(f"#{el_id}.{el_cls}", c2)
               + block(f".{el_cls}", c3, important=rule == "important") + block(f"{tag}.{el_cls}", c4))
        html_class = el_cls
        correct_color = c3 if rule == "important" else c2
        explanation = (
            f"`!important` на `.{el_cls}` перекрывает любую специфичность обычных правил, поэтому цвет `{c3}`."
            if rule == "important" else
            f"Без `!important` побеждает самая специфичная запись: `#{el_id}.{el_cls}` (1, 1, 0) "
            f"выше `{tag}#{el_id}` (1, 0, 1), поэтому цвет `{c2}`."
        )
    else:
        # Two single-class rules have equal specificity (0, 1, 0): the later one wins; tag selectors lose to both
        css = (block(tag, c4) + block(f".{el_cls}", c2) + block(f".{cls_b}", c1) + block(f"body {tag}", c3))
        html_class = f"{cls_b} {el_cls}"
        correct_color = c1
        explanation = (
            f"`.{el_cls}` и `.{cls_b}` имеют одинаковую специфичность (0, 1, 0), побеждает правило, "
            f"объявленное позже: `.{cls_b}`, цвет `{c1}`. Порядок классов в атрибуте class не важен, "
            f"а `body {tag}` (0, 0, 2) слабее любого класса."
        )

    code = (
        f"/* CSS Rules */\n{css}"
        f"<!-- HTML -->\n"
        f"<{tag} id=\"{el_id}\" class=\"{html_class}\">Hello World</{tag}>"
    )
    question_text = f"Какого цвета будет текст элемента `<{tag}>` в браузере при применении данных стилей?"
    options, key = build_options(rng, f"`{correct_color}`", [f"`{c}`" for c in (c1, c2, c3, c4)])

    return ItemRenderResult(
        family_code="CSS_SPECIFICITY_CALC",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_dom_event_propagation(seed: int) -> ItemRenderResult:
    """Family: DOM_EVENT_PROPAGATION.

    Tests DOM event phases: capturing, target, bubbling, and stopPropagation.
    """
    rng = random.Random(seed)
    has_stop_prop = rng.choice([False, True])
    n1 = rng.randint(10, 19)
    n2 = rng.randint(20, 29)
    n3 = rng.randint(30, 39)
    n4 = rng.randint(40, 49)

    outer_id = rng.choice(["section", "container", "wrapper", "modal"])
    inner_id = rng.choice(["card", "dialog", "content", "box"])
    btn_id = rng.choice(["btn-submit", "btn-save", "btn-action", "btn-delete"])

    code = (
        f"// DOM: #{outer_id} > #{inner_id} > #{btn_id}\n"
        f"const outer = document.getElementById('{outer_id}');\n"
        f"const inner = document.getElementById('{inner_id}');\n"
        f"const button = document.getElementById('{btn_id}');\n\n"
        f"outer.addEventListener('click', () => console.log({n1}), true);  // capture\n"
        f"outer.addEventListener('click', () => console.log({n2}), false); // bubble\n"
        f"inner.addEventListener('click', (e) => {{\n"
        f"  console.log({n3}); // bubble\n"
        + ("  e.stopPropagation();\n" if has_stop_prop else "")
        + f"}}, false);\n"
        f"button.addEventListener('click', () => console.log({n4}), false); // target bubble\n\n"
        f"// Пользователь кликает по элементу #{btn_id}"
    )

    if has_stop_prop:
        correct_log = f"{n1}, {n4}, {n3}"
        distractors = [f"{n1}, {n4}, {n3}, {n2}", f"{n4}, {n3}, {n2}, {n1}", f"{n1}, {n2}, {n3}, {n4}",
                       f"{n4}, {n3}", f"{n4}, {n3}, {n1}", f"{n1}, {n3}, {n4}"]
    else:
        correct_log = f"{n1}, {n4}, {n3}, {n2}"
        distractors = [f"{n1}, {n4}, {n3}", f"{n4}, {n3}, {n2}, {n1}", f"{n2}, {n3}, {n4}, {n1}",
                       f"{n1}, {n2}, {n4}, {n3}", f"{n4}, {n3}, {n2}"]

    # A random subset of distractors, so the key is not always the only 3-number (or 4-number) sequence
    options, key = build_options(rng, correct_log, rng.sample(distractors, len(distractors)))

    question_text = (
        f"В каком порядке будут выведены числа в консоль при клике пользователя на элемент `#{btn_id}`?"
    )
    explanation = (
        "Событие проходит три фазы: перехват (capturing сверху вниз), цель (target) и всплытие (bubbling снизу вверх). "
        + ("Вызов `e.stopPropagation()` на элементе inner предотвращает дальнейшее всплытие к outer." if has_stop_prop else
           "Слушатели всплытия срабатывают снизу вверх: button -> inner -> outer.")
    )

    return ItemRenderResult(
        family_code="DOM_EVENT_PROPAGATION",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="CODE_OUTPUT",
    )


def generate_ts_generic_keyof(seed: int) -> ItemRenderResult:
    """Family: TS_GENERIC_KEYOF.

    Tests TypeScript generics, keyof constraints, and property type lookup.
    """
    rng = random.Random(seed)
    entities = [
        ("UserProfile", [("id", "number"), ("username", "string"), ("isActive", "boolean"), ("roles", "string[]")]),
        ("Order", [("orderId", "string"), ("totalAmount", "number"), ("isPaid", "boolean"), ("itemsCount", "number")]),
        ("ProductItem", [("sku", "string"), ("price", "number"), ("inStock", "boolean"), ("tags", "string[]")]),
        ("Employee", [("empId", "number"), ("fullName", "string"), ("department", "string"), ("hireDate", "Date")]),
        ("MetricPoint", [("timestamp", "number"), ("sensorId", "string"), ("isValid", "boolean"), ("value", "number")]),
        ("CustomerAccount", [("accountId", "number"), ("balance", "number"), ("isVerified", "boolean"), ("email", "string")]),
        ("DeviceConfig", [("uuid", "string"), ("port", "number"), ("isEnabled", "boolean"), ("firmware", "string")]),
        ("Invoice", [("invoiceNo", "string"), ("amount", "number"), ("settled", "boolean"), ("dueDate", "Date")]),
        ("SessionData", [("sessionId", "string"), ("userId", "number"), ("authorized", "boolean"), ("expiresAt", "number")]),
        ("TaskRecord", [("taskId", "number"), ("title", "string"), ("completed", "boolean"), ("priority", "number")]),
    ]
    entity_name, fields = rng.choice(entities)
    target_field, expected_type = rng.choice(fields)
    fn_name = rng.choice(["getProperty", "readField", "lookupProperty", "extractValue", "selectProp"])
    sample_id = rng.randint(100, 999)

    fields_code = "\n".join(f"  {f}: {t};" for f, t in fields)
    code = (
        f"interface {entity_name} {{\n"
        f"{fields_code}\n"
        f"}}\n\n"
        f"function {fn_name}<T, K extends keyof T>(obj: T, key: K): T[K] {{\n"
        f"  return obj[key];\n"
        f"}}\n\n"
        f"declare const entity: {entity_name}; // entity #{sample_id}\n"
        f"const result = {fn_name}(entity, '{target_field}');"
    )

    correct_val = f"Тип `{expected_type}` — точный тип свойства {entity_name}['{target_field}']"
    d1 = "Тип `any` — дженерики стираются компилятором в рантайме"
    d2 = f"Тип `keyof {entity_name}` — объединение ключей интерфейса"
    d3 = "Тип `unknown` — компилятор требует приведения типа через as"
    d4 = f"Тип `string` — тип имени ключа '{target_field}'"

    distractors = [d for d in [d1, d2, d3, d4] if d != correct_val]
    options, key = build_options(rng, correct_val, distractors)

    question_text = (
        f"Какой тип будет выведен TypeScript компилятором для константы `result` при вызове "
        f"`{fn_name}(entity, '{target_field}')`?"
    )
    explanation = (
        f"Конструкция `T[K]` производит поиск типа свойства (Indexed Access Type). "
        f"Для интерфейса `{entity_name}` по ключу `'{target_field}'` компилятор точно выводит `{expected_type}`."
    )

    return ItemRenderResult(
        family_code="TS_GENERIC_KEYOF",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_react_usecallback_memo(seed: int) -> ItemRenderResult:
    """Family: REACT_USECALLBACK_MEMO.

    Tests React.memo with useCallback reference stability.
    """
    rng = random.Random(seed)
    scenario = rng.choice(["with_memo_and_callback", "with_memo_no_callback", "no_memo_with_callback"])
    k1 = rng.randint(1, 6)
    k2 = rng.randint(1, 6)
    child_name = rng.choice(["Child", "SubCard", "ItemButton", "ActionWidget"])
    cb_name = rng.choice(["handleClick", "handleAction", "onPress", "trigger"])

    if scenario == "with_memo_and_callback":
        total_renders = 1
        code_memo = f"const {child_name} = React.memo(({{ onClick }}) => {{\n  console.log('{child_name}');\n  return <button onClick={{onClick}}>{child_name}</button>;\n}});"
        code_cb = f"  const {cb_name} = useCallback(() => console.log('click'), []);"
    elif scenario == "with_memo_no_callback":
        total_renders = 1 + k1 + k2
        code_memo = f"const {child_name} = React.memo(({{ onClick }}) => {{\n  console.log('{child_name}');\n  return <button onClick={{onClick}}>{child_name}</button>;\n}});"
        code_cb = f"  const {cb_name} = () => console.log('click'); // без useCallback"
    else:  # no_memo_with_callback
        total_renders = 1 + k1 + k2
        code_memo = f"const {child_name} = ({{ onClick }}) => {{\n  console.log('{child_name}');\n  return <button onClick={{onClick}}>{child_name}</button>;\n}};"
        code_cb = f"  const {cb_name} = useCallback(() => console.log('click'), []);"

    code = (
        f"{code_memo}\n\n"
        f"function Parent() {{\n"
        f"  const [c1, setC1] = useState(0);\n"
        f"  const [c2, setC2] = useState(0);\n"
        f"{code_cb}\n"
        f"  return (\n"
        f"    <div>\n"
        f"      <button id=\"btn1\" onClick={{() => setC1(c => c + 1)}}>Inc 1 ({k1}x)</button>\n"
        f"      <button id=\"btn2\" onClick={{() => setC2(c => c + 1)}}>Inc 2 ({k2}x)</button>\n"
        f"      <{child_name} onClick={{{cb_name}}} />\n"
        f"    </div>\n"
        f"  );\n"
        f"}}"
    )

    # Typical mistakes: memo always works, every click re-renders, only clicks counted, one button counted
    candidates = [1, 1 + k1 + k2, k1 + k2, 1 + k1, 1 + k2, 2, k1 + k2 + 2]
    options, key = build_options(rng, str(total_renders), [str(n) for n in candidates])

    question_text = (
        f"Пользователь нажал кнопку `#btn1` {k1} раз(а), затем кнопку `#btn2` {k2} раз(а). "
        f"Сколько раз суммарно отрендерится компонент `{child_name}` (включая начальный рендер)?"
    )
    explanation = (
        "Мемоизация компонентов через `React.memo` предотвращает ререндер только если ссылки на все пропсы стабильны. "
        "Если функция передается без `useCallback`, каждый рендер родителя создает новую ссылку. "
        "Если же дочерний компонент не обернут в `React.memo`, стабильность пропсов не имеет значения."
    )

    return ItemRenderResult(
        family_code="REACT_USECALLBACK_MEMO",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_css_flex_align(seed: int) -> ItemRenderResult:
    """Family: CSS_FLEX_ALIGN.

    Tests Flexbox main axis vs cross axis alignment properties.
    """
    rng = random.Random(seed)
    direction = rng.choice(["row", "column", "row-reverse", "column-reverse"])
    jc = rng.choice(["flex-start", "flex-end", "center", "space-between"])
    ai = rng.choice(["flex-start", "flex-end", "center"])

    code = (
        f".container {{\n"
        f"  display: flex;\n"
        f"  flex-direction: {direction};\n"
        f"  justify-content: {jc};\n"
        f"  align-items: {ai};\n"
        f"}}"
    )

    is_row = "row" in direction
    main_axis_name = "по горизонтали" if is_row else "по вертикали"
    cross_axis_name = "по вертикали" if is_row else "по горизонтали"

    jc_meaning = {
        "flex-start": "прижаты к началу главной оси",
        "flex-end": "прижаты к концу главной оси",
        "center": "по центру главной оси",
        "space-between": "равномерно распределены с прижатием крайних элементов",
    }
    ai_meaning = {
        "flex-start": "прижаты к началу поперечной оси",
        "flex-end": "прижаты к концу поперечной оси",
        "center": "центрированы по поперечной оси",
    }

    correct_val = f"Главная ось ({main_axis_name}): {jc_meaning[jc]}; Поперечная ось ({cross_axis_name}): {ai_meaning[ai]}."

    d1 = f"Главная ось ({cross_axis_name}): {jc_meaning[jc]}; Поперечная ось ({main_axis_name}): {ai_meaning[ai]}."
    d2 = f"Главная ось ({main_axis_name}): {ai_meaning[ai]}; Поперечная ось ({cross_axis_name}): {jc_meaning[jc]}."
    alt_jc = "flex-end" if jc == "flex-start" else "flex-start"
    d3 = f"Главная ось ({main_axis_name}): {jc_meaning[alt_jc]}; Поперечная ось ({cross_axis_name}): {ai_meaning[ai]}."
    alt_ai = "flex-end" if ai == "flex-start" else "flex-start"
    d4 = f"Главная ось ({main_axis_name}): {jc_meaning[jc]}; Поперечная ось ({cross_axis_name}): {ai_meaning[alt_ai]}."

    distractors = [d for d in [d1, d2, d3, d4] if d != correct_val]
    options, key = build_options(rng, correct_val, distractors)

    question_text = (
        f"Как будут выровнены дочерние элементы внутри `.container` при `flex-direction: {direction}`, "
        f"`justify-content: {jc}` и `align-items: {ai}`?"
    )
    explanation = (
        f"`justify-content` ({jc}) управляет главной осью ({main_axis_name} для `{direction}`), "
        f"а `align-items` ({ai}) — поперечной осью ({cross_axis_name})."
    )

    return ItemRenderResult(
        family_code="CSS_FLEX_ALIGN",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_fe_web_security_cors(seed: int) -> ItemRenderResult:
    """Family: FE_WEB_SECURITY_CORS.

    Tests CORS Preflight OPTIONS requests and headers.
    """
    rng = random.Random(seed)
    client_origin = rng.choice([
        "https://app.fintech.ru",
        "https://dashboard.company.io",
        "https://portal.mycloud.dev",
        "https://shop.ecommerce.com",
        "https://cabinet.bank.net",
    ])
    api_domain = rng.choice([
        "https://api.fintech.ru",
        "https://api.company.io",
        "https://gateway.mycloud.dev",
        "https://backend.ecommerce.com",
        "https://api.bank.net",
    ])
    method = rng.choice(["PUT", "DELETE", "PATCH", "POST"])
    custom_header = rng.choice(["X-Api-Key", "Authorization", "X-Request-ID", "X-Tenant-Code"])
    scenario = rng.choice(["preflight_headers", "credentials_wildcard", "cache_max_age"])

    if scenario == "preflight_headers":
        # Ask either about the method or about the custom header, so the family has two different keys here
        asks_method = rng.random() < 0.5
        subject = f"метод {method}" if asks_method else f"заголовок `{custom_header}`"
        needed, other = ("Methods", "Headers") if asks_method else ("Headers", "Methods")
        question_text = (
            f"Фронтенд на origin `{client_origin}` отправляет {method}-запрос с заголовком `{custom_header}` "
            f"к API на `{api_domain}`. Браузер автоматически инициирует предварительный Preflight-запрос. "
            f"Каким HTTP-методом идёт Preflight и какой заголовок ответа должен разрешить {subject}?"
        )
        correct_val = f"OPTIONS; Access-Control-Allow-{needed}"
        d1 = f"OPTIONS; Access-Control-Allow-{other}"
        d2 = "OPTIONS; Access-Control-Request-" + {"Methods": "Method", "Headers": "Headers"}[needed]
        d3 = f"{method}; Access-Control-Allow-{needed}"
        d4 = f"HEAD; Access-Control-Allow-{needed}"
    elif scenario == "credentials_wildcard":
        # The server either answers with the exact origin (allowed) or with '*' (blocked with credentials)
        wildcard = rng.random() < 0.5
        allow_origin = "*" if wildcard else client_origin
        question_text = (
            f"Клиент на `{client_origin}` выполняет запрос к `{api_domain}` с `credentials: 'include'` (отправка cookie). "
            f"Сервер ответил заголовком `Access-Control-Allow-Origin: {allow_origin}` и "
            f"`Access-Control-Allow-Credentials: true`. Как поведет себя браузер?"
        )
        blocked_wildcard = "Ответ скрипту не отдаётся: при credentials нельзя указывать '*'"
        allowed = "Ответ доступен скрипту: источник указан явно, cookie отправлены"
        if wildcard:
            correct_val = blocked_wildcard
            d1 = "Ответ доступен скрипту: '*' разрешает любой источник, и с cookie тоже"
            d2 = "Ответ доступен скрипту, но браузер убрал cookie из запроса"
            d3 = "Браузер повторит запрос методом OPTIONS без cookie"
            d4 = allowed
        else:
            correct_val = allowed
            d1 = "Ответ скрипту не отдаётся: нужен заголовок Access-Control-Allow-Cookies"
            d2 = "Ответ доступен скрипту, но браузер убрал cookie из запроса"
            d3 = "Ответ скрипту не отдаётся: cookie запрещены в cross-origin запросах"
            d4 = blocked_wildcard
    else:  # cache_max_age
        seconds = rng.choice([300, 600, 3600, 86400])
        question_text = (
            f"Для снижения нагрузки на сервер `{api_domain}` требуется закешировать результаты preflight OPTIONS-запросов "
            f"в браузере на `{client_origin}` на {seconds} секунд. Какой заголовок ответа решает эту задачу?"
        )
        correct_val = f"Access-Control-Max-Age: {seconds}"
        d1 = f"Cache-Control: max-age={seconds}"
        d2 = f"Access-Control-Allow-Age: {seconds}"
        d3 = f"Strict-Transport-Security: max-age={seconds}"
        d4 = f"Expires: {seconds}"

    options, key = build_options(rng, correct_val, [d1, d2, d3, d4])
    explanation = (
        "CORS (Cross-Origin Resource Sharing) протокол безопасности регламентирует Preflight OPTIONS запросы, "
        "валидацию заголовков Access-Control-Allow-*, запрет wildcard '*' при передаче учетных данных (Credentials) "
        "и управление кэшированием предзапросов через Access-Control-Max-Age."
    )

    return ItemRenderResult(
        family_code="FE_WEB_SECURITY_CORS",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_js_closure_counter(seed: int) -> ItemRenderResult:
    """Family: JS_CLOSURE_COUNTER.

    Tests JavaScript closure variables and lexical scoping.
    """
    rng = random.Random(seed)
    inc = rng.randint(2, 5)
    code = (
        "function createCounter() {\n"
        "  let count = 0;\n"
        "  return function() {\n"
        f"    count += {inc};\n"
        "    return count;\n"
        "  };\n"
        "}\n\n"
        "const c1 = createCounter();\n"
        "const c2 = createCounter();\n"
        "c1();\n"
        "console.log(c1(), c2());"
    )
    correct_val = f"{inc * 2} {inc} (у каждого вызова createCounter свое независимое лексическое окружение)"
    d1 = f"{inc * 3} {inc * 3}"
    d2 = f"{inc * 2} 0"
    d3 = f"{inc} {inc}"

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
        family_code="JS_CLOSURE_COUNTER",
        seed=seed,
        question_text="Что выведет данный JavaScript-код в консоль?",
        code_snippet=code,
        options=options,
        correct_answer=correct_key,
        explanation="Каждый вызов createCounter() создает независимое лексическое окружение (Lexical Environment) для переменной count.",
        item_format="CODE_OUTPUT",
    )


def generate_react_key_reconciliation(seed: int) -> ItemRenderResult:
    """Family: REACT_KEY_RECONCILIATION.

    Tests why array index as key in React lists causes state bugs during deletion/sorting.
    """
    rng = random.Random(seed)
    action = rng.choice(["удалении первого элемента", "сортировке списка по алфавиту"])
    question_text = (
        f"В компоненте списка React элементы рендерятся через `items.map((item, index) => <Input key={{index}} />)`. "
        f"При {action} внутреннее локальное состояние инпутов (введенный текст) перемешивается или сохраняется не у тех строк. "
        f"В чем причина этой проблемы согласования (Reconciliation)?"
    )
    correct_val = "React сопоставляет элементы Virtual DOM по key; индексы меняют привязку к элементам при сдвиге массива."
    d1 = "React запрещает использование чисел в качестве ключей."
    d2 = "Проблема вызвана асинхронным обновлением состояния компонента Input."
    d3 = "Индексы вызывают переполнение стека рендеринга."

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
        family_code="REACT_KEY_RECONCILIATION",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=correct_key,
        explanation="Использование уникальных стабильных ID в качестве key необходимо для корректного сопоставления экземпляров компонентов React при мутациях списков.",
        item_format="MCQ",
    )


def generate_css_box_sizing(seed: int) -> ItemRenderResult:
    """Family: CSS_BOX_SIZING.

    Tests content-box vs border-box total rendered width calculation.
    """
    rng = random.Random(seed)
    w = rng.randint(15, 30) * 10
    pad = rng.randint(10, 20)
    border = rng.randint(2, 5)
    model = rng.choice(["content-box", "border-box"])

    code = (
        f"div {{\n"
        f"  box-sizing: {model};\n"
        f"  width: {w}px;\n"
        f"  padding: {pad}px;\n"
        f"  border: {border}px solid black;\n"
        f"}}"
    )

    if model == "content-box":
        total_w = w + 2 * pad + 2 * border
        correct_val = f"{total_w}px (ширина контента {w} + padding слева/справа {2 * pad} + border слева/справа {2 * border})"
        d1 = f"{w}px"
        d2 = f"{w + pad + border}px"
        d3 = f"{w - 2 * pad}px"
    else:
        total_w = w
        correct_val = f"{w}px (border-box включает padding и border в общую ширину {w}px)"
        d1 = f"{w + 2 * pad + 2 * border}px"
        d2 = f"{w - 2 * pad}px"
        d3 = f"{w + pad}px"

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
        family_code="CSS_BOX_SIZING",
        seed=seed,
        question_text=f"Какова итоговая полная ширина блока в браузере при `box-sizing: {model}`?",
        code_snippet=code,
        options=options,
        correct_answer=correct_key,
        explanation=f"Расчет блочной модели CSS для {model}: {correct_val}.",
        item_format="MCQ",
    )


def generate_dom_storage_cookie(seed: int) -> ItemRenderResult:
    """Family: DOM_LOCALSTORAGE_VS_COOKIE.

    Tests difference between localStorage, sessionStorage, and HttpOnly cookies.
    """
    rng = random.Random(seed)
    scenario = rng.choice(["refresh_token", "multi_tab", "size_limit"])
    if scenario == "refresh_token":
        question_text = (
            "Для защиты JWT Refresh Token от кражи через межсайтовый скриптинг (XSS-атаки), "
            "какое хранилище является наиболее безопасным согласно рекомендациям OWASP?"
        )
        correct_val = "Cookie с флагом `HttpOnly` и `Secure` (недоступны для чтения из JavaScript через document.cookie)"
        d1 = "localStorage (хранится бессрочно)"
        d2 = "sessionStorage (очищается при закрытии вкладки)"
        d3 = "IndexedDB без шифрования"
    elif scenario == "multi_tab":
        question_text = (
            "Пользователь открыл сайт в двух соседних вкладках одного браузера. Какое хранилище изолировано "
            "отдельно для каждой вкладки и НЕ синхронизирует изменения между ними?"
        )
        correct_val = "sessionStorage (привязано строго к конкретной вкладке / окну браузера)"
        d1 = "localStorage (разделяется между всеми вкладками одного origin)"
        d2 = "document.cookie"
        d3 = "Service Worker Cache"
    else:
        question_text = "Каков типичный максимальный лимит объема данных, разрешенный для хранения одного Cookie в браузере?"
        correct_val = "Около 4 КБ на один cookie"
        d1 = "Около 5 МБ"
        d2 = "Около 50 МБ"
        d3 = "Неограниченно"

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
        family_code="DOM_LOCALSTORAGE_VS_COOKIE",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=correct_key,
        explanation=f"Браузерные хранилища и безопасность: {correct_val}.",
        item_format="MCQ",
    )


def generate_ts_type_guards_narrowing(seed: int) -> ItemRenderResult:
    """Family: TS_TYPE_GUARDS_NARROWING.

    Tests TypeScript user-defined type predicates (arg is Type).
    """
    rng = random.Random(seed)
    code = (
        "interface Fish { swim(): void; }\n"
        "interface Bird { fly(): void; }\n\n"
        "function isFish(pet: Fish | Bird): pet is Fish {\n"
        "  return (pet as Fish).swim !== undefined;\n"
        "}\n\n"
        "function move(pet: Fish | Bird) {\n"
        "  if (isFish(pet)) {\n"
        "    pet.swim(); // Line A\n"
        "  } else {\n"
        "    pet.fly();  // Line B\n"
        "  }\n"
        "}"
    )
    question_text = (
        "Какую роль играет возвращаемый тип `pet is Fish` в сигнатуре функции `isFish`?"
    )
    correct_val = "User-defined Type Guard: сообщает компилятору сузить тип pet до Fish в ветке if и до Bird в ветке else."
    d1 = "Это стандартный синтаксический сахар для логического типа boolean без влияния на компилятор."
    d2 = "Приводит pet к типу Fish в рантайме JavaScript."
    d3 = "Запрещает передавать в функцию объекты типа Bird."

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
        family_code="TS_TYPE_GUARDS_NARROWING",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=correct_key,
        explanation="Пользовательский предикат типа (Type Predicate) `parameterName is Type` позволяет TypeScript безопасно сужать типы в условных конструкциях.",
        item_format="MCQ",
    )


def generate_react_custom_hook(seed: int) -> ItemRenderResult:
    """Family: REACT_CUSTOM_HOOK.

    Tests React rules of custom hooks and state isolation.
    """
    rng = random.Random(seed)
    question_text = (
        "Два независимых React-компонента ComponentA и ComponentB используют один и тот же кастомный хук `useUserData()`. "
        "Как соотносится состояние (state), создаваемое внутри этого хука, между этими двумя компонентами?"
    )
    correct_val = "Каждый компонент получает полностью изолированную собственную копию состояния (хуки шарят логику, а не состояние)."
    d1 = "Состояние становится глобальным и синхронно разделяется между ComponentA и ComponentB."
    d2 = "React выбросит ошибку, так как один хук нельзя вызывать более одного раза."
    d3 = "ComponentB перезапишет состояние ComponentA при монтировании."

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
        family_code="REACT_CUSTOM_HOOK",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=correct_key,
        explanation="Кастомные хуки React инкапсулируют логику работы с состоянием. При каждом вызове хука создается независимый экземпляр состояния компонента.",
        item_format="MCQ",
    )


def generate_fe_performance_debounce(seed: int) -> ItemRenderResult:
    """Family: FE_PERFORMANCE_DEBOUNCE.

    Tests difference between Debounce and Throttle techniques.
    """
    rng = random.Random(seed)
    tech = rng.choice(["Debounce", "Throttle"])
    if tech == "Debounce":
        question_text = (
            "Пользователь быстро вводит текст в поле поисковой строки. Требуется отправить сетевой запрос к API "
            "только после того, как пользователь сделал паузу в наборе текста длительностью не менее 300 мс. "
            "Какая функция высшего порядка решает данную задачу?"
        )
        correct_val = "Debounce (откладывает вызов функции до истечения заданного интервала тишины)"
        d1 = "Throttle (вызывает функцию не чаще одного раза в заданный интервал времени)"
        d2 = "Memoize (кэширует возвращаемые значения)"
        d3 = "Curry (каррирование аргументов)"
    else:
        question_text = (
            "При бесконечной прокрутке страницы слушатель события scroll генерирует сотни вызовов в секунду. "
            "Требуется гарантировать, что функция проверки положения скролла будет вызываться строго не чаще, чем раз в 100 мс. "
            "Какая техника оптимизации применяется?"
        )
        correct_val = "Throttle (ограничивает максимальную частоту вызовов во времени)"
        d1 = "Debounce"
        d2 = "Lazy Loading"
        d3 = "Code Splitting"

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
        family_code="FE_PERFORMANCE_DEBOUNCE",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=correct_key,
        explanation="Debounce ждет паузы в потоке событий; Throttle обеспечивает регулярный вызов с фиксированной периодичностью.",
        item_format="MCQ",
    )


def generate_js_type_coercion_equality(seed: int) -> ItemRenderResult:
    """Family: JS_TYPE_COERCION_EQUALITY.

    Tests JavaScript implicit type coercion and equality comparisons (== vs ===).
    Target grade: INTERN (difficulty b in [-1.8, -1.2]).
    """
    rng = random.Random(seed)
    n1 = rng.randint(1, 9)
    n2 = rng.randint(1, 9)

    pattern = rng.choice(["plus_minus_coercion", "loose_vs_strict_equality", "boolean_empty_coercion"])

    if pattern == "plus_minus_coercion":
        code = (
            f"const a = '{n1}' + {n2};\n"
            f"const b = '{n1}' - {n2};\n"
            f"console.log(a, b);"
        )
        correct_val = f"'{n1}{n2}' {n1 - n2}"
        distractors = [
            f"{n1 + n2} {n1 - n2}",
            f"'{n1}{n2}' NaN",
            f"'{n1}{n2}' '{n1 - n2}'",
            f"{n1 + n2} NaN",
        ]
        explanation = (
            f"Оператор '+' со строкой выполняет конкатенацию: '{n1}' + {n2} -> '{n1}{n2}'. "
            f"Оператор '-' преобразует строку в число: '{n1}' - {n2} -> {n1 - n2}."
        )
    elif pattern == "loose_vs_strict_equality":
        pair = rng.choice([
            ("0 == false", "0 === false", "true", "false"),
            ("'' == false", "'' === false", "true", "false"),
            ("null == undefined", "null === undefined", "true", "false"),
            ("[] == 0", "[] === 0", "true", "false"),
            (f"{n1} == '{n1}'", f"{n1} === '{n1}'", "true", "false"),
            ("NaN === NaN", "NaN == NaN", "false", "false"),
            ("[] == ''", "[] === ''", "true", "false"),
        ])
        expr1, expr2, res1, res2 = pair
        code = (
            f"const x = {expr1};\n"
            f"const y = {expr2};\n"
            f"console.log(x, y);"
        )
        correct_val = f"{res1} {res2}"
        distractors = [d for d in ["true false", "false true", "true true", "false false"] if d != correct_val]
        explanation = (
            f"Оператор нестрогого сравнения '==' выполняет неявное приведение типов ({expr1} -> {res1}), "
            f"тогда как строгое равенство '===' проверяет и тип, и значение без приведения ({expr2} -> {res2})."
        )
    else:  # boolean_empty_coercion
        v1_raw, v1_bool = rng.choice([("''", "false"), ("'hello'", "true"), ("0", "false"), ("[]", "true"), ("{}", "true"), ("null", "false")])
        v2_num = rng.randint(2, 9)
        v3_raw, v3_num = rng.choice([("null", "0"), ("undefined", "NaN"), ("false", "0"), ("true", "1"), ("''", "0"), (f"'{v2_num}'", str(v2_num))])
        code = (
            f"const p = Boolean({v1_raw});\n"
            f"const q = Boolean({v2_num});\n"
            f"const r = Number({v3_raw});\n"
            f"console.log(p, q, r);"
        )
        correct_val = f"{v1_bool} true {v3_num}"
        distractors = [
            f"{v1_bool} false {v3_num}",
            f"{'true' if v1_bool == 'false' else 'false'} true {v3_num}",
            f"{v1_bool} true {'1' if v3_num == '0' else '0'}",
            f"{v1_bool} false NaN",
        ]
        explanation = (
            f"Boolean({v1_raw}) -> {v1_bool}. Положительное число {v2_num} является truthy. "
            f"Number({v3_raw}) -> {v3_num}."
        )

    options, key = build_options(rng, correct_val, distractors)
    # console.log prints strings without quotes, so the options mark strings explicitly
    question_text = (
        "Какие значения выведет `console.log` в этом фрагменте на JavaScript? "
        "В вариантах строки записаны в кавычках, чтобы их можно было отличить от чисел."
    )

    return ItemRenderResult(
        family_code="JS_TYPE_COERCION_EQUALITY",
        seed=seed,
        question_text=question_text,
        code_snippet=code,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="CODE_OUTPUT",
    )


def generate_fe_security_csp(seed: int) -> ItemRenderResult:
    """Family: FE_SECURITY_CSP.

    Tests Content Security Policy (CSP) directives, nonces, strict-dynamic, and XSS mitigations.
    Target grade: SENIOR (difficulty b in [1.2, 1.8]).
    """
    rng = random.Random(seed)
    nonce = f"{rng.randint(100000, 999999):x}"
    cdn = rng.choice(["https://cdn.jsdelivr.net", "https://unpkg.com", "https://cdnjs.cloudflare.com"])
    api_url = rng.choice(["https://api.service.io", "https://backend.app.dev", "https://events.analytics.org", "https://telemetry.io", "https://api.partner.net"])
    scenario = rng.choice(["nonce_violation", "inline_eval_blocked", "connect_src_violation"])
    fn_name = rng.choice(["initAnalytics", "loadApp", "mountWidget", "trackEvent", "renderChart"])
    lib_name = rng.choice(["TemplateEngine", "FastParser", "DynamicEval", "MathCompiler"])

    if scenario == "nonce_violation":
        csp_header = f"Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{nonce}' {cdn};"
        question_text = (
            f"Веб-приложение возвращает HTTP-заголовок безопасности:\n`{csp_header}`\n\n"
            f"Какой из следующих сценариев приведет к блокировке браузером (CSP Violation) и отправке отчета безопасности?"
        )
        # Inline code without the nonce is blocked, whether it is a <script> block or an event handler attribute
        correct_val = rng.choice([
            f"`<script>{fn_name}({{ debug: true }})</script>`",
            f"`<button onclick=\"{fn_name}()\">Старт</button>`",
        ])
        distractor_1 = f"`<script src='{cdn}/lib.js'></script>`"
        distractor_2 = "`<script src='/static/main.js'></script>`"
        distractor_3 = f"`<script nonce='{nonce}'>{fn_name}()</script>`"
    elif scenario == "inline_eval_blocked":
        allows_eval = rng.random() < 0.5
        unsafe_eval = " 'unsafe-eval'" if allows_eval else ""
        csp_header = (
            f"Content-Security-Policy: default-src 'self'; script-src 'self' 'strict-dynamic' 'nonce-{nonce}'{unsafe_eval};"
        )
        question_text = (
            f"В приложении настроена строгая политика CSP на основе нонсов:\n`{csp_header}`\n\n"
            f"Сторонняя библиотека `{lib_name}` пытается вызвать `eval()` для динамической компиляции. Что произойдет в браузере?"
        )
        if allows_eval:
            correct_val = "eval() выполнится: в script-src есть 'unsafe-eval'"
            distractor_1 = "eval() будет заблокирован: 'strict-dynamic' его запрещает"
            distractor_2 = "eval() будет заблокирован: с nonce eval запрещён"
            distractor_3 = "eval() выполнится, но браузер отправит отчёт"
        else:
            correct_val = "eval() будет заблокирован: в script-src нет 'unsafe-eval'"
            distractor_1 = "eval() выполнится: 'strict-dynamic' разрешает такой код"
            distractor_2 = "eval() выполнится, если библиотеку загрузил скрипт с nonce"
            distractor_3 = "eval() выполнится, а браузер лишь отправит отчёт"
    else:  # connect_src_violation
        csp_header = "Content-Security-Policy: default-src 'self'; connect-src 'self' https://api.mycorp.ru;"
        question_text = (
            f"Сервер отдает заголовок CSP:\n`{csp_header}`\n\n"
            f"Какой из запросов фронтенд-приложения браузер заблокирует?"
        )
        endpoint = rng.choice(["v1/telemetry", "events", "v2/metrics", "collect"])
        # Only the host missing from connect-src is blocked; same-origin and listed-host requests pass
        correct_val = f"`fetch('{api_url}/{endpoint}')`"
        distractor_1 = f"`fetch('/api/{endpoint}')`"
        distractor_2 = f"`fetch('https://api.mycorp.ru/{endpoint}')`"
        distractor_3 = "`fetch('https://api.mycorp.ru/v1/health')`"

    options, key = build_options(rng, correct_val, [distractor_1, distractor_2, distractor_3])
    explanation = (
        "Content Security Policy (CSP) блокирует неавторизованные источники загрузки и выполнения ресурсов. "
        "Инлайн-скрипты требуют явного 'unsafe-inline' либо соответствия nonce/хэша. "
        "Использование eval() требует 'unsafe-eval'. Сетевые запросы fetch/XHR контролируются директивой connect-src."
    )

    return ItemRenderResult(
        family_code="FE_SECURITY_CSP",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )



