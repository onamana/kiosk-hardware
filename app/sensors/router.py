from fastapi import APIRouter, Request

from app.common.json import to_jsonable
from app.sensors.schemas import ApiResponse

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.get("/discovered", response_model=ApiResponse)
def get_discovered_sensors(request: Request):
    rows = request.app.state.mdns_service.get_discovered_sensors()
    return ApiResponse(data=to_jsonable(rows))
