"""Parameterized generators for Data Science and Machine Learning item families.

Every family computes its key from the generated data, so each seed produces a different
question with a different correct answer: an answer leaked from one instance does not
transfer to the next. Distractors are the results of typical mistakes (wrong formula,
wrong denominator, statistics fitted on the wrong split, and so on).
"""

import math
import random
import sqlite3

import numpy as np

from families.base import ItemRenderResult, build_options


def _fmt(value: float, digits: int = 2) -> str:
    text = f"{value:.{digits}f}"
    # "-0.00" and "0.00" must not become two different options
    return text[1:] if text.startswith("-") and float(text) == 0 else text


def _nudges(value: float, digits: int = 2, steps: tuple[float, ...] = (0.05, -0.05, 0.1, -0.1, 0.15)) -> list[str]:
    """Fallback distractors near the correct value, used only when typical mistakes collide."""
    return [_fmt(value + s, digits) for s in steps]


def _int_nudges(value: int) -> list[str]:
    return [str(value + s) for s in (1, -1, 2, -2, 3) if value + s >= 0]


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


# ==========================================
# Metrics
# ==========================================

def generate_ml_metrics_precision_recall(seed: int) -> ItemRenderResult:
    """Family: ML_METRICS_PRECISION_RECALL.

    Precision, Recall or F1 from a random confusion matrix.
    """
    rng = random.Random(seed)
    tp = rng.randint(30, 90)
    fp = rng.randint(3, 40)
    fn = rng.randint(3, 40)
    tn = rng.randint(100, 400)

    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    f1 = 2 * precision * recall / (precision + recall)
    accuracy = (tp + tn) / (tp + tn + fp + fn)
    specificity = tn / (tn + fp)

    metrics = {"Precision": precision, "Recall": recall, "F1-score": f1}
    name = rng.choice(list(metrics))
    value = metrics[name]
    correct = _fmt(value)

    mistakes = [_fmt(v) for k, v in metrics.items() if k != name] + [_fmt(accuracy), _fmt(specificity)]
    rng.shuffle(mistakes)
    options, key = build_options(rng, correct, mistakes + _nudges(value))

    formulas = {
        "Precision": f"TP / (TP + FP) = {tp} / {tp + fp}",
        "Recall": f"TP / (TP + FN) = {tp} / {tp + fn}",
        "F1-score": f"2·P·R / (P + R) при P = {_fmt(precision, 3)}, R = {_fmt(recall, 3)}",
    }
    question_text = (
        "Бинарный классификатор на тестовой выборке дал матрицу ошибок:\n"
        f"TP = {tp}, FP = {fp}, FN = {fn}, TN = {tn}.\n\n"
        f"Чему равен {name}? Ответ округлён до сотых."
    )
    explanation = (
        f"{name} = {formulas[name]} ≈ {correct}. Остальные варианты получаются при подстановке "
        "другой метрики той же матрицы: precision, recall, F1, accuracy или specificity."
    )
    return ItemRenderResult(
        family_code="ML_METRICS_PRECISION_RECALL",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_ml_roc_auc_vs_pr_auc(seed: int) -> ItemRenderResult:
    """Family: ML_ROC_AUC_VS_PR_AUC.

    Precision at a ROC operating point under strong class imbalance: a small FPR still
    produces many false positives, which ROC hides and PR exposes.
    """
    rng = random.Random(seed)
    domain, positive, negative = rng.choice([
        ("антифрод-модель", "мошеннических транзакций", "обычных"),
        ("модель скрининга", "больных пациентов", "здоровых"),
        ("спам-фильтр", "спам-писем", "обычных писем"),
        ("модель оттока", "ушедших клиентов", "оставшихся"),
    ])
    n_pos = rng.choice([40, 50, 80, 100, 120, 200])
    ratio = rng.choice([10, 20, 25, 50, 100])
    n_neg = n_pos * ratio
    tpr = rng.choice([0.70, 0.75, 0.80, 0.85, 0.90, 0.95])
    fpr = rng.choice([0.01, 0.02, 0.03, 0.05, 0.08, 0.10])

    tp = round(tpr * n_pos)
    fp = round(fpr * n_neg)
    precision = tp / (tp + fp)
    accuracy = (tp + n_neg - fp) / (n_pos + n_neg)
    fp_wrong_base = round(fpr * n_pos)  # FPR applied to the positive class size
    precision_wrong_base = tp / (tp + fp_wrong_base) if fp_wrong_base else 1.0

    correct = _fmt(precision)
    mistakes = [_fmt(tpr), _fmt(1 - fpr), _fmt(accuracy), _fmt(precision_wrong_base)]
    options, key = build_options(rng, correct, mistakes + _nudges(precision))

    question_text = (
        f"Для {domain} выбрана рабочая точка на ROC-кривой: TPR = {tpr:.2f}, FPR = {fpr:.2f}. "
        f"В тестовой выборке {n_pos} {positive} и {n_neg} {negative}.\n\n"
        "Какая доля объектов, помеченных моделью как положительные, действительно положительная "
        "(precision)? Ответ округлён до сотых."
    )
    explanation = (
        f"TP = TPR·P = {tpr:.2f}·{n_pos} = {tp}; FP = FPR·N = {fpr:.2f}·{n_neg} = {fp}; "
        f"precision = {tp} / ({tp} + {fp}) ≈ {correct}. При дисбалансе 1:{ratio} даже малый FPR даёт "
        "много ложных срабатываний: ROC-кривая выглядит хорошо, а PR-кривая показывает реальную точность."
    )
    return ItemRenderResult(
        family_code="ML_ROC_AUC_VS_PR_AUC",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_ml_roc_auc_pairwise(seed: int) -> ItemRenderResult:
    """Family: ML_ROC_AUC_PAIRWISE.

    ROC-AUC computed by hand as the share of correctly ordered (positive, negative) pairs,
    with ties counted as one half.
    """
    rng = random.Random(seed)
    grid = [round(0.05 * k, 2) for k in range(2, 20)]
    while True:
        pos = [rng.choice(grid) for _ in range(rng.choice([3, 4]))]
        neg = [rng.choice(grid) for _ in range(rng.choice([3, 4]))]
        pairs = len(pos) * len(neg)
        wins = sum(1 for p in pos for n in neg if p > n)
        ties = sum(1 for p in pos for n in neg if p == n)
        auc = (wins + 0.5 * ties) / pairs
        if 0.55 <= auc <= 0.95:
            break

    accuracy_05 = (sum(p >= 0.5 for p in pos) + sum(n < 0.5 for n in neg)) / (len(pos) + len(neg))
    correct = _fmt(auc)
    mistakes = [
        _fmt(wins / pairs),            # ties ignored
        _fmt((wins + ties) / pairs),   # ties counted as wins
        _fmt(accuracy_05),             # accuracy at threshold 0.5
        _fmt(1 - auc),                 # pairs counted the other way round
    ]
    options, key = build_options(rng, correct, mistakes + _nudges(auc))

    rows = [(s, 1) for s in pos] + [(s, 0) for s in neg]
    rng.shuffle(rows)
    table = "\n".join(f"  объект {i + 1}: оценка {s:.2f}, класс {y}" for i, (s, y) in enumerate(rows))
    question_text = (
        "Модель выдала оценки на тестовой выборке:\n"
        f"{table}\n\n"
        "Чему равен ROC-AUC? Ответ округлён до сотых."
    )
    explanation = (
        f"ROC-AUC равен доле пар (положительный, отрицательный), где положительный объект получил большую оценку; "
        f"совпадения считаются за половину. Пар {pairs}, верно упорядочено {wins}, совпадений {ties}: "
        f"({wins} + 0.5·{ties}) / {pairs} ≈ {correct}."
    )
    return ItemRenderResult(
        family_code="ML_ROC_AUC_PAIRWISE",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_ml_regression_errors(seed: int) -> ItemRenderResult:
    """Family: ML_REGRESSION_ERRORS.

    MAE, MSE or RMSE for a handful of predictions.
    """
    rng = random.Random(seed)
    n = rng.choice([4, 5])
    y_true = [rng.randint(10, 60) for _ in range(n)]
    while True:
        errors = [rng.randint(-6, 6) for _ in range(n)]
        if sum(e != 0 for e in errors) >= 2:
            break
    y_pred = [t + e for t, e in zip(y_true, errors)]

    mae = sum(abs(e) for e in errors) / n
    mse = sum(e * e for e in errors) / n
    rmse = math.sqrt(mse)
    bias = sum(errors) / n
    metrics = {"MAE": mae, "MSE": mse, "RMSE": rmse}
    name = rng.choice(list(metrics))
    value = metrics[name]

    correct = _fmt(value)
    mistakes = [_fmt(v) for k, v in metrics.items() if k != name] + [_fmt(bias), _fmt(sum(abs(e) for e in errors))]
    rng.shuffle(mistakes)
    options, key = build_options(rng, correct, mistakes + _nudges(value, steps=(0.5, -0.5, 1.0, -1.0, 1.5)))

    question_text = (
        "Модель регрессии сделала прогнозы:\n"
        f"  y_true = {y_true}\n"
        f"  y_pred = {y_pred}\n\n"
        f"Чему равна метрика {name}? Ответ округлён до сотых."
    )
    explanation = (
        f"Ошибки y_pred − y_true = {errors}. MAE = среднее |e| = {_fmt(mae)}, "
        f"MSE = среднее e² = {_fmt(mse)}, RMSE = √MSE = {_fmt(rmse)}. Ответ: {name} = {correct}."
    )
    return ItemRenderResult(
        family_code="ML_REGRESSION_ERRORS",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


# ==========================================
# Feature engineering
# ==========================================

_LEAK_LINES = {
    "scaler": ("X = StandardScaler().fit_transform(X)", "среднее и дисперсия посчитаны по всем данным, включая тест"),
    "imputer": ('X = SimpleImputer(strategy="{strategy}").fit_transform(X)', "статистика для заполнения пропусков посчитана по всем данным, включая тест"),
    "selectk": ("X = SelectKBest(f_classif, k={k}).fit_transform(X, y)", "признаки отобраны по связи с таргетом на всех данных, включая тест"),
    "smote": ("X, y = SMOTE(random_state={rs}).fit_resample(X, y)", "синтетические объекты построены по соседям из будущего теста, и их копии попадут в обе части"),
    "target_enc": ('df["{cat}_mean_target"] = df.groupby("{cat}")["{target}"].transform("mean")', "среднее таргета по категории посчитано по всем строкам, включая тестовые"),
}


def generate_ml_feature_data_leakage(seed: int) -> ItemRenderResult:
    """Family: ML_FEATURE_DATA_LEAKAGE.

    A short training script with exactly one line that leaks test information into training.
    The candidate names the line; the leak type, its position and the surrounding code vary.
    """
    rng = random.Random(seed)
    leak = rng.choice(list(_LEAK_LINES))
    target = rng.choice(["churn", "is_fraud", "default", "converted", "label"])
    cat = rng.choice(["city", "region", "segment", "channel"])
    rs = rng.choice([0, 7, 42, 2024])
    leak_template, leak_reason = _LEAK_LINES[leak]
    leak_line = leak_template.format(
        strategy=rng.choice(["mean", "median"]), k=rng.choice([10, 20, 30]), rs=rs, cat=cat, target=target,
    )

    header = rng.sample(["RANDOM_STATE = 42", 'warnings.filterwarnings("ignore")', 'pd.set_option("display.width", 120)'],
                        k=rng.randint(0, 2))
    load = f'df = pd.read_csv("{rng.choice(["clients.csv", "train.csv", "events.parquet.csv", "data/raw.csv"])}")'
    clean = rng.choice([None, "df = df.drop_duplicates()", f'df = df.dropna(subset=["{target}"])'])
    drop_cols = f'["{target}", "{cat}"]' if leak == "target_enc" else f'["{target}"]'
    xy = f'X, y = df.drop(columns={drop_cols}), df["{target}"]'
    split = f"X_train, X_test, y_train, y_test = train_test_split(X, y, test_size={rng.choice([0.2, 0.25, 0.3])}, random_state={rs})"
    prep_cls = rng.choice([c for c in ("StandardScaler", "MinMaxScaler", "SimpleImputer")
                           if not (leak == "scaler" and c == "StandardScaler") and not (leak == "imputer" and c == "SimpleImputer")])
    use_prep = leak != "target_enc" and rng.random() < 0.6
    model = f"model = {rng.choice(['LogisticRegression', 'RandomForestClassifier', 'GradientBoostingClassifier'])}().fit(X_train, y_train)"
    evaluate = f"print({rng.choice(['roc_auc_score', 'f1_score', 'accuracy_score'])}(y_test, model.predict(X_test)))"

    lines = header + [load]
    if leak == "target_enc":
        df_level = [leak_line] + ([clean] if clean else [])
        rng.shuffle(df_level)
        lines += df_level + [xy]
    else:
        lines += ([clean] if clean else []) + [xy, leak_line]
    lines.append(split)
    if use_prep:
        lines += [f"prep = {prep_cls}().fit(X_train)", "X_train, X_test = prep.transform(X_train), prep.transform(X_test)"]
    lines += [model, evaluate]

    numbered = {i + 1: line for i, line in enumerate(lines)}
    leak_no = lines.index(leak_line) + 1

    def option(no: int) -> str:
        return f"Строка {no}: {numbered[no]}"

    decoys = [lines.index(split) + 1, lines.index(model) + 1, lines.index(xy) + 1]
    if use_prep:
        decoys.insert(0, lines.index(f"prep = {prep_cls}().fit(X_train)") + 1)
    if clean:
        decoys.insert(0, lines.index(clean) + 1)
    options, key = build_options(rng, option(leak_no), [option(no) for no in decoys])

    code_snippet = "\n".join(f"{no:>2}  {line}" for no, line in numbered.items())
    question_text = (
        "В скрипте обучения ровно одна строка приводит к утечке данных из тестовой выборки в обучение. "
        "Импорты опущены. Какая это строка?"
    )
    explanation = (
        f"Утечка в строке {leak_no}: {leak_reason}. Любые статистики (масштаб, заполнение пропусков, отбор "
        "признаков, кодирование таргетом, оверсэмплинг) обучаются только на train после разбиения. "
        "Удаление дублей или строк без таргета не использует статистик и утечкой не является."
    )
    return ItemRenderResult(
        family_code="ML_FEATURE_DATA_LEAKAGE",
        seed=seed,
        question_text=question_text,
        code_snippet=code_snippet,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="CODE_ERROR",
    )


def generate_ml_cross_validation_time(seed: int) -> ItemRenderResult:
    """Family: ML_CROSS_VALIDATION_TIME.

    Train size on the k-th split of sklearn's TimeSeriesSplit, where the remainder of
    n_samples / (n_splits + 1) goes to the first training window.
    """
    rng = random.Random(seed)
    n_splits = rng.choice([3, 4, 5, 6])
    while True:
        n_samples = rng.randint(60, 600)
        if n_samples % (n_splits + 1):
            break
    fold = rng.randint(1, n_splits)
    test_size = n_samples // (n_splits + 1)
    train_size = n_samples - (n_splits - fold + 1) * test_size

    correct = str(train_size)
    mistakes = [
        str(fold * test_size),                     # remainder forgotten
        str(n_samples - n_samples // n_splits),    # KFold train size
        str(train_size + test_size),               # test window counted into train
        str(n_samples - test_size),                # every split trains on all but one window
    ]
    options, key = build_options(rng, correct, mistakes + _int_nudges(train_size))

    question_text = (
        f"Временной ряд из {n_samples} наблюдений валидируется через "
        f"`TimeSeriesSplit(n_splits={n_splits})` из scikit-learn (test_size и gap по умолчанию).\n\n"
        f"Сколько наблюдений попадёт в обучающую часть на разбиении № {fold} (нумерация с 1)?"
    )
    explanation = (
        f"test_size = {n_samples} // ({n_splits} + 1) = {test_size}. Тестовые окна занимают последние "
        f"{n_splits}·{test_size} наблюдений, а остаток деления уходит в первое обучающее окно. "
        f"На разбиении № {fold} обучение — всё до начала теста: {n_samples} − ({n_splits} − {fold} + 1)·{test_size} = {train_size}."
    )
    return ItemRenderResult(
        family_code="ML_CROSS_VALIDATION_TIME",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_ml_standard_scaler(seed: int) -> ItemRenderResult:
    """Family: ML_STANDARD_SCALER.

    StandardScaler fitted on train transforms a new value (population std, ddof=0).
    """
    rng = random.Random(seed)
    while True:
        train = [rng.randint(0, 20) for _ in range(4)]
        if len(set(train)) >= 3:
            break
    x_new = rng.randint(0, 30)
    mean = sum(train) / len(train)
    std0 = math.sqrt(sum((v - mean) ** 2 for v in train) / len(train))
    std1 = math.sqrt(sum((v - mean) ** 2 for v in train) / (len(train) - 1))
    z = (x_new - mean) / std0

    with_test = train + [x_new]
    mean_all = sum(with_test) / len(with_test)
    std_all = math.sqrt(sum((v - mean_all) ** 2 for v in with_test) / len(with_test))

    correct = _fmt(z)
    mistakes = [
        _fmt((x_new - mean) / std1),                          # ddof=1 like pandas .std()
        _fmt((x_new - mean_all) / std_all),                   # scaler fitted with the test value
        _fmt((x_new - min(train)) / (max(train) - min(train))),  # MinMax instead of standardisation
        _fmt((x_new - mean) / std0 ** 2),                     # divided by variance
    ]
    options, key = build_options(rng, correct, mistakes + _nudges(z, steps=(0.1, -0.1, 0.2, -0.2, 0.3)))

    question_text = (
        f"`StandardScaler` из scikit-learn обучен на признаке обучающей выборки: {train}.\n\n"
        f"Во что он преобразует значение {x_new} из тестовой выборки? Ответ округлён до сотых."
    )
    explanation = (
        f"mean = {_fmt(mean)}, std (ddof=0, как в StandardScaler) = {_fmt(std0, 3)}; "
        f"z = ({x_new} − {_fmt(mean)}) / {_fmt(std0, 3)} ≈ {correct}. Статистики берутся только из train; "
        "pandas .std() по умолчанию даёт ddof=1, а StandardScaler — нет."
    )
    return ItemRenderResult(
        family_code="ML_STANDARD_SCALER",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


_CATEGORIES = {
    "city": ["Москва", "Казань", "Томск", "Самара", "Пермь", "Омск"],
    "device": ["ios", "android", "web", "desktop", "tv"],
    "plan": ["free", "basic", "pro", "team", "enterprise"],
    "channel": ["seo", "ads", "referral", "email", "social", "offline"],
}


def generate_ml_one_hot_width(seed: int) -> ItemRenderResult:
    """Family: ML_ONE_HOT_WIDTH.

    Number of columns after pd.get_dummies with or without drop_first.
    """
    rng = random.Random(seed)
    numeric = rng.sample(["age", "income", "tenure_months", "score", "visits", "balance"], k=rng.randint(1, 4))
    cat_cols = rng.sample(list(_CATEGORIES), k=rng.randint(1, 2))
    values = {c: rng.sample(_CATEGORIES[c], k=rng.randint(2, len(_CATEGORIES[c]))) for c in cat_cols}
    drop_first = rng.random() < 0.5

    cards = [len(values[c]) for c in cat_cols]
    width = len(numeric) + sum(k - int(drop_first) for k in cards)
    other_drop = len(numeric) + sum(k - int(not drop_first) for k in cards)

    correct = str(width)
    mistakes = [
        str(other_drop),                                   # drop_first misread
        str(sum(k - int(drop_first) for k in cards)),      # numeric columns forgotten
        str(len(numeric) + len(cat_cols)),                 # nothing encoded
        str(width + len(cat_cols)),                        # original categorical columns kept
    ]
    options, key = build_options(rng, correct, mistakes + _int_nudges(width))

    uniques = "\n".join(f"  {c}: {', '.join(values[c])}" for c in cat_cols)
    code_snippet = (
        f"# столбцы df: {', '.join(numeric + cat_cols)}\n"
        f"encoded = pd.get_dummies(df, columns={cat_cols}, drop_first={drop_first})\n"
        "print(encoded.shape[1])"
    )
    question_text = (
        f"В DataFrame числовые столбцы {', '.join(numeric)} и категориальные {', '.join(cat_cols)}. "
        f"Уникальные значения категориальных столбцов:\n{uniques}\n\nЧто выведет код?"
    )
    explanation = (
        f"Числовые столбцы остаются ({len(numeric)}), каждый категориальный заменяется на k "
        f"{'− 1 ' if drop_first else ''}столбцов, где k — число категорий ({', '.join(map(str, cards))}). "
        f"Итого {width}."
    )
    return ItemRenderResult(
        family_code="ML_ONE_HOT_WIDTH",
        seed=seed,
        question_text=question_text,
        code_snippet=code_snippet,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="CODE_OUTPUT",
    )


# ==========================================
# Models
# ==========================================

# (estimator, parameter, values ordered from the simplest model to the most complex one)
_COMPLEXITY_GRIDS = [
    ("DecisionTreeClassifier", "max_depth", [2, 3, 4, 6, 8, 10, 12, 16]),
    ("Ridge", "alpha", [300, 100, 30, 10, 3, 1, 0.3, 0.1]),
    ("KNeighborsClassifier", "n_neighbors", [75, 50, 30, 20, 10, 5, 3, 1]),
    ("GradientBoostingClassifier", "n_estimators", [10, 25, 50, 100, 200, 400, 800, 1600]),
]


def generate_ml_overfitting_regularization(seed: int) -> ItemRenderResult:
    """Family: ML_OVERFITTING_REGULARIZATION.

    Pick the hyperparameter value from a validation curve: train error keeps falling with
    complexity while validation error is U-shaped.
    """
    rng = random.Random(seed)
    estimator, param, grid = rng.choice(_COMPLEXITY_GRIDS)
    start = rng.randint(0, len(grid) - 6)
    values = grid[start:start + 6]
    best = rng.randint(1, 4)

    train_err = []
    level = rng.uniform(22.0, 30.0)
    for _ in values:
        train_err.append(round(level, 1))
        level -= rng.uniform(2.5, 5.5)
        level = max(level, 0.5)
    v_min = rng.uniform(train_err[best] + 1.5, train_err[best] + 5.0)
    val_err = [round(v_min + rng.uniform(2.2, 3.2) * abs(i - best) ** 1.3, 1) for i in range(len(values))]
    # an underfit model still does not score better on validation than on train
    val_err = [max(v, round(t + rng.uniform(0.4, 1.2), 1)) for v, t in zip(val_err, train_err)]

    def option(i: int) -> str:
        return f"{param} = {values[i]}"

    gaps = [v - t for v, t in zip(val_err, train_err)]
    mistakes = [
        option(train_err.index(min(train_err))),   # best on train
        option(gaps.index(min(gaps))),             # smallest train/validation gap
        option(len(values) - 1),                   # most complex model
        option(0),                                 # most regularised model
    ]
    options, key = build_options(rng, option(best), mistakes + [option(best - 1), option(best + 1)])

    order = list(range(len(values)))
    if rng.random() < 0.5:
        order.reverse()
    table = "\n".join(f"  {param} = {values[i]:<6} ошибка на train {train_err[i]:>4}%, на валидации {val_err[i]:>4}%"
                      for i in order)
    question_text = (
        f"Подбор гиперпараметра {param} для {estimator} дал такие доли ошибок:\n{table}\n\n"
        "Какое значение стоит выбрать для итоговой модели?"
    )
    explanation = (
        f"Выбирается минимум ошибки на валидации: {option(best)} ({val_err[best]}%). Дальнейшее усложнение "
        "снижает ошибку на train, но растит её на валидации — это переобучение; более простые модели "
        "недообучены. Маленький разрыв train/валидация сам по себе не цель."
    )
    return ItemRenderResult(
        family_code="ML_OVERFITTING_REGULARIZATION",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def _gini(counts: list[int]) -> float:
    total = sum(counts)
    return 1.0 - sum((c / total) ** 2 for c in counts)


def _entropy(counts: list[int]) -> float:
    total = sum(counts)
    return -sum((c / total) * math.log2(c / total) for c in counts if c)


def generate_ml_decision_tree_split(seed: int) -> ItemRenderResult:
    """Family: ML_DECISION_TREE_SPLIT.

    Weighted Gini impurity of a split, or the impurity decrease it gives.
    """
    rng = random.Random(seed)
    while True:
        left = [rng.randint(0, 30), rng.randint(0, 30)]
        right = [rng.randint(0, 30), rng.randint(0, 30)]
        parent = [left[0] + right[0], left[1] + right[1]]
        if min(sum(left), sum(right)) >= 4 and sum(left) != sum(right) and min(parent) >= 3:
            break
    n, n_l, n_r = sum(parent), sum(left), sum(right)
    g_l, g_r, g_p = _gini(left), _gini(right), _gini(parent)
    weighted = n_l / n * g_l + n_r / n * g_r
    unweighted = (g_l + g_r) / 2
    weighted_entropy = n_l / n * _entropy(left) + n_r / n * _entropy(right)

    ask_decrease = rng.random() < 0.5
    if ask_decrease:
        value = g_p - weighted
        mistakes = [_fmt(weighted, 3), _fmt(g_p - unweighted, 3), _fmt(_entropy(parent) - weighted_entropy, 3), _fmt(g_p, 3)]
        ask = "На сколько уменьшится Gini impurity после этого разбиения (родитель минус взвешенная сумма детей)?"
    else:
        value = weighted
        mistakes = [_fmt(unweighted, 3), _fmt(g_p, 3), _fmt(weighted_entropy, 3), _fmt(g_p - weighted, 3)]
        ask = "Чему равна взвешенная Gini impurity дочерних узлов?"
    correct = _fmt(value, 3)
    options, key = build_options(rng, correct, mistakes + _nudges(value, 3, (0.02, -0.02, 0.04, -0.04, 0.06)))

    question_text = (
        f"Узел дерева содержит {parent[0]} объектов класса 0 и {parent[1]} объектов класса 1. "
        f"Разбиение отправляет влево {left[0]} и {left[1]}, вправо {right[0]} и {right[1]} объектов "
        f"соответственно.\n\n{ask} Ответ округлён до тысячных."
    )
    explanation = (
        f"Gini = 1 − Σp². Gini(лево) = {_fmt(g_l, 3)}, Gini(право) = {_fmt(g_r, 3)}, Gini(родитель) = {_fmt(g_p, 3)}. "
        f"Взвешенная: {n_l}/{n}·{_fmt(g_l, 3)} + {n_r}/{n}·{_fmt(g_r, 3)} = {_fmt(weighted, 3)}; "
        f"уменьшение: {_fmt(g_p, 3)} − {_fmt(weighted, 3)} = {_fmt(g_p - weighted, 3)}."
    )
    return ItemRenderResult(
        family_code="ML_DECISION_TREE_SPLIT",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_ml_knn_neighbors(seed: int) -> ItemRenderResult:
    """Family: ML_KNN_NEIGHBORS.

    The three nearest neighbours of a query point under Euclidean distance.
    """
    rng = random.Random(seed)
    while True:
        cells = rng.sample([(x, y) for x in range(10) for y in range(10)], k=7)
        query, points = cells[0], cells[1:]
        names = [f"P{i + 1}" for i in range(len(points))]
        d_euc = {nm: math.dist(p, query) for nm, p in zip(names, points)}
        ranked = sorted(names, key=lambda nm: d_euc[nm])
        # the 3rd and 4th neighbours must not tie, otherwise the answer is ambiguous
        if d_euc[ranked[3]] - d_euc[ranked[2]] > 1e-9:
            break

    def as_set(items: list[str]) -> str:
        return ", ".join(sorted(items, key=lambda nm: int(nm[1:])))

    pts = dict(zip(names, points))
    d_man = sorted(names, key=lambda nm: (abs(pts[nm][0] - query[0]) + abs(pts[nm][1] - query[1]), nm))
    d_x = sorted(names, key=lambda nm: (abs(pts[nm][0] - query[0]), nm))
    mistakes = [
        as_set(d_man[:3]),                       # Manhattan distance
        as_set(d_x[:3]),                         # only one coordinate compared
        as_set(ranked[:2] + [ranked[3]]),        # off by one in the ranking
        as_set(ranked[-3:]),                     # farthest instead of nearest
    ]
    fallbacks = [as_set(rng.sample(names, 3)) for _ in range(10)]
    options, key = build_options(rng, as_set(ranked[:3]), mistakes + fallbacks)

    listing = ", ".join(f"{nm} = {pts[nm]}" for nm in names)
    question_text = (
        f"Обучающие точки: {listing}.\n\n"
        f"Какие точки станут соседями запроса Q = {query} для kNN с k = 3 и евклидовым расстоянием?"
    )
    explanation = (
        "Евклидовы расстояния до Q: "
        + ", ".join(f"{nm} = {d_euc[nm]:.2f}" for nm in ranked)
        + f". Три ближайшие: {as_set(ranked[:3])}."
    )
    return ItemRenderResult(
        family_code="ML_KNN_NEIGHBORS",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_ml_logreg_probability(seed: int) -> ItemRenderResult:
    """Family: ML_LOGREG_PROBABILITY.

    Predicted probability of logistic regression for given weights, bias and features.
    """
    rng = random.Random(seed)
    weight_grid = [w / 2 for w in range(-4, 5) if w]
    while True:
        w = [rng.choice(weight_grid), rng.choice(weight_grid)]
        b = rng.choice([-1.5, -1.0, -0.5, 0.5, 1.0, 1.5])
        x = [rng.randint(-3, 3), rng.randint(-3, 3)]
        dot = w[0] * x[0] + w[1] * x[1]
        z = dot + b
        if 0.3 <= abs(z) <= 3.5 and abs(dot) >= 0.3:
            break
    p = _sigmoid(z)

    correct = _fmt(p)
    mistakes = [
        _fmt(_sigmoid(dot)),       # bias forgotten
        _fmt(1 - p),               # probability of the other class
        _fmt(_sigmoid(dot - b)),   # bias sign flipped
    ]
    options, key = build_options(rng, correct, mistakes + _nudges(p))

    question_text = (
        f"Логистическая регрессия имеет веса w = ({w[0]}, {w[1]}) и смещение b = {b}. "
        f"Для объекта x = ({x[0]}, {x[1]}) найдите вероятность класса 1. Ответ округлён до сотых."
    )
    explanation = (
        f"z = w·x + b = {w[0]}·{x[0]} + {w[1]}·{x[1]} + {b} = {z:g}; "
        f"P(y=1) = σ(z) = 1 / (1 + e^(−z)) ≈ {correct}."
    )
    return ItemRenderResult(
        family_code="ML_LOGREG_PROBABILITY",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_ml_gradient_descent_lr(seed: int) -> ItemRenderResult:
    """Family: ML_GRADIENT_DESCENT_LR.

    Gradient descent on f(w) = a·(w − c)²: either the weight after two steps, or the
    largest learning rate that still converges (lr < 1/a).
    """
    rng = random.Random(seed)
    if rng.random() < 0.6:
        a = rng.choice([0.5, 1.0, 2.0])
        c = rng.randint(-3, 3)
        w0 = rng.choice([v for v in range(-6, 7) if v != c])
        lr = rng.choice([0.05, 0.1, 0.2, 0.25, 0.4])
        factor = 1 - 2 * a * lr
        w2 = c + factor ** 2 * (w0 - c)
        correct = _fmt(w2)
        mistakes = [
            _fmt(c + factor * (w0 - c)),                 # one step only
            _fmt(c + (1 - a * lr) ** 2 * (w0 - c)),      # derivative without the factor 2
            _fmt(c + (1 + 2 * a * lr) ** 2 * (w0 - c)),  # step along the gradient
        ]
        options, key = build_options(rng, correct, mistakes + _nudges(w2, steps=(0.5, -0.5, 1.0, -1.0, 0.25)))
        question_text = (
            f"Функция потерь f(w) = {a:g}·(w − {c})². Градиентный спуск стартует из w₀ = {w0} "
            f"с learning rate = {lr}. Чему равен w после двух шагов? Ответ округлён до сотых."
        )
        explanation = (
            f"f'(w) = {2 * a:g}·(w − {c}), шаг: w ← w − lr·f'(w), то есть (w − {c}) умножается на "
            f"1 − 2·{a:g}·{lr} = {factor:g} за шаг. После двух шагов: {c} + {factor:g}²·({w0} − {c}) = {correct}."
        )
    else:
        a = rng.choice([0.5, 1.25, 2.0, 2.5, 4.0, 5.0, 8.0, 10.0])
        c = rng.randint(-3, 3)
        limit = 1 / a

        def fmt_lr(v: float) -> str:
            return f"lr < {round(v, 4):g}"

        correct = fmt_lr(limit)
        mistakes = [fmt_lr(2 / a), fmt_lr(1 / (2 * a)), fmt_lr(1 / a ** 2), fmt_lr(4 / a)]
        options, key = build_options(rng, correct, mistakes)
        question_text = (
            f"Градиентный спуск минимизирует f(w) = {a:g}·(w − {c})² с постоянным learning rate. "
            "При каких lr > 0 он сходится к минимуму из любой стартовой точки?"
        )
        explanation = (
            f"Шаг умножает (w − {c}) на 1 − 2·{a:g}·lr. Сходимость при |1 − {2 * a:g}·lr| < 1, "
            f"то есть 0 < lr < 1/{a:g} = {round(limit, 4):g}. При больших lr итерации раскачиваются и расходятся."
        )
    return ItemRenderResult(
        family_code="ML_GRADIENT_DESCENT_LR",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


# ==========================================
# Data processing
# ==========================================

def generate_ml_embeddings_cosine(seed: int) -> ItemRenderResult:
    """Family: ML_EMBEDDINGS_COSINE.

    Rank documents by cosine similarity when the dot product would pick a different one
    because of a larger vector norm.
    """
    rng = random.Random(seed)
    while True:
        q = np.array([rng.randint(-3, 5) for _ in range(3)])
        docs = [np.array([rng.randint(-3, 9) for _ in range(3)]) for _ in range(4)]
        if not q.any() or any(not d.any() for d in docs):
            continue
        cos = [float(q @ d / (np.linalg.norm(q) * np.linalg.norm(d))) for d in docs]
        dot = [float(q @ d) for d in docs]
        best = int(np.argmax(cos))
        ranked_cos = sorted(cos, reverse=True)
        if int(np.argmax(dot)) != best and ranked_cos[0] - ranked_cos[1] >= 0.03 and dot.count(max(dot)) == 1:
            break

    names = [f"D{i + 1}" for i in range(4)]
    options, key = build_options(rng, names[best], [nm for i, nm in enumerate(names) if i != best])

    listing = "\n".join(f"  {nm} = ({', '.join(map(str, d))})" for nm, d in zip(names, docs))
    question_text = (
        f"Поиск по эмбеддингам: вектор запроса q = ({', '.join(map(str, q))}). Векторы документов:\n{listing}\n\n"
        "Какой документ окажется первым при ранжировании по косинусной близости?"
    )
    explanation = (
        "Косинусы: " + ", ".join(f"{nm} = {c:.3f}" for nm, c in zip(names, cos))
        + f". Первым будет {names[best]}. По скалярному произведению выиграл бы {names[int(np.argmax(dot))]} "
        "за счёт большей нормы вектора — поэтому эмбеддинги нормируют или используют косинус."
    )
    return ItemRenderResult(
        family_code="ML_EMBEDDINGS_COSINE",
        seed=seed,
        question_text=question_text,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="MCQ",
    )


def generate_ml_pandas_groupby(seed: int) -> ItemRenderResult:
    """Family: ML_PANDAS_GROUPBY.

    Result of a groupby aggregation on a small DataFrame, possibly with a missing value.
    """
    rng = random.Random(seed)
    col = rng.choice(["score", "revenue", "duration", "clicks"])
    while True:
        teams = [rng.choice("ABC") for _ in range(rng.randint(7, 9))]
        values: list[int | None] = [rng.randint(1, 20) for _ in teams]
        key_team = rng.choice("ABC")
        idx = [i for i, t in enumerate(teams) if t == key_team]
        if len(idx) >= 3:
            break
    if rng.random() < 0.5:
        values[rng.choice(idx)] = None

    group = [values[i] for i in idx]
    present = [v for v in group if v is not None]
    everything = [v for v in values if v is not None]
    results = {
        "mean": sum(present) / len(present),
        "sum": float(sum(present)),
        "max": float(max(present)),
        "count": float(len(present)),
    }
    agg = rng.choice(list(results))
    value = results[agg]

    mistakes = [_fmt(v) for k, v in results.items() if k != agg]
    mistakes += [_fmt(sum(present) / len(group)), _fmt(float(len(group))), _fmt(sum(everything) / len(everything))]
    rng.shuffle(mistakes)
    options, key = build_options(rng, _fmt(value), mistakes + _nudges(value, steps=(1.0, -1.0, 0.5, 2.0)))

    def lit(v: int | None) -> str:
        return "np.nan" if v is None else str(v)

    code_snippet = (
        "df = pd.DataFrame({\n"
        f"    \"team\": {teams},\n"
        f"    \"{col}\": [{', '.join(lit(v) for v in values)}],\n"
        "})\n"
        f"result = df.groupby(\"team\")[\"{col}\"].{agg}()[\"{key_team}\"]"
    ).replace("'", '"')
    question_text = "Чему равно значение result? Ответ дан с точностью до сотых."
    explanation = (
        f"Группа {key_team}: {[lit(v) for v in group]}. Агрегаты pandas пропускают NaN: "
        f"mean = {_fmt(results['mean'])}, sum = {_fmt(results['sum'])}, max = {_fmt(results['max'])}, "
        f"count = {int(results['count'])} (count не считает NaN, в отличие от size)."
    )
    return ItemRenderResult(
        family_code="ML_PANDAS_GROUPBY",
        seed=seed,
        question_text=question_text,
        code_snippet=code_snippet,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="CODE_OUTPUT",
    )


_BROADCAST_ERROR = "ValueError: operands could not be broadcast together"


def generate_ml_numpy_broadcast(seed: int) -> ItemRenderResult:
    """Family: ML_NUMPY_BROADCAST.

    Shape of a + b under NumPy broadcasting, or the error when shapes are incompatible.
    """
    rng = random.Random(seed)
    sizes = [2, 3, 4, 5, 6]
    while True:
        target = [rng.choice(sizes) for _ in range(rng.choice([2, 3]))]
        a = [d if rng.random() < 0.6 else 1 for d in target]
        b = [d if rng.random() < 0.6 else 1 for d in target][rng.randint(0, len(target) - 1):]
        if rng.random() < 0.25:
            pos = rng.randrange(len(b))
            b[pos] = rng.choice([s for s in sizes if s != a[len(a) - len(b) + pos]])
            if a[len(a) - len(b) + pos] == 1:
                continue
        a, b = tuple(a), tuple(b)
        if a != b:
            break

    try:
        result = str(tuple(np.broadcast_shapes(a, b)))
    except ValueError:
        result = _BROADCAST_ERROR

    padded_b = (1,) * (len(a) - len(b)) + b
    naive_max = str(tuple(max(x, y) for x, y in zip(a, padded_b)))
    left_aligned = b + (1,) * (len(a) - len(b))
    left_max = str(tuple(max(x, y) for x, y in zip(a, left_aligned)))
    mistakes = [naive_max, str(a), _BROADCAST_ERROR, left_max, str(a + b)]
    fallbacks = [
        str(b),
        str(padded_b),
        str(tuple(x * y for x, y in zip(a, padded_b))),  # sizes multiplied instead of stretched
        str(tuple(reversed(a))),
        str((1,) + a),
    ]
    options, key = build_options(rng, result, mistakes + fallbacks)

    code_snippet = f"a = np.zeros({a})\nb = np.ones({b})\nprint((a + b).shape)"
    question_text = "Что выведет код?"
    explanation = (
        "Формы выравниваются по правому краю; размерности совместимы, если равны или одна из них 1. "
        f"{a} и {b}: " + (f"результат {result}." if result != _BROADCAST_ERROR else "есть пара разных размерностей, ни одна из которых не 1, поэтому ValueError.")
    )
    return ItemRenderResult(
        family_code="ML_NUMPY_BROADCAST",
        seed=seed,
        question_text=question_text,
        code_snippet=code_snippet,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="CODE_OUTPUT",
    )


def _top_user(conn: sqlite3.Connection, sql: str) -> tuple[int, int] | None:
    row = conn.execute(sql).fetchone()
    return (row[0], row[1]) if row else None


def generate_ml_sql_group_filter(seed: int) -> ItemRenderResult:
    """Family: ML_SQL_GROUP_FILTER.

    WHERE filters rows before GROUP BY. The key is obtained by running the query in SQLite.
    """
    rng = random.Random(seed)
    while True:
        users = rng.sample(range(1, 10), k=4)
        rows = [(rng.choice(users), rng.randrange(10, 310, 10)) for _ in range(rng.randint(8, 10))]
        threshold = rng.randrange(50, 210, 10)

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE payments (user_id INTEGER, amount INTEGER)")
        conn.executemany("INSERT INTO payments VALUES (?, ?)", rows)
        query = (
            "SELECT user_id, SUM(amount) AS total\n"
            "FROM payments\n"
            f"WHERE amount > {threshold}\n"
            "GROUP BY user_id\n"
            "ORDER BY total DESC\n"
            "LIMIT 1;"
        )
        totals = conn.execute(
            f"SELECT SUM(amount) AS t FROM payments WHERE amount > {threshold} GROUP BY user_id ORDER BY t DESC LIMIT 2"
        ).fetchall()
        answer = _top_user(conn, query)
        no_where = _top_user(conn, "SELECT user_id, SUM(amount) AS t FROM payments GROUP BY user_id ORDER BY t DESC, user_id LIMIT 1")
        # the WHERE clause has to matter, otherwise the item does not test it
        if len(totals) == 2 and totals[0][0] != totals[1][0] and no_where != answer:
            break
        conn.close()

    by_count = _top_user(conn, f"SELECT user_id, SUM(amount) AS t FROM payments WHERE amount > {threshold} GROUP BY user_id ORDER BY COUNT(*) DESC, t LIMIT 1")
    ascending = _top_user(conn, f"SELECT user_id, SUM(amount) AS t FROM payments WHERE amount > {threshold} GROUP BY user_id ORDER BY t ASC LIMIT 1")
    unfiltered_total = conn.execute(f"SELECT SUM(amount) FROM payments WHERE user_id = {answer[0]}").fetchone()[0]
    conn.close()

    def fmt(pair: tuple[int, int] | None) -> str:
        return f"user_id = {pair[0]}, total = {pair[1]}" if pair else ""

    mistakes = [fmt(no_where), fmt((answer[0], unfiltered_total)), fmt(by_count), fmt(ascending)]
    fallbacks = [fmt((answer[0], answer[1] + d)) for d in (10, -10, 20, 30)]
    options, key = build_options(rng, fmt(answer), [m for m in mistakes if m] + fallbacks)

    table = "\n".join(f"-- ({u}, {amt})" for u, amt in rows)
    code_snippet = f"-- payments(user_id, amount):\n{table}\n\n{query}"
    question_text = "Что вернёт запрос к таблице payments?"
    explanation = (
        f"WHERE отбрасывает платежи с amount ≤ {threshold} до группировки; затем суммы считаются по "
        f"оставшимся строкам. Наибольшая сумма у {fmt(answer)}. Без WHERE (или с фильтром на итог) получился бы другой ответ."
    )
    return ItemRenderResult(
        family_code="ML_SQL_GROUP_FILTER",
        seed=seed,
        question_text=question_text,
        code_snippet=code_snippet,
        options=options,
        correct_answer=key,
        explanation=explanation,
        item_format="SQL",
    )
