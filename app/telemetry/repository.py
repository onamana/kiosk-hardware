from typing import Any

from app.db.session import MariaDb, parse_mysql_time


class TelemetryRepository:
    def __init__(self, db: MariaDb):
        self.db = db

    def insert_temperature_humidity(
        self,
        sen_id: int,
        time_val: Any = None,
        temp: float | None = None,
        humid: float | None = None,
    ) -> bool:
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO th_trans (sen_id, time, temp, humid)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        temp = VALUES(temp),
                        humid = VALUES(humid)
                    """,
                    (sen_id, parse_mysql_time(time_val), temp, humid),
                )
            conn.commit()
            return True

    def insert_heart_rate(self, sen_id: int, time_val: Any = None, hr: float | None = None) -> bool:
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO hb_trans (sen_id, time, hr)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE hr = VALUES(hr)
                    """,
                    (sen_id, parse_mysql_time(time_val), hr),
                )
            conn.commit()
            return True

    def get_latest_temperature_humidity(self, sensor_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        where = ""
        params: tuple[Any, ...] = (limit,)
        if sensor_id:
            where = "WHERE s.sensor_id = %s"
            params = (sensor_id, limit)

        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT s.sensor_id, s.sen_name, t.sen_id, t.time, t.temp, t.humid
                    FROM th_trans t
                    JOIN sensor s ON s.sen_id = t.sen_id
                    {where}
                    ORDER BY t.time DESC
                    LIMIT %s
                    """,
                    params,
                )
                return list(cursor.fetchall())

    def get_latest_heart_rate(self, sensor_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        where = ""
        params: tuple[Any, ...] = (limit,)
        if sensor_id:
            where = "WHERE s.sensor_id = %s"
            params = (sensor_id, limit)

        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT s.sensor_id, s.sen_name, h.sen_id, h.time, h.hr
                    FROM hb_trans h
                    JOIN sensor s ON s.sen_id = h.sen_id
                    {where}
                    ORDER BY h.time DESC
                    LIMIT %s
                    """,
                    params,
                )
                return list(cursor.fetchall())
