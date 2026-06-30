import argparse
import json
import os
from datetime import datetime
from pathlib import Path
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from paho.mqtt import client as mqtt_client
from paho.mqtt.enums import CallbackAPIVersion

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(ROOT_DIR / ".env.sonoff")

from app.config.settings import settings

BROKER = settings.mqtt_broker_host
PORT = settings.mqtt_broker_port

CLIENT_ID = "sonoff_temperature_humidity_collector"
SENSOR_ID = os.getenv("SONOFF_SENSOR_ID", "sonoff_1")
SENSOR_TYPE = "temp_humidity"
SENSOR_NAME = os.getenv("SONOFF_SENSOR_NAME", SENSOR_ID)
TELEMETRY_TOPIC = f"sensors/{SENSOR_ID}/telemetry"
STATUS_TOPIC = f"sensors/{SENSOR_ID}/status"


def request_home_assistant_state(base_url: str, token: str, entity_id: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/states/{entity_id}"
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_float_state(state: dict[str, Any], entity_id: str) -> float:
    value = state.get("state")
    if value in (None, "unknown", "unavailable"):
        raise ValueError(f"{entity_id} state is not available: {value}")
    return float(value)


def publish_hardware_status(client: mqtt_client.Client, is_online: bool) -> None:
    status_payload = {
        "sensor_id": SENSOR_ID,
        "sensor_type": SENSOR_TYPE,
        "sensor_name": SENSOR_NAME,
        "is_online": is_online,
    }
    client.publish(STATUS_TOPIC, json.dumps(status_payload), qos=1, retain=False)


def publish_telemetry(client: mqtt_client.Client, temp: float, humid: float) -> None:
    telemetry_payload = {
        "sensor_id": SENSOR_ID,
        "sensor_type": SENSOR_TYPE,
        "sensor_name": SENSOR_NAME,
        "temp": temp,
        "humid": humid,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    client.publish(TELEMETRY_TOPIC, json.dumps(telemetry_payload), qos=1, retain=False)
    print(f"[telemetry] topic={TELEMETRY_TOPIC} payload={telemetry_payload}")


def run() -> None:
    parser = argparse.ArgumentParser(
        description="Read SONOFF SNZB-02P values from Home Assistant and publish Shelly-compatible MQTT telemetry."
    )
    parser.add_argument(
        "--ha-url",
        default=os.getenv("HOME_ASSISTANT_URL", "http://localhost:8123"),
        help="Home Assistant base URL. Default: HOME_ASSISTANT_URL or http://localhost:8123",
    )
    parser.add_argument(
        "--ha-token",
        default=os.getenv("HOME_ASSISTANT_TOKEN", ""),
        help="Home Assistant long-lived access token. Default: HOME_ASSISTANT_TOKEN",
    )
    parser.add_argument(
        "--temperature-entity",
        default=os.getenv("SONOFF_TEMPERATURE_ENTITY", ""),
        help="Home Assistant temperature entity_id, for example sensor.snzb_02p_temperature.",
    )
    parser.add_argument(
        "--humidity-entity",
        default=os.getenv("SONOFF_HUMIDITY_ENTITY", ""),
        help="Home Assistant humidity entity_id, for example sensor.snzb_02p_humidity.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("SONOFF_PUBLISH_INTERVAL", "5")),
        help="Polling and publishing interval in seconds. Default: 5",
    )
    args = parser.parse_args()

    if not args.ha_token:
        raise SystemExit("HOME_ASSISTANT_TOKEN or --ha-token is required.")
    if not args.temperature_entity:
        raise SystemExit("SONOFF_TEMPERATURE_ENTITY or --temperature-entity is required.")
    if not args.humidity_entity:
        raise SystemExit("SONOFF_HUMIDITY_ENTITY or --humidity-entity is required.")
    if args.interval <= 0:
        raise SystemExit("--interval must be greater than 0.")

    client = mqtt_client.Client(CallbackAPIVersion.VERSION2, CLIENT_ID)
    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password or None)

    try:
        client.connect(BROKER, PORT, keepalive=60)
        client.loop_start()
        publish_hardware_status(client, is_online=True)
        print(
            "[START] SONOFF collector "
            f"ha_url={args.ha_url} temp_entity={args.temperature_entity} "
            f"humidity_entity={args.humidity_entity} mqtt_topic={TELEMETRY_TOPIC} interval={args.interval}s"
        )

        while True:
            try:
                temp_state = request_home_assistant_state(args.ha_url, args.ha_token, args.temperature_entity)
                humid_state = request_home_assistant_state(args.ha_url, args.ha_token, args.humidity_entity)
                temp = parse_float_state(temp_state, args.temperature_entity)
                humid = parse_float_state(humid_state, args.humidity_entity)
                publish_telemetry(client, temp, humid)
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                print(f"[WARN] failed to read Home Assistant state: {exc}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[STOP] SONOFF collector is shutting down.")
    finally:
        try:
            publish_hardware_status(client, is_online=False)
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    run()
