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

## Local Sensor Run

Create the database and tables before running the hardware server:

```bash
python scripts/init_db.py
```

If the database and tables already exist, this command leaves them as they are.

Start an MQTT broker on `localhost:1883` before running collectors. On
Windows, Mosquitto is a common choice. The hardware server will keep retrying if
the broker is not ready yet, but no sensor data can flow until the broker is
running.

```bash
uvicorn app.main:app --reload --port 8081
```

```bash
python scripts/shelly.py
```

The collector listens to temperature/humidity source topics and republishes normalized
telemetry to `sensors/shelly_1/telemetry`, which the hardware server stores
in `temperature_humidity_sensor`. After the first real reading arrives,
the collector republishes the latest temperature/humidity every 5 minutes by
default. Configure the sensor itself to wake/report every 5 minutes.

Disable repeated publishing:

```bash
python scripts/shelly.py --republish-interval 0
```

Check the inserted rows:

```sql
USE ON_SAFE;

SELECT * FROM temperature_humidity_sensor ORDER BY sensor_id DESC LIMIT 5
SELECT * FROM heartbeat_sensor ORDER BY sensor_id DESC LIMIT 5

SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE `process`;
TRUNCATE TABLE heartbeat_sensor;
TRUNCATE TABLE temperature_humidity_sensor;
SET FOREIGN_KEY_CHECKS = 1;
```

## MQTT Payloads

Galaxy Watch heart-rate messages:

```text
topic: sensors/{sensor_id}/telemetry
```

```json
{
  "sensor_id": "watch-001",
  "sensor_type": "heart_rate",
  "hr": 82,
  "timestamp": "2026-06-17T12:00:00"
}

```
Shelly H&T Gen3 temperature/humidity messages:

```text
topic: sensors/{sensor_id}/telemetry
```

```json
{
  "sensor_id": "shelly_1",
  "sensor_type": "temp_humidity",
  "sensor_name": "shelly_1",
  "temp": 24.4,
  "humid": 73.7,
  "timestamp": "2026-06-17T12:00:00"
}
```

SONOFF SNZB-02P temperature/humidity messages use the same shape with `"sensor_name": "sonoff_1"`.

Temperature/humidity samples are inserted into
`temperature_humidity_sensor(temperature, humidity, measured_at)`. `sensor_type`
can be `temp_humidity`, `th`, `temperature`, or `temperature_humidity`, but the
payload keys are enough for classification.
