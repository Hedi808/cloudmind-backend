from app.agents.conversation_agent import ConversationAgent
from app.agents.deployment_prepare_agent import DeploymentPrepareAgent
from app.agents.docker_agent import DockerAgent
from app.agents.intent_router import IntentRouter
from app.agents.kubernetes_agent import KubernetesAgent
from app.agents.repo_analyzer_agent import RepositoryAnalyzerAgent


class Orchestrator:
    """
    Central brain of CloudMind.

    It receives a user message, detects the intent,
    then routes the request to the correct agent.
    """

    def __init__(self):
        self.intent_router = IntentRouter()
        self.conversation_agent = ConversationAgent()
        self.repo_analyzer_agent = RepositoryAnalyzerAgent()
        self.docker_agent = DockerAgent()
        self.kubernetes_agent = KubernetesAgent()
        self.deployment_prepare_agent = DeploymentPrepareAgent()

    def handle_message(
        self,
        message: str,
        repo_url: str | None = None,
        branch: str | None = None,
        environment: str = "staging",
    ) -> dict:
        intent = self.intent_router.detect_intent(message)

        if intent == "analyze_repo":
            if not repo_url:
                return {
                    "detected_intent": intent,
                    "agent_used": "RepositoryAnalyzerAgent",
                    "response": (
                        "Repository analysis requested, but no repository URL was provided. "
                        "Please send a GitHub repository URL so I can analyze the project architecture."
                    ),
                    "metadata": {
                        "repo_url": repo_url,
                        "branch": branch,
                        "environment": environment,
                        "phase": "phase_2_repository_analysis",
                    },
                }

            try:
                analysis = self.repo_analyzer_agent.analyze(
                    repo_url=repo_url,
                    branch=branch,
                )

                frameworks = ", ".join(analysis["detected_frameworks"]) or "unknown"
                languages = ", ".join(analysis["detected_languages"]) or "unknown"
                missing_files = ", ".join(analysis["missing_devops_files"]) or "none"

                response = (
                    "Repository analyzed successfully. "
                    f"Project type: {analysis['project_type']}. "
                    f"Detected languages: {languages}. "
                    f"Detected frameworks: {frameworks}. "
                    f"Missing DevOps files: {missing_files}."
                )

                return {
                    "detected_intent": intent,
                    "agent_used": "RepositoryAnalyzerAgent",
                    "response": response,
                    "metadata": {
                        "repo_url": repo_url,
                        "branch": branch,
                        "environment": environment,
                        "phase": "phase_2_repository_analysis",
                        "analysis": analysis,
                    },
                }

            except Exception as exc:
                return {
                    "detected_intent": intent,
                    "agent_used": "RepositoryAnalyzerAgent",
                    "response": f"Repository analysis failed: {exc}",
                    "metadata": {
                        "repo_url": repo_url,
                        "branch": branch,
                        "environment": environment,
                        "phase": "phase_2_repository_analysis",
                        "error": str(exc),
                    },
                }

        elif intent == "generate_docker":
            if not repo_url:
                return {
                    "detected_intent": intent,
                    "agent_used": "DockerAgent",
                    "response": (
                        "Docker generation requested, but no repository URL was provided. "
                        "Please send a GitHub repository URL so I can generate or review Docker files."
                    ),
                    "metadata": {
                        "repo_url": repo_url,
                        "branch": branch,
                        "environment": environment,
                        "phase": "phase_3_docker_generation",
                    },
                }

            try:
                result = self.docker_agent.generate_for_repo(
                    repo_url=repo_url,
                    branch=branch,
                    overwrite=False,
                )

                generated_count = len(result.get("generated_files", []))
                skipped_count = len(result.get("skipped_files", []))
                existing_count = len(result.get("existing_files", []))

                response = (
                    "DockerAgent completed successfully. "
                    f"Generated files: {generated_count}. "
                    f"Existing files detected: {existing_count}. "
                    f"Skipped files: {skipped_count}."
                )

                return {
                    "detected_intent": intent,
                    "agent_used": "DockerAgent",
                    "response": response,
                    "metadata": {
                        "repo_url": repo_url,
                        "branch": branch,
                        "environment": environment,
                        "phase": "phase_3_docker_generation",
                        "docker_result": result,
                    },
                }

            except Exception as exc:
                return {
                    "detected_intent": intent,
                    "agent_used": "DockerAgent",
                    "response": f"Docker generation failed: {exc}",
                    "metadata": {
                        "repo_url": repo_url,
                        "branch": branch,
                        "environment": environment,
                        "phase": "phase_3_docker_generation",
                        "error": str(exc),
                    },
                }

        elif intent == "generate_kubernetes":
            if not repo_url:
                return {
                    "detected_intent": intent,
                    "agent_used": "KubernetesAgent",
                    "response": (
                        "Kubernetes generation requested, but no repository URL was provided. "
                        "Please send a GitHub repository URL so I can generate Kubernetes manifests."
                    ),
                    "metadata": {
                        "repo_url": repo_url,
                        "branch": branch,
                        "environment": environment,
                        "phase": "phase_4_kubernetes_generation",
                    },
                }

            try:
                result = self.kubernetes_agent.generate_for_repo(
                    repo_url=repo_url,
                    branch=branch,
                    overwrite=False,
                    namespace="cloudmind-staging",
                )

                generated_count = len(result.get("generated_files", []))
                skipped_count = len(result.get("skipped_files", []))

                response = (
                    "KubernetesAgent completed successfully. "
                    f"Generated manifests: {generated_count}. "
                    f"Skipped files: {skipped_count}."
                )

                return {
                    "detected_intent": intent,
                    "agent_used": "KubernetesAgent",
                    "response": response,
                    "metadata": {
                        "repo_url": repo_url,
                        "branch": branch,
                        "environment": environment,
                        "phase": "phase_4_kubernetes_generation",
                        "kubernetes_result": result,
                    },
                }

            except Exception as exc:
                return {
                    "detected_intent": intent,
                    "agent_used": "KubernetesAgent",
                    "response": f"Kubernetes generation failed: {exc}",
                    "metadata": {
                        "repo_url": repo_url,
                        "branch": branch,
                        "environment": environment,
                        "phase": "phase_4_kubernetes_generation",
                        "error": str(exc),
                    },
                }

        elif intent == "deploy_app":
            if not repo_url:
                return {
                    "detected_intent": intent,
                    "agent_used": "DeploymentPrepareAgent",
                    "response": (
                        "Deployment preparation requested, but no repository URL was provided. "
                        "Please send a GitHub repository URL so I can prepare Docker and Kubernetes deployment files."
                    ),
                    "metadata": {
                        "repo_url": repo_url,
                        "branch": branch,
                        "environment": environment,
                        "phase": "phase_5_deployment_preparation",
                    },
                }

            try:
                result = self.deployment_prepare_agent.prepare(
                    repo_url=repo_url,
                    branch=branch or "main",
                    base_branch=branch or "main",
                    overwrite=False,
                    publish=False,
                    namespace="cloudmind-staging",
                )

                generated_count = len(result.get("generated_file_paths", []))

                response = (
                    "Deployment preparation completed locally. "
                    f"Generated deployment files: {generated_count}. "
                    "Use POST /api/deployment/prepare with publish=true to open a GitHub pull request."
                )

                return {
                    "detected_intent": intent,
                    "agent_used": "DeploymentPrepareAgent",
                    "response": response,
                    "metadata": {
                        "repo_url": repo_url,
                        "branch": branch,
                        "environment": environment,
                        "phase": "phase_5_deployment_preparation",
                        "deployment_result": result,
                    },
                }

            except Exception as exc:
                return {
                    "detected_intent": intent,
                    "agent_used": "DeploymentPrepareAgent",
                    "response": f"Deployment preparation failed: {exc}",
                    "metadata": {
                        "repo_url": repo_url,
                        "branch": branch,
                        "environment": environment,
                        "phase": "phase_5_deployment_preparation",
                        "error": str(exc),
                    },
                }

        elif intent == "check_health":
            response = (
                "Health check requested. "
                "In the observability phase, I will inspect Kubernetes pods, services, logs, "
                "events, Prometheus metrics, and application health endpoints."
            )
            agent_used = "ObservabilityAgent"

        elif intent == "incident_response":
            response = (
                "Incident response requested. "
                "In the incident response phase, I will diagnose failures such as CrashLoopBackOff, "
                "ImagePullBackOff, failed readiness probes, and bad rollouts, then suggest or apply safe remediation actions."
            )
            agent_used = "IncidentResponseAgent"

        else:
            response = self.conversation_agent.respond(message)
            agent_used = "ConversationAgent"

        return {
            "detected_intent": intent,
            "agent_used": agent_used,
            "response": response,
            "metadata": {
                "repo_url": repo_url,
                "branch": branch,
                "environment": environment,
                "phase": "cloudmind_orchestration",
            },
        }