from fastapi import APIRouter, Query, Request

from app.common.json import to_jsonable
from app.sensors.schemas import ApiResponse

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/temperature/latest", response_model=ApiResponse)
def get_latest_temperature(
    request: Request,
    sensor_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
):
    rows = request.app.state.telemetry_repository.get_latest_temperature_humidity(sensor_id, limit)
    return ApiResponse(data=to_jsonable(rows))


@router.get("/heartrate/latest", response_model=ApiResponse)
def get_latest_heartrate(
    request: Request,
    sensor_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
):
    rows = request.app.state.telemetry_repository.get_latest_heart_rate(sensor_id, limit)
    return ApiResponse(data=to_jsonable(rows))

