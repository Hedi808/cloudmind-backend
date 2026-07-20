from fastapi import APIRouter

from app.agents.orchestrator import Orchestrator
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["Chat"])

orchestrator = Orchestrator()


@router.post("/", response_model=ChatResponse)
def chat(request: ChatRequest):
    result = orchestrator.handle_message(
        message=request.message,
        repo_url=request.repo_url,
        branch=request.branch,
        environment=request.environment,
    )

    return ChatResponse(
        user_message=request.message,
        detected_intent=result["detected_intent"],
        agent_used=result["agent_used"],
        response=result["response"],
        metadata=result["metadata"],
    )