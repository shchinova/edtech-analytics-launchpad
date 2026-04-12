# Отчёт о качестве данных — STAGING

**Источник данных:** Очищенные данные (staging layer, DuckDB)  
**Дата проверки:** 2026-04-11 12:39  
**Период данных:** январь 2024 — июнь 2025

## Объём данных

| Таблица | Строк |
|---|---|
| users | 4,950 |
| courses | 113 |
| enrollments | 9,905 |
| payments | 7,619 |
| payment_attempts | 11,326 |
| ad_costs | 1,626 |

## Сводка

| Уровень | Проверок с ошибками | Записей с ошибками |
|---|---|---|
| 🔴 CRITICAL | 0 | 0 |
| 🟡 WARNING  | 1 | 5 |
| **Итого** | **1** | **5** |

## Найденные ошибки

| Код | Таблица | Записей | Уровень | Описание | Рекомендация |
|---|---|---|---|---|---|
| `A4` | `courses` | **5** | 🟡 WARNING | Курс с ценой 0 — если не бесплатный, ошибка заведения продукта. | Добавить флаг is_free; исключать из расчёта выручки и среднего чека. |

## Проверки без ошибок

| Код | Таблица | Уровень |
|---|---|---|
| `A1` | `users` | 🟡 WARNING |
| `A2` | `users` | 🟡 WARNING |
| `A3` | `users` | 🟢 INFO |
| `A5` | `courses` | 🟢 INFO |
| `A6` | `enrollments+users` | 🔴 CRITICAL |
| `A7` | `enrollments` | 🔴 CRITICAL |
| `A8` | `enrollments` | 🟡 WARNING |
| `A9` | `enrollments→courses` | 🔴 CRITICAL |
| `A10` | `payments` | 🔴 CRITICAL |
| `A11` | `payments` | 🔴 CRITICAL |
| `A12` | `payments+users` | 🔴 CRITICAL |
| `A13` | `payments+courses` | 🟡 WARNING |
| `A14` | `payments→enrollments` | 🔴 CRITICAL |
| `A15` | `payment_attempts→users` | 🟡 WARNING |
| `A16` | `payment_attempts→payments` | 🔴 CRITICAL |
| `A17` | `payment_attempts` | 🔴 CRITICAL |
| `A18` | `ad_costs` | 🟡 WARNING |
| `A19` | `ad_costs` | 🟡 WARNING |
| `A20` | `ad_costs` | 🟢 INFO |

## Что изменилось после очистки

Staging-слой применяет следующие фильтры:

- Пользователи: исключены дубли email (оставлена первая запись)
- Пользователи: исключены `registered_at` в будущем
- Курсы: исключены неопубликованные (`is_published = 0`)
- Enrollments: исключены записи где `enrolled_at < registered_at`
- Payments: исключены `amount_rub ≤ 0`
- Payments: исключены `amount_rub = 0` при `status = success`
- Payments: исключены записи где `paid_at < registered_at`
- Payment_attempts: исключены orphan records
- Ad_costs: исключены `spend_rub = 0` при `impressions > 0`
- Ad_costs: исключены даты в будущем

Для сравнения с исходным состоянием: [quality_raw.md](./quality_raw.md)  
Детальное сравнение: `python scripts/check_quality.py --source compare`

---
*Сгенерировано: `python scripts/check_quality.py --source staging`*