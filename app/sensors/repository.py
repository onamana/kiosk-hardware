from typing import Any

from app.db.session import MariaDb, parse_mysql_time


class SensorRepository:
    def __init__(self, db: MariaDb):
        self.db = db

    def get_first_jetson(self) -> dict[str, Any] | None:
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM jetson ORDER BY jetson_id LIMIT 1")
                return cursor.fetchone()

    def get_registered_sensors(self) -> list[dict[str, Any]]:
        query = """
            SELECT
                s.sen_id,
                s.sensor_id,
                s.jetson_id,
                s.sensor_type,
                s.sen_name,
                s.sen_locate,
                s.model,
                s.mqtt_topic,
                s.mdns_hostname,
                s.ip_addr,
                s.space_id,
                sp.space_name,
                sp.hazard_type,
                sp.is_hazard,
                s.is_online,
                s.last_seen_at,
                s.registered_at,
                s.created_at,
                s.updated_at
            FROM sensor s
            LEFT JOIN ds_space sp ON s.space_id = sp.space_id
            ORDER BY s.updated_at DESC
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                return list(cursor.fetchall())

    def get_sensor_by_sensor_id(self, sensor_id: str) -> dict[str, Any] | None:
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM sensor WHERE sensor_id = %s LIMIT 1", (sensor_id,))
                return cursor.fetchone()

    def get_sensor_by_mqtt_topic(self, topic: str) -> dict[str, Any] | None:
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM sensor WHERE mqtt_topic = %s LIMIT 1", (topic,))
                return cursor.fetchone()

    def is_registered_sensor(self, sensor_id: str) -> bool:
        return self.get_sensor_by_sensor_id(sensor_id) is not None

    def register_discovered_sensors(self, jetson_id: int, sensors: list[dict[str, Any]]) -> int:
        query = """
            INSERT INTO sensor (
                sensor_id,
                jetson_id,
                sensor_type,
                sen_name,
                sen_locate,
                model,
                mqtt_topic,
                mdns_hostname,
                ip_addr,
                is_online,
                last_seen_at,
                registered_at,
                created_at,
                updated_at,
                space_id
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, NOW(), NOW(), NOW(), %s
            )
            ON DUPLICATE KEY UPDATE
                jetson_id = VALUES(jetson_id),
                sensor_type = VALUES(sensor_type),
                sen_name = VALUES(sen_name),
                sen_locate = VALUES(sen_locate),
                model = VALUES(model),
                mqtt_topic = VALUES(mqtt_topic),
                mdns_hostname = VALUES(mdns_hostname),
                ip_addr = VALUES(ip_addr),
                is_online = VALUES(is_online),
                last_seen_at = VALUES(last_seen_at),
                space_id = VALUES(space_id),
                updated_at = NOW()
        """
        with self.db.connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT space_id FROM jetson WHERE jetson_id = %s LIMIT 1", (jetson_id,))
                    jetson = cursor.fetchone()
                    if not jetson:
                        raise ValueError(f"존재하지 않는 Jetson입니다. jetson_id={jetson_id}")
                    space_id = jetson["space_id"]
                    if space_id is None:
                        raise ValueError("Jetson에 공간이 매핑되어 있지 않아 센서를 등록할 수 없습니다.")

                    count = 0
                    for sensor in sensors:
                        sensor_id = sensor.get("sensor_id")
                        if not sensor_id:
                            continue

                        mqtt_topic = (
                            sensor.get("mqtt_topic")
                            or sensor.get("telemetry_topic")
                            or (
                                f"{sensor.get('mqtt_base')}/telemetry"
                                if sensor.get("mqtt_base")
                                else None
                            )
                        )

                        cursor.execute(
                            query,
                            (
                                sensor_id,
                                jetson_id,
                                sensor.get("sensor_type", "unknown"),
                                sensor.get("sen_name") or sensor.get("sensor_name") or sensor_id,
                                sensor.get("sen_locate") or sensor.get("sensor_location") or "default",
                                sensor.get("model"),
                                mqtt_topic,
                                sensor.get("mdns_hostname"),
                                sensor.get("ip_addr"),
                                1 if sensor.get("is_online", True) else 0,
                                parse_mysql_time(sensor.get("last_seen_at")),
                                space_id,
                            ),
                        )
                        count += 1
                conn.commit()
                return count
            except Exception:
                conn.rollback()
                raise

    def unregister_sensor(self, sensor_id: str) -> bool:
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                affected = cursor.execute("DELETE FROM sensor WHERE sensor_id = %s", (sensor_id,))
            conn.commit()
            return affected > 0

    def update_sensor_online(self, sensor_id: str, is_online: bool, last_seen_at: Any = None) -> bool:
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                affected = cursor.execute(
                    """
                    UPDATE sensor
                    SET is_online = %s, last_seen_at = %s, updated_at = NOW()
                    WHERE sensor_id = %s
                    """,
                    (1 if is_online else 0, parse_mysql_time(last_seen_at), sensor_id),
                )
            conn.commit()
            return affected > 0

    def update_sensor_last_seen_by_id(self, sen_id: int) -> bool:
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                affected = cursor.execute(
                    """
                    UPDATE sensor
                    SET is_online = 1, last_seen_at = NOW(), updated_at = NOW()
                    WHERE sen_id = %s
                    """,
                    (sen_id,),
                )
            conn.commit()
            return affected > 0
