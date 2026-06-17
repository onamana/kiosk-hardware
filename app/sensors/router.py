from fastapi import APIRouter, HTTPException, Request

from app.common.json import to_jsonable
from app.config.settings import settings
from app.sensors.schemas import (
    ApiResponse,
    SensorCommandRequest,
    SensorRegisterRequest,
    SensorUnregisterRequest,
)

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.get("", response_model=ApiResponse)
def get_registered_sensors(request: Request):
    rows = request.app.state.sensor_repository.get_registered_sensors()
    return ApiResponse(data=to_jsonable(rows))


@router.get("/discovered", response_model=ApiResponse)
def get_discovered_sensors(request: Request):
    rows = request.app.state.mdns_service.get_discovered_sensors()
    return ApiResponse(data=to_jsonable(rows))


@router.post("/register", response_model=ApiResponse)
def register_sensors(req: SensorRegisterRequest, request: Request):
    if not req.selected_sensors:
        raise HTTPException(status_code=400, detail="선택된 센서가 없습니다.")

    jetson_id = req.jetson_id or settings.hardware_default_jetson_id
    if jetson_id is None:
        jetson = request.app.state.sensor_repository.get_first_jetson()
        if not jetson:
            raise HTTPException(status_code=400, detail="등록된 Jetson 정보가 없습니다.")
        jetson_id = int(jetson["jetson_id"])

    sensors = [sensor.model_dump() for sensor in req.selected_sensors]
    try:
        count = request.app.state.sensor_repository.register_discovered_sensors(jetson_id, sensors)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    mqtt_service = request.app.state.mqtt_service
    for sensor in sensors:
        mqtt_service.publish_register(
            sensor_id=sensor["sensor_id"],
            site_id=f"jetson-{jetson_id:02d}",
            interval_ms=settings.sensor_register_interval_ms,
        )

    return ApiResponse(message=f"{count}개 센서 등록 완료")


@router.post("/unregister", response_model=ApiResponse)
def unregister_sensor(req: SensorUnregisterRequest, request: Request):
    request.app.state.mqtt_service.publish_unregister(req.sensor_id)
    ok = request.app.state.sensor_repository.unregister_sensor(req.sensor_id)
    if not ok:
        raise HTTPException(status_code=404, detail="해당 sensor_id를 가진 등록 센서가 없습니다.")
    return ApiResponse(message="센서 등록 해제 완료")


@router.post("/{sensor_id}/interval", response_model=ApiResponse)
def set_sensor_interval(sensor_id: str, req: SensorCommandRequest, request: Request):
    if not request.app.state.sensor_repository.is_registered_sensor(sensor_id):
        raise HTTPException(status_code=404, detail="등록되지 않은 센서입니다.")
    request.app.state.mqtt_service.publish_set_interval(sensor_id, req.interval_ms)
    return ApiResponse(message="센서 측정 주기 변경 명령 발행 완료")

