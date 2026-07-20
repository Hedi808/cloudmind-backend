from typing import Any

from pydantic import BaseModel


class HealthCheckRequest(BaseModel):
    base_url: str
    health_path: str = "/health"
    timeout_seconds: int = 10


class HealthCheckResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]


class AzureContainerAppStatusRequest(BaseModel):
    resource_group: str
    app_name: str
    health_path: str = "/health"
    timeout_seconds: int = 10


class AzureContainerAppStatusResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]


class AzureContainerAppLogsRequest(BaseModel):
    resource_group: str
    app_name: str
    tail: int = 50


class AzureContainerAppLogsResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]