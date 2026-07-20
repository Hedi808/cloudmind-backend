from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.azure import router as azure_router
from app.api.chat import router as chat_router
from app.api.cicd import router as cicd_router
from app.api.demo_orchestrator import router as demo_orchestrator_router
from app.api.deployment import router as deployment_router
from app.api.deployment_verification import router as deployment_verification_router
from app.api.docker import router as docker_router
from app.api.git import router as git_router
from app.api.incident_response import router as incident_response_router
from app.api.kubernetes import router as kubernetes_router
from app.api.observability import router as observability_router
from app.api.pr_validation import router as pr_validation_router
from app.api.remediation import router as remediation_router
from app.api.remediation_pr import router as remediation_pr_router

app = FastAPI(
    title="CloudMind API",
    description=(
        "CloudMind is a multi-agent DevOps platform that analyzes repositories, "
        "generates Docker/Kubernetes/CI-CD/Azure deployment files, monitors cloud apps, "
        "diagnoses incidents, proposes remediation plans, opens safe GitOps pull requests, "
        "validates PRs before human merge, verifies deployments after merge, "
        "and generates final demo mission reports."
    ),
    version="0.14.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(git_router)
app.include_router(docker_router)
app.include_router(kubernetes_router)
app.include_router(deployment_router)
app.include_router(cicd_router)
app.include_router(azure_router)
app.include_router(observability_router)
app.include_router(incident_response_router)
app.include_router(remediation_router)
app.include_router(remediation_pr_router)
app.include_router(pr_validation_router)
app.include_router(deployment_verification_router)
app.include_router(demo_orchestrator_router)


@app.get("/")
def root():
    return {
        "message": "CloudMind API is running.",
        "version": "0.14.0",
        "phases": {
            "phase_1": "Conversation and orchestration",
            "phase_2": "Repository analysis",
            "phase_3": "Docker generation",
            "phase_4": "Kubernetes generation",
            "phase_5": "Deployment preparation",
            "phase_6": "CI/CD generation",
            "phase_7": "Azure deployment generation",
            "phase_8": "Observability",
            "phase_9": "Incident response",
            "phase_10": "Remediation planning",
            "phase_11": "Remediation pull requests",
            "phase_12": "Post-PR validation",
            "phase_13": "Deployment verification after merge",
            "phase_14": "Final demo orchestrator",
        },
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "cloudmind-api",
        "version": "0.14.0",
    }