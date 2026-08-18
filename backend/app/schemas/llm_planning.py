from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SpecialistAgentName = Literal[
    "CloudMindCoordinatorAgent",
    "RepositoryAnalyzerAgent",
    "DockerAgent",
    "KubernetesAgent",
    "AzureDeploymentAgent",
    "CICDAgent",
    "PipelineCheckpointAgent",
    "AzureRuntimeDeploymentAgent",
    "ObservabilityAgent",
    "IncidentResponseAgent",
    "RemediationPlannerAgent",
    "DeploymentVerificationAgent",
    "FinalDemoOrchestratorAgent",
]

PlanActionKind = Literal[
    "read",
    "gitops_write",
    "cloud_write",
    "checkpoint",
    "report",
    "manual_check",
]

PlanRiskLevel = Literal["low", "medium", "high"]


class LLMPlannedAgentStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    specialist_agent: SpecialistAgentName
    tool_name: str | None
    objective: str = Field(min_length=1, max_length=1000)
    action_kind: PlanActionKind
    risk: PlanRiskLevel
    requires_approval: bool
    depends_on: list[str]
    success_criteria: list[str]


class LLMPlannerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=1000)
    intent: str = Field(min_length=1, max_length=100)
    response_type: Literal["plan", "clarification", "status"]
    summary: str = Field(min_length=1, max_length=2000)
    assumptions: list[str]
    missing_information: list[str]
    risks: list[str]
    steps: list[LLMPlannedAgentStep]
    requires_approval: bool
    approval_summary: str
    can_start: bool
    recommended_next_action: str = Field(min_length=1, max_length=1000)
