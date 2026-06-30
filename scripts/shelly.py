import argparse
import json
from datetime import datetime
from pathlib import Path
import sys
import threading
import time

from paho.mqtt import client as mqtt_client
from paho.mqtt.enums import CallbackAPIVersion

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config.settings import settings

BROKER = settings.mqtt_broker_host
PORT = settings.mqtt_broker_port
COLLECTOR_CLIENT_ID = "temperature_humidity_collector"

SHELLY_TOPIC_TEMP = "sensors/status/temperature:0"
SHELLY_TOPIC_HUMI = "sensors/status/humidity:0"
SHELLY_TOPIC_RPC = "sensors/events/rpc"

SENSOR_ID = "shelly_1"
SENSOR_TYPE = "temp_humidity"
SENSOR_NAME = "shelly_1"
TELEMETRY_TOPIC = f"sensors/{SENSOR_ID}/telemetry"
STATUS_TOPIC = f"sensors/{SENSOR_ID}/status"

cached_data = {
    "temp": None,
    "humid": None,
    "timestamp": None,
    "temp_seen_at": None,
    "humid_seen_at": None,
}
cache_lock = threading.Lock()
last_published_signature = None
last_published_at = 0.0
DEDUP_WINDOW_SEC = 30.0
PAIR_WINDOW_SEC = 30.0


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code.is_failure:
        print(f"[FAIL] MQTT broker connection failed: {reason_code}")
        return

    client.subscribe(SHELLY_TOPIC_TEMP)
    client.subscribe(SHELLY_TOPIC_HUMI)
    client.subscribe(SHELLY_TOPIC_RPC)
    publish_hardware_status(client, is_online=True)


def publish_hardware_status(client, is_online: bool):
    status_payload = {
        "sensor_id": SENSOR_ID,
        "sensor_type": SENSOR_TYPE,
        "sensor_name": SENSOR_NAME,
        "is_online": is_online,
    }
    client.publish(STATUS_TOPIC, json.dumps(status_payload), qos=1, retain=False)


def process_and_publish_telemetry(client, *, reason: str, require_fresh_pair: bool = False):
    global last_published_at, last_published_signature

    with cache_lock:
        temp = cached_data["temp"]
        humid = cached_data["humid"]
        timestamp = cached_data["timestamp"]
        temp_seen_at = cached_data["temp_seen_at"]
        humid_seen_at = cached_data["humid_seen_at"]

    if temp is None or humid is None:
        return False

    if require_fresh_pair:
        if temp_seen_at is None or humid_seen_at is None:
            return False
        if abs(temp_seen_at - humid_seen_at) > PAIR_WINDOW_SEC:
            return False

    now = time.monotonic()
    signature = (temp, humid)
    if signature == last_published_signature and now - last_published_at < DEDUP_WINDOW_SEC:
        return False

    telemetry_payload = {
        "sensor_id": SENSOR_ID,
        "sensor_type": SENSOR_TYPE,
        "sensor_name": SENSOR_NAME,
        "temp": temp,
        "humid": humid,
        "timestamp": timestamp or datetime.now().isoformat(timespec="seconds"),
    }
    client.publish(TELEMETRY_TOPIC, json.dumps(telemetry_payload), qos=1, retain=False)
    last_published_signature = signature
    last_published_at = now
    if reason == "interval":
        print(f"[telemetry:interval] topic={TELEMETRY_TOPIC} payload={telemetry_payload}")
    return True


def republish_cached_telemetry(client, interval_sec: float):
    while True:
        time.sleep(interval_sec)
        process_and_publish_telemetry(client, reason="interval")


def on_message(client, userdata, msg):
    topic = msg.topic
    raw_payload = msg.payload.decode("utf-8")

    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        print(f"[WARN] invalid JSON: {raw_payload}")
        return

    if topic == SHELLY_TOPIC_TEMP:
        temp_c = data.get("tC")
        if temp_c is not None:
            timestamp = datetime.now().isoformat(timespec="seconds")
            with cache_lock:
                cached_data["temp"] = temp_c
                cached_data["timestamp"] = timestamp
                cached_data["temp_seen_at"] = time.monotonic()
            process_and_publish_telemetry(client, reason="actual", require_fresh_pair=True)
        return

    if topic == SHELLY_TOPIC_HUMI:
        humidity = data.get("rh")
        if humidity is not None:
            timestamp = datetime.now().isoformat(timespec="seconds")
            with cache_lock:
                cached_data["humid"] = humidity
                cached_data["timestamp"] = timestamp
                cached_data["humid_seen_at"] = time.monotonic()
            process_and_publish_telemetry(client, reason="actual", require_fresh_pair=True)
        return

    if topic == SHELLY_TOPIC_RPC:
        params = data.get("params")
        if not isinstance(params, dict):
            return
        timestamp = datetime.fromtimestamp(params.get("ts")).isoformat(timespec="seconds") if params.get("ts") else datetime.now().isoformat(timespec="seconds")

        temperature = params.get("temperature:0")
        if isinstance(temperature, dict) and temperature.get("tC") is not None:
            with cache_lock:
                cached_data["temp"] = temperature["tC"]
                cached_data["timestamp"] = timestamp
                cached_data["temp_seen_at"] = time.monotonic()

        humidity = params.get("humidity:0")
        if isinstance(humidity, dict) and humidity.get("rh") is not None:
            with cache_lock:
                cached_data["humid"] = humidity["rh"]
                cached_data["timestamp"] = timestamp
                cached_data["humid_seen_at"] = time.monotonic()

        process_and_publish_telemetry(client, reason="actual", require_fresh_pair=True)


def run():
    parser = argparse.ArgumentParser(description="Collect temperature/humidity MQTT data and republish normalized telemetry.")
    parser.add_argument(
        "--republish-interval",
        type=float,
        default=300.0,
        help="Republish the latest real temperature/humidity every N seconds. Use 0 to disable.",
    )
    args = parser.parse_args()

    client = mqtt_client.Client(CallbackAPIVersion.VERSION2, COLLECTOR_CLIENT_ID)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, keepalive=60)
        if args.republish_interval > 0:
            threading.Thread(
                target=republish_cached_telemetry,
                args=(client, args.republish_interval),
                daemon=True,
            ).start()
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[STOP] Temperature/humidity collector is shutting down.")
        try:
            publish_hardware_status(client, is_online=False)
        except Exception:
            pass
    except Exception as exc:
        print(f"[ERROR] {exc}")


if __name__ == "__main__":
    run()
