from fastapi import APIRouter

from app.agents.conversation_brain_agent import ConversationBrainAgent
from app.schemas.chat import (
    ChatRequest,
    ChatSessionRequest,
    ClearChatMemoryRequest,
)

router = APIRouter(
    prefix="/api/chat",
    tags=["Phase 21A - LLM Multi-Agent Brain"],
)

conversation_brain_agent = ConversationBrainAgent()


@router.post("/")
def chat(request: ChatRequest):
    result = conversation_brain_agent.chat(
        message=request.message,
        session_id=request.session_id,
        repo_url=request.repo_url,
        resource_group=request.resource_group,
        app_name=request.app_name,
        pull_request_url=request.pull_request_url,
        approval_confirmed=request.approval_confirmed,
        context=request.context,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Conversation processed."),
        "result": result,
    }


@router.post("/session")
def get_session(request: ChatSessionRequest):
    result = conversation_brain_agent.get_session(
        session_id=request.session_id,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Conversation session loaded."),
        "result": result,
    }


@router.post("/clear")
def clear_memory(request: ClearChatMemoryRequest):
    result = conversation_brain_agent.clear_memory(
        session_id=request.session_id,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Conversation memory cleared."),
        "result": result,
    }


@router.get("/tools")
def list_tools():
    return {
        "status": "success",
        "message": "Available CloudMind tools listed.",
        "result": {
            "tools": conversation_brain_agent.tools.list_tools(),
        },
    }


@router.get("/llm-status")
def llm_status():
    return {
        "status": "success",
        "message": "CloudMind LLM configuration status loaded. A real request is required to verify credentials.",
        "result": conversation_brain_agent.llm_planner.health(),
    }
