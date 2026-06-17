SENSOR_STATUS = "sensors/+/status"
SENSOR_TELEMETRY = "sensors/+/telemetry"
SENSOR_DATA_SHORT = "sensor/+/+"
SENSOR_DATA = "sensors/+/data"


def command_topic(sensor_id: str) -> str:
    return f"sensors/{sensor_id}/cmd"


def alert_topic(sensor_id: str) -> str:
    return f"sensors/{sensor_id}/alert"

