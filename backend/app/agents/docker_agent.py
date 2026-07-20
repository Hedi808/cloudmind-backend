from pathlib import Path
from typing import Any


COMPOSE_FILE_NAMES = {
    "compose.yml",
    "compose.yaml",
    "docker-compose.yml",
    "docker-compose.yaml",
}


class DockerAgent:
    """
    Phase 3 agent.

    Responsibilities:
    - generate Dockerfile and .dockerignore for detected components
    - generate compose.yml for local multi-container execution
    - skip existing Docker files unless overwrite=True
    - review existing Docker files and suggest improvements
    """

    def generate_from_analysis(
        self,
        analysis: dict[str, Any],
        overwrite: bool = False,
    ) -> dict[str, Any]:
        repo_path = Path(analysis["metadata"]["local_path"])
        components = analysis.get("components", [])

        generated_files: list[dict[str, Any]] = []
        skipped_files: list[dict[str, Any]] = []
        existing_files: list[dict[str, Any]] = []

        if not components:
            return {
                "status": "failed",
                "message": "No deployable components were detected. Docker files were not generated.",
                "analysis": analysis,
                "generated_files": generated_files,
                "skipped_files": skipped_files,
                "existing_files": existing_files,
                "recommendations": [
                    "Improve repository analysis first by adding standard dependency files such as package.json, requirements.txt, or pyproject.toml.",
                ],
            }

        for component in components:
            component_dir = self._get_component_dir(component)

            dockerfile_path = component_dir / "Dockerfile"
            dockerignore_path = component_dir / ".dockerignore"

            if dockerfile_path.exists() and not overwrite:
                existing_files.append(
                    {
                        "path": str(dockerfile_path),
                        "type": "Dockerfile",
                        "component": component["name"],
                    }
                )
                skipped_files.append(
                    {
                        "path": str(dockerfile_path),
                        "reason": "Dockerfile already exists. Use overwrite=true to replace it.",
                    }
                )
            else:
                dockerfile_content = self._generate_dockerfile(component, component_dir)
                dockerfile_path.write_text(dockerfile_content, encoding="utf-8")
                generated_files.append(
                    {
                        "path": str(dockerfile_path),
                        "type": "Dockerfile",
                        "component": component["name"],
                    }
                )

            if dockerignore_path.exists() and not overwrite:
                existing_files.append(
                    {
                        "path": str(dockerignore_path),
                        "type": ".dockerignore",
                        "component": component["name"],
                    }
                )
                skipped_files.append(
                    {
                        "path": str(dockerignore_path),
                        "reason": ".dockerignore already exists. Use overwrite=true to replace it.",
                    }
                )
            else:
                dockerignore_content = self._generate_dockerignore(component)
                dockerignore_path.write_text(dockerignore_content, encoding="utf-8")
                generated_files.append(
                    {
                        "path": str(dockerignore_path),
                        "type": ".dockerignore",
                        "component": component["name"],
                    }
                )

        compose_result = self._generate_compose_file(
            repo_path=repo_path,
            components=components,
            overwrite=overwrite,
        )

        if compose_result["status"] == "generated":
            generated_files.append(compose_result)
        elif compose_result["status"] == "exists":
            existing_files.append(compose_result)
            skipped_files.append(
                {
                    "path": compose_result["path"],
                    "reason": "Compose file already exists. Use overwrite=true to replace it.",
                }
            )

        review = self.review_docker_files(repo_path)

        return {
            "status": "success",
            "message": "DockerAgent completed successfully.",
            "repo_url": analysis["repo_url"],
            "repo_name": analysis["repo_name"],
            "project_type": analysis["project_type"],
            "components": components,
            "generated_files": generated_files,
            "skipped_files": skipped_files,
            "existing_files": existing_files,
            "review": review,
            "analysis": analysis,
            "next_step": "After reviewing the generated files, GitAgent can push them to a CloudMind branch and open a pull request.",
        }

    def generate_for_repo(
        self,
        repo_url: str,
        branch: str | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        from app.agents.repo_analyzer_agent import RepositoryAnalyzerAgent

        repo_analyzer = RepositoryAnalyzerAgent()
        analysis = repo_analyzer.analyze(repo_url=repo_url, branch=branch)

        return self.generate_from_analysis(
            analysis=analysis,
            overwrite=overwrite,
        )

    def review_docker_files(self, repo_path: Path) -> dict[str, Any]:
        dockerfiles = []
        dockerignore_files = []
        compose_files = []
        recommendations = []

        for path in repo_path.rglob("*"):
            if not path.is_file():
                continue

            if ".git" in path.parts or "node_modules" in path.parts:
                continue

            if path.name == "Dockerfile":
                dockerfiles.append(str(path))
                content = self._safe_read(path)

                if "USER " not in content:
                    recommendations.append(
                        {
                            "file": str(path),
                            "recommendation": "Consider running the container as a non-root user for better security.",
                        }
                    )

                if "HEALTHCHECK" not in content:
                    recommendations.append(
                        {
                            "file": str(path),
                            "recommendation": "Consider adding a HEALTHCHECK instruction or rely on Kubernetes probes later.",
                        }
                    )

                if ":latest" in content:
                    recommendations.append(
                        {
                            "file": str(path),
                            "recommendation": "Avoid using the latest tag for base images in production.",
                        }
                    )

            if path.name == ".dockerignore":
                dockerignore_files.append(str(path))

            if path.name in COMPOSE_FILE_NAMES:
                compose_files.append(str(path))

        if not dockerfiles:
            recommendations.append(
                {
                    "file": None,
                    "recommendation": "No Dockerfile found. Generate Dockerfiles for deployable components.",
                }
            )

        if not dockerignore_files:
            recommendations.append(
                {
                    "file": None,
                    "recommendation": "No .dockerignore found. Add one to keep images smaller and avoid copying sensitive/unnecessary files.",
                }
            )

        if not compose_files:
            recommendations.append(
                {
                    "file": None,
                    "recommendation": "No Compose file found. Generate compose.yml for local multi-container testing.",
                }
            )

        return {
            "dockerfiles": dockerfiles,
            "dockerignore_files": dockerignore_files,
            "compose_files": compose_files,
            "recommendations": recommendations,
        }

    def _get_component_dir(self, component: dict[str, Any]) -> Path:
        package_file = component.get("package_file")

        if not package_file:
            raise RuntimeError(f"Component {component.get('name')} has no package_file.")

        return Path(package_file).parent

    def _generate_dockerfile(self, component: dict[str, Any], component_dir: Path) -> str:
        language = (component.get("language") or "").lower()
        framework = (component.get("framework") or "").lower()

        if "python" in language:
            return self._generate_python_dockerfile(component, component_dir)

        if "javascript" in language or "typescript" in language:
            if framework in ["react", "vue.js", "angular"]:
                return self._generate_frontend_static_dockerfile(component)

            if framework == "next.js":
                return self._generate_nextjs_dockerfile(component)

            return self._generate_node_dockerfile(component)

        if "java" in language:
            return self._generate_java_dockerfile(component)

        return self._generate_generic_dockerfile(component)

    def _generate_python_dockerfile(self, component: dict[str, Any], component_dir: Path) -> str:
        port = component.get("port") or 8000
        framework = component.get("framework") or "Python"
        start_command = component.get("start_command") or "python main.py"

        has_requirements = (component_dir / "requirements.txt").exists()
        has_pyproject = (component_dir / "pyproject.toml").exists()

        dependency_install = (
            "RUN python -m pip install --upgrade pip && \\\n"
            "    if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; \\\n"
            "    elif [ -f pyproject.toml ]; then pip install --no-cache-dir .; \\\n"
            "    fi"
        )

        if not has_requirements and not has_pyproject:
            dependency_install = (
                "RUN python -m pip install --upgrade pip\n"
                "# WARNING: No requirements.txt or pyproject.toml was detected."
            )

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: {framework}

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt* pyproject.toml* ./

{dependency_install}

COPY . .

RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app

USER appuser

EXPOSE {port}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:{port}/health')" || exit 1

CMD ["sh", "-c", "{start_command}"]
"""

    def _generate_node_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 3000
        framework = component.get("framework") or "Node.js"
        start_command = component.get("start_command") or "npm start"

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: {framework}

FROM node:22-alpine

WORKDIR /app

COPY package*.json ./

RUN npm ci || npm install

COPY . .

USER node

EXPOSE {port}

CMD ["sh", "-c", "{start_command}"]
"""

    def _generate_frontend_static_dockerfile(self, component: dict[str, Any]) -> str:
        framework = component.get("framework") or "Frontend"
        build_command = component.get("build_command") or "npm run build"

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: {framework}

FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./

RUN npm ci || npm install

COPY . .

RUN {build_command}

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
    CMD wget -qO- http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
"""

    def _generate_nextjs_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 3000
        build_command = component.get("build_command") or "npm run build"
        start_command = component.get("start_command") or "npm start"

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: Next.js

FROM node:22-alpine

WORKDIR /app

COPY package*.json ./

RUN npm ci || npm install

COPY . .

RUN {build_command}

USER node

EXPOSE {port}

CMD ["sh", "-c", "{start_command}"]
"""

    def _generate_java_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 8080
        build_command = component.get("build_command") or "mvn clean package"
        start_command = component.get("start_command") or "java -jar app.jar"

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: {component.get("framework") or "Java"}

FROM eclipse-temurin:21-jdk AS build

WORKDIR /app

COPY . .

RUN {build_command}

FROM eclipse-temurin:21-jre

WORKDIR /app

COPY --from=build /app/target/*.jar app.jar

EXPOSE {port}

CMD ["sh", "-c", "{start_command}"]
"""

    def _generate_generic_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 8080

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# WARNING: CloudMind could not confidently detect this component runtime.

FROM alpine:latest

WORKDIR /app

COPY . .

EXPOSE {port}

CMD ["sh"]
"""

    def _generate_dockerignore(self, component: dict[str, Any]) -> str:
        language = (component.get("language") or "").lower()

        common = [
            ".git",
            ".github",
            ".env",
            ".env.*",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".DS_Store",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            "logs",
            "*.log",
            "coverage",
            ".coverage",
        ]

        if "python" in language:
            common.extend(
                [
                    ".venv",
                    "venv",
                    "env",
                    "dist",
                    "build",
                    "*.egg-info",
                ]
            )

        if "javascript" in language or "typescript" in language:
            common.extend(
                [
                    "node_modules",
                    "dist",
                    "build",
                    ".next",
                    ".turbo",
                    "npm-debug.log",
                    "yarn-error.log",
                ]
            )

        return "\n".join(common) + "\n"

    def _generate_compose_file(
        self,
        repo_path: Path,
        components: list[dict[str, Any]],
        overwrite: bool,
    ) -> dict[str, Any]:
        existing_compose = self._find_existing_compose_file(repo_path)

        if existing_compose and not overwrite:
            return {
                "status": "exists",
                "path": str(existing_compose),
                "type": "compose",
            }

        compose_path = repo_path / "compose.yml"
        compose_content = self._build_compose_content(repo_path, components)
        compose_path.write_text(compose_content, encoding="utf-8")

        return {
            "status": "generated",
            "path": str(compose_path),
            "type": "compose",
        }

    def _build_compose_content(self, repo_path: Path, components: list[dict[str, Any]]) -> str:
        lines = [
            "# Generated by CloudMind",
            "services:",
        ]

        service_names = []

        for component in components:
            service_name = self._normalize_service_name(component.get("name") or component.get("type") or "app")
            service_names.append(service_name)

            component_dir = self._get_component_dir(component)
            context = self._relative_path(repo_path, component_dir)

            host_port = component.get("port") or self._runtime_container_port(component)
            container_port = self._runtime_container_port(component)

            lines.extend(
                [
                    f"  {service_name}:",
                    "    build:",
                    f"      context: ./{context}",
                    "      dockerfile: Dockerfile",
                    f"    container_name: cloudmind-{service_name}",
                    "    ports:",
                    f'      - "{host_port}:{container_port}"',
                    "    restart: unless-stopped",
                ]
            )

            if component.get("type") == "frontend" and "backend" in service_names:
                lines.extend(
                    [
                        "    depends_on:",
                        "      - backend",
                    ]
                )

        return "\n".join(lines) + "\n"

    def _find_existing_compose_file(self, repo_path: Path) -> Path | None:
        for file_name in COMPOSE_FILE_NAMES:
            compose_path = repo_path / file_name

            if compose_path.exists():
                return compose_path

        return None

    def _runtime_container_port(self, component: dict[str, Any]) -> int:
        component_type = component.get("type")
        framework = (component.get("framework") or "").lower()

        if component_type == "frontend" and framework in ["react", "vue.js", "angular"]:
            return 80

        return component.get("port") or 8080

    def _relative_path(self, repo_path: Path, path: Path) -> str:
        try:
            return path.relative_to(repo_path).as_posix()
        except ValueError:
            return path.as_posix()

    def _normalize_service_name(self, name: str) -> str:
        name = name.lower().strip()
        name = name.replace("_", "-")
        name = "".join(char if char.isalnum() or char == "-" else "-" for char in name)
        name = name.strip("-")

        return name or "app"

    def _safe_read(self, path: Path, max_chars: int = 200_000) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        except Exception:
            return ""