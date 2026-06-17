import asyncio
import socket
from datetime import datetime
from typing import Any

from zeroconf import ServiceBrowser, ServiceStateChange
from zeroconf.asyncio import AsyncZeroconf


class MdnsSensorService:
    def __init__(self, service_type: str):
        self.service_type = service_type
        self.aiozc: AsyncZeroconf | None = None
        self.browser: ServiceBrowser | None = None
        self.discovered_sensors: dict[str, dict[str, Any]] = {}
        self._running = False
        self.loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        if self._running:
            return
        self.loop = asyncio.get_running_loop()
        self.aiozc = AsyncZeroconf()
        self.browser = ServiceBrowser(
            self.aiozc.zeroconf,
            self.service_type,
            handlers=[self._on_service_state_change],
        )
        self._running = True

    async def stop(self) -> None:
        self._running = False
        if self.aiozc:
            await self.aiozc.async_close()
            self.aiozc = None
        self.browser = None

    def get_discovered_sensors(self) -> list[dict[str, Any]]:
        return list(self.discovered_sensors.values())

    def get_discovered_sensor(self, sensor_id: str) -> dict[str, Any] | None:
        return self.discovered_sensors.get(sensor_id)

    def _on_service_state_change(self, zeroconf, service_type, name, state_change) -> None:
        if not self.loop:
            return
        if state_change in (ServiceStateChange.Added, ServiceStateChange.Updated):
            asyncio.run_coroutine_threadsafe(self._handle_upsert(name), self.loop)
        elif state_change is ServiceStateChange.Removed:
            asyncio.run_coroutine_threadsafe(self._handle_removed(name), self.loop)

    async def _handle_upsert(self, name: str) -> None:
        if not self.aiozc:
            return

        info = await self.aiozc.async_get_service_info(self.service_type, name, timeout=3000)
        if not info:
            return

        props = {
            (key.decode() if isinstance(key, bytes) else key): (
                value.decode() if isinstance(value, bytes) else value
            )
            for key, value in info.properties.items()
        }

        sensor_id = props.get("sensor_id")
        if not sensor_id:
            return

        ip_addr = None
        if info.addresses:
            try:
                ip_addr = socket.inet_ntoa(info.addresses[0])
            except Exception:
                ip_addr = None

        mqtt_base = props.get("mqtt_base", f"sensors/{sensor_id}")
        self.discovered_sensors[sensor_id] = {
            "sensor_id": sensor_id,
            "sensor_type": props.get("sensor_type", "unknown"),
            "sen_name": props.get("sen_name", sensor_id),
            "sen_locate": props.get("sen_locate", "default"),
            "model": props.get("model", ""),
            "mqtt_base": mqtt_base,
            "mqtt_topic": f"{mqtt_base}/telemetry",
            "status_topic": f"{mqtt_base}/status",
            "cmd_topic": f"{mqtt_base}/cmd",
            "alert_topic": f"{mqtt_base}/alert",
            "mdns_hostname": info.server.rstrip(".") if info.server else name.rstrip("."),
            "ip_addr": ip_addr,
            "is_online": True,
            "last_seen_at": datetime.now(),
        }

    async def _handle_removed(self, name: str) -> None:
        for sensor_id, sensor in self.discovered_sensors.items():
            if sensor.get("mdns_hostname") == name.rstrip("."):
                self.discovered_sensors[sensor_id]["is_online"] = False
                self.discovered_sensors[sensor_id]["last_seen_at"] = datetime.now()
                break

