from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    status: str = "success"
    message: str | None = None
    data: Any = None

