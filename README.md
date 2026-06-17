# Hardware Server

OnSafe hardware-facing FastAPI server.

Responsibilities:

- discover sensors with mDNS
- receive sensor data through MQTT
- register/update sensors in MariaDB
- store temperature, humidity, and heart-rate samples
- expose health, sensor, and telemetry APIs

## Setup

Install system packages for the local MQTT broker:

```bash
sudo apt install mosquitto mosquitto-clients
sudo systemctl start mosquitto
```

Create and use a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment

Create `.env` in the project root:

```env
MARIADB_HOST=127.0.0.1
MARIADB_USER=root
MARIADB_PASSWORD=ekthf123
MARIADB_DB_NAME=ON_SAFE
MARIADB_PORT=3306

MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883

SENSOR_REGISTER_INTERVAL_MS=5000
HARDWARE_MDNS_SERVICE_TYPE=_onsafe-sensor._tcp.local.
```

## Run

From the project root:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8081
```

Health check:

```bash
curl http://127.0.0.1:8081/health
```

## MQTT Payloads

Galaxy Watch heart-rate messages:

```text
topic: sensors/heartrate/{sensor_id}
```

```json
{
  "sensor_id": "watch-001",
  "hr": 82,
  "timestamp": "2026-06-17T12:00:00"
}
```

`sensor_id` must already exist in the `sensor` table. `timestamp` is optional.

Shelly H&T Gen3 temperature/humidity messages:

```text
topic: sensors/{sensor_id}/telemetry
```

```json
{
  "sensor_id": "shelly-ht-001",
  "sensor_type": "temp_humidity",
  "temp": 24.4,
  "humid": 73.7,
  "timestamp": "2026-06-17T12:00:00"
}
```

Register the Shelly sensor with `sensor_type` set to `temp_humidity`, `th`,
`temperature`, or `temperature_humidity`. The example Shelly script is in
`examples/shelly_ht_gen3_mqtt.js`.
