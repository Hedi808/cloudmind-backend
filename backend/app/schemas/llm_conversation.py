from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMConversationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_type: Literal["greeting", "answer", "clarification"]
    intent_summary: str = Field(min_length=1, max_length=300)
    message: str = Field(min_length=1, max_length=4000)
    suggested_prompts: list[str]
