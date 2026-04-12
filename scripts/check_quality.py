"""
check_quality.py — проверка качества данных

Запускается кнопкой в VS Code. При запуске скрипт сам спросит,
какой режим выбрать.

Три режима:
  1 — raw      читает data/raw/*.csv         (запускать ДО init_db.py)
  2 — staging  читает staging из DuckDB      (запускать ПОСЛЕ init_db.py)
  3 — compare  сравнивает два готовых отчёта (запускать когда оба готовы)

Отчёты сохраняются в папку reports/:
  quality_raw.md      — снимок ДО очистки
  quality_staging.md  — снимок ПОСЛЕ очистки
"""

import os
import re
import sys
from datetime import datetime

import pandas as pd

# ─── Интерактивный выбор режима ───────────────────────────────────────────────
print()
print("=" * 60)
print("  Data Quality Check")
print("=" * 60)
print()
print("  Выберите режим проверки:")
print()
print("  1 — raw      сырые CSV из data/raw/")
print("               запускать ДО init_db.py")
print()
print("  2 — staging  очищенные данные из DuckDB")
print("               запускать ПОСЛЕ init_db.py")
print()
print("  3 — compare  сравнить два готовых отчёта")
print("               запускать когда оба отчёта уже сохранены")
print()

VALID = {"1": "raw", "2": "staging", "3": "compare"}

while True:
    choice = input("  Введите номер (1 / 2 / 3): ").strip()
    if choice in VALID:
        SOURCE = VALID[choice]
        print(f"  → Выбран режим: {SOURCE.upper()}")
        print()
        break
    print("  Пожалуйста, введите 1, 2 или 3.")

SOURCE     = SOURCE
RAW_DIR    = "data/raw"
REPORT_DIR = "reports"
DB_PATH    = "data/db/platform.duckdb"
NOW        = datetime.now()

os.makedirs(REPORT_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# РЕЖИМ COMPARE
# Читает два готовых Markdown-отчёта и выводит таблицу сравнения
# ══════════════════════════════════════════════════════════════════════════════
if SOURCE == "compare":
    raw_path     = os.path.join(REPORT_DIR, "quality_raw.md")
    staging_path = os.path.join(REPORT_DIR, "quality_staging.md")

    missing = [p for p in [raw_path, staging_path] if not os.path.exists(p)]
    if missing:
        print("\n❌ Не найдены отчёты:")
        for p in missing:
            print(f"   — {p}")
        print("\n   Сначала запустите:")
        print("   python scripts/check_quality.py --source raw")
        print("   python scripts/init_db.py")
        print("   python scripts/check_quality.py --source staging")
        sys.exit(1)

    def parse_report(path: str) -> dict:
        """
        Парсит Markdown-отчёт и возвращает словарь {код: количество_записей}.
        Ищет строки таблицы вида: | `A1` | `users` | **100** | ...
        """
        counts = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                # Строки с найденными ошибками: | `A1` | ... | **100** | ...
                m = re.match(r'\|\s*`(A\d+)`\s*\|.*?\|\s*\*\*(\d[\d,]*)\*\*\s*\|', line)
                if m:
                    code  = m.group(1)
                    count = int(m.group(2).replace(",", ""))
                    counts[code] = count
                # Строки без ошибок: | `A7` | ... | 0 | ...
                m2 = re.match(r'\|\s*`(A\d+)`\s*\|.*?\|\s*(\d+)\s*\|', line)
                if m2 and m2.group(1) not in counts:
                    code  = m2.group(1)
                    count = int(m2.group(2))
                    counts[code] = count
        return counts

    raw_counts     = parse_report(raw_path)
    staging_counts = parse_report(staging_path)

    all_codes = sorted(set(raw_counts) | set(staging_counts),
                       key=lambda x: int(x[1:]))

    print(f"\n{'='*65}")
    print("  Сравнение качества данных: RAW → STAGING")
    print(f"  {NOW.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*65}\n")
    print(f"  {'Код':<6}  {'Было (raw)':>12}  {'Стало (staging)':>16}  "
          f"{'Изменение':>12}  {'%':>7}")
    print("  " + "─" * 57)

    total_raw     = 0
    total_staging = 0

    for code in all_codes:
        before = raw_counts.get(code, 0)
        after  = staging_counts.get(code, 0)
        delta  = after - before

        if before == 0 and after == 0:
            continue  # пропускаем проверки без ошибок в обоих отчётах

        total_raw     += before
        total_staging += after

        if before > 0:
            pct = (delta / before) * 100
            pct_str = f"{pct:+.0f}%"
        else:
            pct_str = "—"

        delta_str = f"{delta:+,}" if delta != 0 else "без изменений"
        marker    = "✅" if after == 0 and before > 0 else ("⚠️ " if after > 0 else "  ")

        print(f"  {code:<6}  {before:>12,}  {after:>16,}  "
              f"{delta_str:>12}  {pct_str:>7}  {marker}")

    print("  " + "─" * 57)

    if total_raw > 0:
        total_pct = ((total_staging - total_raw) / total_raw) * 100
        total_pct_str = f"{total_pct:+.0f}%"
    else:
        total_pct_str = "—"

    print(f"  {'ИТОГО':<6}  {total_raw:>12,}  {total_staging:>16,}  "
          f"{total_staging - total_raw:>+12,}  {total_pct_str:>7}")

    # A16 — вторичный эффект очистки: не включаем в итоговый счётчик
    SECONDARY = {"A16"}

    eliminated = sum(
        1 for c in all_codes
        if raw_counts.get(c, 0) > 0
        and staging_counts.get(c, 0) == 0
        and c not in SECONDARY
    )
    remaining = sum(
        1 for c in all_codes
        if staging_counts.get(c, 0) > 0 and c not in SECONDARY
    )
    total_raw_adj     = sum(raw_counts.get(c, 0)     for c in all_codes if c not in SECONDARY)
    total_staging_adj = sum(staging_counts.get(c, 0) for c in all_codes if c not in SECONDARY)

    print(f"  Проверок устранено полностью: {eliminated}")
    print(f"  Проверок с остаточными ошибками: {remaining}")
    if total_raw_adj > 0:
        adj_pct = (total_staging_adj - total_raw_adj) / total_raw_adj * 100
        print(f"  Снижение ошибок (без вторичных эффектов): {adj_pct:+.0f}%")

    # Примечание по A16
    a16_before = raw_counts.get("A16", 0)
    a16_after  = staging_counts.get("A16", 0)
    if a16_after > a16_before:
        print()
        print(f"  ⚠️  A16: вырос с {a16_before:,} до {a16_after:,} — вторичный эффект очистки.")
        print("      Staging удалил часть платежей, но попытки оплаты остались.")
        print("      Требует расследования на уровне источника данных.")

    # ── Сохраняем отчёт в файл ────────────────────────────────────────────────
    compare_path = os.path.join(REPORT_DIR, "quality_compare.md")
    lines = [
        "# Сравнение качества данных: RAW → STAGING",
        "",
        f"**Дата:** {NOW.strftime('%Y-%m-%d %H:%M')}",
        "",
        "| Код | Было (raw) | Стало (staging) | Изменение | % | Статус |",
        "|---|---|---|---|---|---|",
    ]
    for code in all_codes:
        before = raw_counts.get(code, 0)
        after  = staging_counts.get(code, 0)
        if before == 0 and after == 0:
            continue
        delta   = after - before
        pct_s   = f"{(delta/before)*100:+.0f}%" if before > 0 else "—"
        delta_s = f"{delta:+,}" if delta != 0 else "без изменений"
        if code in SECONDARY:
            status = "⚠️ вторичный эффект"
        elif after == 0 and before > 0:
            status = "✅ устранено"
        else:
            status = "⚠️ остаётся"
        lines.append(f"| `{code}` | {before:,} | {after:,} | {delta_s} | {pct_s} | {status} |")

    lines += [
        "",
        "| | Записей с ошибками |",
        "|---|---|",
        f"| До очистки (raw) | {total_raw_adj:,} |",
        f"| После очистки (staging) | {total_staging_adj:,} |",
        f"| Устранено | {total_raw_adj - total_staging_adj:,} |",
        f"| Снижение | {((total_staging_adj - total_raw_adj) / total_raw_adj * 100):+.0f}% |" if total_raw_adj > 0 else "",
        "",
        "---",
        "*Сгенерировано: check_quality.py — режим compare*",
    ]

    with open(compare_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n  ✅ Отчёт сохранён: {compare_path}")
    sys.exit(0)

# ══════════════════════════════════════════════════════════════════════════════
# ЗАГРУЗКА ДАННЫХ (режимы raw и staging)
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"  Data Quality Check  |  source: {SOURCE.upper()}")
print(f"  {NOW.strftime('%Y-%m-%d %H:%M')}")
print(f"{'='*60}\n")

if SOURCE == "raw":
    print("Загрузка данных из CSV (data/raw/)...")
    try:
        users            = pd.read_csv(f"{RAW_DIR}/users.csv",
                                       parse_dates=["registered_at"])
        courses          = pd.read_csv(f"{RAW_DIR}/courses.csv")
        enrollments      = pd.read_csv(f"{RAW_DIR}/enrollments.csv",
                                       parse_dates=["enrolled_at"])
        payments         = pd.read_csv(f"{RAW_DIR}/payments.csv",
                                       parse_dates=["paid_at"])
        payment_attempts = pd.read_csv(f"{RAW_DIR}/payment_attempts.csv",
                                       parse_dates=["attempted_at"])
        ad_costs         = pd.read_csv(f"{RAW_DIR}/ad_costs.csv",
                                       parse_dates=["date"])
    except FileNotFoundError as e:
        print(f"\n❌ Файл не найден: {e}")
        print("   Сначала запустите: python scripts/generate_data.py")
        sys.exit(1)

else:  # staging
    print("Загрузка данных из DuckDB (staging)...")
    try:
        import duckdb
    except ImportError:
        print("\n❌ DuckDB не установлен. Выполните: pip install duckdb")
        sys.exit(1)

    if not os.path.exists(DB_PATH):
        print(f"\n❌ База данных не найдена: {DB_PATH}")
        print("   Сначала запустите: python scripts/init_db.py")
        sys.exit(1)

    con = duckdb.connect(DB_PATH, read_only=True)
    users            = con.execute("SELECT * FROM staging.stg_users").df()
    courses          = con.execute("SELECT * FROM staging.stg_courses").df()
    enrollments      = con.execute("SELECT * FROM staging.stg_enrollments").df()
    payments         = con.execute("SELECT * FROM staging.stg_payments").df()
    payment_attempts = con.execute(
                           "SELECT * FROM staging.stg_payment_attempts").df()
    ad_costs         = con.execute("SELECT * FROM staging.stg_ad_costs").df()
    con.close()

    for df, col in [
        (users,            "registered_at"),
        (enrollments,      "enrolled_at"),
        (payments,         "paid_at"),
        (payment_attempts, "attempted_at"),
        (ad_costs,         "date"),
    ]:
        if df[col].dtype == object:
            df[col] = pd.to_datetime(df[col])

print(f"  users:            {len(users):>7,}")
print(f"  courses:          {len(courses):>7,}")
print(f"  enrollments:      {len(enrollments):>7,}")
print(f"  payments:         {len(payments):>7,}")
print(f"  payment_attempts: {len(payment_attempts):>7,}")
print(f"  ad_costs:         {len(ad_costs):>7,}\n")

# ══════════════════════════════════════════════════════════════════════════════
# МЕХАНИЗМ ПРОВЕРОК
# ══════════════════════════════════════════════════════════════════════════════
class CheckResult:
    def __init__(self, code, table, count, severity, description, fix_hint):
        self.code        = code
        self.table       = table
        self.count       = count
        self.severity    = severity   # CRITICAL | WARNING | INFO
        self.description = description
        self.fix_hint    = fix_hint

results: list[CheckResult] = []
ICONS = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🟢"}

def check(code, table, count, severity, description, fix_hint):
    results.append(CheckResult(code, table, count, severity, description, fix_hint))
    icon   = ICONS[severity]
    status = "⚠️  FOUND" if count > 0 else "✅ OK   "
    print(f"  {icon} {code:<6} {status}  {count:>6,} записей  — {table}")

# ══════════════════════════════════════════════════════════════════════════════
# ПРОВЕРКИ
# ══════════════════════════════════════════════════════════════════════════════

# ── USERS ─────────────────────────────────────────────────────────────────────
print("─" * 60)
print("USERS")
print("─" * 60)

# A1: Дублирующиеся email
# WARNING (не CRITICAL): два разных человека могут иметь один email.
# Проблема не в идентификации (для этого есть user_id), а в бизнес-процессах:
# логин, рассылки, CRM-связка.
dup_emails = users.duplicated(subset="email", keep=False).sum()
check(
    "A1", "users", int(dup_emails), "WARNING",
    "Дублирующиеся email у разных user_id — проблема для логина и рассылок.",
    "Выяснить причину: общий ящик, повторная регистрация, ошибка импорта."
)

# A2: Регистрация в будущем
future_reg = (users["registered_at"] > NOW).sum()
check(
    "A2", "users", int(future_reg), "WARNING",
    "registered_at > текущей даты — тестовые аккаунты или ошибка серверного времени.",
    "Исключать из когортного анализа до наступления даты регистрации."
)

# A3: Пустой канал привлечения
null_channel = users["channel"].isna().sum()
check(
    "A3", "users", int(null_channel), "INFO",
    "Отсутствует канал привлечения — невозможно атрибутировать пользователя.",
    "Заполнить значением 'unknown' для сохранения полноты выборки."
)

# ── COURSES ───────────────────────────────────────────────────────────────────
print()
print("─" * 60)
print("COURSES")
print("─" * 60)

# A4: Цена 0
zero_price = (courses["price_rub"] == 0).sum()
check(
    "A4", "courses", int(zero_price), "WARNING",
    "Курс с ценой 0 — если не бесплатный, ошибка заведения продукта.",
    "Добавить флаг is_free; исключать из расчёта выручки и среднего чека."
)

# A5: Неопубликованные курсы
unpublished = (courses["is_published"] == 0).sum()
check(
    "A5", "courses", int(unpublished), "INFO",
    "Курс не опубликован — не должен попадать в метрики конверсии и выручки.",
    "Фильтровать WHERE is_published = 1 во всех витринах."
)

# ── ENROLLMENTS ───────────────────────────────────────────────────────────────
print()
print("─" * 60)
print("ENROLLMENTS")
print("─" * 60)

enr_usr = enrollments.merge(
    users[["user_id", "registered_at"]], on="user_id", how="left"
)

# A6: Запись раньше регистрации
before_reg = (enr_usr["enrolled_at"] < enr_usr["registered_at"]).sum()
check(
    "A6", "enrollments+users", int(before_reg), "CRITICAL",
    "enrolled_at < registered_at — физически невозможно, ошибка ETL или часового пояса.",
    "Исключать из воронки или корректировать до даты регистрации."
)

# A7: Недопустимый статус
valid_statuses = {"active", "completed", "dropped", "paused"}
invalid_status = (~enrollments["status"].isin(valid_statuses)).sum()
check(
    "A7", "enrollments", int(invalid_status), "CRITICAL",
    "Статус не входит в допустимый справочник (active/completed/dropped/paused).",
    "Добавить ENUM-тип или CHECK-constraint на уровне схемы БД."
)

# A8: Прогресс 100% при статусе не completed
progress_mismatch = (
    (enrollments["progress_pct"] == 100) & (enrollments["status"] != "completed")
).sum()
check(
    "A8", "enrollments", int(progress_mismatch), "WARNING",
    "progress_pct = 100% но status ≠ completed — логическое противоречие.",
    "Добавить триггер: при достижении 100% автоматически ставить status = completed."
)

# A9: Записи на несуществующие курсы
orphan_enroll_courses = (~enrollments["course_id"].isin(courses["course_id"])).sum()
check(
    "A9", "enrollments→courses", int(orphan_enroll_courses), "CRITICAL",
    "course_id в enrollments не существует в courses — нарушение ссылочной целостности.",
    "Добавить FOREIGN KEY constraint; проверить ETL-пайплайн."
)

# ── PAYMENTS ──────────────────────────────────────────────────────────────────
print()
print("─" * 60)
print("PAYMENTS")
print("─" * 60)

# A10: Отрицательная сумма
negative_amount = (payments["amount_rub"] < 0).sum()
check(
    "A10", "payments", int(negative_amount), "CRITICAL",
    "amount_rub < 0 — возвраты закодированы как отрицательные суммы.",
    "Хранить возвраты отдельной записью с типом транзакции 'refund'."
)

# A11: Нулевая сумма при успешном статусе
zero_success = (
    (payments["amount_rub"] == 0) & (payments["status"] == "success")
).sum()
check(
    "A11", "payments", int(zero_success), "CRITICAL",
    "amount_rub = 0 при status = success — ошибка интеграции со шлюзом.",
    "Добавить NOT NULL и CHECK (amount_rub > 0) для статуса success."
)

# A12: Платёж раньше регистрации
pay_usr = payments.merge(
    users[["user_id", "registered_at"]], on="user_id", how="left"
)
pay_before_reg = (pay_usr["paid_at"] < pay_usr["registered_at"]).sum()
check(
    "A12", "payments+users", int(pay_before_reg), "CRITICAL",
    "paid_at < registered_at пользователя — физически невозможная ситуация.",
    "Исключать из расчётов; проверить обработку часовых поясов в ETL."
)

# A13: Платёж на бесплатный курс
pay_course = payments.merge(
    courses[["course_id", "price_rub"]], on="course_id", how="left"
)
free_course_paid = (
    (pay_course["price_rub"] == 0) & (pay_course["amount_rub"] > 0)
).sum()
check(
    "A13", "payments+courses", int(free_course_paid), "WARNING",
    "Оплата за курс с price_rub = 0 — возможно, цена изменилась после оплаты.",
    "Хранить price_at_purchase в таблице payments (цена на момент оплаты)."
)

# A14: Платёж без соответствующего enrollment
orphan_payments = (~payments["enrollment_id"].isin(
    enrollments["enrollment_id"]
)).sum()
check(
    "A14", "payments→enrollments", int(orphan_payments), "CRITICAL",
    "enrollment_id в payments не существует в enrollments — нарушение ссылочной целостности.",
    "Добавить FOREIGN KEY; проверить, не удалялись ли записи после оплаты."
)

# ── PAYMENT_ATTEMPTS ──────────────────────────────────────────────────────────
print()
print("─" * 60)
print("PAYMENT_ATTEMPTS")
print("─" * 60)

# A15: Orphan records — user_id не существует
orphan_attempts = (~payment_attempts["user_id"].isin(users["user_id"])).sum()
check(
    "A15", "payment_attempts→users", int(orphan_attempts), "WARNING",
    "user_id в payment_attempts не существует в users — гостевой чекаут или удалённые аккаунты.",
    "Допустимо при гостевой оплате; исключать из пользовательских метрик."
)

# A16: Успешная попытка без соответствующего платежа
# Важно: сравниваем данные из одного слоя.
# В режиме raw — payment_attempts raw vs payments raw.
# В режиме staging — payment_attempts staging vs payments staging.
# Иначе после очистки платежей счётчик вырастет из-за разных слоёв.
success_attempts = payment_attempts[
    payment_attempts["result"] == "success"
].copy()
success_payments_keys = set(zip(payments["user_id"], payments["course_id"]))
success_attempts["has_payment"] = success_attempts.apply(
    lambda r: (r["user_id"], r["course_id"]) in success_payments_keys, axis=1
)
success_no_payment = (~success_attempts["has_payment"]).sum()
check(
    "A16", "payment_attempts→payments", int(success_no_payment), "CRITICAL",
    "Успешная попытка оплаты без соответствующего платежа в payments.",
    "Расследовать: webhook от шлюза мог не дойти — платёж списан, но не записан."
)

# A17: Недопустимый результат попытки
valid_results = {"success", "failed", "abandoned"}
invalid_result = (~payment_attempts["result"].isin(valid_results)).sum()
check(
    "A17", "payment_attempts", int(invalid_result), "CRITICAL",
    "result не входит в допустимый справочник (success/failed/abandoned).",
    "Добавить ENUM-тип на уровне схемы."
)

# ── AD_COSTS ──────────────────────────────────────────────────────────────────
print()
print("─" * 60)
print("AD_COSTS")
print("─" * 60)

# A18: Нулевой расход при ненулевых показах
zero_spend_nonzero_imp = (
    (ad_costs["spend_rub"] == 0) & (ad_costs["impressions"] > 0)
).sum()
check(
    "A18", "ad_costs", int(zero_spend_nonzero_imp), "WARNING",
    "spend_rub = 0 при impressions > 0 — данные о расходах потерялись при выгрузке.",
    "Исключать из расчёта CPM и CAC; запросить повторную выгрузку."
)

# A19: Дата в будущем
future_ad = (ad_costs["date"] > NOW).sum()
check(
    "A19", "ad_costs", int(future_ad), "WARNING",
    "Дата записи в будущем — тестовая запись или ошибка при ручной выгрузке.",
    "Исключать из расчётов до наступления даты."
)

# A20: Недопустимый канал
valid_channels = {"vk_ads", "yandex_direct", "telegram"}
invalid_channel = (~ad_costs["channel"].isin(valid_channels)).sum()
check(
    "A20", "ad_costs", int(invalid_channel), "INFO",
    "Канал не входит в справочник платных каналов (vk_ads/yandex_direct/telegram).",
    "Проверить справочник; возможно, добавили новый канал без обновления документации."
)

# ══════════════════════════════════════════════════════════════════════════════
# СВОДКА В КОНСОЛЬ
# Показываем только проверки с найденными ошибками
# ══════════════════════════════════════════════════════════════════════════════
found_results  = [r for r in results if r.count > 0]
critical_found = [r for r in found_results if r.severity == "CRITICAL"]
warning_found  = [r for r in found_results if r.severity == "WARNING"]

total_records = sum(r.count for r in found_results)

print()
print("=" * 60)
print("СВОДКА  (показаны только проверки с ошибками)")
print("=" * 60)

if not found_results:
    print("  ✅ Ошибок не найдено")
else:
    print(f"  🔴 CRITICAL: {len(critical_found)} проверок  "
          f"| {sum(r.count for r in critical_found):,} записей")
    print(f"  🟡 WARNING:  {len(warning_found)} проверок  "
          f"| {sum(r.count for r in warning_found):,} записей")
    print(f"  Всего записей с ошибками: {total_records:,}")

print(f"  Всего выполнено проверок: {len(results)}")

# ══════════════════════════════════════════════════════════════════════════════
# MARKDOWN-ОТЧЁТ
# ══════════════════════════════════════════════════════════════════════════════
report_path  = os.path.join(REPORT_DIR, f"quality_{SOURCE}.md")
source_label = ("Сырые данные (data/raw/*.csv)"
                if SOURCE == "raw"
                else "Очищенные данные (staging layer, DuckDB)")

lines = [
    f"# Отчёт о качестве данных — {SOURCE.upper()}",
    "",
    f"**Источник данных:** {source_label}  ",
    f"**Дата проверки:** {NOW.strftime('%Y-%m-%d %H:%M')}  ",
    f"**Период данных:** январь 2024 — июнь 2025",
    "",
    "## Объём данных",
    "",
    "| Таблица | Строк |",
    "|---|---|",
    f"| users | {len(users):,} |",
    f"| courses | {len(courses):,} |",
    f"| enrollments | {len(enrollments):,} |",
    f"| payments | {len(payments):,} |",
    f"| payment_attempts | {len(payment_attempts):,} |",
    f"| ad_costs | {len(ad_costs):,} |",
    "",
    "## Сводка",
    "",
    "| Уровень | Проверок с ошибками | Записей с ошибками |",
    "|---|---|---|",
    f"| 🔴 CRITICAL | {len(critical_found)} "
    f"| {sum(r.count for r in critical_found):,} |",
    f"| 🟡 WARNING  | {len(warning_found)} "
    f"| {sum(r.count for r in warning_found):,} |",
    f"| **Итого** | **{len(found_results)}** | **{total_records:,}** |",
    "",
]

# Только проверки с ошибками — основная таблица
if found_results:
    lines += [
        "## Найденные ошибки",
        "",
        "| Код | Таблица | Записей | Уровень | Описание | Рекомендация |",
        "|---|---|---|---|---|---|",
    ]
    for r in found_results:
        icon = ICONS[r.severity]
        lines.append(
            f"| `{r.code}` | `{r.table}` | **{r.count:,}** "
            f"| {icon} {r.severity} | {r.description} | {r.fix_hint} |"
        )
    lines.append("")

# Проверки без ошибок — отдельный компактный блок
clean_results = [r for r in results if r.count == 0]
if clean_results:
    lines += [
        "## Проверки без ошибок",
        "",
        "| Код | Таблица | Уровень |",
        "|---|---|---|",
    ]
    for r in clean_results:
        icon = ICONS[r.severity]
        lines.append(f"| `{r.code}` | `{r.table}` | {icon} {r.severity} |")
    lines.append("")

# Приоритеты — только для raw
if SOURCE == "raw" and found_results:
    lines += [
        "## Приоритеты устранения",
        "",
        "### 🔴 Немедленно (искажают ключевые метрики)",
        "",
    ]
    for r in critical_found:
        lines.append(f"- **{r.code}** {r.description.split(' — ')[0]}")

    if warning_found:
        lines += ["", "### 🟡 В ближайший спринт", ""]
        for r in warning_found:
            lines.append(f"- **{r.code}** {r.description.split(' — ')[0]}")

    lines += [
        "",
        "### 🟢 Технический долг",
        "",
        "- Добавить ENUM, NOT NULL и FOREIGN KEY constraints на уровне схемы БД",
        "- Настроить автоматический запуск этого скрипта после каждого ETL-прогона",
    ]

elif SOURCE == "staging":
    lines += [
        "## Что изменилось после очистки",
        "",
        "Staging-слой применяет следующие фильтры:",
        "",
        "- Пользователи: исключены дубли email (оставлена первая запись)",
        "- Пользователи: исключены `registered_at` в будущем",
        "- Курсы: исключены неопубликованные (`is_published = 0`)",
        "- Enrollments: исключены записи где `enrolled_at < registered_at`",
        "- Payments: исключены `amount_rub ≤ 0`",
        "- Payments: исключены `amount_rub = 0` при `status = success`",
        "- Payments: исключены записи где `paid_at < registered_at`",
        "- Payment_attempts: исключены orphan records",
        "- Ad_costs: исключены `spend_rub = 0` при `impressions > 0`",
        "- Ad_costs: исключены даты в будущем",
        "",
        "Для сравнения с исходным состоянием: "
        "[quality_raw.md](./quality_raw.md)  ",
        "Детальное сравнение: "
        "`python scripts/check_quality.py --source compare`",
    ]

lines += [
    "",
    "---",
    f"*Сгенерировано: `python scripts/check_quality.py --source {SOURCE}`*",
]

with open(report_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"\n✅ Отчёт сохранён: {report_path}")
print()

if SOURCE == "raw":
    print("Следующий шаг:")
    print("  python scripts/init_db.py")
    print("  python scripts/check_quality.py --source staging")
elif SOURCE == "staging":
    print("Следующий шаг:")
    print("  python scripts/check_quality.py --source compare")