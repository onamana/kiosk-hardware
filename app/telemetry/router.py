from fastapi import APIRouter, Query, Request

from app.common.json import to_jsonable
from app.sensors.schemas import ApiResponse

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/temperature/latest", response_model=ApiResponse)
def get_latest_temperature(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
):
    rows = request.app.state.telemetry_repository.get_latest_temperature_humidity(limit)
    return ApiResponse(data=to_jsonable(rows))


@router.get("/heartrate/latest", response_model=ApiResponse)
def get_latest_heartrate(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
):
    rows = request.app.state.telemetry_repository.get_latest_heart_rate(limit)
    return ApiResponse(data=to_jsonable(rows))

