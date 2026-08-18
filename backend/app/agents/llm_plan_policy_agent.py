from __future__ import annotations

from app.schemas.llm_planning import LLMPlannedAgentStep, LLMPlannerOutput


class LLMPlanPolicyAgent:
    """Deterministically validates LLM plans before they reach the executor."""

    TOOL_POLICY = {
        "analyze_repository": ("RepositoryAnalyzerAgent", "read", "low", False),
        "generate_docker": ("DockerAgent", "gitops_write", "medium", True),
        "generate_kubernetes": ("KubernetesAgent", "gitops_write", "medium", True),
        "generate_azure": ("AzureDeploymentAgent", "gitops_write", "medium", True),
        "generate_cicd": ("CICDAgent", "gitops_write", "medium", True),
        "deploy_azure_runtime": (
            "AzureRuntimeDeploymentAgent",
            "cloud_write",
            "high",
            True,
        ),
        "check_azure_status": ("ObservabilityAgent", "read", "low", False),
        "get_azure_logs": ("ObservabilityAgent", "read", "low", False),
        "analyze_incident": ("IncidentResponseAgent", "read", "low", False),
        "plan_remediation": ("RemediationPlannerAgent", "read", "low", False),
        "verify_azure_deployment": (
            "DeploymentVerificationAgent",
            "read",
            "low",
            False,
        ),
        "final_demo_report": ("FinalDemoOrchestratorAgent", "report", "low", False),
    }

    def enforce(self, plan: LLMPlannerOutput) -> tuple[LLMPlannerOutput, list[str]]:
        notes: list[str] = []
        normalized_steps: list[LLMPlannedAgentStep] = []
        seen_ids: set[str] = set()

        for index, step in enumerate(plan.steps, start=1):
            step_id = self._unique_step_id(step.id, index, seen_ids)
            seen_ids.add(step_id)
            dependencies = [
                dependency
                for dependency in step.depends_on
                if dependency in seen_ids and dependency != step_id
            ]

            if step.tool_name is None:
                update = {
                    "id": step_id,
                    "depends_on": dependencies,
                }

                if step.action_kind in {"gitops_write", "cloud_write"}:
                    notes.append(
                        f"Converted tool-less write step '{step_id}' to an approval-gated manual check."
                    )
                    update.update(
                        {
                            "specialist_agent": "CloudMindCoordinatorAgent",
                            "action_kind": "manual_check",
                            "risk": "high",
                            "requires_approval": True,
                        }
                    )

                normalized_steps.append(
                    step.model_copy(update=update)
                )
                continue

            policy = self.TOOL_POLICY.get(step.tool_name)

            if policy is None:
                notes.append(
                    f"Removed unsupported tool '{step.tool_name}' from step '{step_id}'."
                )
                normalized_steps.append(
                    step.model_copy(
                        update={
                            "id": step_id,
                            "specialist_agent": "CloudMindCoordinatorAgent",
                            "tool_name": None,
                            "action_kind": "manual_check",
                            "risk": "high",
                            "requires_approval": True,
                            "depends_on": dependencies,
                        }
                    )
                )
                continue

            agent_name, action_kind, risk, approval_required = policy

            if step.requires_approval is False and approval_required:
                notes.append(
                    f"Added mandatory approval to write step '{step_id}'."
                )

            normalized_steps.append(
                step.model_copy(
                    update={
                        "id": step_id,
                        "specialist_agent": agent_name,
                        "action_kind": action_kind,
                        "risk": risk,
                        "requires_approval": approval_required,
                        "depends_on": dependencies,
                    }
                )
            )

        requires_approval = any(step.requires_approval for step in normalized_steps)
        missing_information = [item for item in plan.missing_information if item.strip()]
        can_start = plan.can_start and not missing_information and bool(normalized_steps)
        approval_summary = (
            "Human approval is required before GitHub or Azure write actions."
            if requires_approval
            else "The proposed plan contains read-only or reporting actions only."
        )

        return (
            plan.model_copy(
                update={
                    "steps": normalized_steps,
                    "requires_approval": requires_approval,
                    "approval_summary": approval_summary,
                    "can_start": can_start,
                    "missing_information": missing_information,
                }
            ),
            notes,
        )

    def _unique_step_id(self, value: str, index: int, seen_ids: set[str]) -> str:
        normalized = "".join(
            character if character.isalnum() or character in {"_", "-"} else "_"
            for character in value.strip().lower()
        ).strip("_-")
        normalized = normalized or f"step_{index}"

        if normalized not in seen_ids:
            return normalized

        return f"{normalized}_{index}"
