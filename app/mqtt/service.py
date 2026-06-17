import json
import logging
import threading
from datetime import datetime
from typing import Any

import paho.mqtt.client as mqtt

from app.mqtt import topics
from app.sensors.repository import SensorRepository
from app.telemetry.repository import TelemetryRepository

logger = logging.getLogger(__name__)

TEMPERATURE_TYPES = {"temp_humidity", "th", "temperature", "temperature_humidity"}
HEART_RATE_TYPES = {"heart_band", "heartbeat", "heart_rate", "hb", "watch"}


class MqttSensorService:
    def __init__(
        self,
        sensor_repository: SensorRepository,
        telemetry_repository: TelemetryRepository,
        broker_host: str,
        broker_port: int,
        username: str = "",
        password: str = "",
    ):
        self.sensor_repository = sensor_repository
        self.telemetry_repository = telemetry_repository
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password

        self.client = mqtt.Client()
        if username:
            self.client.username_pw_set(username, password or None)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self.client.connect(self.broker_host, self.broker_port, 60)
        self._thread = threading.Thread(target=self.client.loop_forever, daemon=True)
        self._thread.start()
        self._running = True
        logger.info("[Hardware MQTT] started broker=%s:%s", self.broker_host, self.broker_port)

    def stop(self) -> None:
        self._running = False
        try:
            self.client.disconnect()
        except Exception:
            logger.exception("[Hardware MQTT] disconnect failed")

    def publish_register(self, sensor_id: str, site_id: str, interval_ms: int) -> None:
        self.client.publish(
            topics.command_topic(sensor_id),
            json.dumps({"cmd": "register", "site_id": site_id, "interval_ms": interval_ms}),
        )

    def publish_unregister(self, sensor_id: str) -> None:
        self.client.publish(topics.command_topic(sensor_id), json.dumps({"cmd": "unregister"}))

    def publish_set_interval(self, sensor_id: str, interval_ms: int) -> None:
        self.client.publish(
            topics.command_topic(sensor_id),
            json.dumps({"cmd": "set_interval", "interval_ms": interval_ms}),
        )

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            logger.error("[Hardware MQTT] broker connect failed rc=%s", rc)
            return

        client.subscribe(topics.SENSOR_STATUS)
        client.subscribe(topics.SENSOR_TELEMETRY)
        client.subscribe(topics.SENSOR_DATA_SHORT)
        client.subscribe(topics.SENSOR_DATA)
        logger.info("[Hardware MQTT] subscribed sensor topics")

    def _on_message(self, client, userdata, msg) -> None:
        topic = str(msg.topic)
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            logger.warning("[Hardware MQTT] invalid JSON topic=%s", topic)
            return

        if not isinstance(payload, dict):
            return

        try:
            if topic.endswith("/status"):
                self._handle_status(payload)
            elif topic.endswith("/telemetry"):
                self._handle_telemetry(topic, payload)
            else:
                self._handle_sensor_data_topic(topic, payload)
        except Exception:
            logger.exception("[Hardware MQTT] message handling failed topic=%s", topic)

    def _handle_status(self, payload: dict[str, Any]) -> None:
        sensor_id = payload.get("sensor_id")
        if not sensor_id:
            return
        if self.sensor_repository.is_registered_sensor(sensor_id):
            self.sensor_repository.update_sensor_online(sensor_id, True, datetime.now())

    def _handle_telemetry(self, topic: str, payload: dict[str, Any]) -> None:
        sensor_id = payload.get("sensor_id") or self._extract_sensor_id_from_topic(topic)
        if not sensor_id:
            return

        sensor = self.sensor_repository.get_sensor_by_sensor_id(sensor_id)
        if not sensor:
            return

        data_type = self._classify_data_type(str(payload.get("sensor_type") or sensor.get("sensor_type") or ""), payload)
        self._store_payload(topic, sensor, data_type, payload)

    def _handle_sensor_data_topic(self, topic: str, payload: dict[str, Any]) -> None:
        sensor_id = payload.get("sensor_id") or self._extract_sensor_id_from_topic(topic)
        sensor = self.sensor_repository.get_sensor_by_sensor_id(sensor_id) if sensor_id else None
        if sensor is None:
            sensor = self.sensor_repository.get_sensor_by_mqtt_topic(topic)
        if sensor is None:
            return

        data_type = self._classify_data_type(str(sensor.get("sensor_type") or ""), payload)
        self._store_payload(topic, sensor, data_type, payload)

    def _store_payload(
        self,
        topic: str,
        sensor: dict[str, Any],
        data_type: str,
        payload: dict[str, Any],
    ) -> None:
        sen_id = int(sensor["sen_id"])
        sensor_id = str(sensor.get("sensor_id") or "")
        ts = payload.get("time") or payload.get("timestamp") or datetime.now()

        if data_type == "temperature":
            temp = payload.get("temp") if payload.get("temp") is not None else payload.get("temperature")
            humid = payload.get("humid") if payload.get("humid") is not None else payload.get("humidity")
            if temp is None and humid is None:
                return
            self.telemetry_repository.insert_temperature_humidity(sen_id, ts, temp, humid)
            self.sensor_repository.update_sensor_last_seen_by_id(sen_id)
            logger.info("[Hardware MQTT] temperature saved sensor_id=%s topic=%s", sensor_id, topic)
            return

        if data_type == "heart_rate":
            hr = payload.get("hr") if payload.get("hr") is not None else payload.get("heart_rate")
            if hr is None:
                return
            try:
                hr = float(hr)
            except Exception:
                return
            if hr <= 0:
                return
            self.telemetry_repository.insert_heart_rate(sen_id, ts, hr)
            self.sensor_repository.update_sensor_last_seen_by_id(sen_id)
            logger.info("[Hardware MQTT] heart-rate saved sensor_id=%s topic=%s", sensor_id, topic)

    @staticmethod
    def _extract_sensor_id_from_topic(topic: str) -> str | None:
        parts = topic.split("/")
        if len(parts) >= 2 and parts[1]:
            return parts[1]
        return None

    @staticmethod
    def _classify_data_type(sensor_type: str, payload: dict[str, Any]) -> str:
        normalized = sensor_type.lower().strip()
        if normalized in TEMPERATURE_TYPES:
            return "temperature"
        if normalized in HEART_RATE_TYPES:
            return "heart_rate"
        if any(key in payload for key in ("temp", "temperature", "humid", "humidity")):
            return "temperature"
        if any(key in payload for key in ("hr", "heart_rate")):
            return "heart_rate"
        return "unknown"
