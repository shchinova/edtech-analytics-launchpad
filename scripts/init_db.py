"""
init_db.py — создание и инициализация базы данных platform.duckdb

Что делает этот скрипт:
  1. Создаёт файл data/db/platform.duckdb
  2. Создаёт три схемы: raw, staging, marts
  3. Загружает 6 CSV-файлов в схему raw (данные как есть, без изменений)
  4. Создаёт таблицы схемы staging — очищенные данные с применёнными фильтрами
  5. Строит витрины данных в схеме marts (метрики)

Запуск:
  python scripts/init_db.py

После запуска:
  python scripts/check_quality.py --source staging
"""

import os
import sys
import time
from datetime import datetime

# ─── Проверяем наличие duckdb ─────────────────────────────────────────────────
try:
    import duckdb
except ImportError:
    print("❌ DuckDB не установлен.")
    print("   Выполните: pip install duckdb")
    sys.exit(1)

# ─── Пути ─────────────────────────────────────────────────────────────────────
RAW_DIR = "data/raw"
DB_DIR  = "data/db"
DB_PATH = f"{DB_DIR}/platform.duckdb"
SQL_DIR = "sql"

os.makedirs(DB_DIR, exist_ok=True)

# ─── Удаляем старую БД если есть ─────────────────────────────────────────────
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print(f"  ♻️  Старая база удалена: {DB_PATH}")

# ─── Проверяем наличие CSV ────────────────────────────────────────────────────
required_files = [
    "users.csv", "courses.csv", "enrollments.csv",
    "payments.csv", "payment_attempts.csv", "ad_costs.csv"
]
missing = [f for f in required_files if not os.path.exists(f"{RAW_DIR}/{f}")]
if missing:
    print(f"\n❌ Не найдены файлы в {RAW_DIR}/:")
    for f in missing:
        print(f"   — {f}")
    print("\n   Сначала запустите: python scripts/generate_data.py")
    sys.exit(1)

# ─── Подключение ──────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  init_db.py  |  DuckDB {duckdb.__version__}")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"{'='*60}\n")

con = duckdb.connect(DB_PATH)
t_start = time.time()

# ══════════════════════════════════════════════════════════════════════════════
# ШАГ 1 — СОЗДАЁМ СХЕМЫ
# ══════════════════════════════════════════════════════════════════════════════
print("Шаг 1/3 — Создание схем...")

con.execute("CREATE SCHEMA IF NOT EXISTS raw")
con.execute("CREATE SCHEMA IF NOT EXISTS staging")
con.execute("CREATE SCHEMA IF NOT EXISTS marts")

print("  ✅ Схемы созданы: raw, staging, marts\n")

# ══════════════════════════════════════════════════════════════════════════════
# ШАГ 2 — ЗАГРУЗКА CSV В СХЕМУ raw
# Данные загружаются как есть — без фильтрации и изменений.
# Схема raw — это зеркало источников данных.
# ══════════════════════════════════════════════════════════════════════════════
print("Шаг 2/3 — Загрузка CSV в raw-слой...")

raw_tables = {
    "users":            "users.csv",
    "courses":          "courses.csv",
    "enrollments":      "enrollments.csv",
    "payments":         "payments.csv",
    "payment_attempts": "payment_attempts.csv",
    "ad_costs":         "ad_costs.csv",
}

for table_name, file_name in raw_tables.items():
    csv_path = f"{RAW_DIR}/{file_name}"
    con.execute(f"""
        CREATE TABLE raw.{table_name} AS
        SELECT * FROM read_csv_auto('{csv_path}', header=true)
    """)
    count = con.execute(f"SELECT COUNT(*) FROM raw.{table_name}").fetchone()[0]
    print(f"  ✅ raw.{table_name:<20} {count:>8,} строк  ← {file_name}")

print()

# ══════════════════════════════════════════════════════════════════════════════
# ШАГ 3 — СОЗДАНИЕ STAGING-СЛОЯ
#
# Staging применяет базовые фильтры качества из Data Dictionary.
# Каждый фильтр задокументирован комментарием — чтобы было понятно,
# почему именно эти записи исключаются.
#
# Что НЕ делает staging:
#   — не исправляет данные (не меняет значения)
#   — не агрегирует
#   — не обогащает данными из других таблиц
# Staging только исключает заведомо невалидные записи.
# ══════════════════════════════════════════════════════════════════════════════
print("Шаг 3/3 — Создание staging-слоя (применение фильтров)...")

# ── stg_users ─────────────────────────────────────────────────────────────────
con.execute("""
    CREATE TABLE staging.stg_users AS
    SELECT *
    FROM raw.users
    WHERE
        -- A2: исключаем регистрации в будущем
        registered_at::TIMESTAMP <= CURRENT_TIMESTAMP
        -- A1: оставляем только первую запись для каждого email
        -- (пользователь с наиболее ранней датой регистрации)
        AND user_id IN (
            SELECT MIN(user_id)
            FROM raw.users
            GROUP BY email
        )
""")
raw_count = con.execute("SELECT COUNT(*) FROM raw.users").fetchone()[0]
stg_count = con.execute("SELECT COUNT(*) FROM staging.stg_users").fetchone()[0]
print(f"  ✅ staging.stg_users            {stg_count:>8,} строк  "
      f"(исключено: {raw_count - stg_count:,})")

# ── stg_courses ───────────────────────────────────────────────────────────────
con.execute("""
    CREATE TABLE staging.stg_courses AS
    SELECT *
    FROM raw.courses
    WHERE
        -- A5: только опубликованные курсы попадают в аналитику
        is_published = 1
""")
raw_count = con.execute("SELECT COUNT(*) FROM raw.courses").fetchone()[0]
stg_count = con.execute("SELECT COUNT(*) FROM staging.stg_courses").fetchone()[0]
print(f"  ✅ staging.stg_courses          {stg_count:>8,} строк  "
      f"(исключено: {raw_count - stg_count:,})")

# ── stg_enrollments ───────────────────────────────────────────────────────────
con.execute("""
    CREATE TABLE staging.stg_enrollments AS
    SELECT e.*
    FROM raw.enrollments e
    JOIN staging.stg_users u ON e.user_id = u.user_id
    WHERE
        -- A6: дата записи не может быть раньше даты регистрации
        e.enrolled_at::TIMESTAMP >= u.registered_at::TIMESTAMP
        -- только записи на опубликованные курсы
        AND e.course_id IN (SELECT course_id FROM staging.stg_courses)
""")
raw_count = con.execute("SELECT COUNT(*) FROM raw.enrollments").fetchone()[0]
stg_count = con.execute("SELECT COUNT(*) FROM staging.stg_enrollments").fetchone()[0]
print(f"  ✅ staging.stg_enrollments      {stg_count:>8,} строк  "
      f"(исключено: {raw_count - stg_count:,})")

# ── stg_payments ──────────────────────────────────────────────────────────────
con.execute("""
    CREATE TABLE staging.stg_payments AS
    SELECT p.*
    FROM raw.payments p
    JOIN staging.stg_users u ON p.user_id = u.user_id
    WHERE
        -- A10: исключаем отрицательные суммы (закодированные возвраты)
        p.amount_rub > 0
        -- A11: исключаем нулевые суммы при успешном статусе
        AND NOT (p.amount_rub = 0 AND p.status = 'success')
        -- A12: дата платежа не может быть раньше регистрации
        AND p.paid_at::TIMESTAMP >= u.registered_at::TIMESTAMP
        -- только платежи к существующим записям
        AND p.enrollment_id IN (SELECT enrollment_id FROM staging.stg_enrollments)
""")
raw_count = con.execute("SELECT COUNT(*) FROM raw.payments").fetchone()[0]
stg_count = con.execute("SELECT COUNT(*) FROM staging.stg_payments").fetchone()[0]
print(f"  ✅ staging.stg_payments         {stg_count:>8,} строк  "
      f"(исключено: {raw_count - stg_count:,})")

# ── stg_payment_attempts ──────────────────────────────────────────────────────
con.execute("""
    CREATE TABLE staging.stg_payment_attempts AS
    SELECT pa.*
    FROM raw.payment_attempts pa
    WHERE
        -- A15: исключаем orphan records без пользователя
        pa.user_id IN (SELECT user_id FROM staging.stg_users)
        -- A17: только допустимые статусы
        AND pa.result IN ('success', 'failed', 'abandoned')
        -- A16: успешная попытка должна иметь соответствующий платёж в staging.
        -- Это гарантирует согласованность внутри staging-слоя:
        -- если платёж был удалён как невалидный, попытка тоже исключается.
        AND NOT (
            pa.result = 'success'
            AND NOT EXISTS (
                SELECT 1 FROM staging.stg_payments sp
                WHERE sp.user_id   = pa.user_id
                  AND sp.course_id = pa.course_id
            )
        )
""")
raw_count = con.execute("SELECT COUNT(*) FROM raw.payment_attempts").fetchone()[0]
stg_count = con.execute("SELECT COUNT(*) FROM staging.stg_payment_attempts").fetchone()[0]
print(f"  ✅ staging.stg_payment_attempts {stg_count:>8,} строк  "
      f"(исключено: {raw_count - stg_count:,})")

# ── stg_ad_costs ──────────────────────────────────────────────────────────────
con.execute("""
    CREATE TABLE staging.stg_ad_costs AS
    SELECT *
    FROM raw.ad_costs
    WHERE
        -- A18: исключаем строки с нулевым расходом при ненулевых показах
        NOT (spend_rub = 0 AND impressions > 0)
        -- A19: исключаем даты в будущем
        AND date::DATE <= CURRENT_DATE
        -- A20: только допустимые каналы
        AND channel IN ('vk_ads', 'yandex_direct', 'telegram')
""")
raw_count = con.execute("SELECT COUNT(*) FROM raw.ad_costs").fetchone()[0]
stg_count = con.execute("SELECT COUNT(*) FROM staging.stg_ad_costs").fetchone()[0]
print(f"  ✅ staging.stg_ad_costs         {stg_count:>8,} строк  "
      f"(исключено: {raw_count - stg_count:,})")

print()

# ══════════════════════════════════════════════════════════════════════════════
# ШАГ 4 — ВИТРИНЫ ДАННЫХ (marts)
# SQL-логика вынесена в sql/metrics_mart.sql
# ══════════════════════════════════════════════════════════════════════════════
sql_path = os.path.join(SQL_DIR, "metrics_mart.sql")

if os.path.exists(sql_path):
    print("Шаг 4/4 — Создание витрин данных (marts)...")
    with open(sql_path, encoding="utf-8") as f:
        sql_content = f.read()

    # Разбиваем по блокам CREATE OR REPLACE TABLE
    # (split по ; не работает с CTE в DuckDB)
    import re as _re
    blocks = _re.split(r'(?=CREATE OR REPLACE TABLE)', sql_content)
    blocks = [b.strip() for b in blocks if b.strip() and 'CREATE' in b]
    for block in blocks:
        try:
            con.execute(block)
        except Exception as e:
            print(f"  ⚠️  Ошибка: {e}")

    marts = con.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'marts'
        ORDER BY table_name
    """).fetchall()

    for (mart_name,) in marts:
        count = con.execute(f"SELECT COUNT(*) FROM marts.{mart_name}").fetchone()[0]
        print(f"  ✅ marts.{mart_name:<25} {count:>8,} строк")
    print()
else:
    print(f"  ⏭️  Файл {sql_path} не найден — витрины пропущены.")
    print(f"     Создайте sql/metrics_mart.sql и повторно запустите init_db.py\n")

# ══════════════════════════════════════════════════════════════════════════════
# ФИНАЛЬНАЯ СВОДКА
# ══════════════════════════════════════════════════════════════════════════════
elapsed = time.time() - t_start
db_size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)

print("=" * 60)
print("✅ База данных создана успешно!")
print("=" * 60)
print(f"  Файл:    {DB_PATH}")
print(f"  Размер:  {db_size_mb:.1f} МБ")
print(f"  Время:   {elapsed:.1f} сек")
print()

# Сводная таблица по всем слоям
print("  Слой      Таблица                  Строк")
print("  " + "─" * 50)
for schema in ["raw", "staging", "marts"]:
    tables = con.execute(f"""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = '{schema}'
        ORDER BY table_name
    """).fetchall()
    for (tname,) in tables:
        count = con.execute(f"SELECT COUNT(*) FROM {schema}.{tname}").fetchone()[0]
        print(f"  {schema:<10}{tname:<25}{count:>8,}")
    if tables:
        print()

con.close()

print("Следующий шаг:")
print("  python scripts/check_quality.py --source staging")
print("  → сравните reports/quality_raw.md и reports/quality_staging.md")