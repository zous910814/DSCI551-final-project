"""MySQL connection helper. Reads settings from .env (see .env.example)."""
import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def get_connection(use_database=True):
    """Return a MySQL connection. Pass use_database=False before the schema exists."""
    config = {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "charset": "utf8mb4",
    }
    if use_database:
        config["database"] = os.getenv("MYSQL_DATABASE", "ptcg")
    return mysql.connector.connect(**config)
