import os

from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


class Settings(BaseModel):
    app_name: str = "CloudMind"
    environment: str = "development"
    api_version: str = "0.3.0"

    github_token: str | None = os.getenv("GITHUB_TOKEN")
    github_username: str | None = os.getenv("GITHUB_USERNAME")

    llm_enabled: bool = _env_bool("CLOUDMIND_LLM_ENABLED", False)
    llm_provider: str = os.getenv("CLOUDMIND_LLM_PROVIDER", "ollama")
    llm_model: str = os.getenv("CLOUDMIND_LLM_MODEL", "llama3.2:3b")
    llm_reasoning_effort: str = os.getenv("CLOUDMIND_LLM_REASONING_EFFORT", "medium")
    llm_timeout_seconds: int = _env_int("CLOUDMIND_LLM_TIMEOUT_SECONDS", 60)

    auth_cookie_name: str = os.getenv("AUTH_COOKIE_NAME", "cloudmind_session")
    auth_session_days: int = _env_int("AUTH_SESSION_DAYS", 14)
    auth_cookie_secure: bool = _env_bool("AUTH_COOKIE_SECURE", False)
    auth_frontend_url: str = os.getenv("AUTH_FRONTEND_URL", "http://localhost:5173")

    google_oauth_client_id: str | None = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: str | None = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    google_oauth_redirect_uri: str = os.getenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/auth/google/callback",
    )

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    gemini_base_url: str = os.getenv(
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    )


settings = Settings()
