import json
import re
from typing import Any
from urllib.parse import urlparse

from app.agents.conversation_memory_agent import ConversationMemoryAgent
from app.agents.project_memory_agent import ProjectMemoryAgent
from app.agents.tool_registry_agent import ToolRegistryAgent


class ConversationBrainAgent:
    """
    Conversational brain for CloudMind.

    Phase 20H:
    - Uses PostgreSQL ProjectMemoryAgent for persistent project memory.
    - Stores projects, conversations, messages, action runs, PRs, generated files, and deployments.
    - Hydrates tool arguments from project history.
    - Passes detected health_path automatically to runtime tools.
    - Does not force /health as a fallback when the repository exposes a different health endpoint.
    """

    SUCCESS_STATUSES = [
        "success",
        "completed",
        "analyzed",
        "prepared",
        "generated",
        "published",
        "plan_ready",
        "healthy",
        "verification_passed",
        "demo_ready",
        "deployed",
        "deployed_with_warnings",
        "no_changes",
        "no_incident",
    ]

    REPO_WRITE_INTENTS = [
        "generate_docker",
        "generate_kubernetes",
        "prepare_deployment",
        "generate_cicd",
        "generate_azure",
    ]

    CLOUD_WRITE_INTENTS = [
        "deploy_azure_runtime",
    ]

    RUNTIME_INTENTS = [
        "check_azure_status",
        "get_azure_logs",
        "analyze_incident",
        "plan_remediation",
        "verify_azure_deployment",
    ]

    def __init__(self) -> None:
        self.memory = ConversationMemoryAgent()
        self.project_memory = ProjectMemoryAgent()
        self.tools = ToolRegistryAgent()

    def chat(
        self,
        message: str,
        session_id: str | None = None,
        repo_url: str | None = None,
        resource_group: str | None = None,
        app_name: str | None = None,
        pull_request_url: str | None = None,
        approval_confirmed: bool = False,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.memory.get_or_create_session(session_id)
        session_id = session["session_id"]

        message = message.strip()
        context = context or {}

        extracted = self._extract_entities(message)

        repo_url = repo_url or extracted.get("repo_url") or context.get("repo_url")
        resource_group = resource_group or extracted.get("resource_group") or context.get("resource_group")
        app_name = app_name or extracted.get("app_name") or context.get("app_name")
        pull_request_url = pull_request_url or extracted.get("pull_request_url") or context.get("pull_request_url")

        health_path = (
            extracted.get("health_path")
            or context.get("health_path")
            or context.get("detected_health_path")
        )

        project = None
        project_id = None
        project_context = None

        if repo_url:
            project = self.project_memory.create_or_get_project(repo_url=repo_url)
            project_id = project["id"]
            project_context = self.project_memory.get_project_context(project_id=project_id)

            hydrated = self._hydrate_from_project_context(project_context)

            resource_group = resource_group or hydrated.get("resource_group")
            app_name = app_name or hydrated.get("app_name")
            pull_request_url = pull_request_url or hydrated.get("pull_request_url")
            health_path = health_path or hydrated.get("health_path")

        self.project_memory.create_or_get_session(
            session_id=session_id,
            project_id=project_id,
            title=f"CloudMind - {project.get('name')}" if project else "CloudMind session",
        )

        if extracted.get("latest_pr_number"):
            self.memory.update_state(
                session_id=session_id,
                updates={"latest_pr_number": extracted.get("latest_pr_number")},
            )

        project_state_updates = self._state_updates_from_project_context(project_context)

        explicit_state_updates = {
            "project_id": project_id,
            "project_name": project.get("name") if project else None,
            "repo_url": repo_url,
            "resource_group": resource_group,
            "app_name": app_name,
            "latest_pr_url": pull_request_url,
            "health_path": health_path,
        }

        self.memory.update_state(
            session_id=session_id,
            updates=self._remove_none_values(
                {
                    **project_state_updates,
                    **explicit_state_updates,
                }
            ),
        )

        state = self.memory.get_state(session_id)

        self.memory.add_message(
            session_id=session_id,
            role="user",
            content=message,
            metadata={
                "repo_url": repo_url,
                "resource_group": resource_group,
                "app_name": app_name,
                "pull_request_url": pull_request_url,
                "project_id": project_id,
                "health_path": health_path,
            },
        )

        self.project_memory.save_message(
            session_id=session_id,
            role="user",
            content=message,
            metadata={
                "repo_url": repo_url,
                "resource_group": resource_group,
                "app_name": app_name,
                "pull_request_url": pull_request_url,
                "project_id": project_id,
                "health_path": health_path,
            },
        )

        intent = self._detect_intent(message)

        action_plan = self._build_action_plan(
            intent=intent,
            state=state,
            approval_confirmed=approval_confirmed,
        )

        tool_result = None
        action_run_id = None

        if action_plan["can_execute"]:
            started_action = self.project_memory.start_action_run(
                project_id=project_id,
                session_id=session_id,
                action_type=intent,
                tool_name=action_plan.get("tool_name"),
                approval_required=action_plan.get("requires_approval", False),
                approval_confirmed=approval_confirmed,
                input_json=self._json_safe(action_plan.get("arguments", {})),
            )
            action_run_id = started_action["id"]

            tool_result = self.tools.run_tool(
                tool_name=action_plan["tool_name"],
                arguments=action_plan["arguments"],
            )

            self.project_memory.finish_action_run(
                action_run_id=action_run_id,
                status=str(tool_result.get("status", "unknown")) if isinstance(tool_result, dict) else "unknown",
                output_json=self._json_safe(tool_result),
                error=tool_result.get("error") if isinstance(tool_result, dict) else None,
            )

            self._store_useful_result(
                session_id=session_id,
                intent=intent,
                tool_name=action_plan["tool_name"],
                tool_result=tool_result,
                project_id=project_id,
                action_run_id=action_run_id,
                action_arguments=action_plan.get("arguments", {}),
            )

        assistant_message = self._build_assistant_message(
            intent=intent,
            action_plan=action_plan,
            tool_result=tool_result,
            state=self.memory.get_state(session_id),
        )

        self.memory.add_message(
            session_id=session_id,
            role="assistant",
            content=assistant_message,
            metadata={
                "intent": intent,
                "action_plan": action_plan,
                "tool_status": tool_result.get("status") if isinstance(tool_result, dict) else None,
                "project_id": project_id,
                "action_run_id": action_run_id,
            },
        )

        self.project_memory.save_message(
            session_id=session_id,
            role="assistant",
            content=assistant_message,
            intent=intent,
            tool_name=action_plan.get("tool_name"),
            metadata={
                "tool_status": tool_result.get("status") if isinstance(tool_result, dict) else None,
                "project_id": project_id,
                "action_run_id": action_run_id,
            },
        )

        refreshed_project_context = (
            self.project_memory.get_project_context(project_id=project_id)
            if project_id
            else None
        )

        return {
            "status": "success",
            "message": "Conversation processed.",
            "phase": "phase_20h_health_path_aware_chat_brain",
            "session_id": session_id,
            "project_id": project_id,
            "intent": intent,
            "assistant_message": assistant_message,
            "action": {
                "executed": action_plan["can_execute"],
                "tool_name": action_plan.get("tool_name"),
                "requires_approval": action_plan.get("requires_approval", False),
                "missing_fields": action_plan.get("missing_fields", []),
                "reason": action_plan.get("reason"),
                "action_run_id": action_run_id,
            },
            "tool_result": self._trim_tool_result(tool_result),
            "conversation_state": self.memory.get_state(session_id),
            "project_context": refreshed_project_context,
            "suggested_actions": self._suggest_next_actions(
                intent=intent,
                tool_result=tool_result,
                state=self.memory.get_state(session_id),
            ),
            "safety": {
                "human_approval_required_for_write_actions": True,
                "approval_confirmed": approval_confirmed,
                "direct_main_push": False,
                "auto_merge": False,
                "auto_deploy_without_approval": False,
                "health_path_auto_detection": True,
            },
        }

    def clear_memory(self, session_id: str) -> dict[str, Any]:
        session = self.memory.clear_session(session_id)

        return {
            "status": "success",
            "message": "Short-term conversation memory cleared. PostgreSQL project history is preserved.",
            "session_id": session["session_id"],
            "state": session["state"],
        }

    def get_session(self, session_id: str) -> dict[str, Any]:
        session = self.memory.get_or_create_session(session_id)

        return {
            "status": "success",
            "message": "Conversation session loaded.",
            "session_id": session_id,
            "state": session["state"],
            "recent_messages": self.memory.get_recent_messages(session_id=session_id, limit=20),
        }

    def _detect_intent(self, message: str) -> str:
        text = message.lower()

        if any(word in text for word in ["help", "what can you do", "commands", "features"]):
            return "help"

        if any(word in text for word in ["final report", "mission report", "demo report", "professor demo"]):
            return "final_demo_report"

        if (
            "azure" in text
            and any(
                phrase in text
                for phrase in [
                    "deploy this app",
                    "deploy app",
                    "deploy to azure",
                    "run on azure",
                ]
            )
        ) or any(
            phrase in text
            for phrase in [
                "deploy this app to azure",
                "deploy this repo to azure",
                "deploy current app",
                "launch this app on azure",
            ]
        ):
            return "deploy_azure_runtime"

        if any(word in text for word in ["verify deployment", "deployment verification", "verify azure", "is deployment ok"]):
            return "verify_azure_deployment"

        if any(word in text for word in ["incident", "diagnose", "why is it failing", "failure", "error in azure", "analyze problem"]):
            return "analyze_incident"

        if any(word in text for word in ["remediation", "fix plan", "how to fix", "plan fix", "repair plan"]):
            return "plan_remediation"

        if any(word in text for word in ["logs", "show logs", "azure logs", "container logs"]):
            return "get_azure_logs"

        if any(word in text for word in ["health", "status", "is it running", "check azure", "check app"]):
            return "check_azure_status"

        if any(
            phrase in text
            for phrase in [
                "prepare this repo",
                "prepare this repository",
                "prepare deployment",
                "prepare it",
                "make it deployable",
                "full deployment",
            ]
        ):
            return "prepare_deployment"

        if any(word in text for word in ["azure", "container app", "deploy script"]) and any(
            word in text for word in ["generate", "create", "prepare"]
        ):
            return "generate_azure"

        if any(word in text for word in ["ci/cd", "cicd", "github actions", "workflow", "pipeline"]):
            return "generate_cicd"

        if any(word in text for word in ["kubernetes", "k8s", "manifest", "deployment yaml"]):
            return "generate_kubernetes"

        if any(word in text for word in ["docker", "dockerfile", "compose"]):
            return "generate_docker"

        if any(word in text for word in ["deploy this repo", "deploy repo", "deploy it"]):
            return "prepare_deployment"

        if any(word in text for word in ["analyze", "analyse", "scan", "understand repo", "what framework"]):
            return "analyze_repository"

        if self._extract_entities(message).get("repo_url"):
            return "analyze_repository"

        return "general_chat"

    def _build_action_plan(
        self,
        intent: str,
        state: dict[str, Any],
        approval_confirmed: bool,
    ) -> dict[str, Any]:
        if intent == "help":
            return self._no_tool_plan("Help request.")

        if intent == "general_chat":
            return self._no_tool_plan("No executable DevOps intent detected.")

        if intent == "analyze_repository":
            arguments = {
                "repo_url": state.get("repo_url"),
            }

            missing = self._missing(arguments, ["repo_url"])

            return {
                "can_execute": len(missing) == 0,
                "tool_name": "analyze_repository",
                "requires_approval": False,
                "missing_fields": missing,
                "reason": "Ready to execute." if not missing else "Missing required fields.",
                "arguments": arguments,
            }

        if intent in self.REPO_WRITE_INTENTS:
            arguments = {
                "repo_url": state.get("repo_url"),
                "overwrite": True,
                "publish_to_github": True,
            }

            missing = self._missing(arguments, ["repo_url"])

            if missing:
                return {
                    "can_execute": False,
                    "tool_name": intent,
                    "requires_approval": False,
                    "missing_fields": missing,
                    "reason": "Missing required fields.",
                    "arguments": arguments,
                }

            if not approval_confirmed:
                return {
                    "can_execute": False,
                    "tool_name": intent,
                    "requires_approval": True,
                    "missing_fields": [],
                    "reason": "Repo write actions create a GitHub branch and pull request. Approval is required.",
                    "arguments": arguments,
                }

            return {
                "can_execute": True,
                "tool_name": intent,
                "requires_approval": True,
                "missing_fields": [],
                "reason": "Ready to publish generated files through a GitHub pull request.",
                "arguments": arguments,
            }

        if intent == "deploy_azure_runtime":
            arguments = {
                "repo_url": state.get("repo_url"),
                "image": state.get("ghcr_image"),
                "resource_group": state.get("resource_group"),
                "app_name": state.get("app_name"),
                "health_path": state.get("health_path"),
                "azure_location": "francecentral",
                "min_replicas": 0,
                "max_replicas": 1,
                "cpu": 0.25,
                "memory": "0.5Gi",
                "timeout_seconds": 900,
            }

            missing = self._missing(arguments, ["repo_url"])

            if missing:
                return {
                    "can_execute": False,
                    "tool_name": "deploy_azure_runtime",
                    "requires_approval": False,
                    "missing_fields": missing,
                    "reason": "Missing repository information.",
                    "arguments": arguments,
                }

            if not approval_confirmed:
                return {
                    "can_execute": False,
                    "tool_name": "deploy_azure_runtime",
                    "requires_approval": True,
                    "missing_fields": [],
                    "reason": "Azure runtime deployment creates cloud resources and may consume credits. Approval is required.",
                    "arguments": arguments,
                }

            return {
                "can_execute": True,
                "tool_name": "deploy_azure_runtime",
                "requires_approval": True,
                "missing_fields": [],
                "reason": "Ready to deploy the app to Azure Container Apps.",
                "arguments": arguments,
            }

        if intent in self.RUNTIME_INTENTS:
            arguments = {
                "repo_url": state.get("repo_url"),
                "resource_group": state.get("resource_group"),
                "app_name": state.get("app_name"),
                "health_path": state.get("health_path"),
                "timeout_seconds": 60,
                "log_tail": 100,
                "tail": 100,
                "environment": "development",
                "require_azure_healthy": True,
            }

            missing = self._missing(arguments, ["resource_group", "app_name"])

            return {
                "can_execute": len(missing) == 0,
                "tool_name": intent,
                "requires_approval": False,
                "missing_fields": missing,
                "reason": "Ready to execute." if not missing else "Missing Azure resource information.",
                "arguments": arguments,
            }

        if intent == "final_demo_report":
            arguments = {
                "repo_url": state.get("repo_url"),
                "resource_group": state.get("resource_group"),
                "app_name": state.get("app_name"),
                "pull_request_url": state.get("latest_pr_url"),
                "pull_request_number": state.get("latest_pr_number"),
                "health_path": state.get("health_path"),
                "timeout_seconds": 60,
                "log_tail": 100,
                "environment": "development",
                "run_pr_validation": False,
                "run_azure_verification": True,
                "run_remediation_plan": True,
                "require_pr_merged_for_deployment": False,
                "require_ci_success_for_deployment": False,
                "require_azure_healthy": True,
                "include_raw_outputs": False,
            }

            missing = self._missing(arguments, ["repo_url", "resource_group", "app_name"])

            return {
                "can_execute": len(missing) == 0,
                "tool_name": "final_demo_report",
                "requires_approval": False,
                "missing_fields": missing,
                "reason": "Ready to execute." if not missing else "Missing demo report context.",
                "arguments": arguments,
            }

        return self._no_tool_plan("Unsupported intent.")

    def _build_assistant_message(
        self,
        intent: str,
        action_plan: dict[str, Any],
        tool_result: dict[str, Any] | None,
        state: dict[str, Any],
    ) -> str:
        if intent == "help":
            return (
                "I can analyze repositories, generate Docker/Kubernetes/CI/CD/Azure files through GitHub pull requests, "
                "deploy apps to Azure Container Apps with approval, check health, inspect logs, diagnose incidents, "
                "plan remediation, verify deployments, generate final demo reports, and remember project history in PostgreSQL."
            )

        if action_plan.get("requires_approval") and not action_plan.get("can_execute"):
            if action_plan.get("tool_name") == "deploy_azure_runtime":
                return (
                    "This action will deploy the app to Azure Container Apps and may consume Azure credits.\n\n"
                    "For safety, tick the approval checkbox on the left, then send the same command again."
                )

            return (
                "This action will create a GitHub branch, commit generated files, push the branch, "
                "and open a pull request.\n\n"
                "For safety, tick the approval checkbox on the left, then send the same command again."
            )

        missing_fields = action_plan.get("missing_fields", [])

        if missing_fields:
            return self._missing_fields_message(missing_fields=missing_fields)

        if tool_result is None:
            return (
                "I understood your message, but I did not need to run a DevOps tool yet. "
                "Give me a GitHub repository URL or ask for a specific operation."
            )

        if self._tool_failed(tool_result):
            return self._tool_failed_message(
                tool_name=action_plan.get("tool_name"),
                tool_result=tool_result,
            )

        tool_name = action_plan["tool_name"]

        if tool_name == "analyze_repository":
            return self._repository_analysis_message(tool_result)

        if tool_name == "prepare_deployment":
            return self._prepare_deployment_message(tool_result)

        if tool_name == "generate_docker":
            return self._generic_generation_message("Docker assets", tool_result)

        if tool_name == "generate_kubernetes":
            return self._generic_generation_message("Kubernetes manifests", tool_result)

        if tool_name == "generate_cicd":
            return self._generic_generation_message("CI/CD workflow", tool_result)

        if tool_name == "generate_azure":
            return self._generic_generation_message("Azure deployment assets", tool_result)

        if tool_name == "deploy_azure_runtime":
            return self._azure_runtime_deployment_message(tool_result)

        if tool_name == "check_azure_status":
            return self._azure_status_message(tool_result)

        if tool_name == "get_azure_logs":
            return self._azure_logs_message(tool_result)

        if tool_name == "analyze_incident":
            return self._incident_message(tool_result)

        if tool_name == "plan_remediation":
            return self._remediation_message(tool_result)

        if tool_name == "verify_azure_deployment":
            return self._deployment_verification_message(tool_result)

        if tool_name == "final_demo_report":
            return self._final_report_message(tool_result)

        return f"I completed the operation. Status: {tool_result.get('status', 'unknown')}."

    def _repository_analysis_message(self, tool_result: dict[str, Any]) -> str:
        repo_name = tool_result.get("repo_name", "unknown repository")
        project_type = tool_result.get("project_type", "unknown")
        detected_languages = tool_result.get("detected_languages", [])
        detected_frameworks = tool_result.get("detected_frameworks", [])
        components = tool_result.get("components", [])
        missing_devops_files = tool_result.get("missing_devops_files", [])
        recommendations = tool_result.get("recommendations", [])

        language = ", ".join(detected_languages) if detected_languages else "unknown"
        framework = ", ".join(detected_frameworks) if detected_frameworks else "unknown"

        start_command = "not detected"
        port = "not detected"
        health_path = tool_result.get("health_path") or "not detected"

        primary_component = tool_result.get("primary_component")

        if isinstance(primary_component, dict):
            start_command = primary_component.get("start_command") or start_command
            port = primary_component.get("port") or port
            health_path = primary_component.get("health_path") or health_path
        elif components:
            first_component = components[0]
            start_command = first_component.get("start_command") or start_command
            port = first_component.get("port") or port
            health_path = first_component.get("health_path") or health_path

        missing_text = ", ".join(missing_devops_files) if missing_devops_files else "None"

        recommendation_text = ""
        if recommendations:
            recommendation_text = "\n\nRecommendation:\n" + "\n".join(f"- {item}" for item in recommendations)

        return (
            "I analyzed the repository successfully and saved the analysis in PostgreSQL project memory.\n\n"
            f"Repository: {repo_name}\n"
            f"Project type: {project_type}\n"
            f"Detected language: {language}\n"
            f"Detected framework: {framework}\n"
            f"Port: {port}\n"
            f"Start command: {start_command}\n"
            f"Health path: {health_path}\n"
            f"Missing DevOps files: {missing_text}"
            f"{recommendation_text}\n\n"
            "Next, I can generate DevOps files through GitHub pull requests or deploy the app to Azure after the image exists."
        )

    def _prepare_deployment_message(self, tool_result: dict[str, Any]) -> str:
        return (
            "Deployment preparation completed, published successfully, and saved in project history.\n\n"
            f"{tool_result.get('message', 'Deployment assets were prepared.')}"
            f"{self._build_files_text(tool_result)}"
            f"{self._build_pr_text(tool_result)}\n\n"
            "Review and merge the pull request before relying on these files in the repository."
        )

    def _generic_generation_message(self, label: str, tool_result: dict[str, Any]) -> str:
        status = str(tool_result.get("status", "")).lower()

        if status == "no_changes":
            return (
                f"No new {label} changes were published.\n\n"
                f"{tool_result.get('message', 'No generated files were detected.')}\n\n"
                "This action was still saved in PostgreSQL project history."
            )

        verb = "generated and published" if status == "published" or self._extract_pull_request(tool_result) else "generated"

        return (
            f"{label} {verb} successfully.\n\n"
            f"{tool_result.get('message', '')}"
            f"{self._build_files_text(tool_result)}"
            f"{self._build_pr_text(tool_result)}\n\n"
            "I saved this action, generated files, and pull request in PostgreSQL project history."
        )

    def _azure_runtime_deployment_message(self, tool_result: dict[str, Any]) -> str:
        status = tool_result.get("status")
        health = tool_result.get("health", {})
        health_text = "healthy" if health.get("healthy") else "not healthy yet"

        environment_reused = tool_result.get("environment_reused")
        environment_decision = tool_result.get("environment_decision")

        if environment_reused is True:
            environment_text = "Reused existing Azure Container Apps environment"
        elif environment_reused is False:
            environment_text = "Created a new Azure Container Apps environment"
        else:
            environment_text = "Environment decision not available"

        return (
            "Azure runtime deployment completed and saved in PostgreSQL project memory.\n\n"
            f"Status: {status}\n"
            f"Resource group: {tool_result.get('resource_group')}\n"
            f"Container App: {tool_result.get('app_name')}\n"
            f"Environment: {tool_result.get('environment_name')}\n"
            f"Environment strategy: {environment_text}\n"
            f"Environment decision: {environment_decision}\n"
            f"Image: {tool_result.get('image')}\n"
            f"URL: {tool_result.get('app_url')}\n"
            f"Health path: {tool_result.get('health_path')}\n"
            f"Health: {health_text}\n\n"
            f"{tool_result.get('message')}\n\n"
            "Next, I can check Azure status, analyze incidents, or generate the final demo report."
        )

    def _azure_status_message(self, tool_result: dict[str, Any]) -> str:
        healthy = self._status_result_is_healthy(tool_result)
        app_url = tool_result.get("app_url") or tool_result.get("url")
        azure = tool_result.get("azure", {})
        running_status = azure.get("running_status")
        revision = azure.get("latest_ready_revision_name") or azure.get("latest_revision_name")
        health_path = tool_result.get("health_path")
        health_path_source = tool_result.get("health_path_source")

        if healthy:
            return (
                "Azure Container App is healthy. I saved the health check in project history.\n\n"
                f"Running status: {running_status}\n"
                f"Revision: {revision}\n"
                f"URL: {app_url}\n"
                f"Health path: {health_path}\n"
                f"Health path source: {health_path_source}"
            )

        return (
            "Azure Container App is not healthy or could not be verified. I saved this status in project history.\n\n"
            f"Status: {tool_result.get('status')}\n"
            f"Message: {tool_result.get('message')}\n"
            f"Health path used: {health_path}\n"
            f"Health path source: {health_path_source}"
        )

    def _azure_logs_message(self, tool_result: dict[str, Any]) -> str:
        log_count = tool_result.get("log_count", 0)

        return (
            "Azure logs were retrieved successfully and saved as an action in project history.\n\n"
            f"Log lines inspected: {log_count}\n"
            "I can now analyze them for incidents."
        )

    def _incident_message(self, tool_result: dict[str, Any]) -> str:
        result = tool_result.get("result", tool_result)
        incident_detected = result.get("incident_detected")
        severity = result.get("severity", "unknown")
        summary = result.get("summary", result.get("message", ""))
        health_path = result.get("health_path") or tool_result.get("health_path")
        health_path_source = result.get("health_path_source") or tool_result.get("health_path_source")

        if incident_detected:
            return (
                "I detected a possible incident and saved the incident analysis in project history.\n\n"
                f"Severity: {severity}\n"
                f"Summary: {summary}\n"
                f"Health path used: {health_path}\n"
                f"Health path source: {health_path_source}\n\n"
                "Next, I can create a remediation plan."
            )

        return (
            "No active incident was detected. I saved the incident analysis in project history.\n\n"
            f"Severity: {severity}\n"
            f"Summary: {summary}\n"
            f"Health path used: {health_path}\n"
            f"Health path source: {health_path_source}"
        )

    def _remediation_message(self, tool_result: dict[str, Any]) -> str:
        incident_detected = tool_result.get("incident_detected")
        remediation_required = tool_result.get("remediation_required")
        steps = tool_result.get("remediation_steps", [])

        if incident_detected or remediation_required:
            return (
                "I created a remediation plan and saved it in project history.\n\n"
                f"Number of steps: {len(steps)}\n"
                "No risky action was executed automatically."
            )

        return (
            "No remediation is required right now. I saved the check in project history.\n\n"
            f"I still found {len(steps)} monitoring or hardening suggestion(s), but no active incident is present."
        )

    def _deployment_verification_message(self, tool_result: dict[str, Any]) -> str:
        status = tool_result.get("status")
        verified = tool_result.get("verified")
        recommendation = tool_result.get("deployment_recommendation")

        if status == "verification_passed":
            return (
                "Deployment verification passed and was saved in project history.\n\n"
                f"Verified: {verified}\n"
                f"Recommendation: {recommendation}\n"
                "Azure is healthy, logs are available, and no active incident was detected."
            )

        return (
            "Deployment verification did not fully pass. I saved the result in project history.\n\n"
            f"Status: {status}\n"
            f"Recommendation: {recommendation}\n"
            f"Message: {tool_result.get('message')}"
        )

    def _final_report_message(self, tool_result: dict[str, Any]) -> str:
        status = tool_result.get("status")
        demo_ready = tool_result.get("demo_ready")
        recommendation = tool_result.get("demo_recommendation") or tool_result.get("recommendation")
        summary = tool_result.get("executive_summary", "")
        health_path = tool_result.get("health_path")
        health_path_source = tool_result.get("health_path_source")

        if status == "demo_blocked":
            blockers = tool_result.get("blockers") or []
            blocker_text = "\n".join(f"- {item}" for item in blockers)

            return (
                "Final CloudMind demo report was blocked because runtime verification is not clean.\n\n"
                f"Status: {status}\n"
                f"Demo ready: {demo_ready}\n"
                f"Recommendation: {recommendation}\n"
                f"Health path used: {health_path}\n"
                f"Health path source: {health_path_source}\n\n"
                f"Blockers:\n{blocker_text}"
            )

        return (
            "Final CloudMind demo report generated and saved in project history.\n\n"
            f"Status: {status}\n"
            f"Demo ready: {demo_ready}\n"
            f"Recommendation: {recommendation}\n"
            f"Health path used: {health_path}\n"
            f"Health path source: {health_path_source}\n\n"
            f"{summary}"
        )

    def _suggest_next_actions(
        self,
        intent: str,
        tool_result: dict[str, Any] | None,
        state: dict[str, Any],
    ) -> list[dict[str, str]]:
        repo_url = state.get("repo_url")
        resource_group = state.get("resource_group")
        app_name = state.get("app_name")
        health_path = state.get("health_path")

        suggestions: list[dict[str, str]] = []

        if not repo_url:
            return [
                {
                    "label": "Analyze a repository",
                    "message": "Analyze this repo https://github.com/Hedi808/test-3s.git",
                }
            ]

        if intent == "analyze_repository":
            suggestions.extend(
                [
                    {
                        "label": "Publish Docker PR",
                        "message": "Generate Docker files for this repo",
                    },
                    {
                        "label": "Publish Kubernetes PR",
                        "message": "Generate Kubernetes manifests for this repo",
                    },
                    {
                        "label": "Publish Azure PR",
                        "message": "Generate Azure deployment files for this repo",
                    },
                    {
                        "label": "Publish CI/CD PR",
                        "message": "Generate CI/CD for this repo",
                    },
                ]
            )

        if intent in ["generate_cicd", "generate_docker", "generate_kubernetes", "generate_azure", "prepare_deployment"]:
            suggestions.append(
                {
                    "label": "Deploy to Azure",
                    "message": "Deploy this app to Azure",
                }
            )

        if resource_group and app_name:
            health_suffix = f" using health path {health_path}" if health_path else ""

            suggestions.extend(
                [
                    {
                        "label": "Check Azure status",
                        "message": f"Check Azure status for resource group {resource_group} and app {app_name}{health_suffix}",
                    },
                    {
                        "label": "Analyze incident",
                        "message": f"Analyze incident for this Azure app{health_suffix}",
                    },
                    {
                        "label": "Final report",
                        "message": "Generate the final demo report",
                    },
                ]
            )

        return suggestions[:5]

    def _store_useful_result(
        self,
        session_id: str,
        intent: str,
        tool_name: str,
        tool_result: dict[str, Any],
        project_id: str | None,
        action_run_id: str | None,
        action_arguments: dict[str, Any],
    ) -> None:
        updates: dict[str, Any] = {
            "latest_intent": intent,
            "latest_action": tool_name,
            "latest_result_status": tool_result.get("status"),
        }

        result_health_path = self._extract_health_path_from_tool_result(tool_result)
        argument_health_path = action_arguments.get("health_path")

        if result_health_path:
            updates["health_path"] = result_health_path
        elif argument_health_path:
            updates["health_path"] = argument_health_path

        if tool_name == "analyze_repository" and self._is_success_status(tool_result.get("status")):
            updates["repo_analysis"] = tool_result

            analysis_health_path = self._extract_health_path_from_analysis(tool_result)

            if analysis_health_path:
                updates["health_path"] = analysis_health_path

            if project_id:
                self.project_memory.save_repo_analysis(
                    project_id=project_id,
                    analysis=self._json_safe(tool_result),
                )

        if tool_name in [
            "generate_docker",
            "generate_kubernetes",
            "prepare_deployment",
            "generate_cicd",
            "generate_azure",
        ]:
            pull_request = self._extract_pull_request(tool_result)
            files = self._extract_file_list(tool_result)

            if pull_request:
                pr_url = pull_request.get("url") or pull_request.get("html_url")
                pr_number = pull_request.get("number") or pull_request.get("pr_number")

                if pr_url:
                    updates["latest_pr_url"] = pr_url

                if pr_number:
                    updates["latest_pr_number"] = pr_number

                if project_id:
                    self.project_memory.save_pull_request_artifact(
                        project_id=project_id,
                        pull_request=self._json_safe(pull_request),
                        action_run_id=action_run_id,
                    )

            if files and project_id:
                self.project_memory.save_generated_files(
                    project_id=project_id,
                    files=files,
                    action_run_id=action_run_id,
                    metadata={
                        "tool_name": tool_name,
                        "intent": intent,
                    },
                )

        if tool_name == "deploy_azure_runtime":
            deployment_updates = self._extract_deployment_updates(
                tool_result=tool_result,
                fallback_arguments=action_arguments,
                fallback_state=self.memory.get_state(session_id),
            )

            updates.update(
                {
                    "resource_group": deployment_updates.get("resource_group"),
                    "app_name": deployment_updates.get("app_name"),
                    "azure_environment_name": deployment_updates.get("environment_name"),
                    "latest_app_url": deployment_updates.get("url"),
                    "ghcr_image": deployment_updates.get("image"),
                    "health_path": deployment_updates.get("health_path") or updates.get("health_path"),
                }
            )

            if project_id:
                self.project_memory.save_deployment_state(
                    project_id=project_id,
                    provider="azure",
                    resource_group=deployment_updates.get("resource_group"),
                    app_name=deployment_updates.get("app_name"),
                    environment_name=deployment_updates.get("environment_name"),
                    image=deployment_updates.get("image"),
                    url=deployment_updates.get("url"),
                    health_status=deployment_updates.get("health_status"),
                    metadata=self._json_safe(tool_result),
                )

        if tool_name in ["check_azure_status", "verify_azure_deployment"]:
            deployment_updates = self._extract_deployment_updates(
                tool_result=tool_result,
                fallback_arguments=action_arguments,
                fallback_state=self.memory.get_state(session_id),
            )

            updates.update(
                {
                    "resource_group": deployment_updates.get("resource_group"),
                    "app_name": deployment_updates.get("app_name"),
                    "latest_app_url": deployment_updates.get("url"),
                    "health_path": deployment_updates.get("health_path") or updates.get("health_path"),
                }
            )

            if project_id:
                self.project_memory.save_deployment_state(
                    project_id=project_id,
                    provider="azure",
                    resource_group=deployment_updates.get("resource_group"),
                    app_name=deployment_updates.get("app_name"),
                    environment_name=deployment_updates.get("environment_name"),
                    image=deployment_updates.get("image"),
                    url=deployment_updates.get("url"),
                    health_status=deployment_updates.get("health_status"),
                    metadata=self._json_safe(tool_result),
                )

        if tool_name in ["analyze_incident", "plan_remediation", "final_demo_report"] and project_id:
            artifact_type = {
                "analyze_incident": "incident_analysis",
                "plan_remediation": "remediation_plan",
                "final_demo_report": "final_demo_report",
            }.get(tool_name, "tool_result")

            self.project_memory.save_artifact(
                project_id=project_id,
                action_run_id=action_run_id,
                artifact_type=artifact_type,
                name=tool_name,
                metadata=self._json_safe(tool_result),
            )

        clean_updates = {
            key: value
            for key, value in updates.items()
            if value is not None
        }

        self.memory.update_state(session_id=session_id, updates=clean_updates)

    def _hydrate_from_project_context(
        self,
        project_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not project_context:
            return {}

        project = project_context.get("project") or {}
        deployment = project_context.get("latest_deployment") or {}
        artifacts = project_context.get("latest_artifacts") or []

        latest_pr = self._latest_pr_from_artifacts(artifacts)

        health_path = (
            project.get("health_path")
            or deployment.get("health_path")
            or self._extract_health_path_from_project_dict(project)
            or self._extract_health_path_from_deployment_dict(deployment)
        )

        return {
            "resource_group": project.get("azure_resource_group") or deployment.get("resource_group"),
            "app_name": project.get("azure_app_name") or deployment.get("app_name"),
            "environment_name": project.get("azure_environment_name") or deployment.get("environment_name"),
            "app_url": project.get("azure_app_url") or deployment.get("url"),
            "ghcr_image": project.get("ghcr_image") or deployment.get("image"),
            "health_path": health_path,
            "pull_request_url": latest_pr.get("url") if latest_pr else None,
            "pull_request_number": latest_pr.get("number") if latest_pr else None,
        }

    def _state_updates_from_project_context(
        self,
        project_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not project_context:
            return {}

        project = project_context.get("project") or {}
        hydrated = self._hydrate_from_project_context(project_context)

        return self._remove_none_values(
            {
                "project_id": project.get("id"),
                "project_name": project.get("name"),
                "repo_url": project.get("repo_url"),
                "repo_analysis": (project.get("metadata_json") or {}).get("latest_analysis"),
                "resource_group": hydrated.get("resource_group"),
                "app_name": hydrated.get("app_name"),
                "azure_environment_name": hydrated.get("environment_name"),
                "latest_app_url": hydrated.get("app_url"),
                "ghcr_image": hydrated.get("ghcr_image"),
                "health_path": hydrated.get("health_path"),
                "latest_pr_url": hydrated.get("pull_request_url"),
                "latest_pr_number": hydrated.get("pull_request_number"),
            }
        )

    def _latest_pr_from_artifacts(
        self,
        artifacts: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        for artifact in artifacts:
            if artifact.get("artifact_type") != "github_pull_request":
                continue

            metadata = artifact.get("metadata_json") or {}
            url = artifact.get("url") or metadata.get("url") or metadata.get("html_url")
            number = metadata.get("number") or metadata.get("pr_number")

            return {
                "url": url,
                "number": number,
            }

        return None

    def _extract_deployment_updates(
        self,
        tool_result: dict[str, Any],
        fallback_arguments: dict[str, Any],
        fallback_state: dict[str, Any],
    ) -> dict[str, Any]:
        health = tool_result.get("health") or {}
        healthy = tool_result.get("healthy")

        if healthy is None and isinstance(health, dict):
            healthy = health.get("healthy")

        health_status = "healthy" if healthy else str(tool_result.get("status", "unknown"))

        azure = tool_result.get("azure") or {}
        status_result = azure.get("status_result") or {}

        health_path = (
            tool_result.get("health_path")
            or status_result.get("health_path")
            or fallback_arguments.get("health_path")
            or fallback_state.get("health_path")
        )

        return {
            "resource_group": (
                tool_result.get("resource_group")
                or status_result.get("resource_group")
                or fallback_arguments.get("resource_group")
                or fallback_state.get("resource_group")
            ),
            "app_name": (
                tool_result.get("app_name")
                or status_result.get("app_name")
                or fallback_arguments.get("app_name")
                or fallback_state.get("app_name")
            ),
            "environment_name": (
                tool_result.get("environment_name")
                or status_result.get("environment_name")
                or fallback_state.get("azure_environment_name")
            ),
            "image": (
                tool_result.get("image")
                or status_result.get("image")
                or fallback_arguments.get("image")
                or fallback_state.get("ghcr_image")
            ),
            "url": (
                tool_result.get("app_url")
                or tool_result.get("url")
                or status_result.get("app_url")
                or fallback_state.get("latest_app_url")
            ),
            "health_status": health_status,
            "health_path": health_path,
        }

    def _status_result_is_healthy(
        self,
        tool_result: dict[str, Any],
    ) -> bool:
        if tool_result.get("healthy") is True:
            return True

        status = str(tool_result.get("status", "")).lower()

        if status in {"healthy", "success", "completed"}:
            return True

        health = tool_result.get("health")

        if isinstance(health, dict):
            if health.get("healthy") is True:
                return True

            health_status = str(health.get("status", "")).lower()

            if health_status in {"healthy", "success", "completed"}:
                return True

        return False

    def _extract_health_path_from_project_dict(
        self,
        project: dict[str, Any],
    ) -> str | None:
        metadata = project.get("metadata_json") or {}
        latest_analysis = metadata.get("latest_analysis")

        return self._extract_health_path_from_analysis(latest_analysis)

    def _extract_health_path_from_deployment_dict(
        self,
        deployment: dict[str, Any],
    ) -> str | None:
        metadata = deployment.get("metadata_json") or deployment.get("metadata") or {}
        health_path = (
            deployment.get("health_path")
            or metadata.get("health_path")
        )

        if health_path:
            return self._normalize_health_path(str(health_path))

        return None

    def _extract_health_path_from_tool_result(
        self,
        tool_result: dict[str, Any],
    ) -> str | None:
        health_path = tool_result.get("health_path") or tool_result.get("detected_health_path")

        if health_path:
            return self._normalize_health_path(str(health_path))

        analysis = tool_result.get("analysis")

        health_path = self._extract_health_path_from_analysis(analysis)

        if health_path:
            return health_path

        result = tool_result.get("result")

        if isinstance(result, dict):
            health_path = result.get("health_path") or result.get("detected_health_path")

            if health_path:
                return self._normalize_health_path(str(health_path))

        return None

    def _extract_health_path_from_analysis(
        self,
        analysis: Any,
    ) -> str | None:
        if not isinstance(analysis, dict):
            return None

        primary_component = analysis.get("primary_component")

        if isinstance(primary_component, dict):
            health_path = primary_component.get("health_path")

            if health_path:
                return self._normalize_health_path(str(health_path))

        health_path = analysis.get("health_path")

        if health_path:
            return self._normalize_health_path(str(health_path))

        components = analysis.get("components")

        if isinstance(components, list):
            for component in components:
                if not isinstance(component, dict):
                    continue

                health_path = component.get("health_path")

                if health_path:
                    return self._normalize_health_path(str(health_path))

        return None

    def _normalize_health_path(
        self,
        value: str,
    ) -> str:
        health_path = value.strip()

        if not health_path:
            return "/health"

        if not health_path.startswith("/"):
            health_path = "/" + health_path

        return health_path

    def _tool_failed(self, tool_result: dict[str, Any]) -> bool:
        status = str(tool_result.get("status", "")).lower()
        return status in ["failed", "error"] or "failed" in status

    def _tool_failed_message(
        self,
        tool_name: str | None,
        tool_result: dict[str, Any],
    ) -> str:
        message = tool_result.get("message") or "The tool failed while executing."
        error = tool_result.get("error")
        readable_tool_name = tool_name or tool_result.get("tool_name") or "the requested operation"

        if error:
            return (
                f"I could not complete {readable_tool_name}.\n\n"
                f"Reason: {message}\n"
                f"Error: {error}"
            )

        return (
            f"I could not complete {readable_tool_name}.\n\n"
            f"Reason: {message}"
        )

    def _missing_fields_message(self, missing_fields: list[str]) -> str:
        if "repo_url" in missing_fields:
            return (
                "I need a GitHub repository URL first. "
                "Example: `Analyze this repo https://github.com/Hedi808/test-3s.git`"
            )

        if "resource_group" in missing_fields or "app_name" in missing_fields:
            return (
                "I need the Azure resource group and Container App name first. "
                "If this project was already deployed, I can load it from PostgreSQL project memory. "
                "Otherwise, deploy the app first."
            )

        return f"I need more information before continuing: {', '.join(missing_fields)}."

    def _build_files_text(self, tool_result: dict[str, Any]) -> str:
        files = self._extract_file_list(tool_result)

        if not files:
            return ""

        return "\n\nGenerated files:\n" + "\n".join(f"- {file}" for file in files)

    def _build_pr_text(self, tool_result: dict[str, Any]) -> str:
        pull_request = self._extract_pull_request(tool_result)

        if not pull_request:
            return ""

        number = pull_request.get("number") or pull_request.get("pr_number") or "unknown"
        url = pull_request.get("url") or pull_request.get("html_url") or pull_request.get("pull_request_url") or "not available"
        branch = pull_request.get("branch") or pull_request.get("head_branch") or pull_request.get("source_branch")

        branch_text = f"\n- Branch: {branch}" if branch else ""

        return (
            "\n\nPull request created:\n"
            f"- Number: {number}\n"
            f"- URL: {url}"
            f"{branch_text}"
        )

    def _extract_file_list(self, tool_result: dict[str, Any]) -> list[str]:
        possible_keys = [
            "changed_files",
            "generated_files",
            "files",
            "written_files",
            "created_files",
            "generated_file_paths",
        ]

        result: list[str] = []

        for key in possible_keys:
            value = tool_result.get(key)

            if not value:
                continue

            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        result.append(item)
                    elif isinstance(item, dict):
                        path = item.get("relative_path") or item.get("path") or item.get("filename") or item.get("file") or item.get("name")
                        file_type = item.get("type")

                        if path and file_type:
                            result.append(f"{path} ({file_type})")
                        elif path:
                            result.append(str(path))
                        else:
                            result.append(str(item))

            elif isinstance(value, dict):
                path = value.get("relative_path") or value.get("path") or value.get("filename") or value.get("file") or value.get("name")
                file_type = value.get("type")

                if path and file_type:
                    result.append(f"{path} ({file_type})")
                elif path:
                    result.append(str(path))

        nested_keys = ["docker", "kubernetes", "cicd", "azure"]

        for nested_key in nested_keys:
            nested_value = tool_result.get(nested_key)

            if isinstance(nested_value, dict):
                result.extend(self._extract_file_list(nested_value))

        return self._deduplicate_strings(result)

    def _extract_pull_request(self, tool_result: dict[str, Any]) -> dict[str, Any] | None:
        possible_keys = [
            "pull_request",
            "pr",
            "github_pull_request",
        ]

        for key in possible_keys:
            value = tool_result.get(key)

            if isinstance(value, dict):
                return value

        nested_result = tool_result.get("result")

        if isinstance(nested_result, dict):
            for key in possible_keys:
                value = nested_result.get(key)

                if isinstance(value, dict):
                    return value

        git_result = tool_result.get("git")

        if isinstance(git_result, dict):
            for key in possible_keys:
                value = git_result.get(key)

                if isinstance(value, dict):
                    return value

            pr_url = (
                git_result.get("pull_request_url")
                or git_result.get("pr_url")
                or git_result.get("html_url")
                or git_result.get("url")
            )

            pr_number = (
                git_result.get("pull_request_number")
                or git_result.get("pr_number")
                or git_result.get("number")
            )

            branch = (
                git_result.get("branch")
                or git_result.get("branch_name")
                or git_result.get("head_branch")
            )

            if pr_url or pr_number or branch:
                return {
                    "url": pr_url,
                    "number": pr_number,
                    "branch": branch,
                }

        return None

    def _deduplicate_strings(self, items: list[str]) -> list[str]:
        seen = set()
        result = []

        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)

        return result

    def _extract_entities(self, message: str) -> dict[str, Any]:
        entities: dict[str, Any] = {}

        repo_url = self._extract_repo_url(message)
        pr_url = self._extract_pull_request_url(message)
        resource_group = self._extract_resource_group(message)
        app_name = self._extract_app_name(message)
        health_path = self._extract_health_path(message)

        if repo_url:
            entities["repo_url"] = repo_url

        if pr_url:
            entities["pull_request_url"] = pr_url
            pr_number = self._extract_pr_number_from_url(pr_url)
            if pr_number:
                entities["latest_pr_number"] = pr_number

        if resource_group:
            entities["resource_group"] = resource_group

        if app_name:
            entities["app_name"] = app_name

        if health_path:
            entities["health_path"] = health_path

        return entities

    def _extract_repo_url(self, message: str) -> str | None:
        urls = re.findall(
            r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?",
            message,
        )

        for url in urls:
            if "/pull/" not in url:
                return url

        return None

    def _extract_pull_request_url(self, message: str) -> str | None:
        matches = re.findall(
            r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+",
            message,
        )

        if matches:
            return matches[0]

        return None

    def _extract_pr_number_from_url(self, pr_url: str) -> int | None:
        parsed = urlparse(pr_url)
        parts = [part for part in parsed.path.split("/") if part]

        if len(parts) >= 4 and parts[2] == "pull":
            try:
                return int(parts[3])
            except ValueError:
                return None

        return None

    def _extract_resource_group(self, message: str) -> str | None:
        patterns = [
            r"resource group\s+([A-Za-z0-9_.-]+)",
            r"resource_group\s*[:=]\s*([A-Za-z0-9_.-]+)",
            r"rg-[A-Za-z0-9_.-]+",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)

            if match:
                if match.groups():
                    return match.group(1)

                return match.group(0)

        return None

    def _extract_app_name(self, message: str) -> str | None:
        patterns = [
            r"app name\s+([A-Za-z0-9_.-]+)",
            r"app\s+([A-Za-z0-9_.-]+-backend)",
            r"app\s+([A-Za-z0-9_.-]+-app)",
            r"container app\s+([A-Za-z0-9_.-]+)",
            r"app_name\s*[:=]\s*([A-Za-z0-9_.-]+)",
            r"[A-Za-z0-9_.-]+-backend",
            r"[A-Za-z0-9_.-]+-app",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)

            if match:
                if match.groups():
                    return match.group(1)

                return match.group(0)

        return None

    def _extract_health_path(self, message: str) -> str | None:
        patterns = [
            r"health path\s+(/[A-Za-z0-9_./-]+)",
            r"health_path\s*[:=]\s*(/[A-Za-z0-9_./-]+)",
            r"endpoint\s+(/[A-Za-z0-9_./-]+)",
            r"using\s+(/[A-Za-z0-9_./-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)

            if match:
                return self._normalize_health_path(match.group(1))

        return None

    def _is_success_status(self, status: Any) -> bool:
        normalized = str(status or "").lower()
        return normalized in self.SUCCESS_STATUSES

    def _missing(self, arguments: dict[str, Any], required: list[str]) -> list[str]:
        return [
            key
            for key in required
            if arguments.get(key) is None or arguments.get(key) == ""
        ]

    def _no_tool_plan(self, reason: str) -> dict[str, Any]:
        return {
            "can_execute": False,
            "tool_name": None,
            "requires_approval": False,
            "missing_fields": [],
            "reason": reason,
            "arguments": {},
        }

    def _remove_none_values(self, value: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item
            for key, item in value.items()
            if item is not None
        }

    def _json_safe(self, value: Any) -> Any:
        return json.loads(json.dumps(value, default=str))

    def _trim_tool_result(self, tool_result: dict[str, Any] | None) -> dict[str, Any] | None:
        if tool_result is None:
            return None

        return tool_result