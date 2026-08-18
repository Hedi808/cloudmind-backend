from fastapi import APIRouter, HTTPException

from app.agents.observability_agent import ObservabilityAgent
from app.schemas.observability import (
    AzureContainerAppLogsRequest,
    AzureContainerAppLogsResponse,
    AzureContainerAppStatusRequest,
    AzureContainerAppStatusResponse,
    HealthCheckRequest,
    HealthCheckResponse,
)

router = APIRouter(prefix="/observability", tags=["Observability"])

observability_agent = ObservabilityAgent()


@router.post("/health-check", response_model=HealthCheckResponse)
def check_health_endpoint(request: HealthCheckRequest):
    """
    Check a public HTTP health endpoint.
    """
    try:
        result = observability_agent.check_http_health(
            base_url=request.base_url,
            health_path=request.health_path,
            timeout_seconds=request.timeout_seconds,
        )

        return HealthCheckResponse(
            status=result["status"],
            message=result["message"],
            result=result,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {exc}",
        ) from exc


@router.post("/azure/status", response_model=AzureContainerAppStatusResponse)
def check_azure_container_app_status(request: AzureContainerAppStatusRequest):
    """
    Inspect Azure Container Apps status using Azure CLI.

    Requires:
    - Azure CLI installed
    - az login completed
    - access to the target Azure subscription
    """
    try:
        result = observability_agent.check_azure_container_app_status(
            resource_group=request.resource_group,
            app_name=request.app_name,
            app_url=request.app_url,
            health_path=request.health_path,
            timeout_seconds=request.timeout_seconds,
        )

        return AzureContainerAppStatusResponse(
            status=result["status"],
            message=result["message"],
            result=result,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Azure Container App status check failed: {exc}",
        ) from exc


@router.post("/azure/logs", response_model=AzureContainerAppLogsResponse)
def get_azure_container_app_logs(request: AzureContainerAppLogsRequest):
    """
    Retrieve Azure Container Apps logs using Azure CLI.

    Requires:
    - Azure CLI installed
    - az login completed
    - access to the target Azure subscription
    """
    try:
        result = observability_agent.get_azure_container_app_logs(
            resource_group=request.resource_group,
            app_name=request.app_name,
            tail=request.tail,
        )

        return AzureContainerAppLogsResponse(
            status=result["status"],
            message=result["message"],
            result=result,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Azure Container App logs retrieval failed: {exc}",
        ) from exc
