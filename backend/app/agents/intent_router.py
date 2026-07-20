class IntentRouter:
    """
    Simple rule-based intent router for Phase 1.
    Later, we can replace this with an LLM-based router.
    """

    def detect_intent(self, message: str) -> str:
        text = message.lower()

        if any(word in text for word in ["analyze", "understand", "architecture", "repo", "repository", "github"]):
            return "analyze_repo"

        if any(word in text for word in ["docker", "dockerfile", "container", "containerize"]):
            return "generate_docker"

        if any(word in text for word in ["kubernetes", "k8s", "manifest", "helm", "orchestration"]):
            return "generate_kubernetes"

        if any(word in text for word in ["deploy", "deployment", "release"]):
            return "deploy_app"

        if any(word in text for word in ["health", "status", "state", "monitor", "infra", "infrastructure"]):
            return "check_health"

        if any(word in text for word in ["incident", "fix", "crash", "down", "error", "failed", "rollback"]):
            return "incident_response"

        return "general_chat"