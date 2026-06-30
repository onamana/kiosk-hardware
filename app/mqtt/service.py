import json
import logging
import threading
from datetime import datetime
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from app.mqtt import topics
from app.telemetry.repository import TelemetryRepository

logger = logging.getLogger(__name__)

TEMPERATURE_TYPES = {"temp_humidity", "th", "temperature", "temperature_humidity"}
HEART_RATE_TYPES = {"heart_band", "heartbeat", "heart_rate", "hb", "watch"}
TEMPERATURE_KEYS = ("temp", "temperature")
HUMIDITY_KEYS = ("humid", "humidity")
HEART_RATE_KEYS = ("hr", "heart_rate")


class MqttSensorService:
    def __init__(
        self,
        telemetry_repository: TelemetryRepository,
        broker_host: str,
        broker_port: int,
        username: str = "",
        password: str = "",
    ):
        self.telemetry_repository = telemetry_repository
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password

        self.client = mqtt.Client(CallbackAPIVersion.VERSION2)
        if username:
            self.client.username_pw_set(username, password or None)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self.client.connect_async(self.broker_host, self.broker_port, 60)
        self._thread = threading.Thread(
            target=self.client.loop_forever,
            kwargs={"retry_first_connection": True},
            daemon=True,
        )
        self._thread.start()
        self._running = True
        logger.info("[Hardware MQTT] connecting broker=%s:%s", self.broker_host, self.broker_port)

    def stop(self) -> None:
        self._running = False
        try:
            self.client.disconnect()
        except Exception:
            logger.exception("[Hardware MQTT] disconnect failed")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code.is_failure:
            logger.error("[Hardware MQTT] broker connect failed rc=%s", reason_code)
            return

        for topic in topics.SENSOR_TOPICS:
            client.subscribe(topic)
        logger.info("[Hardware MQTT] subscribed sensor topics")

    def _on_message(self, client, userdata, msg) -> None:
        topic = str(msg.topic)
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            logger.warning("[Hardware MQTT] invalid JSON topic=%s", topic)
            return

        if not isinstance(payload, dict):
            logger.warning("[Hardware MQTT] ignored non-object payload topic=%s payload=%s", topic, payload)
            return

        logger.debug("[Hardware MQTT] received topic=%s payload=%s", topic, payload)

        try:
            if topic.endswith("/status"):
                self._handle_status(payload)
            elif topic.endswith("/telemetry"):
                self._handle_telemetry(topic, payload)
            else:
                logger.debug("[Hardware MQTT] ignored unsubscribed topic=%s", topic)
        except Exception:
            logger.exception("[Hardware MQTT] message handling failed topic=%s", topic)

    def _handle_status(self, payload: dict[str, Any]) -> None:
        logger.debug("[Hardware MQTT] ignored status payload=%s", payload)

    def _handle_telemetry(self, topic: str, payload: dict[str, Any]) -> None:
        data_type = self._classify_data_type(str(payload.get("sensor_type") or ""), payload)
        logger.debug("[Hardware MQTT] classified topic=%s data_type=%s", topic, data_type)
        self._store_payload(topic, data_type, payload)

    def _store_payload(
        self,
        topic: str,
        data_type: str,
        payload: dict[str, Any],
    ) -> None:
        sensor_name = str(payload.get("sensor_name") or payload.get("sensor_id") or self._extract_sensor_id_from_topic(topic) or "")
        ts = payload.get("time") or payload.get("timestamp") or datetime.now()

        if data_type == "temperature":
            temp = self._first_present(payload, TEMPERATURE_KEYS)
            humid = self._first_present(payload, HUMIDITY_KEYS)
            if temp is None and humid is None:
                return
            sensor_id = self.telemetry_repository.insert_temperature_humidity(ts, temp, humid, sensor_name)
            logger.info(
                "[Hardware DB] inserted temperature_humidity_sensor sensor_id=%s sensor_name=%s temp=%s humid=%s measured_at=%s topic=%s",
                sensor_id,
                sensor_name or "-",
                temp,
                humid,
                ts,
                topic,
            )
            return

        if data_type == "heart_rate":
            hr = self._first_present(payload, HEART_RATE_KEYS)
            if hr is None:
                logger.warning("[Hardware MQTT] ignored heart-rate without hr topic=%s payload=%s", topic, payload)
                return
            try:
                hr = float(hr)
            except Exception:
                logger.warning("[Hardware MQTT] ignored invalid heart-rate topic=%s hr=%s", topic, hr)
                return
            if hr <= 0:
                logger.warning("[Hardware MQTT] ignored non-positive heart-rate topic=%s hr=%s", topic, hr)
                return
            logger.debug("[Hardware MQTT] heart-rate parsed source=%s hr=%s measured_at=%s", sensor_name or "-", hr, ts)
            sensor_id = self.telemetry_repository.insert_heart_rate(ts, hr)
            logger.info(
                "[Hardware DB] inserted heartbeat_sensor sensor_id=%s heart_rate=%s measured_at=%s topic=%s source=%s",
                sensor_id,
                hr,
                ts,
                topic,
                sensor_name or "-",
            )

    @staticmethod
    def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return value
        return None

    @staticmethod
    def _extract_sensor_id_from_topic(topic: str) -> str | None:
        parts = topic.split("/")
        if len(parts) >= 3 and parts[0] == "sensors":
            return parts[2]
        return None

    @staticmethod
    def _classify_data_type(sensor_type: str, payload: dict[str, Any]) -> str:
        normalized = sensor_type.lower().strip()
        if normalized in TEMPERATURE_TYPES:
            return "temperature"
        if normalized in HEART_RATE_TYPES:
            return "heart_rate"
        if any(key in payload for key in (*TEMPERATURE_KEYS, *HUMIDITY_KEYS)):
            return "temperature"
        if any(key in payload for key in HEART_RATE_KEYS):
            return "heart_rate"
        return "unknown"
