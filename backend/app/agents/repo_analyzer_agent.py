import json
import re
from pathlib import Path
from typing import Any

from app.tools.git_tools import clone_repository, sanitize_repo_name


IGNORED_DIRS = {
    ".git",
    ".github",
    ".agents",
    ".claude",
    ".copier",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    ".idea",
    ".vscode",
    "docs",
    "docs_src",
    "doc",
    "tests",
    "test",
    "img",
    ".pytest_cache",
    ".mypy_cache",
}


IMPORTANT_FILE_NAMES = {
    "README.md",
    "readme.md",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "Pipfile",
    "pom.xml",
    "build.gradle",
    "go.mod",
    "composer.json",
    "pubspec.yaml",
    "Dockerfile",
    ".dockerignore",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "Chart.yaml",
}


class RepositoryAnalyzerAgent:
    """
    Phase 2 agent.

    It clones a Git repository, scans important files,
    detects languages/frameworks, identifies components,
    checks DevOps readiness, and returns an architecture summary.
    """

    def analyze(self, repo_url: str, branch: str | None = None) -> dict[str, Any]:
        repo_path = clone_repository(repo_url=repo_url, branch=branch)
        files = self._collect_files(repo_path)

        important_files = self._find_important_files(files)
        detected_languages = self._detect_languages(files)
        detected_frameworks = self._detect_frameworks(repo_path, files)
        components = self._detect_components(repo_path, files)
        missing_devops_files = self._detect_missing_devops_files(files)
        project_type = self._detect_project_type(components)
        recommendations = self._generate_recommendations(
            components=components,
            missing_devops_files=missing_devops_files,
        )

        return {
            "repo_url": repo_url,
            "repo_name": sanitize_repo_name(repo_url),
            "status": "analyzed",
            "project_type": project_type,
            "detected_languages": detected_languages,
            "detected_frameworks": detected_frameworks,
            "components": components,
            "important_files": important_files,
            "missing_devops_files": missing_devops_files,
            "tree_preview": self._generate_tree_preview(repo_path),
            "recommendations": recommendations,
            "metadata": {
                "local_path": str(repo_path),
                "files_scanned": len(files),
                "branch": branch or "default",
            },
        }

    def _collect_files(self, repo_path: Path) -> list[Path]:
        files: list[Path] = []

        for path in repo_path.rglob("*"):
            if not path.is_file():
                continue

            if self._should_ignore_path(path, repo_path):
                continue

            files.append(path)

        return files

    def _should_ignore_path(self, path: Path, repo_path: Path) -> bool:
        relative_parts = path.relative_to(repo_path).parts
        return any(part in IGNORED_DIRS for part in relative_parts)

    def _find_important_files(self, files: list[Path]) -> list[str]:
        result = []

        for file in files:
            if file.name in IMPORTANT_FILE_NAMES:
                result.append(str(file))

        return result

    def _detect_languages(self, files: list[Path]) -> list[str]:
        languages = set()
        file_names = {file.name for file in files}
        suffixes = {file.suffix.lower() for file in files}

        if "package.json" in file_names:
            languages.add("JavaScript/TypeScript")

        if "requirements.txt" in file_names or "pyproject.toml" in file_names or ".py" in suffixes:
            languages.add("Python")

        if "pom.xml" in file_names or "build.gradle" in file_names or ".java" in suffixes:
            languages.add("Java")

        if "go.mod" in file_names or ".go" in suffixes:
            languages.add("Go")

        if "composer.json" in file_names or ".php" in suffixes:
            languages.add("PHP")

        if "pubspec.yaml" in file_names or ".dart" in suffixes:
            languages.add("Dart/Flutter")

        if ".csproj" in suffixes or ".cs" in suffixes:
            languages.add("C#/.NET")

        return sorted(languages)

    def _detect_frameworks(self, repo_path: Path, files: list[Path]) -> list[str]:
        frameworks = set()

        package_json_files = self._find_files(files, "package.json")

        for package_json in package_json_files:
            package_data = self._read_json(package_json)

            dependencies = {}
            dependencies.update(package_data.get("dependencies", {}))
            dependencies.update(package_data.get("devDependencies", {}))

            dep_names = set(dependencies.keys())

            if "react" in dep_names:
                frameworks.add("React")

            if "vite" in dep_names:
                frameworks.add("Vite")

            if "next" in dep_names:
                frameworks.add("Next.js")

            if "express" in dep_names:
                frameworks.add("Express.js")

            if "@nestjs/core" in dep_names:
                frameworks.add("NestJS")

            if "vue" in dep_names:
                frameworks.add("Vue.js")

            if "@angular/core" in dep_names:
                frameworks.add("Angular")

        python_dependency_files: list[Path] = []
        python_dependency_files.extend(self._find_files(files, "requirements.txt"))
        python_dependency_files.extend(self._find_files(files, "pyproject.toml"))
        python_dependency_files.extend(self._find_files(files, "Pipfile"))

        python_content = ""

        for dependency_file in python_dependency_files:
            python_content += "\n" + self._safe_read(dependency_file).lower()

        if self._dependency_exists(python_content, "fastapi"):
            frameworks.add("FastAPI")

        if self._dependency_exists(python_content, "flask"):
            frameworks.add("Flask")

        if self._dependency_exists(python_content, "django"):
            frameworks.add("Django")

        if self._dependency_exists(python_content, "streamlit"):
            frameworks.add("Streamlit")

        pom_files = self._find_files(files, "pom.xml")
        gradle_files = self._find_files(files, "build.gradle")

        java_content = ""

        for pom in pom_files:
            java_content += "\n" + self._safe_read(pom).lower()

        for gradle in gradle_files:
            java_content += "\n" + self._safe_read(gradle).lower()

        if "spring-boot" in java_content:
            frameworks.add("Spring Boot")

        repo_name = repo_path.name.lower()
        if repo_name == "fastapi" and "FastAPI" in frameworks:
            frameworks.discard("Flask")

        return sorted(frameworks)

    def _detect_components(self, repo_path: Path, files: list[Path]) -> list[dict[str, Any]]:
        components: list[dict[str, Any]] = []

        package_json_files = self._find_files(files, "package.json")

        for package_json in package_json_files:
            package_data = self._read_json(package_json)

            dependencies = {}
            dependencies.update(package_data.get("dependencies", {}))
            dependencies.update(package_data.get("devDependencies", {}))

            scripts = package_data.get("scripts", {})
            dep_names = set(dependencies.keys())

            component_folder = package_json.parent
            component_name = component_folder.name

            if (
                "react" in dep_names
                or "next" in dep_names
                or "vue" in dep_names
                or "@angular/core" in dep_names
            ):
                framework = "Frontend JS"

                if "react" in dep_names:
                    framework = "React"

                if "next" in dep_names:
                    framework = "Next.js"

                if "vue" in dep_names:
                    framework = "Vue.js"

                if "@angular/core" in dep_names:
                    framework = "Angular"

                default_port = 5173 if "vite" in dep_names else 3000

                components.append(
                    {
                        "name": component_name if component_name != repo_path.name else "frontend",
                        "type": "frontend",
                        "language": "JavaScript/TypeScript",
                        "framework": framework,
                        "package_file": str(package_json),
                        "port": self._guess_port(component_folder, default=default_port),
                        "start_command": scripts.get("dev") or scripts.get("start") or "npm run dev",
                        "build_command": scripts.get("build", "npm run build"),
                    }
                )

            if "express" in dep_names or "@nestjs/core" in dep_names:
                framework = "Express.js" if "express" in dep_names else "NestJS"

                components.append(
                    {
                        "name": component_name if component_name != repo_path.name else "backend",
                        "type": "backend",
                        "language": "JavaScript/TypeScript",
                        "framework": framework,
                        "package_file": str(package_json),
                        "port": self._guess_port(component_folder, default=3000),
                        "start_command": scripts.get("start", "npm start"),
                        "build_command": scripts.get("build"),
                    }
                )

        python_dependency_files: list[Path] = []
        python_dependency_files.extend(self._find_files(files, "requirements.txt"))
        python_dependency_files.extend(self._find_files(files, "pyproject.toml"))
        python_dependency_files.extend(self._find_files(files, "Pipfile"))

        for dependency_file in python_dependency_files:
            python_content = self._safe_read(dependency_file).lower()

            component_folder = dependency_file.parent
            component_name = component_folder.name

            has_fastapi = self._dependency_exists(python_content, "fastapi")
            has_flask = self._dependency_exists(python_content, "flask")
            has_django = self._dependency_exists(python_content, "django")
            has_streamlit = self._dependency_exists(python_content, "streamlit")

            repo_name = repo_path.name.lower()
            if repo_name == "fastapi" and has_fastapi:
                has_flask = False

            if has_fastapi or has_flask or has_django or has_streamlit:
                framework = "Python Backend"
                port = 8000
                start_command = "python main.py"

                if has_fastapi:
                    framework = "FastAPI"
                    start_command = self._detect_fastapi_start_command(component_folder, default_port=8000)

                elif has_flask:
                    framework = "Flask"
                    port = 5000
                    start_command = "flask run --host=0.0.0.0"

                elif has_django:
                    framework = "Django"
                    port = 8000
                    start_command = "python manage.py runserver 0.0.0.0:8000"

                elif has_streamlit:
                    framework = "Streamlit"
                    port = 8501
                    start_command = "streamlit run app.py --server.port=8501 --server.address=0.0.0.0"

                components.append(
                    {
                        "name": component_name if component_name != repo_path.name else "backend",
                        "type": "backend",
                        "language": "Python",
                        "framework": framework,
                        "package_file": str(dependency_file),
                        "port": self._guess_port(component_folder, default=port),
                        "start_command": start_command,
                        "build_command": None,
                    }
                )

        pom_files = self._find_files(files, "pom.xml")
        gradle_files = self._find_files(files, "build.gradle")

        for build_file in pom_files + gradle_files:
            java_content = self._safe_read(build_file).lower()

            component_folder = build_file.parent
            component_name = component_folder.name

            if "spring-boot" in java_content:
                components.append(
                    {
                        "name": component_name if component_name != repo_path.name else "backend",
                        "type": "backend",
                        "language": "Java",
                        "framework": "Spring Boot",
                        "package_file": str(build_file),
                        "port": self._guess_port(component_folder, default=8080),
                        "start_command": "java -jar app.jar",
                        "build_command": "mvn clean package" if build_file.name == "pom.xml" else "gradle build",
                    }
                )

        return components

    def _detect_project_type(self, components: list[dict[str, Any]]) -> str:
        component_types = {component["type"] for component in components}

        if "frontend" in component_types and "backend" in component_types:
            return "fullstack"

        if "backend" in component_types:
            return "backend"

        if "frontend" in component_types:
            return "frontend"

        return "unknown"

    def _detect_missing_devops_files(self, files: list[Path]) -> list[str]:
        file_names = {file.name for file in files}
        relative_paths = {str(file).replace("\\", "/") for file in files}

        missing = []

        if "Dockerfile" not in file_names:
            missing.append("Dockerfile")

        if ".dockerignore" not in file_names:
            missing.append(".dockerignore")

        compose_file_names = {
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
        }

        if not file_names.intersection(compose_file_names):
            missing.append("Docker Compose file")

        has_k8s = any(
            "/k8s/" in path
            or "/kubernetes/" in path
            or path.startswith("k8s/")
            or path.startswith("kubernetes/")
            for path in relative_paths
        )

        if not has_k8s:
            missing.append("Kubernetes manifests")

        has_helm = "Chart.yaml" in file_names

        if not has_helm:
            missing.append("Helm chart")

        return missing

    def _generate_recommendations(
        self,
        components: list[dict[str, Any]],
        missing_devops_files: list[str],
    ) -> list[str]:
        recommendations = []

        if not components:
            recommendations.append(
                "CloudMind could not confidently detect the application architecture. "
                "Add README, dependency files, or standard project structure."
            )

        if "Dockerfile" in missing_devops_files:
            recommendations.append("Generate a Dockerfile based on the detected framework.")

        if ".dockerignore" in missing_devops_files:
            recommendations.append("Add a .dockerignore file to avoid copying unnecessary files into the image.")

        if "Docker Compose file" in missing_devops_files:
            recommendations.append("Generate a Docker Compose file for local multi-container testing.")

        if "Kubernetes manifests" in missing_devops_files:
            recommendations.append(
                "Generate Kubernetes Deployment, Service, ConfigMap, Secret template, and Ingress files."
            )

        if "Helm chart" in missing_devops_files:
            recommendations.append(
                "Later, package the Kubernetes manifests into a Helm chart for reusable deployments."
            )

        for component in components:
            if not component.get("port"):
                recommendations.append(f"Define an explicit port for the {component['name']} component.")

        return recommendations

    def _generate_tree_preview(self, repo_path: Path, max_items: int = 80) -> list[str]:
        preview = []

        for path in sorted(repo_path.rglob("*")):
            if self._should_ignore_path(path, repo_path):
                continue

            relative = path.relative_to(repo_path)
            prefix = "📁 " if path.is_dir() else "📄 "
            preview.append(prefix + str(relative).replace("\\", "/"))

            if len(preview) >= max_items:
                break

        return preview

    def _detect_fastapi_start_command(self, component_folder: Path, default_port: int = 8000) -> str:
        """
        Detect the best Uvicorn command for a FastAPI app.

        Examples:
        - main.py with app = FastAPI()       -> uvicorn main:app
        - app/main.py with app = FastAPI()   -> uvicorn app.main:app
        - src/main.py with app = FastAPI()   -> uvicorn src.main:app
        """
        candidates = [
            component_folder / "main.py",
            component_folder / "app.py",
            component_folder / "app" / "main.py",
            component_folder / "src" / "main.py",
        ]

        for candidate in candidates:
            if not candidate.exists():
                continue

            content = self._safe_read(candidate).lower()

            if "fastapi(" in content and "app" in content:
                module_path = candidate.relative_to(component_folder).with_suffix("")
                module_name = ".".join(module_path.parts)

                return f"uvicorn {module_name}:app --host 0.0.0.0 --port {default_port}"

        return f"uvicorn main:app --host 0.0.0.0 --port {default_port}"

    def _find_file(self, files: list[Path], file_name: str) -> Path | None:
        for file in files:
            if file.name == file_name:
                return file

        return None

    def _find_files(self, files: list[Path], file_name: str) -> list[Path]:
        return [file for file in files if file.name == file_name]

    def _safe_read(self, file_path: Path, max_chars: int = 200_000) -> str:
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        except Exception:
            return ""

    def _read_json(self, file_path: Path) -> dict[str, Any]:
        try:
            return json.loads(self._safe_read(file_path))
        except Exception:
            return {}

    def _dependency_exists(self, content: str, package_name: str) -> bool:
        content = content.lower()
        package_name = package_name.lower()

        patterns = [
            rf'["\']{re.escape(package_name)}(?:\[.*?\])?(?:[=<>~!;\s,"\'])',
            rf"^{re.escape(package_name)}(?:\[.*?\])?[=<>~!\s]",
            rf"\n{re.escape(package_name)}(?:\[.*?\])?[=<>~!\s]",
            rf"{re.escape(package_name)}\s*=",
        ]

        return any(re.search(pattern, content) for pattern in patterns)

    def _guess_port(self, search_path: Path, default: int) -> int:
        content_parts = []

        base_path = search_path if search_path.is_dir() else search_path.parent

        for file_name in [
            "package.json",
            "main.py",
            "app.py",
            "server.js",
            "index.js",
            "vite.config.ts",
            "vite.config.js",
            "application.properties",
            "application.yml",
        ]:
            for path in base_path.rglob(file_name):
                relative_parts = path.relative_to(base_path).parts

                if any(part in IGNORED_DIRS for part in relative_parts):
                    continue

                content_parts.append(self._safe_read(path, max_chars=50_000))

        content = "\n".join(content_parts)

        common_ports = [5173, 3000, 8000, 8080, 5000, 4000, 8501]

        for port in common_ports:
            if str(port) in content:
                return port

        return default