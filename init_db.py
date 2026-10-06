"""Create the database and apply schema.sql: python init_db.py

Safe to re-run: existing tables and data are left untouched.
"""
import os
from pathlib import Path

from db import get_connection

database = os.getenv("MYSQL_DATABASE", "ptcg")
schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")

# Drop comment lines first so a ';' inside a comment cannot split a statement
sql = "\n".join(line for line in schema.splitlines() if not line.lstrip().startswith("--"))
statements = [s.strip() for s in sql.split(";") if s.strip()]

conn = get_connection(use_database=False)
cur = conn.cursor()
cur.execute(
    f"CREATE DATABASE IF NOT EXISTS `{database}` "
    "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
)
cur.execute(f"USE `{database}`")
for statement in statements:
    cur.execute(statement)
conn.commit()

cur.execute(
    "SELECT table_name, table_rows FROM information_schema.tables "
    "WHERE table_schema = %s ORDER BY table_name",
    (database,),
)
print(f"Database '{database}' is ready:")
for name, rows in cur.fetchall():
    print(f"  {name:<16} ~{rows} rows")

cur.close()
conn.close()
