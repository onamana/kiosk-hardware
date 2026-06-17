from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DiscoveredSensor(BaseModel):
    sensor_id: str
    sensor_type: str = "unknown"
    sen_name: str | None = None
    sen_locate: str | None = None
    model: str | None = None
    mqtt_base: str | None = None
    mqtt_topic: str | None = None
    status_topic: str | None = None
    cmd_topic: str | None = None
    alert_topic: str | None = None
    mdns_hostname: str | None = None
    ip_addr: str | None = None
    is_online: bool = True
    last_seen_at: datetime | None = None


class SensorRegisterRequest(BaseModel):
    jetson_id: int | None = None
    selected_sensors: list[DiscoveredSensor] = Field(default_factory=list)


class SensorUnregisterRequest(BaseModel):
    sensor_id: str


class SensorCommandRequest(BaseModel):
    interval_ms: int = 5000


class ApiResponse(BaseModel):
    status: str = "success"
    message: str | None = None
    data: Any = None

