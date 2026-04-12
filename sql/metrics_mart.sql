
-- ============================================================
-- metrics_mart.sql
-- Витрины данных платформы "ЕГЭ Экспресс"
--
-- Четыре витрины, каждая закрывает один дашборд:
--   mart_revenue        → R1 Финансовый дашборд
--   mart_ad_performance → R3 Маркетинговый дашборд
--   mart_activity       → R5 Продуктовый дашборд
--   mart_conversion     → R7 Воронка конверсии
--
-- Дополнительная витрина:
--   mart_completion     → Completion Rate по предметам и уровням
--
-- Все витрины читают из схемы staging.
-- Запускается автоматически через init_db.py.
-- ============================================================


-- ============================================================
-- mart_revenue — финансовые метрики по месяцам
-- Закрывает: R1 (дашборд), R2 (еженедельный отчёт)
-- Получатели: CEO, финансовый директор
-- ============================================================
CREATE OR REPLACE TABLE marts.mart_revenue AS

WITH payments_base AS (
    SELECT
        p.payment_id,
        p.user_id,
        p.amount_rub,
        p.discount_pct,
        c.course_type,
        DATE_TRUNC('month', p.paid_at) AS payment_month
    FROM staging.stg_payments p
    JOIN staging.stg_courses c ON p.course_id = c.course_id
    WHERE p.status = 'success'
),

monthly AS (
    SELECT
        payment_month,
        COUNT(DISTINCT user_id)                                          AS paying_users,
        COUNT(payment_id)                                                AS transactions,
        SUM(amount_rub)                                                  AS revenue,
        ROUND(AVG(amount_rub), 0)                                        AS avg_check,
        ROUND(SUM(amount_rub)::DOUBLE / COUNT(DISTINCT user_id), 0)     AS arpu,
        SUM(CASE WHEN course_type = 'Подписка' THEN amount_rub ELSE 0 END) AS mrr,
        ROUND(100.0 * SUM(CASE WHEN discount_pct > 0 THEN 1 ELSE 0 END)
              / COUNT(payment_id), 1)                                    AS discount_rate_pct,
        SUM(CASE WHEN course_type = 'Курс'      THEN amount_rub ELSE 0 END) AS revenue_courses,
        SUM(CASE WHEN course_type = 'Интенсив'  THEN amount_rub ELSE 0 END) AS revenue_intensive,
        SUM(CASE WHEN course_type = 'Подписка'  THEN amount_rub ELSE 0 END) AS revenue_subscription
    FROM payments_base
    GROUP BY payment_month
)

SELECT
    payment_month,
    paying_users,
    transactions,
    revenue,
    avg_check,
    arpu,
    mrr,
    discount_rate_pct,
    revenue_courses,
    revenue_intensive,
    revenue_subscription,
    LAG(revenue) OVER (ORDER BY payment_month)                           AS revenue_prev_month,
    ROUND(
        100.0 * (revenue - LAG(revenue) OVER (ORDER BY payment_month))
        / NULLIF(LAG(revenue) OVER (ORDER BY payment_month), 0), 1
    )                                                                    AS revenue_mom_pct,
    SUM(revenue) OVER (ORDER BY payment_month)                           AS revenue_cumulative
FROM monthly
ORDER BY payment_month;


-- ============================================================
-- mart_ad_performance — эффективность рекламных каналов
-- Закрывает: R3 (дашборд), R4 (ежемесячный отчёт)
-- Получатели: маркетолог, CEO
-- ============================================================
CREATE OR REPLACE TABLE marts.mart_ad_performance AS

WITH ad_monthly AS (
    SELECT
        DATE_TRUNC('month', date) AS month,
        channel,
        SUM(spend_rub)            AS spend,
        SUM(impressions)          AS impressions,
        SUM(clicks)               AS clicks
    FROM staging.stg_ad_costs
    GROUP BY DATE_TRUNC('month', date), channel
),

reg_monthly AS (
    SELECT
        DATE_TRUNC('month', registered_at) AS month,
        channel,
        COUNT(user_id)                     AS registrations
    FROM staging.stg_users
    WHERE channel IN ('vk_ads', 'yandex_direct', 'telegram')
    GROUP BY DATE_TRUNC('month', registered_at), channel
),

paying_monthly AS (
    SELECT
        DATE_TRUNC('month', p.paid_at) AS month,
        u.channel,
        COUNT(DISTINCT p.user_id)      AS paying_users,
        SUM(p.amount_rub)              AS revenue
    FROM staging.stg_payments p
    JOIN staging.stg_users u ON p.user_id = u.user_id
    WHERE p.status = 'success'
      AND u.channel IN ('vk_ads', 'yandex_direct', 'telegram')
    GROUP BY DATE_TRUNC('month', p.paid_at), u.channel
)

SELECT
    a.month,
    a.channel,
    a.spend,
    a.impressions,
    a.clicks,
    COALESCE(r.registrations,    0)                                AS registrations,
    COALESCE(pm.paying_users,    0)                                AS paying_users,
    COALESCE(pm.revenue,         0)                                AS revenue_from_channel,
    ROUND(100.0 * a.clicks / NULLIF(a.impressions, 0), 2)         AS ctr_pct,
    ROUND(a.spend::DOUBLE / NULLIF(a.clicks, 0), 0)               AS cpc,
    ROUND(1000.0 * a.spend / NULLIF(a.impressions, 0), 0)         AS cpm,
    ROUND(a.spend::DOUBLE / NULLIF(pm.paying_users, 0), 0)        AS cac,
    ROUND(COALESCE(pm.revenue, 0)::DOUBLE / NULLIF(a.spend, 0), 2) AS roas
FROM ad_monthly a
LEFT JOIN reg_monthly  r  ON a.month = r.month  AND a.channel = r.channel
LEFT JOIN paying_monthly pm ON a.month = pm.month AND a.channel = pm.channel
ORDER BY a.month, a.channel;


-- ============================================================
-- mart_activity — когортный retention
-- Закрывает: R5 (дашборд), R6 (когортный отчёт)
-- Получатели: продакт-менеджер, CEO
-- Примечание: активность — прокси через enrollments.
-- В продакшн заменить на таблицу events/sessions.
-- ============================================================
CREATE OR REPLACE TABLE marts.mart_activity AS

WITH first_enrollment AS (
    SELECT
        user_id,
        DATE_TRUNC('month', MIN(enrolled_at))::DATE AS cohort_month
    FROM staging.stg_enrollments
    GROUP BY user_id
),

cohort_activity AS (
    SELECT
        fe.cohort_month,
        DATE_TRUNC('month', e.enrolled_at)::DATE    AS activity_month,
        DATEDIFF('month',
            fe.cohort_month,
            DATE_TRUNC('month', e.enrolled_at)::DATE
        )                                           AS month_number,
        COUNT(DISTINCT e.user_id)                   AS retained_users
    FROM staging.stg_enrollments e
    JOIN first_enrollment fe ON e.user_id = fe.user_id
    GROUP BY fe.cohort_month, DATE_TRUNC('month', e.enrolled_at)::DATE
),

cohort_sizes AS (
    SELECT cohort_month, retained_users AS cohort_size
    FROM cohort_activity
    WHERE month_number = 0
)

SELECT
    ca.cohort_month,
    ca.month_number,
    cs.cohort_size,
    ca.retained_users,
    ROUND(100.0 * ca.retained_users / NULLIF(cs.cohort_size, 0), 1) AS retention_rate_pct
FROM cohort_activity ca
JOIN cohort_sizes cs ON ca.cohort_month = cs.cohort_month
ORDER BY ca.cohort_month, ca.month_number;


-- ============================================================
-- mart_completion — completion rate по предметам и уровням
-- Закрывает: R5 (продуктовый дашборд, блок успеваемости)
-- Получатели: продакт-менеджер
-- ============================================================
CREATE OR REPLACE TABLE marts.mart_completion AS

SELECT
    c.subject,
    c.level,
    c.course_type,
    COUNT(e.enrollment_id)                                           AS total_enrollments,
    SUM(CASE WHEN e.status = 'completed' THEN 1 ELSE 0 END)         AS completed,
    SUM(CASE WHEN e.status = 'active'    THEN 1 ELSE 0 END)         AS active,
    SUM(CASE WHEN e.status = 'dropped'   THEN 1 ELSE 0 END)         AS dropped,
    ROUND(100.0
          * SUM(CASE WHEN e.status = 'completed' THEN 1 ELSE 0 END)
          / NULLIF(COUNT(e.enrollment_id), 0), 1)                    AS completion_rate_pct,
    ROUND(100.0
          * SUM(CASE WHEN e.status = 'dropped' THEN 1 ELSE 0 END)
          / NULLIF(COUNT(e.enrollment_id), 0), 1)                    AS dropout_rate_pct,
    ROUND(AVG(CASE WHEN e.status = 'active'
                   THEN e.progress_pct END), 1)                      AS avg_progress_active
FROM staging.stg_enrollments e
JOIN staging.stg_courses c ON e.course_id = c.course_id
GROUP BY c.subject, c.level, c.course_type
ORDER BY completion_rate_pct DESC;


-- ============================================================
-- mart_conversion — воронка конверсии по когортам
-- Закрывает: R7 (дашборд)
-- Получатели: продакт-менеджер, маркетолог
-- ============================================================
CREATE OR REPLACE TABLE marts.mart_conversion AS

WITH step_registered AS (
    SELECT
        DATE_TRUNC('month', registered_at) AS cohort_month,
        COUNT(user_id)                     AS registered
    FROM staging.stg_users
    GROUP BY DATE_TRUNC('month', registered_at)
),

step_enrolled AS (
    SELECT
        DATE_TRUNC('month', u.registered_at) AS cohort_month,
        COUNT(DISTINCT e.user_id)            AS enrolled
    FROM staging.stg_users u
    JOIN staging.stg_enrollments e ON u.user_id = e.user_id
    GROUP BY DATE_TRUNC('month', u.registered_at)
),

step_paid AS (
    SELECT
        DATE_TRUNC('month', u.registered_at) AS cohort_month,
        COUNT(DISTINCT p.user_id)            AS paid
    FROM staging.stg_users u
    JOIN staging.stg_payments p
        ON u.user_id = p.user_id AND p.status = 'success'
    GROUP BY DATE_TRUNC('month', u.registered_at)
),

step_completed AS (
    SELECT
        DATE_TRUNC('month', u.registered_at) AS cohort_month,
        COUNT(DISTINCT e.user_id)            AS completed
    FROM staging.stg_users u
    JOIN staging.stg_enrollments e
        ON u.user_id = e.user_id AND e.status = 'completed'
    GROUP BY DATE_TRUNC('month', u.registered_at)
),

step_attempts AS (
    SELECT
        DATE_TRUNC('month', u.registered_at)                AS cohort_month,
        COUNT(pa.attempt_id)                                AS total_attempts,
        SUM(CASE WHEN pa.result = 'abandoned' THEN 1 ELSE 0 END) AS abandoned
    FROM staging.stg_payment_attempts pa
    JOIN staging.stg_users u ON pa.user_id = u.user_id
    GROUP BY DATE_TRUNC('month', u.registered_at)
)

SELECT
    r.cohort_month,
    r.registered,
    COALESCE(e.enrolled,  0)                                         AS enrolled,
    COALESCE(p.paid,      0)                                         AS paid,
    COALESCE(c.completed, 0)                                         AS completed,
    ROUND(100.0 * COALESCE(e.enrolled, 0)
          / NULLIF(r.registered, 0), 1)                              AS cvr_reg_to_enroll_pct,
    ROUND(100.0 * COALESCE(p.paid, 0)
          / NULLIF(e.enrolled, 0), 1)                                AS cvr_enroll_to_paid_pct,
    ROUND(100.0 * COALESCE(c.completed, 0)
          / NULLIF(p.paid, 0), 1)                                    AS cvr_paid_to_completed_pct,
    ROUND(100.0 * COALESCE(p.paid, 0)
          / NULLIF(r.registered, 0), 2)                              AS overall_cvr_pct,
    COALESCE(pa.total_attempts, 0)                                   AS payment_attempts_total,
    COALESCE(pa.abandoned, 0)                                        AS payment_attempts_abandoned,
    ROUND(100.0 * COALESCE(pa.abandoned, 0)
          / NULLIF(pa.total_attempts, 0), 1)                         AS payment_dropoff_pct
FROM step_registered r
LEFT JOIN step_enrolled   e  ON r.cohort_month = e.cohort_month
LEFT JOIN step_paid       p  ON r.cohort_month = p.cohort_month
LEFT JOIN step_completed  c  ON r.cohort_month = c.cohort_month
LEFT JOIN step_attempts   pa ON r.cohort_month = pa.cohort_month
ORDER BY r.cohort_month;