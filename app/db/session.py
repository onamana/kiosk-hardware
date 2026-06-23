from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

import pymysql

from app.config.settings import Settings


class MariaDb:
    def __init__(self, settings: Settings):
        self.config = {
            "host": settings.mariadb_host,
            "user": settings.mariadb_user,
            "password": settings.mariadb_password,
            "database": settings.mariadb_db_name,
            "port": settings.mariadb_port,
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": False,
        }

    @contextmanager
    def connection(self) -> Iterator[pymysql.connections.Connection]:
        conn = pymysql.connect(**self.config)
        try:
            yield conn
        finally:
            conn.close()


def parse_mysql_time(value: Any = None) -> str:
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 9999999999:
                timestamp = timestamp / 1000
            dt = datetime.fromtimestamp(timestamp)
        elif isinstance(value, str):
            normalized = value.replace("Z", "").replace("T", " ")
            dt = datetime.fromisoformat(normalized)
        else:
            dt = datetime.now()
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
