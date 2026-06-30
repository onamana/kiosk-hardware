from typing import Any

from app.db.session import MariaDb, parse_mysql_time


class TelemetryRepository:
    def __init__(self, db: MariaDb):
        self.db = db

    def insert_temperature_humidity(
        self,
        time_val: Any = None,
        temp: float | None = None,
        humid: float | None = None,
        sensor_name: str | None = None,
    ) -> int:
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO temperature_humidity_sensor (sensor_name, temperature, humidity, measured_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (sensor_name, temp, humid, parse_mysql_time(time_val)),
                )
                sensor_id = cursor.lastrowid
            conn.commit()
            return int(sensor_id)

    def insert_heart_rate(self, time_val: Any = None, hr: float | None = None) -> int:
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO heartbeat_sensor (heart_rate, measured_at)
                    VALUES (%s, %s)
                    """,
                    (hr, parse_mysql_time(time_val)),
                )
                sensor_id = cursor.lastrowid
            conn.commit()
            return int(sensor_id)

    def get_latest_temperature_humidity(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT sensor_id, sensor_name, temperature, humidity, measured_at
                    FROM temperature_humidity_sensor
                    ORDER BY measured_at DESC, sensor_id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return list(cursor.fetchall())

    def get_latest_heart_rate(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT sensor_id, heart_rate, measured_at
                    FROM heartbeat_sensor
                    ORDER BY measured_at DESC, sensor_id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return list(cursor.fetchall())
