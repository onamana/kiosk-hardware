from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "OnSafe Hardware Server"

    mariadb_host: str = "127.0.0.1"
    mariadb_user: str = "root"
    mariadb_password: str = "ekthf123"
    mariadb_db_name: str = "ON_SAFE"
    mariadb_port: int = 3306

    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""

    sensor_register_interval_ms: int = 5000
    hardware_mdns_service_type: str = "_onsafe-sensor._tcp.local."
    hardware_default_jetson_id: int | None = None


settings = Settings()

