import os

from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv()


class Settings(BaseModel):
    app_name: str = "CloudMind"
    environment: str = "development"
    api_version: str = "0.3.0"

    github_token: str | None = os.getenv("GITHUB_TOKEN")
    github_username: str | None = os.getenv("GITHUB_USERNAME")


settings = Settings()