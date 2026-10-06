"""Check that Python can reach MySQL: python test_connection.py"""
import os

import mysql.connector

from db import get_connection

try:
    conn = get_connection(use_database=False)
except mysql.connector.Error as err:
    raise SystemExit(f"Connection failed: {err}")

cur = conn.cursor()
cur.execute("SELECT VERSION(), CURRENT_USER()")
version, user = cur.fetchone()
print(f"Connected: MySQL {version} as {user}")

cur.execute("SHOW DATABASES")
databases = [row[0] for row in cur.fetchall()]
print("Databases:", ", ".join(databases))

target = os.getenv("MYSQL_DATABASE", "ptcg")
print(f"Database '{target}':", "exists" if target in databases else "not created yet")

cur.close()
conn.close()
