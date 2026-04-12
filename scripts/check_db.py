import duckdb

con = duckdb.connect("data/db/platform.duckdb", read_only=True)

print("=== Все таблицы в базе ===\n")

schemas = ["raw", "staging", "marts"]
for schema in schemas:
    tables = con.execute(f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = '{schema}'
        ORDER BY table_name
    """).fetchall()

    print(f"  [{schema}]")
    for (table,) in tables:
        count = con.execute(
            f"SELECT COUNT(*) FROM {schema}.{table}"
        ).fetchone()[0]
        print(f"    {table:<30} {count:>8,} строк")
    print()

print("=== Первые 3 строки mart_revenue ===\n")
rows = con.execute("""
    SELECT payment_month, paying_users, revenue, avg_check, revenue_mom_pct
    FROM marts.mart_revenue
    ORDER BY payment_month
    LIMIT 3
""").fetchall()
for r in rows:
    print(" ", r)

con.close()