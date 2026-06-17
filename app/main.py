from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.config.settings import settings
from app.db.session import MariaDb
from app.mdns.service import MdnsSensorService
from app.mqtt.service import MqttSensorService
from app.sensors.repository import SensorRepository
from app.sensors.router import router as sensors_router
from app.telemetry.repository import TelemetryRepository
from app.telemetry.router import router as telemetry_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = MariaDb(settings)
    sensor_repository = SensorRepository(db)
    telemetry_repository = TelemetryRepository(db)
    mdns_service = MdnsSensorService(settings.hardware_mdns_service_type)
    mqtt_service = MqttSensorService(
        sensor_repository=sensor_repository,
        telemetry_repository=telemetry_repository,
        broker_host=settings.mqtt_broker_host,
        broker_port=settings.mqtt_broker_port,
        username=settings.mqtt_username,
        password=settings.mqtt_password,
    )

    app.state.db = db
    app.state.sensor_repository = sensor_repository
    app.state.telemetry_repository = telemetry_repository
    app.state.mdns_service = mdns_service
    app.state.mqtt_service = mqtt_service

    await mdns_service.start()
    mqtt_service.start()
    try:
        yield
    finally:
        mqtt_service.stop()
        await mdns_service.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(sensors_router)
app.include_router(telemetry_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "hardware_server"}
