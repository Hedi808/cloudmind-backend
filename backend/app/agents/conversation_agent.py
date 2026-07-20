class ConversationAgent:
    """
    Handles general CloudMind conversation in Phase 1.
    """

    def respond(self, message: str) -> str:
        return (
            "I am CloudMind, your AI DevOps assistant. "
            "In Phase 1, I can understand your request and route it to the correct agent. "
            "Soon, I will analyze repositories, generate Docker files, create Kubernetes manifests, "
            "deploy applications, monitor infrastructure, and help with incident response."
        )