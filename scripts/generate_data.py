
"""
Генератор синтетического датасета образовательной платформы "ЕГЭ Экспресс".
Период: январь 2024 — июнь 2025 (18 месяцев).

Создаёт 6 CSV-файлов в папке data/raw/:
  users.csv           — пользователи платформы
  courses.csv         — каталог курсов
  enrollments.csv     — записи на курсы
  payments.csv        — транзакции
  payment_attempts.csv — попытки оплаты (включая незавершённые)
  ad_costs.csv        — расходы на рекламу по каналам

Намеренно вносит аномалии — см. DATA_SOURCES.md для полного списка.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import os

# ─── Воспроизводимость ────────────────────────────────────────────────────────
random.seed(42)
np.random.seed(42)

# ─── Выходная директория ──────────────────────────────────────────────────────
OUTPUT_DIR = "data/raw"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Период генерации ─────────────────────────────────────────────────────────
START_DATE = datetime(2024, 1, 1)
END_DATE   = datetime(2025, 6, 30)
# Дата "сегодня" для проверок аномалий (будущие даты — относительно неё)
TODAY      = datetime(2025, 7, 15)

# ─── Справочники ──────────────────────────────────────────────────────────────
SUBJECTS = [
    "Математика", "Русский язык", "Физика", "Химия",
    "Биология", "История", "Обществознание", "Английский язык", "Информатика"
]
# Вес предметов: математика и русский язык вдвое популярнее
SUBJECT_WEIGHTS = [0.20, 0.20, 0.10, 0.10, 0.10, 0.07, 0.10, 0.07, 0.06]

LEVELS       = ["Базовый", "Продвинутый", "Эксперт"]
COURSE_TYPES = ["Курс", "Интенсив", "Подписка"]
CHANNELS     = ["organic", "vk_ads", "yandex_direct", "telegram", "referral", "email"]
PAID_CHANNELS = ["vk_ads", "yandex_direct", "telegram"]

CITIES = [
    "Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург",
    "Ростов-на-Дону", "Краснодар", "Воронеж", "Нижний Новгород", "Самара", "Другой"
]
CITY_WEIGHTS = [0.28, 0.15, 0.07, 0.06, 0.06, 0.05, 0.05, 0.04, 0.04, 0.04, 0.16]

# ─── Сезонные коэффициенты (месяц → множитель активности) ────────────────────
SEASON = {
    1: 0.6,   # январь — низкий сезон
    2: 0.9,   # февраль
    3: 0.9,   # март
    4: 1.8,   # апрель — пик ЕГЭ
    5: 1.8,   # май — пик ЕГЭ
    6: 0.7,   # июнь — спад
    7: 0.5,   # июль — лето
    8: 0.5,   # август — лето
    9: 1.4,   # сентябрь — начало учебного года
    10: 1.0,  # октябрь
    11: 1.0,  # ноябрь
    12: 1.0,  # декабрь
}

# ─── Вспомогательные функции ──────────────────────────────────────────────────
def rand_date(start: datetime, end: datetime) -> datetime:
    """Случайная дата в диапазоне [start, end]."""
    delta = (end - start).total_seconds()
    if delta <= 0:
        return start
    return start + timedelta(seconds=random.randint(0, int(delta)))

def date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def seasonal_dates(n: int, start: datetime, end: datetime) -> list:
    """
    Генерирует n дат с сезонным распределением.
    Месяцы с высоким коэффициентом получают больше дат.
    """
    # Строим список дней с весами
    days = []
    weights = []
    cur = start.replace(hour=0, minute=0, second=0)
    while cur <= end:
        days.append(cur)
        weights.append(SEASON[cur.month])
        cur += timedelta(days=1)

    weights_arr = np.array(weights, dtype=float)
    weights_arr /= weights_arr.sum()

    chosen_days = np.random.choice(len(days), size=n, p=weights_arr)
    result = []
    for idx in chosen_days:
        base = days[idx]
        # Добавляем случайное время внутри дня
        result.append(base + timedelta(
            hours=random.randint(6, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59)
        ))
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 1. USERS
# ══════════════════════════════════════════════════════════════════════════════
print("Generating users...")
N_USERS = 5_000

user_ids  = list(range(1, N_USERS + 1))

# Регистрации с сезонностью
reg_dates = seasonal_dates(N_USERS, START_DATE, END_DATE)

# Возраст: 30% школьники (14–18), 70% взрослые (19–35)
teen_ages  = list(range(14, 19))   # 5 значений
adult_ages = list(range(19, 36))   # 17 значений
teen_p  = [0.06] * 5               # сумма = 0.30
adult_p = [0.70 / 17] * 17
adult_p[-1] += 1.0 - sum(teen_p) - sum(adult_p)  # коррекция округления
ages = np.random.choice(
    teen_ages + adult_ages,
    size=N_USERS,
    p=teen_p + adult_p
)

cities   = np.random.choice(CITIES,    size=N_USERS, p=CITY_WEIGHTS)
channels = np.random.choice(CHANNELS,  size=N_USERS, p=[0.35, 0.25, 0.18, 0.10, 0.07, 0.05])

emails = [f"user{uid}@example.com" for uid in user_ids]

# ── Аномалия A1: ~50 дублирующихся email ──────────────────────────────────────
for i in range(50):
    emails[N_USERS - 1 - i] = emails[i]

# ── Аномалия A2: 30 дат регистрации в будущем ─────────────────────────────────
future_idxs = random.sample(range(N_USERS), 30)
for idx in future_idxs:
    reg_dates[idx] = rand_date(TODAY + timedelta(days=1), TODAY + timedelta(days=90))

users_df = pd.DataFrame({
    "user_id":       user_ids,
    "email":         emails,
    "age":           ages,
    "city":          cities,
    "channel":       channels,
    "registered_at": [date_str(d) for d in reg_dates],
    "is_active":     np.random.choice([1, 0], size=N_USERS, p=[0.72, 0.28]),
})
users_df.to_csv(f"{OUTPUT_DIR}/users.csv", index=False)
print(f"  → {len(users_df):,} users")

# ── Словари для последующих таблиц ────────────────────────────────────────────
user_reg_map = {row.user_id: datetime.strptime(row.registered_at, "%Y-%m-%d %H:%M:%S")
                for row in users_df.itertuples()}

# ══════════════════════════════════════════════════════════════════════════════
# 2. COURSES
# ══════════════════════════════════════════════════════════════════════════════
print("Generating courses...")
N_COURSES = 120

course_ids      = list(range(1, N_COURSES + 1))
course_subjects = np.random.choice(SUBJECTS, size=N_COURSES, p=SUBJECT_WEIGHTS)
course_levels   = np.random.choice(LEVELS,   size=N_COURSES)
course_types    = np.random.choice(COURSE_TYPES, size=N_COURSES, p=[0.55, 0.25, 0.20])

LEVEL_BASE = {"Базовый": 2_900, "Продвинутый": 5_900, "Эксперт": 9_900}
SUBSCRIPTION_PRICES = [990, 1_490, 1_990, 2_490, 2_900]

base_prices    = []
duration_weeks = []

for lvl, ctype in zip(course_levels, course_types):
    if ctype == "Подписка":
        base_prices.append(int(np.random.choice(SUBSCRIPTION_PRICES)))
        duration_weeks.append(None)   # подписка — без фиксированной длительности
    elif ctype == "Интенсив":
        base = int(LEVEL_BASE[lvl] * 1.3 * np.random.uniform(0.85, 1.15))
        base_prices.append(base)
        duration_weeks.append(int(np.random.choice([4, 6, 8])))
    else:  # Курс
        base = int(LEVEL_BASE[lvl] * np.random.uniform(0.85, 1.15))
        base_prices.append(base)
        dur_map = {"Базовый": [8, 12], "Продвинутый": [12, 16], "Эксперт": [16, 24]}
        duration_weeks.append(int(np.random.choice(dur_map[lvl])))

# ── Аномалия A3: 5 курсов с ценой 0 ──────────────────────────────────────────
zero_price_idxs = random.sample(range(N_COURSES), 5)
for idx in zero_price_idxs:
    base_prices[idx] = 0

courses_df = pd.DataFrame({
    "course_id":      course_ids,
    "title":          [f"{subj} — {lvl} ({ctype})"
                       for subj, lvl, ctype in zip(course_subjects, course_levels, course_types)],
    "subject":        course_subjects,
    "level":          course_levels,
    "course_type":    course_types,
    "price_rub":      base_prices,
    "duration_weeks": duration_weeks,
    "created_at":     [date_str(rand_date(
                           START_DATE - timedelta(days=180),
                           START_DATE + timedelta(days=60)
                       )) for _ in range(N_COURSES)],
    "is_published":   np.random.choice([1, 0], size=N_COURSES, p=[0.90, 0.10]),
})
courses_df.to_csv(f"{OUTPUT_DIR}/courses.csv", index=False)
print(f"  → {len(courses_df):,} courses")

# ── Словари ───────────────────────────────────────────────────────────────────
course_price_map = dict(zip(courses_df["course_id"], courses_df["price_rub"]))
course_type_map  = dict(zip(courses_df["course_id"], courses_df["course_type"]))

# Веса курсов для записей — популярные предметы получают больше
subject_weight_map = dict(zip(SUBJECTS, SUBJECT_WEIGHTS))
course_popularity = np.array([
    subject_weight_map[s] for s in courses_df["subject"]
], dtype=float)
course_popularity /= course_popularity.sum()

# ══════════════════════════════════════════════════════════════════════════════
# 3. ENROLLMENTS
# ══════════════════════════════════════════════════════════════════════════════
print("Generating enrollments...")

# Генерируем записи с учётом распределения курсов на пользователя:
# 1 курс — 50%, 2–3 курса — 35%, 4+ — 15%
enrollment_rows = []
eid = 1

for uid in user_ids:
    reg_dt = user_reg_map[uid]

    # Определяем количество курсов для этого пользователя
    n_courses_draw = random.random()
    if n_courses_draw < 0.50:
        n = 1
    elif n_courses_draw < 0.85:
        n = random.randint(2, 3)
    else:
        n = random.randint(4, 6)

    chosen_courses = np.random.choice(
        course_ids, size=min(n, len(course_ids)),
        replace=False, p=course_popularity
    )

    for cid in chosen_courses:
        # Задержка от регистрации до записи
        delay_draw = random.random()
        if delay_draw < 0.40:
            delay_days = random.uniform(0, 1)
        elif delay_draw < 0.75:
            delay_days = random.uniform(1, 7)
        elif delay_draw < 0.95:
            delay_days = random.uniform(7, 30)
        else:
            delay_days = random.uniform(30, 120)

        enroll_dt = reg_dt + timedelta(days=delay_days)

        # Не выходим за конец периода
        if enroll_dt > END_DATE:
            enroll_dt = rand_date(reg_dt, END_DATE) if reg_dt < END_DATE else END_DATE

        # Статус и прогресс
        status_draw = random.random()
        if status_draw < 0.28:
            status = "completed"
            progress = 100
        elif status_draw < 0.63:
            status = "active"
            progress = random.randint(1, 99)
        elif status_draw < 0.88:
            status = "dropped"
            progress = random.randint(5, 60)
        else:
            status = "paused"
            progress = random.randint(20, 75)

        enrollment_rows.append({
            "enrollment_id": eid,
            "user_id":       uid,
            "course_id":     int(cid),
            "enrolled_at":   date_str(enroll_dt),
            "status":        status,
            "progress_pct":  progress,
        })
        eid += 1

enrollments_df = pd.DataFrame(enrollment_rows)
enrollments_df = enrollments_df.drop_duplicates(subset=["user_id", "course_id"])
enrollments_df = enrollments_df.reset_index(drop=True)
enrollments_df["enrollment_id"] = range(1, len(enrollments_df) + 1)

# ── Аномалия A4: 100 записей enrollment раньше регистрации ────────────────────
anomaly_idxs = random.sample(range(len(enrollments_df)), 100)
for idx in anomaly_idxs:
    uid  = enrollments_df.at[idx, "user_id"]
    reg  = user_reg_map[uid]
    bad_dt = reg - timedelta(days=random.randint(1, 30))
    enrollments_df.at[idx, "enrolled_at"] = date_str(bad_dt)

enrollments_df.to_csv(f"{OUTPUT_DIR}/enrollments.csv", index=False)
print(f"  → {len(enrollments_df):,} enrollments")

# ── Словари ───────────────────────────────────────────────────────────────────
enroll_dt_map  = {row.enrollment_id: datetime.strptime(row.enrolled_at, "%Y-%m-%d %H:%M:%S")
                  for row in enrollments_df.itertuples()}
enroll_key_map = {}  # (user_id, course_id) → enrollment_id
for row in enrollments_df.itertuples():
    enroll_key_map[(row.user_id, row.course_id)] = row.enrollment_id

# ══════════════════════════════════════════════════════════════════════════════
# 4. PAYMENTS
# ══════════════════════════════════════════════════════════════════════════════
print("Generating payments...")

# Только записи на платные курсы
paid_enroll = enrollments_df[
    enrollments_df["course_id"].map(course_price_map) > 0
].copy()

# 65% записей на платные курсы имеют оплату
paying_sample = paid_enroll.sample(frac=0.65, random_state=42).reset_index(drop=True)

payment_rows = []
pid = 1

for _, row in paying_sample.iterrows():
    enroll_dt  = datetime.strptime(row["enrolled_at"], "%Y-%m-%d %H:%M:%S")
    base_price = course_price_map[row["course_id"]]
    ctype      = course_type_map[row["course_id"]]

    # Подписки — несколько платежей с интервалом 30 дней
    n_payments = 1
    if ctype == "Подписка" and row["status"] in ("active", "completed"):
        months_active = max(1, int((END_DATE - enroll_dt).days / 30))
        n_payments = min(months_active, random.randint(1, 12))

    for payment_num in range(n_payments):
        pay_offset = timedelta(hours=random.randint(0, 72)) + timedelta(days=30 * payment_num)
        pay_dt = enroll_dt + pay_offset
        if pay_dt > END_DATE:
            break

        # Скидка — чаще в низкий сезон
        discount = 0
        low_season = pay_dt.month in (1, 7, 8)
        if random.random() < (0.30 if low_season else 0.15):
            discount = random.choice([10, 15, 20, 30])

        amount = int(base_price * (1 - discount / 100))

        # Статус
        status = np.random.choice(
            ["success", "refunded", "failed"],
            p=[0.88, 0.08, 0.04]
        )

        payment_rows.append({
            "payment_id":     pid,
            "user_id":        int(row["user_id"]),
            "course_id":      int(row["course_id"]),
            "enrollment_id":  int(row["enrollment_id"]),
            "paid_at":        date_str(pay_dt),
            "amount_rub":     amount,
            "base_price":     base_price,
            "discount_pct":   discount,
            "status":         status,
            "payment_method": np.random.choice(["card", "sbp", "wallet"], p=[0.65, 0.25, 0.10]),
        })
        pid += 1

payments_df = pd.DataFrame(payment_rows)

# ── Аномалия A5: 40 платежей с отрицательной суммой ──────────────────────────
neg_idxs = random.sample(range(len(payments_df)), 40)
for idx in neg_idxs:
    payments_df.at[idx, "amount_rub"] = -abs(payments_df.at[idx, "amount_rub"])

# ── Аномалия A6: 20 платежей с суммой 0 при статусе success ──────────────────
# Выбираем только из тех, что не попали в аномалию A5
remaining = [i for i in range(len(payments_df)) if i not in neg_idxs]
zero_idxs = random.sample(remaining, 20)
for idx in zero_idxs:
    payments_df.at[idx, "amount_rub"] = 0
    payments_df.at[idx, "status"]     = "success"

payments_df.to_csv(f"{OUTPUT_DIR}/payments.csv", index=False)
print(f"  → {len(payments_df):,} payments")

# ── Словари для payment_attempts ──────────────────────────────────────────────
success_payments = payments_df[payments_df["status"] == "success"]

# ══════════════════════════════════════════════════════════════════════════════
# 5. PAYMENT_ATTEMPTS
# ══════════════════════════════════════════════════════════════════════════════
print("Generating payment_attempts...")

attempt_rows = []
aid = 1

FAILURE_REASONS = ["user_cancelled", "insufficient_funds", "card_declined", "timeout"]
FAILURE_WEIGHTS = [0.40, 0.25, 0.20, 0.15]

# Шаг A: каждый успешный платёж → одна попытка success
for _, pay in success_payments.iterrows():
    pay_dt = datetime.strptime(pay["paid_at"], "%Y-%m-%d %H:%M:%S")
    attempt_rows.append({
        "attempt_id":     aid,
        "user_id":        int(pay["user_id"]),
        "course_id":      int(pay["course_id"]),
        "attempted_at":   date_str(pay_dt),
        "result":         "success",
        "failure_reason": None,
        "payment_method": pay["payment_method"],
    })
    aid += 1

# Шаг B: дополнительные failed/abandoned (на каждые 100 успешных — 40 failed, 25 abandoned)
n_success = len(success_payments)
n_failed   = int(n_success * 0.40)
n_abandoned = int(n_success * 0.25)

# Берём случайных пользователей и курсы для незавершённых попыток
all_user_ids   = users_df["user_id"].tolist()
paid_course_list = paid_enroll["course_id"].tolist()

for result, n in [("failed", n_failed), ("abandoned", n_abandoned)]:
    for _ in range(n):
        uid = random.choice(all_user_ids)
        cid = random.choice(paid_course_list)
        reg = user_reg_map[uid]

        attempt_dt = rand_date(
            max(reg, START_DATE),
            END_DATE
        )
        reason = np.random.choice(FAILURE_REASONS, p=FAILURE_WEIGHTS)

        attempt_rows.append({
            "attempt_id":     aid,
            "user_id":        int(uid),
            "course_id":      int(cid),
            "attempted_at":   date_str(attempt_dt),
            "result":         result,
            "failure_reason": reason,
            "payment_method": np.random.choice(["card", "sbp", "wallet"], p=[0.65, 0.25, 0.10]),
        })
        aid += 1

payment_attempts_df = pd.DataFrame(attempt_rows)

# ── Аномалия A7: ~200 orphan records с несуществующим user_id ─────────────────
max_uid = max(user_ids)
orphan_idxs = random.sample(range(len(payment_attempts_df)), 200)
for idx in orphan_idxs:
    payment_attempts_df.at[idx, "user_id"] = max_uid + random.randint(1, 500)

payment_attempts_df = payment_attempts_df.sort_values("attempted_at").reset_index(drop=True)
payment_attempts_df["attempt_id"] = range(1, len(payment_attempts_df) + 1)

payment_attempts_df.to_csv(f"{OUTPUT_DIR}/payment_attempts.csv", index=False)
print(f"  → {len(payment_attempts_df):,} payment_attempts")

# ══════════════════════════════════════════════════════════════════════════════
# 6. AD_COSTS
# ══════════════════════════════════════════════════════════════════════════════
print("Generating ad_costs...")

CHANNEL_BUDGETS = {
    "vk_ads":        {"min": 15_000, "max": 45_000, "ctr_min": 0.008, "ctr_max": 0.015},
    "yandex_direct": {"min": 10_000, "max": 35_000, "ctr_min": 0.020, "ctr_max": 0.040},
    "telegram":      {"min":  3_000, "max": 10_000, "ctr_min": 0.030, "ctr_max": 0.060},
}

ad_rows = []
cur_date = START_DATE.date()
end_date = END_DATE.date()

while cur_date <= end_date:
    month    = cur_date.month
    season_k = SEASON[month]

    for channel, params in CHANNEL_BUDGETS.items():
        # Базовый расход с учётом сезонности
        base_spend = random.uniform(params["min"], params["max"])
        spend = int(base_spend * season_k)

        # CTR для расчёта кликов
        ctr = random.uniform(params["ctr_min"], params["ctr_max"])

        # Показы из бюджета (CPM ~200–400 рублей за 1000 показов)
        cpm = random.uniform(200, 400)
        impressions = int((spend / cpm) * 1000)
        clicks      = int(impressions * ctr)

        ad_rows.append({
            "date":        str(cur_date),
            "channel":     channel,
            "impressions": impressions,
            "clicks":      clicks,
            "spend_rub":   spend,
        })

    cur_date += timedelta(days=1)

ad_costs_df = pd.DataFrame(ad_rows)

# ── Аномалия A8: ~15 строк — нулевой расход при ненулевых показах ─────────────
zero_spend_idxs = random.sample(range(len(ad_costs_df)), 15)
for idx in zero_spend_idxs:
    ad_costs_df.at[idx, "spend_rub"] = 0
    # показы и клики оставляем ненулевыми — это и есть аномалия

# ── Аномалия A9: несколько дат в будущем ──────────────────────────────────────
future_ad_idxs = random.sample(range(len(ad_costs_df)), 5)
for idx in future_ad_idxs:
    future_d = TODAY.date() + timedelta(days=random.randint(1, 30))
    ad_costs_df.at[idx, "date"] = str(future_d)

ad_costs_df.to_csv(f"{OUTPUT_DIR}/ad_costs.csv", index=False)
print(f"  → {len(ad_costs_df):,} ad_costs rows")

# ══════════════════════════════════════════════════════════════════════════════
# СВОДКА
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*55)
print("✅ Dataset generated successfully!")
print("="*55)
print(f"   {'users.csv':<25} {len(users_df):>7,} rows")
print(f"   {'courses.csv':<25} {len(courses_df):>7,} rows")
print(f"   {'enrollments.csv':<25} {len(enrollments_df):>7,} rows")
print(f"   {'payments.csv':<25} {len(payments_df):>7,} rows")
print(f"   {'payment_attempts.csv':<25} {len(payment_attempts_df):>7,} rows")
print(f"   {'ad_costs.csv':<25} {len(ad_costs_df):>7,} rows")
print()
print("   Намеренные аномалии:")
print("   A1 · ~50  дублирующихся email в users")
print("   A2 · 30   дат регистрации в будущем (users)")
print("   A3 · 5    курсов с ценой 0 (courses)")
print("   A4 · 100  записей enrollment раньше регистрации")
print("   A5 · 40   платежей с отрицательной суммой")
print("   A6 · 20   платежей с суммой 0 при статусе success")
print("   A7 · ~200 orphan records в payment_attempts")
print("   A8 · 15   строк с spend=0 при показах > 0 (ad_costs)")
print("   A9 · 5    дат в будущем (ad_costs)")
print()
print(f"   Период: {START_DATE.strftime('%Y-%m-%d')} → {END_DATE.strftime('%Y-%m-%d')}")
print(f"   Выходная папка: {OUTPUT_DIR}/")