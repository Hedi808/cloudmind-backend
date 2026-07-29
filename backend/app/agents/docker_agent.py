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
    - generate Dockerfile and .dockerignore for detected deployable components
    - generate compose.yml for local multi-container execution
    - skip existing Docker files unless overwrite=True
    - review existing Docker files and suggest improvements

    Phase 20C improvements:
    - uses repo_path + component_path/package_file safely
    - supports smart analyzer primary_component
    - supports fullstack Node.js native HTTP projects
    - does not crash on nested static frontend components
    - verifies generated files exist before returning success
    """

    def generate_from_analysis(
        self,
        analysis: dict[str, Any],
        overwrite: bool = False,
    ) -> dict[str, Any]:
        repo_path = Path(analysis["metadata"]["local_path"])
        all_components = analysis.get("components", [])
        primary_component = analysis.get("primary_component")

        components = self._select_deployable_components(
            repo_path=repo_path,
            components=all_components,
            primary_component=primary_component,
        )

        generated_files: list[dict[str, Any]] = []
        skipped_files: list[dict[str, Any]] = []
        existing_files: list[dict[str, Any]] = []

        if not components:
            return {
                "status": "failed",
                "message": "No deployable components were detected. Docker files were not generated.",
                "analysis": analysis,
                "components": [],
                "generated_files": generated_files,
                "skipped_files": skipped_files,
                "existing_files": existing_files,
                "recommendations": [
                    "Improve repository analysis first by adding a manifest, start command, component_path, package_file, or README run instructions.",
                ],
            }

        for component in components:
            component_dir = self._get_component_dir(repo_path, component)

            if not component_dir.exists():
                return {
                    "status": "failed",
                    "message": f"Component directory does not exist: {component_dir}",
                    "analysis": analysis,
                    "components": components,
                    "generated_files": generated_files,
                    "skipped_files": skipped_files,
                    "existing_files": existing_files,
                    "recommendations": [
                        "Re-run repository analysis and make sure component_path/package_file points inside the cloned repository.",
                    ],
                }

            dockerfile_path = component_dir / "Dockerfile"
            dockerignore_path = component_dir / ".dockerignore"

            if dockerfile_path.exists() and not overwrite:
                existing_files.append(
                    self._file_record(
                        repo_path=repo_path,
                        path=dockerfile_path,
                        file_type="Dockerfile",
                        component=component,
                    )
                )
                skipped_files.append(
                    {
                        "path": str(dockerfile_path),
                        "relative_path": self._relative_path(repo_path, dockerfile_path),
                        "reason": "Dockerfile already exists. Use overwrite=true to replace it.",
                    }
                )
            else:
                dockerfile_content = self._generate_dockerfile(component, component_dir)
                dockerfile_path.write_text(dockerfile_content, encoding="utf-8")
                generated_files.append(
                    self._file_record(
                        repo_path=repo_path,
                        path=dockerfile_path,
                        file_type="Dockerfile",
                        component=component,
                    )
                )

            if dockerignore_path.exists() and not overwrite:
                existing_files.append(
                    self._file_record(
                        repo_path=repo_path,
                        path=dockerignore_path,
                        file_type=".dockerignore",
                        component=component,
                    )
                )
                skipped_files.append(
                    {
                        "path": str(dockerignore_path),
                        "relative_path": self._relative_path(repo_path, dockerignore_path),
                        "reason": ".dockerignore already exists. Use overwrite=true to replace it.",
                    }
                )
            else:
                dockerignore_content = self._generate_dockerignore(component)
                dockerignore_path.write_text(dockerignore_content, encoding="utf-8")
                generated_files.append(
                    self._file_record(
                        repo_path=repo_path,
                        path=dockerignore_path,
                        file_type=".dockerignore",
                        component=component,
                    )
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
                    "relative_path": compose_result.get("relative_path"),
                    "reason": "Compose file already exists. Use overwrite=true to replace it.",
                }
            )

        missing_generated_files = [
            generated_file
            for generated_file in generated_files
            if generated_file.get("path")
            and not Path(generated_file["path"]).exists()
        ]

        if missing_generated_files:
            return {
                "status": "failed",
                "message": "DockerAgent reported generated files, but some files do not exist on disk.",
                "repo_url": analysis.get("repo_url"),
                "repo_name": analysis.get("repo_name"),
                "project_type": analysis.get("project_type"),
                "components": components,
                "generated_files": generated_files,
                "missing_generated_files": missing_generated_files,
                "skipped_files": skipped_files,
                "existing_files": existing_files,
                "analysis": analysis,
                "recommendations": [
                    "Fix DockerAgent path resolution before publishing generated files to GitHub.",
                ],
            }

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

    def _select_deployable_components(
        self,
        repo_path: Path,
        components: list[dict[str, Any]],
        primary_component: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not components and primary_component:
            components = [primary_component]

        if not components:
            return []

        if primary_component:
            primary = dict(primary_component)

            if self._component_has_component_dir(repo_path, primary):
                primary_path = str(primary.get("component_path") or ".").strip("/")
                primary_type = primary.get("type")

                if primary_type == "fullstack" and primary_path in {"", "."}:
                    return [primary]

        deployable: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        package_managed_components = [
            component
            for component in components
            if component.get("package_file")
        ]

        for component in components:
            if self._is_nested_static_component(component, package_managed_components):
                continue

            if not self._component_has_component_dir(repo_path, component):
                continue

            key = self._component_identity(component)

            if key in seen_keys:
                continue

            seen_keys.add(key)
            deployable.append(component)

        return sorted(
            deployable,
            key=lambda component: (
                self._component_priority(component),
                int(component.get("confidence") or 0),
            ),
            reverse=True,
        )

    def _component_has_component_dir(self, repo_path: Path, component: dict[str, Any]) -> bool:
        try:
            component_dir = self._get_component_dir(repo_path, component)
            return component_dir.exists() and component_dir.is_dir()
        except Exception:
            return False

    def _is_nested_static_component(
        self,
        component: dict[str, Any],
        package_managed_components: list[dict[str, Any]],
    ) -> bool:
        component_type = component.get("type")
        framework = (component.get("framework") or "").lower()
        package_file = component.get("package_file")

        if package_file:
            return False

        if component_type != "frontend":
            return False

        if "static" not in framework:
            return False

        component_path = str(component.get("component_path") or ".").strip("/")

        for parent in package_managed_components:
            parent_path = str(parent.get("component_path") or ".").strip("/")

            if component_path in {"", "."}:
                continue

            if parent_path in {"", "."}:
                return True

            if component_path.startswith(parent_path + "/"):
                return True

        return False

    def _component_priority(self, component: dict[str, Any]) -> int:
        component_type = component.get("type")

        if component_type == "fullstack":
            return 4

        if component_type == "backend":
            return 3

        if component_type == "frontend":
            return 2

        return 1

    def _component_identity(self, component: dict[str, Any]) -> str:
        return "|".join(
            [
                str(component.get("name") or ""),
                str(component.get("type") or ""),
                str(component.get("component_path") or ""),
                str(component.get("package_file") or ""),
            ]
        )

    def _get_component_dir(self, repo_path: Path, component: dict[str, Any]) -> Path:
        component_path = component.get("component_path")

        if component_path:
            return self._path_inside_repo(repo_path, component_path)

        package_file = component.get("package_file")

        if package_file:
            return self._path_inside_repo(repo_path, package_file).parent

        component_name = component.get("name")

        if component_name and (repo_path / str(component_name)).exists():
            return repo_path / str(component_name)

        if component.get("type") in {"frontend", "backend", "fullstack"}:
            return repo_path

        raise RuntimeError(
            f"Component {component.get('name')} has no component_path or package_file."
        )

    def _path_inside_repo(self, repo_path: Path, raw_path: str | Path) -> Path:
        path = Path(raw_path)

        if path.is_absolute():
            return path

        repo_text = repo_path.as_posix().rstrip("/")
        path_text = path.as_posix()

        if path_text == repo_text or path_text.startswith(repo_text + "/"):
            return path

        return repo_path / path

    def _file_record(
        self,
        repo_path: Path,
        path: Path,
        file_type: str,
        component: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "path": str(path),
            "relative_path": self._relative_path(repo_path, path),
            "type": file_type,
        }

        if component:
            record["component"] = component.get("name")
            record["component_path"] = component.get("component_path")

        return record

    def _generate_dockerfile(self, component: dict[str, Any], component_dir: Path) -> str:
        language = (component.get("language") or "").lower()
        framework = (component.get("framework") or "").lower()

        if "python" in language:
            return self._generate_python_dockerfile(component, component_dir)

        if "javascript" in language or "typescript" in language:
            if framework == "next.js":
                return self._generate_nextjs_dockerfile(component)

            if framework in ["react", "vue.js", "angular", "vite", "svelte", "static frontend"]:
                if component.get("package_file"):
                    return self._generate_frontend_static_dockerfile(component)

                return self._generate_plain_static_dockerfile(component)

            return self._generate_node_dockerfile(component)

        if "html" in language or "static" in language:
            return self._generate_plain_static_dockerfile(component)

        if "java" in language:
            return self._generate_java_dockerfile(component)

        if "go" in language:
            return self._generate_go_dockerfile(component)

        if "php" in language:
            return self._generate_php_dockerfile(component)

        if "ruby" in language:
            return self._generate_ruby_dockerfile(component)

        if ".net" in language or "c#" in language:
            return self._generate_dotnet_dockerfile(component)

        if "rust" in language:
            return self._generate_rust_dockerfile(component)

        return self._generate_generic_dockerfile(component)

    def _generate_python_dockerfile(self, component: dict[str, Any], component_dir: Path) -> str:
        port = component.get("port") or 8000
        framework = component.get("framework") or "Python"
        start_command = component.get("start_command") or "python main.py"
        health_path = component.get("health_path") or "/health"

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
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:{port}{health_path}')" || exit 1

CMD ["sh", "-c", "{start_command}"]
"""

    def _generate_node_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 3000
        framework = component.get("framework") or "Node.js"
        start_command = component.get("start_command") or "npm start"
        health_path = component.get("health_path") or "/"
        node_major = self._node_major_version(component.get("runtime"))

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: {framework}

FROM node:{node_major}-alpine

ENV NODE_ENV=production
ENV PORT={port}

WORKDIR /app

COPY package*.json ./

RUN if [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi

COPY . .

RUN chown -R node:node /app

USER node

EXPOSE {port}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
    CMD node -e "fetch('http://127.0.0.1:{port}{health_path}').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["sh", "-c", "{start_command}"]
"""

    def _generate_frontend_static_dockerfile(self, component: dict[str, Any]) -> str:
        framework = component.get("framework") or "Frontend"
        build_command = component.get("build_command") or "npm run build"
        output_dir = self._frontend_output_dir(component)

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: {framework}

FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./

RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .

RUN {build_command}

FROM nginx:alpine

COPY --from=build /app/{output_dir} /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
    CMD wget -qO- http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
"""

    def _generate_plain_static_dockerfile(self, component: dict[str, Any]) -> str:
        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: {component.get("framework") or "Static frontend"}

FROM nginx:alpine

COPY . /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
    CMD wget -qO- http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
"""

    def _generate_nextjs_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 3000
        build_command = component.get("build_command") or "npm run build"
        start_command = component.get("start_command") or "npm start"
        health_path = component.get("health_path") or "/"
        node_major = self._node_major_version(component.get("runtime"))

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: Next.js

FROM node:{node_major}-alpine

ENV NODE_ENV=production
ENV PORT={port}

WORKDIR /app

COPY package*.json ./

RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .

RUN {build_command}

RUN chown -R node:node /app

USER node

EXPOSE {port}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
    CMD node -e "fetch('http://127.0.0.1:{port}{health_path}').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["sh", "-c", "{start_command}"]
"""

    def _generate_java_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 8080
        build_command = component.get("build_command") or "mvn clean package"
        start_command = component.get("start_command") or "java -jar app.jar"
        health_path = component.get("health_path") or "/actuator/health"

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

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \\
    CMD curl -fsS http://127.0.0.1:{port}{health_path} || exit 1

CMD ["sh", "-c", "{start_command}"]
"""

    def _generate_go_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 8080
        health_path = component.get("health_path") or "/health"

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: {component.get("framework") or "Go"}

FROM golang:1.23-alpine AS build

WORKDIR /app

COPY go.mod go.sum* ./
RUN go mod download

COPY . .
RUN go build -o /app/bin/app .

FROM alpine:3.20

WORKDIR /app

COPY --from=build /app/bin/app ./app

EXPOSE {port}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
    CMD wget -qO- http://127.0.0.1:{port}{health_path} || exit 1

CMD ["./app"]
"""

    def _generate_php_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 8000
        start_command = component.get("start_command") or "php -S 0.0.0.0:8000 -t public"

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: {component.get("framework") or "PHP"}

FROM php:8.3-cli

WORKDIR /app

COPY . .

EXPOSE {port}

CMD ["sh", "-c", "{start_command}"]
"""

    def _generate_ruby_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 3000
        start_command = component.get("start_command") or "ruby app.rb -o 0.0.0.0"

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: {component.get("framework") or "Ruby"}

FROM ruby:3.3-slim

WORKDIR /app

COPY Gemfile Gemfile.lock* ./

RUN bundle install

COPY . .

EXPOSE {port}

CMD ["sh", "-c", "{start_command}"]
"""

    def _generate_dotnet_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 8080
        start_command = component.get("start_command") or "dotnet out/*.dll"

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: {component.get("framework") or ".NET"}

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build

WORKDIR /src

COPY . .

RUN dotnet publish -c Release -o /app/out

FROM mcr.microsoft.com/dotnet/aspnet:8.0

WORKDIR /app

COPY --from=build /app/out ./out

ENV ASPNETCORE_URLS=http://0.0.0.0:{port}

EXPOSE {port}

CMD ["sh", "-c", "{start_command}"]
"""

    def _generate_rust_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 8000

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# Framework: {component.get("framework") or "Rust"}

FROM rust:1.80 AS build

WORKDIR /app

COPY . .

RUN cargo build --release

FROM debian:bookworm-slim

WORKDIR /app

COPY --from=build /app/target/release/* /app/app

EXPOSE {port}

CMD ["/app/app"]
"""

    def _generate_generic_dockerfile(self, component: dict[str, Any]) -> str:
        port = component.get("port") or 8080

        return f"""# Generated by CloudMind
# Component: {component.get("name")}
# WARNING: CloudMind could not confidently detect this component runtime.

FROM alpine:3.20

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
            "!.env.example",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".DS_Store",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            "logs",
            "*.log",
            "coverage",
            ".coverage",
            ".cache",
            "tmp",
            "temp",
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
                    ".nuxt",
                    ".output",
                    ".turbo",
                    "npm-debug.log",
                    "yarn-error.log",
                    "pnpm-debug.log",
                ]
            )

        if "java" in language:
            common.extend(
                [
                    "target",
                    ".gradle",
                    "build",
                ]
            )

        if "go" in language:
            common.extend(
                [
                    "bin",
                    "*.test",
                ]
            )

        if "rust" in language:
            common.extend(
                [
                    "target",
                ]
            )

        return "\n".join(dict.fromkeys(common)) + "\n"

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
                "relative_path": self._relative_path(repo_path, existing_compose),
                "type": "compose",
            }

        compose_path = repo_path / "compose.yml"
        compose_content = self._build_compose_content(repo_path, components)
        compose_path.write_text(compose_content, encoding="utf-8")

        return {
            "status": "generated",
            "path": str(compose_path),
            "relative_path": self._relative_path(repo_path, compose_path),
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

            component_dir = self._get_component_dir(repo_path, component)
            context = self._relative_path(repo_path, component_dir)
            context_value = "." if context in {"", "."} else f"./{context}"

            host_port = component.get("port") or self._runtime_container_port(component)
            container_port = self._runtime_container_port(component)

            lines.extend(
                [
                    f"  {service_name}:",
                    "    build:",
                    f"      context: {context_value}",
                    "      dockerfile: Dockerfile",
                    f"    container_name: cloudmind-{service_name}",
                    "    ports:",
                    f'      - "{host_port}:{container_port}"',
                    "    restart: unless-stopped",
                ]
            )

            if component.get("health_path"):
                lines.extend(
                    [
                        "    environment:",
                        f'      PORT: "{container_port}"',
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

        if component_type == "frontend" and framework in [
            "react",
            "vue.js",
            "angular",
            "vite",
            "svelte",
            "static frontend",
        ]:
            if component.get("package_file"):
                return 80

            return 80

        return component.get("port") or 8080

    def _node_major_version(self, runtime: str | None) -> str:
        if not runtime:
            return "22"

        runtime = str(runtime).lower()

        for candidate in ["22", "21", "20", "18"]:
            if candidate in runtime:
                return candidate

        return "22"

    def _frontend_output_dir(self, component: dict[str, Any]) -> str:
        framework = (component.get("framework") or "").lower()

        if framework in {"vite", "react", "vue.js", "svelte"}:
            return "dist"

        if framework == "angular":
            return "dist"

        return "dist"

    def _relative_path(self, repo_path: Path, path: Path) -> str:
        try:
            relative = path.relative_to(repo_path)
            return relative.as_posix() or "."
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