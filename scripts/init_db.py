from pathlib import Path
import sys

import pymysql

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config.settings import settings


SCHEMA_SQL = (
    """
    CREATE DATABASE IF NOT EXISTS `{database}`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS temperature_humidity_sensor (
        sensor_id INT NOT NULL AUTO_INCREMENT,
        sensor_name VARCHAR(100) NULL,
        temperature DECIMAL(5,2) NULL,
        humidity DECIMAL(5,2) NULL,
        measured_at DATETIME NOT NULL,
        PRIMARY KEY (sensor_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS heartbeat_sensor (
        sensor_id INT NOT NULL AUTO_INCREMENT,
        heart_rate INT NULL,
        measured_at DATETIME NOT NULL,
        PRIMARY KEY (sensor_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS cctv_info (
        cctv_id INT NOT NULL AUTO_INCREMENT,
        rtsp_url VARCHAR(255) NULL,
        frame_dir VARCHAR(200) NULL,
        PRIMARY KEY (cctv_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS unstable_behavior (
        behavior_id INT NOT NULL AUTO_INCREMENT,
        hat_removal_count INT NOT NULL DEFAULT 0,
        ladder_alone_count INT NOT NULL DEFAULT 0,
        restricted_area_count INT NOT NULL DEFAULT 0,
        speaker_touch_count INT NOT NULL DEFAULT 0,
        PRIMARY KEY (behavior_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS `process` (
        process_id INT NOT NULL AUTO_INCREMENT,
        process_name VARCHAR(100) NULL,
        behavior_id INT NULL,
        th_sensor_id INT NULL,
        hb_sensor_id INT NULL,
        cctv_id INT NULL,
        PRIMARY KEY (process_id),
        INDEX idx_process_behavior_id (behavior_id),
        INDEX idx_process_th_sensor_id (th_sensor_id),
        INDEX idx_process_hb_sensor_id (hb_sensor_id),
        INDEX idx_process_cctv_id (cctv_id),
        CONSTRAINT fk_process_behavior
            FOREIGN KEY (behavior_id) REFERENCES unstable_behavior (behavior_id),
        CONSTRAINT fk_process_th_sensor
            FOREIGN KEY (th_sensor_id) REFERENCES temperature_humidity_sensor (sensor_id),
        CONSTRAINT fk_process_hb_sensor
            FOREIGN KEY (hb_sensor_id) REFERENCES heartbeat_sensor (sensor_id),
        CONSTRAINT fk_process_cctv
            FOREIGN KEY (cctv_id) REFERENCES cctv_info (cctv_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)


def connect(database: str | None = None):
    return pymysql.connect(
        host=settings.mariadb_host,
        user=settings.mariadb_user,
        password=settings.mariadb_password,
        database=database,
        port=settings.mariadb_port,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def ensure_schema() -> None:
    with connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SCHEMA_SQL[0].format(database=settings.mariadb_db_name))
        conn.commit()

    with connect(settings.mariadb_db_name) as conn:
        with conn.cursor() as cursor:
            for statement in SCHEMA_SQL[1:]:
                cursor.execute(statement)
            cursor.execute("SHOW COLUMNS FROM cctv_info LIKE 'frame_dir'")
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE cctv_info ADD COLUMN frame_dir VARCHAR(200) NULL AFTER rtsp_url")
        conn.commit()


def main() -> None:
    ensure_schema()
    print(f"DB ready: {settings.mariadb_host}:{settings.mariadb_port}/{settings.mariadb_db_name}")


if __name__ == "__main__":
    main()
