from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.azure import router as azure_router
from app.api.chat import router as chat_router
from app.api.cicd import router as cicd_router
from app.api.demo_orchestrator import router as demo_orchestrator_router
from app.api.deployment import router as deployment_router
from app.api.deployment_verification import router as deployment_verification_router
from app.api.docker import router as docker_router
from app.api.incident_response import router as incident_response_router
from app.api.kubernetes import router as kubernetes_router
from app.api.observability import router as observability_router
from app.api.pr_validation import router as pr_validation_router
from app.api.projects import router as projects_router
from app.api.remediation import router as remediation_router
from app.api.remediation_pr import router as remediation_pr_router


app = FastAPI(
    title="CloudMind API",
    description=(
        "CloudMind is a conversational multi-agent DevOps assistant that analyzes "
        "repositories, generates deployment assets, opens GitHub pull requests, "
        "deploys to Azure Container Apps, verifies runtime health, analyzes incidents, "
        "and stores project history in PostgreSQL."
    ),
    version="0.18.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "status": "success",
        "message": "CloudMind API is running.",
        "version": "0.18.0",
        "phase": "phase_18_project_history_api",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "cloudmind-backend",
        "version": "0.18.0",
    }


# chat_router already has prefix="/api/chat" inside app/api/chat.py
app.include_router(chat_router)

# Other routers are kept with prefix="/api"
app.include_router(projects_router, prefix="/api")
app.include_router(docker_router, prefix="/api")
app.include_router(kubernetes_router, prefix="/api")
app.include_router(deployment_router, prefix="/api")
app.include_router(cicd_router, prefix="/api")
app.include_router(azure_router, prefix="/api")
app.include_router(observability_router, prefix="/api")
app.include_router(incident_response_router, prefix="/api")
app.include_router(remediation_router, prefix="/api")
app.include_router(remediation_pr_router, prefix="/api")
app.include_router(pr_validation_router, prefix="/api")
app.include_router(deployment_verification_router, prefix="/api")
app.include_router(demo_orchestrator_router, prefix="/api")