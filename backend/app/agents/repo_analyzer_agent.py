import json
import re
from collections import Counter, defaultdict
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
    ".nuxt",
    ".output",
    ".idea",
    ".vscode",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".turbo",
    ".cache",
    "target",
    "bin",
    "obj",
    "vendor",
}

LOW_VALUE_DIRS_FOR_PREVIEW = {
    "docs",
    "docs_src",
    "doc",
    "tests",
    "test",
    "img",
    "images",
    "assets",
}

IMPORTANT_FILE_NAMES = {
    "README.md",
    "readme.md",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "requirements.txt",
    "pyproject.toml",
    "Pipfile",
    "poetry.lock",
    "uv.lock",
    "environment.yml",
    "conda.yml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "go.mod",
    "go.sum",
    "composer.json",
    "Gemfile",
    "Cargo.toml",
    "pubspec.yaml",
    "Dockerfile",
    ".dockerignore",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "Chart.yaml",
    "Makefile",
    "Procfile",
    "vercel.json",
    "netlify.toml",
    "railway.json",
    "fly.toml",
    "render.yaml",
}

SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".java",
    ".go",
    ".php",
    ".rb",
    ".cs",
    ".fs",
    ".rs",
    ".dart",
    ".kt",
    ".kts",
    ".swift",
    ".html",
    ".css",
    ".vue",
    ".svelte",
}

LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".js": "JavaScript/TypeScript",
    ".jsx": "JavaScript/TypeScript",
    ".ts": "JavaScript/TypeScript",
    ".tsx": "JavaScript/TypeScript",
    ".mjs": "JavaScript/TypeScript",
    ".cjs": "JavaScript/TypeScript",
    ".vue": "JavaScript/TypeScript",
    ".svelte": "JavaScript/TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".php": "PHP",
    ".rb": "Ruby",
    ".cs": "C#/.NET",
    ".fs": "F#/.NET",
    ".rs": "Rust",
    ".dart": "Dart/Flutter",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".html": "HTML/CSS/Static",
    ".css": "HTML/CSS/Static",
}

JS_BACKEND_ENTRY_NAMES = {
    "server.js",
    "server.ts",
    "server.mjs",
    "server.cjs",
    "index.js",
    "index.ts",
    "index.mjs",
    "index.cjs",
    "app.js",
    "app.ts",
    "main.js",
    "main.ts",
}

PYTHON_ENTRY_NAMES = {
    "main.py",
    "app.py",
    "server.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
}

STATIC_FRONTEND_ENTRY_NAMES = {
    "index.html",
}


class RepositoryAnalyzerAgent:
    """
    Smart evidence-based repository analyzer.

    Design goal:
    - No repository-specific hardcoding.
    - Detect stacks from manifests, scripts, folder structure, source-code imports,
      common entrypoints, and runtime signals.
    - Return confidence and evidence so the rest of CloudMind can make safer decisions.
    """

    def analyze(self, repo_url: str, branch: str | None = None) -> dict[str, Any]:
        repo_path = clone_repository(repo_url=repo_url, branch=branch)
        files = self._collect_files(repo_path)

        important_files = self._find_important_files(repo_path, files)
        file_inventory = self._build_file_inventory(repo_path, files)

        detected_languages = self._detect_languages(files)
        detected_frameworks = self._detect_frameworks(repo_path, files)

        components = self._detect_components(repo_path, files)
        components = self._deduplicate_components(components)

        missing_devops_files = self._detect_missing_devops_files(repo_path, files)
        project_type = self._detect_project_type(components, files)
        primary_component = self._select_primary_component(components)

        recommendations = self._generate_recommendations(
            components=components,
            missing_devops_files=missing_devops_files,
            primary_component=primary_component,
            file_inventory=file_inventory,
        )

        return {
            "repo_url": repo_url,
            "repo_name": sanitize_repo_name(repo_url),
            "status": "analyzed",
            "project_type": project_type,
            "detected_language": primary_component.get("language") if primary_component else self._first_or_none(detected_languages),
            "detected_framework": primary_component.get("framework") if primary_component else self._first_or_none(detected_frameworks),
            "port": primary_component.get("port") if primary_component else None,
            "start_command": primary_component.get("start_command") if primary_component else None,
            "build_command": primary_component.get("build_command") if primary_component else None,
            "health_path": primary_component.get("health_path") if primary_component else None,
            "detected_languages": detected_languages,
            "detected_frameworks": detected_frameworks,
            "components": components,
            "primary_component": primary_component,
            "important_files": important_files,
            "missing_devops_files": missing_devops_files,
            "file_inventory": file_inventory,
            "tree_preview": self._generate_tree_preview(repo_path),
            "recommendations": recommendations,
            "metadata": {
                "local_path": str(repo_path),
                "files_scanned": len(files),
                "branch": branch or "default",
                "analyzer_version": "phase_20c_smart_evidence_analyzer",
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
        try:
            relative_parts = path.relative_to(repo_path).parts
        except ValueError:
            return True

        return any(part in IGNORED_DIRS for part in relative_parts)

    def _find_important_files(self, repo_path: Path, files: list[Path]) -> list[str]:
        result = []

        for file in files:
            if file.name in IMPORTANT_FILE_NAMES:
                result.append(self._relative(repo_path, file))
                continue

            if file.suffix.lower() in {".csproj", ".fsproj", ".sln"}:
                result.append(self._relative(repo_path, file))
                continue

        return sorted(result)

    def _build_file_inventory(self, repo_path: Path, files: list[Path]) -> dict[str, Any]:
        suffix_counts = Counter(file.suffix.lower() or "[no extension]" for file in files)
        top_level_dirs = Counter()

        for file in files:
            relative = file.relative_to(repo_path)
            if len(relative.parts) > 1:
                top_level_dirs[relative.parts[0]] += 1

        return {
            "total_files": len(files),
            "source_files": len([file for file in files if file.suffix.lower() in SOURCE_SUFFIXES]),
            "suffix_counts": dict(suffix_counts.most_common(20)),
            "top_level_dirs": dict(top_level_dirs.most_common(20)),
            "has_readme": any(file.name.lower() == "readme.md" for file in files),
        }

    def _detect_languages(self, files: list[Path]) -> list[str]:
        languages = set()
        file_names = {file.name for file in files}
        suffixes = {file.suffix.lower() for file in files}

        for suffix in suffixes:
            language = LANGUAGE_BY_SUFFIX.get(suffix)
            if language:
                languages.add(language)

        manifest_language_signals = {
            "package.json": "JavaScript/TypeScript",
            "requirements.txt": "Python",
            "pyproject.toml": "Python",
            "Pipfile": "Python",
            "poetry.lock": "Python",
            "pom.xml": "Java",
            "build.gradle": "Java",
            "build.gradle.kts": "Java/Kotlin",
            "go.mod": "Go",
            "composer.json": "PHP",
            "Gemfile": "Ruby",
            "Cargo.toml": "Rust",
            "pubspec.yaml": "Dart/Flutter",
        }

        for file_name, language in manifest_language_signals.items():
            if file_name in file_names:
                languages.add(language)

        if any(file.suffix.lower() in {".csproj", ".fsproj", ".sln"} for file in files):
            languages.add("C#/.NET")

        return sorted(languages)

    def _detect_frameworks(self, repo_path: Path, files: list[Path]) -> list[str]:
        frameworks = set()

        for component in self._detect_components(repo_path, files):
            framework = component.get("framework")
            if framework and framework != "Unknown":
                frameworks.add(framework)

        return sorted(frameworks)

    def _detect_components(self, repo_path: Path, files: list[Path]) -> list[dict[str, Any]]:
        components: list[dict[str, Any]] = []

        components.extend(self._detect_javascript_components(repo_path, files))
        components.extend(self._detect_python_components(repo_path, files))
        components.extend(self._detect_java_components(repo_path, files))
        components.extend(self._detect_go_components(repo_path, files))
        components.extend(self._detect_php_components(repo_path, files))
        components.extend(self._detect_ruby_components(repo_path, files))
        components.extend(self._detect_dotnet_components(repo_path, files))
        components.extend(self._detect_rust_components(repo_path, files))
        components.extend(self._detect_flutter_components(repo_path, files))
        components.extend(self._detect_static_frontend_components(repo_path, files))

        return components

    def _detect_javascript_components(self, repo_path: Path, files: list[Path]) -> list[dict[str, Any]]:
        components: list[dict[str, Any]] = []
        package_json_files = self._find_files(files, "package.json")

        for package_json in package_json_files:
            package_data = self._read_json(package_json)
            component_folder = package_json.parent
            component_name = self._component_name(repo_path, component_folder)

            dependencies = self._package_dependencies(package_data)
            scripts = package_data.get("scripts", {}) if isinstance(package_data.get("scripts"), dict) else {}

            dep_names = set(dependencies.keys())
            script_text = " ".join(str(value) for value in scripts.values()).lower()
            source_text = self._read_relevant_source_text(
                component_folder,
                suffixes={".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".html"},
                max_files=80,
                max_chars_per_file=15_000,
            ).lower()

            framework_scores = self._score_js_frameworks(
                dep_names=dep_names,
                scripts=scripts,
                script_text=script_text,
                source_text=source_text,
                component_folder=component_folder,
            )

            sorted_frameworks = sorted(
                framework_scores.items(),
                key=lambda item: item[1]["score"],
                reverse=True,
            )

            primary_framework = sorted_frameworks[0][0] if sorted_frameworks else None
            primary_score = sorted_frameworks[0][1]["score"] if sorted_frameworks else 0
            evidence = sorted_frameworks[0][1]["evidence"] if sorted_frameworks else []

            has_frontend_files = self._has_static_frontend(component_folder)
            has_backend_entry = self._has_js_backend_entry(component_folder, source_text)
            has_server_signal = self._has_js_server_signal(source_text, dep_names)

            package_type = self._classify_js_component(
                primary_framework=primary_framework,
                dep_names=dep_names,
                scripts=scripts,
                source_text=source_text,
                has_frontend_files=has_frontend_files,
                has_backend_entry=has_backend_entry,
                has_server_signal=has_server_signal,
            )

            if not primary_framework and package_type != "unknown":
                primary_framework = self._fallback_js_framework_name(
                    package_type=package_type,
                    source_text=source_text,
                    has_frontend_files=has_frontend_files,
                    has_server_signal=has_server_signal,
                )
                primary_score = 55
                evidence.append("Detected from scripts/source structure instead of dependencies")

            if package_type == "unknown":
                package_type = "backend" if scripts.get("start") else "unknown"

            if package_type == "unknown":
                continue

            default_port = self._default_js_port(
                framework=primary_framework,
                package_type=package_type,
                dep_names=dep_names,
            )

            start_command = self._select_js_start_command(
                scripts=scripts,
                package_type=package_type,
                framework=primary_framework,
            )
            build_command = self._select_js_build_command(scripts=scripts, package_type=package_type)
            health_path = self._detect_health_path(
                component_folder=component_folder,
                source_text=source_text,
                default="/api/status" if package_type in {"backend", "fullstack"} else "/",
            )

            components.append(
                {
                    "name": component_name,
                    "type": package_type,
                    "language": "JavaScript/TypeScript",
                    "framework": primary_framework or "JavaScript/Node.js",
                    "package_file": self._relative(repo_path, package_json),
                    "component_path": self._relative(repo_path, component_folder),
                    "port": self._guess_port(component_folder, default=default_port),
                    "start_command": start_command,
                    "build_command": build_command,
                    "health_path": health_path,
                    "confidence": min(100, primary_score or 50),
                    "evidence": evidence,
                    "runtime": self._detect_node_runtime(package_data),
                }
            )

        return components

    def _score_js_frameworks(
        self,
        dep_names: set[str],
        scripts: dict[str, Any],
        script_text: str,
        source_text: str,
        component_folder: Path,
    ) -> dict[str, dict[str, Any]]:
        scores: dict[str, dict[str, Any]] = defaultdict(lambda: {"score": 0, "evidence": []})

        def add(framework: str, points: int, evidence: str) -> None:
            scores[framework]["score"] += points
            scores[framework]["evidence"].append(evidence)

        dependency_frameworks = {
            "next": "Next.js",
            "react": "React",
            "vite": "Vite",
            "vue": "Vue.js",
            "@vue/cli-service": "Vue.js",
            "@angular/core": "Angular",
            "svelte": "Svelte",
            "@sveltejs/kit": "SvelteKit",
            "astro": "Astro",
            "@remix-run/node": "Remix",
            "nuxt": "Nuxt",
            "express": "Express.js",
            "fastify": "Fastify",
            "koa": "Koa",
            "hapi": "Hapi",
            "@nestjs/core": "NestJS",
            "socket.io": "Socket.io",
        }

        for dependency, framework in dependency_frameworks.items():
            if dependency in dep_names:
                add(framework, 45, f"Dependency found: {dependency}")

        script_frameworks = {
            "next": "Next.js",
            "vite": "Vite",
            "vue-cli-service": "Vue.js",
            "ng serve": "Angular",
            "astro": "Astro",
            "remix": "Remix",
            "nuxt": "Nuxt",
            "svelte-kit": "SvelteKit",
            "node ": "Node.js native HTTP",
            "node --watch": "Node.js native HTTP",
            "tsx ": "Node.js/TypeScript",
            "ts-node": "Node.js/TypeScript",
            "nest": "NestJS",
        }

        for token, framework in script_frameworks.items():
            if token in script_text:
                add(framework, 20, f"Script contains: {token}")

        source_frameworks = {
            "createServer(": "Node.js native HTTP",
            "node:http": "Node.js native HTTP",
            "require('http')": "Node.js native HTTP",
            'require("http")': "Node.js native HTTP",
            "express(": "Express.js",
            "from 'express'": "Express.js",
            'from "express"': "Express.js",
            "fastify(": "Fastify",
            "@nestjs": "NestJS",
            "createApp(": "Vue.js",
            "new Vue(": "Vue.js",
            "ReactDOM": "React",
            "from 'react'": "React",
            'from "react"': "React",
            "use client": "Next.js",
        }

        for token, framework in source_frameworks.items():
            if token.lower() in source_text:
                add(framework, 30, f"Source contains: {token}")

        if (component_folder / "next.config.js").exists() or (component_folder / "next.config.mjs").exists():
            add("Next.js", 35, "Next config file found")

        if (component_folder / "vite.config.js").exists() or (component_folder / "vite.config.ts").exists():
            add("Vite", 35, "Vite config file found")

        if (component_folder / "angular.json").exists():
            add("Angular", 35, "angular.json found")

        if (component_folder / "frontend" / "index.html").exists() or (component_folder / "public" / "index.html").exists():
            add("Static frontend", 15, "Static frontend entrypoint found")

        return dict(scores)

    def _classify_js_component(
        self,
        primary_framework: str | None,
        dep_names: set[str],
        scripts: dict[str, Any],
        source_text: str,
        has_frontend_files: bool,
        has_backend_entry: bool,
        has_server_signal: bool,
    ) -> str:
        frontend_frameworks = {
            "React",
            "Vite",
            "Next.js",
            "Vue.js",
            "Angular",
            "Svelte",
            "SvelteKit",
            "Astro",
            "Remix",
            "Nuxt",
            "Static frontend",
        }

        backend_frameworks = {
            "Node.js native HTTP",
            "Express.js",
            "Fastify",
            "Koa",
            "Hapi",
            "NestJS",
            "Node.js/TypeScript",
        }

        if has_server_signal and has_frontend_files:
            return "fullstack"

        if primary_framework in {"Next.js", "Remix", "Nuxt", "SvelteKit"}:
            return "fullstack"

        if primary_framework in backend_frameworks or has_backend_entry or has_server_signal:
            return "backend"

        if primary_framework in frontend_frameworks or has_frontend_files:
            return "frontend"

        if scripts.get("start") and "node" in str(scripts.get("start")).lower():
            return "backend"

        if scripts.get("dev") and any(token in str(scripts.get("dev")).lower() for token in ["vite", "next", "nuxt", "astro"]):
            return "frontend"

        if dep_names:
            return "frontend"

        return "unknown"

    def _fallback_js_framework_name(
        self,
        package_type: str,
        source_text: str,
        has_frontend_files: bool,
        has_server_signal: bool,
    ) -> str:
        if has_server_signal and has_frontend_files:
            return "Node.js native HTTP + static frontend"

        if has_server_signal:
            return "Node.js native HTTP"

        if has_frontend_files:
            return "Static frontend"

        if package_type == "backend":
            return "Node.js"

        return "JavaScript/TypeScript"

    def _default_js_port(
        self,
        framework: str | None,
        package_type: str,
        dep_names: set[str],
    ) -> int:
        if framework == "Vite" or "vite" in dep_names:
            return 5173

        if framework == "Angular":
            return 4200

        if package_type in {"backend", "fullstack"}:
            return 3000

        return 3000

    def _select_js_start_command(
        self,
        scripts: dict[str, Any],
        package_type: str,
        framework: str | None,
    ) -> str:
        if package_type in {"backend", "fullstack"}:
            if scripts.get("start"):
                return "npm start"

            if scripts.get("preview"):
                return "npm run preview -- --host 0.0.0.0"

            if scripts.get("dev"):
                return "npm run dev"

            return "node server.js"

        if framework == "Vite" and scripts.get("preview"):
            return "npm run preview -- --host 0.0.0.0"

        if scripts.get("start"):
            return "npm start"

        if scripts.get("preview"):
            return "npm run preview -- --host 0.0.0.0"

        if scripts.get("dev"):
            return "npm run dev -- --host 0.0.0.0"

        return "npm start"

    def _select_js_build_command(self, scripts: dict[str, Any], package_type: str) -> str | None:
        if scripts.get("build"):
            return "npm run build"

        if package_type == "frontend":
            return "npm run build"

        return None

    def _detect_node_runtime(self, package_data: dict[str, Any]) -> str:
        engines = package_data.get("engines")

        if isinstance(engines, dict):
            node_version = engines.get("node")
            if node_version:
                return f"node {node_version}"

        return "node"

    def _has_static_frontend(self, folder: Path) -> bool:
        possible_roots = [
            folder,
            folder / "frontend",
            folder / "public",
            folder / "src",
            folder / "app",
            folder / "pages",
        ]

        for root in possible_roots:
            if not root.exists():
                continue

            if any((root / file_name).exists() for file_name in STATIC_FRONTEND_ENTRY_NAMES):
                return True

            if any(root.rglob("*.html")) and any(root.rglob("*.css")):
                return True

        return False

    def _has_js_backend_entry(self, folder: Path, source_text: str) -> bool:
        for entry_name in JS_BACKEND_ENTRY_NAMES:
            if (folder / entry_name).exists():
                return True

            if (folder / "backend" / entry_name).exists():
                return True

            if (folder / "server" / entry_name).exists():
                return True

            if (folder / "src" / entry_name).exists():
                return True

        return self._has_js_server_signal(source_text, set())

    def _has_js_server_signal(self, source_text: str, dep_names: set[str]) -> bool:
        server_dependencies = {
            "express",
            "fastify",
            "koa",
            "hapi",
            "@nestjs/core",
            "socket.io",
        }

        if dep_names.intersection(server_dependencies):
            return True

        server_tokens = [
            "createserver(",
            "node:http",
            "node:https",
            "server.listen(",
            ".listen(",
            "app.listen(",
            "fastify.listen",
        ]

        return any(token in source_text for token in server_tokens)

    def _detect_python_components(self, repo_path: Path, files: list[Path]) -> list[dict[str, Any]]:
        components: list[dict[str, Any]] = []
        dependency_files: list[Path] = []
        dependency_files.extend(self._find_files(files, "requirements.txt"))
        dependency_files.extend(self._find_files(files, "pyproject.toml"))
        dependency_files.extend(self._find_files(files, "Pipfile"))

        candidate_folders = {dependency_file.parent for dependency_file in dependency_files}

        for file in files:
            if file.suffix.lower() == ".py" and file.name in PYTHON_ENTRY_NAMES:
                candidate_folders.add(file.parent)

        for folder in sorted(candidate_folders):
            dependency_text = ""
            for file_name in ["requirements.txt", "pyproject.toml", "Pipfile"]:
                path = folder / file_name
                if path.exists():
                    dependency_text += "\n" + self._safe_read(path).lower()

            source_text = self._read_relevant_source_text(
                folder,
                suffixes={".py"},
                max_files=80,
                max_chars_per_file=15_000,
            ).lower()

            framework, confidence, evidence = self._detect_python_framework(
                dependency_text=dependency_text,
                source_text=source_text,
                folder=folder,
            )

            if not framework:
                continue

            default_port = self._default_python_port(framework)
            start_command = self._select_python_start_command(folder, framework, default_port)
            health_path = self._detect_health_path(folder, source_text, default="/health")

            components.append(
                {
                    "name": self._component_name(repo_path, folder),
                    "type": "backend" if framework != "Streamlit" else "frontend",
                    "language": "Python",
                    "framework": framework,
                    "package_file": self._python_package_file(repo_path, folder),
                    "component_path": self._relative(repo_path, folder),
                    "port": self._guess_port(folder, default=default_port),
                    "start_command": start_command,
                    "build_command": None,
                    "health_path": health_path,
                    "confidence": confidence,
                    "evidence": evidence,
                    "runtime": "python",
                }
            )

        return components

    def _detect_python_framework(
        self,
        dependency_text: str,
        source_text: str,
        folder: Path,
    ) -> tuple[str | None, int, list[str]]:
        signals = {
            "FastAPI": {
                "dependency_tokens": ["fastapi"],
                "source_tokens": ["fastapi(", "from fastapi import", "import fastapi"],
                "score": 0,
                "evidence": [],
            },
            "Flask": {
                "dependency_tokens": ["flask"],
                "source_tokens": ["flask(", "from flask import", "import flask"],
                "score": 0,
                "evidence": [],
            },
            "Django": {
                "dependency_tokens": ["django"],
                "source_tokens": ["django", "manage.py", "wsgi.py", "asgi.py"],
                "score": 0,
                "evidence": [],
            },
            "Streamlit": {
                "dependency_tokens": ["streamlit"],
                "source_tokens": ["streamlit", "st."],
                "score": 0,
                "evidence": [],
            },
            "Gradio": {
                "dependency_tokens": ["gradio"],
                "source_tokens": ["gradio", ".launch("],
                "score": 0,
                "evidence": [],
            },
        }

        for framework, config in signals.items():
            for token in config["dependency_tokens"]:
                if self._dependency_exists(dependency_text, token):
                    config["score"] += 45
                    config["evidence"].append(f"Dependency found: {token}")

            for token in config["source_tokens"]:
                if token in source_text:
                    config["score"] += 25
                    config["evidence"].append(f"Source contains: {token}")

        if (folder / "manage.py").exists():
            signals["Django"]["score"] += 40
            signals["Django"]["evidence"].append("manage.py found")

        ranked = sorted(
            signals.items(),
            key=lambda item: item[1]["score"],
            reverse=True,
        )

        best_name, best_config = ranked[0]

        if best_config["score"] <= 0:
            return None, 0, []

        return best_name, min(100, best_config["score"]), best_config["evidence"]

    def _default_python_port(self, framework: str) -> int:
        return {
            "FastAPI": 8000,
            "Flask": 5000,
            "Django": 8000,
            "Streamlit": 8501,
            "Gradio": 7860,
        }.get(framework, 8000)

    def _select_python_start_command(self, folder: Path, framework: str, default_port: int) -> str:
        if framework == "FastAPI":
            return self._detect_fastapi_start_command(folder, default_port=default_port)

        if framework == "Flask":
            return f"flask run --host=0.0.0.0 --port={default_port}"

        if framework == "Django":
            return f"python manage.py runserver 0.0.0.0:{default_port}"

        if framework == "Streamlit":
            app_file = self._find_likely_python_app_file(folder)
            return f"streamlit run {app_file} --server.port={default_port} --server.address=0.0.0.0"

        if framework == "Gradio":
            app_file = self._find_likely_python_app_file(folder)
            return f"python {app_file}"

        return "python main.py"

    def _python_package_file(self, repo_path: Path, folder: Path) -> str | None:
        for file_name in ["requirements.txt", "pyproject.toml", "Pipfile"]:
            path = folder / file_name
            if path.exists():
                return self._relative(repo_path, path)

        return None

    def _find_likely_python_app_file(self, folder: Path) -> str:
        for file_name in ["app.py", "main.py", "server.py"]:
            if (folder / file_name).exists():
                return file_name

        python_files = sorted(folder.glob("*.py"))
        if python_files:
            return python_files[0].name

        return "app.py"

    def _detect_java_components(self, repo_path: Path, files: list[Path]) -> list[dict[str, Any]]:
        components = []

        build_files = []
        build_files.extend(self._find_files(files, "pom.xml"))
        build_files.extend(self._find_files(files, "build.gradle"))
        build_files.extend(self._find_files(files, "build.gradle.kts"))

        for build_file in build_files:
            folder = build_file.parent
            content = self._safe_read(build_file).lower()
            source_text = self._read_relevant_source_text(folder, suffixes={".java", ".kt"}, max_files=80).lower()

            framework = None
            evidence = []
            confidence = 0

            if "spring-boot" in content or "@springbootapplication" in source_text:
                framework = "Spring Boot"
                evidence.append("Spring Boot build/source signal found")
                confidence = 85
            elif "quarkus" in content:
                framework = "Quarkus"
                evidence.append("Quarkus dependency signal found")
                confidence = 80
            elif "micronaut" in content:
                framework = "Micronaut"
                evidence.append("Micronaut dependency signal found")
                confidence = 80

            if not framework:
                continue

            components.append(
                {
                    "name": self._component_name(repo_path, folder),
                    "type": "backend",
                    "language": "Java",
                    "framework": framework,
                    "package_file": self._relative(repo_path, build_file),
                    "component_path": self._relative(repo_path, folder),
                    "port": self._guess_port(folder, default=8080),
                    "start_command": "java -jar app.jar",
                    "build_command": "mvn clean package" if build_file.name == "pom.xml" else "gradle build",
                    "health_path": self._detect_health_path(folder, source_text, default="/actuator/health"),
                    "confidence": confidence,
                    "evidence": evidence,
                    "runtime": "jvm",
                }
            )

        return components

    def _detect_go_components(self, repo_path: Path, files: list[Path]) -> list[dict[str, Any]]:
        components = []

        for go_mod in self._find_files(files, "go.mod"):
            folder = go_mod.parent
            source_text = self._read_relevant_source_text(folder, suffixes={".go"}, max_files=80).lower()
            framework = "Go HTTP Service"
            evidence = ["go.mod found"]
            confidence = 60

            framework_signals = {
                "gin-gonic/gin": "Gin",
                "fiber": "Fiber",
                "echo": "Echo",
                "chi": "Chi",
            }

            for token, name in framework_signals.items():
                if token in source_text:
                    framework = name
                    evidence.append(f"Source contains: {token}")
                    confidence = 85
                    break

            if "http.listenandserve" in source_text:
                evidence.append("Source contains http.ListenAndServe")
                confidence = max(confidence, 75)

            components.append(
                {
                    "name": self._component_name(repo_path, folder),
                    "type": "backend",
                    "language": "Go",
                    "framework": framework,
                    "package_file": self._relative(repo_path, go_mod),
                    "component_path": self._relative(repo_path, folder),
                    "port": self._guess_port(folder, default=8080),
                    "start_command": "go run .",
                    "build_command": "go build -o app .",
                    "health_path": self._detect_health_path(folder, source_text, default="/health"),
                    "confidence": confidence,
                    "evidence": evidence,
                    "runtime": "go",
                }
            )

        return components

    def _detect_php_components(self, repo_path: Path, files: list[Path]) -> list[dict[str, Any]]:
        components = []

        for composer in self._find_files(files, "composer.json"):
            folder = composer.parent
            data = self._read_json(composer)
            dependencies = {}
            dependencies.update(data.get("require", {}) if isinstance(data.get("require"), dict) else {})
            dependencies.update(data.get("require-dev", {}) if isinstance(data.get("require-dev"), dict) else {})
            dep_names = set(dependencies.keys())

            framework = None
            evidence = []
            confidence = 0

            if "laravel/framework" in dep_names:
                framework = "Laravel"
                evidence.append("Dependency found: laravel/framework")
                confidence = 90
            elif "symfony/framework-bundle" in dep_names:
                framework = "Symfony"
                evidence.append("Dependency found: symfony/framework-bundle")
                confidence = 85

            if not framework:
                continue

            components.append(
                {
                    "name": self._component_name(repo_path, folder),
                    "type": "backend",
                    "language": "PHP",
                    "framework": framework,
                    "package_file": self._relative(repo_path, composer),
                    "component_path": self._relative(repo_path, folder),
                    "port": self._guess_port(folder, default=8000),
                    "start_command": "php artisan serve --host=0.0.0.0 --port=8000"
                    if framework == "Laravel"
                    else "php -S 0.0.0.0:8000 -t public",
                    "build_command": "composer install --no-dev --optimize-autoloader",
                    "health_path": "/",
                    "confidence": confidence,
                    "evidence": evidence,
                    "runtime": "php",
                }
            )

        return components

    def _detect_ruby_components(self, repo_path: Path, files: list[Path]) -> list[dict[str, Any]]:
        components = []

        for gemfile in self._find_files(files, "Gemfile"):
            folder = gemfile.parent
            content = self._safe_read(gemfile).lower()

            framework = None
            evidence = []
            confidence = 0

            if "rails" in content:
                framework = "Ruby on Rails"
                evidence.append("Gemfile contains rails")
                confidence = 90
            elif "sinatra" in content:
                framework = "Sinatra"
                evidence.append("Gemfile contains sinatra")
                confidence = 80

            if not framework:
                continue

            components.append(
                {
                    "name": self._component_name(repo_path, folder),
                    "type": "backend",
                    "language": "Ruby",
                    "framework": framework,
                    "package_file": self._relative(repo_path, gemfile),
                    "component_path": self._relative(repo_path, folder),
                    "port": self._guess_port(folder, default=3000),
                    "start_command": "rails server -b 0.0.0.0"
                    if framework == "Ruby on Rails"
                    else "ruby app.rb -o 0.0.0.0",
                    "build_command": "bundle install",
                    "health_path": "/",
                    "confidence": confidence,
                    "evidence": evidence,
                    "runtime": "ruby",
                }
            )

        return components

    def _detect_dotnet_components(self, repo_path: Path, files: list[Path]) -> list[dict[str, Any]]:
        components = []

        project_files = [
            file
            for file in files
            if file.suffix.lower() in {".csproj", ".fsproj"}
        ]

        for project_file in project_files:
            folder = project_file.parent
            content = self._safe_read(project_file).lower()
            source_text = self._read_relevant_source_text(folder, suffixes={".cs", ".fs"}, max_files=80).lower()

            framework = ".NET"
            evidence = [f"{project_file.suffix} project file found"]
            confidence = 65

            if "microsoft.aspnetcore" in content or "webapplication.createbuilder" in source_text:
                framework = "ASP.NET Core"
                evidence.append("ASP.NET Core signal found")
                confidence = 90

            components.append(
                {
                    "name": self._component_name(repo_path, folder),
                    "type": "backend",
                    "language": "C#/.NET",
                    "framework": framework,
                    "package_file": self._relative(repo_path, project_file),
                    "component_path": self._relative(repo_path, folder),
                    "port": self._guess_port(folder, default=8080),
                    "start_command": "dotnet run --urls http://0.0.0.0:8080",
                    "build_command": "dotnet publish -c Release -o out",
                    "health_path": self._detect_health_path(folder, source_text, default="/health"),
                    "confidence": confidence,
                    "evidence": evidence,
                    "runtime": "dotnet",
                }
            )

        return components

    def _detect_rust_components(self, repo_path: Path, files: list[Path]) -> list[dict[str, Any]]:
        components = []

        for cargo in self._find_files(files, "Cargo.toml"):
            folder = cargo.parent
            content = self._safe_read(cargo).lower()
            source_text = self._read_relevant_source_text(folder, suffixes={".rs"}, max_files=80).lower()

            framework = "Rust Service"
            evidence = ["Cargo.toml found"]
            confidence = 60

            if "actix-web" in content:
                framework = "Actix Web"
                evidence.append("Dependency found: actix-web")
                confidence = 85
            elif "rocket" in content:
                framework = "Rocket"
                evidence.append("Dependency found: rocket")
                confidence = 85
            elif "axum" in content:
                framework = "Axum"
                evidence.append("Dependency found: axum")
                confidence = 85

            components.append(
                {
                    "name": self._component_name(repo_path, folder),
                    "type": "backend",
                    "language": "Rust",
                    "framework": framework,
                    "package_file": self._relative(repo_path, cargo),
                    "component_path": self._relative(repo_path, folder),
                    "port": self._guess_port(folder, default=8000),
                    "start_command": "cargo run --release",
                    "build_command": "cargo build --release",
                    "health_path": self._detect_health_path(folder, source_text, default="/health"),
                    "confidence": confidence,
                    "evidence": evidence,
                    "runtime": "rust",
                }
            )

        return components

    def _detect_flutter_components(self, repo_path: Path, files: list[Path]) -> list[dict[str, Any]]:
        components = []

        for pubspec in self._find_files(files, "pubspec.yaml"):
            folder = pubspec.parent
            content = self._safe_read(pubspec).lower()

            framework = "Dart"
            component_type = "frontend"
            evidence = ["pubspec.yaml found"]
            confidence = 60

            if "flutter:" in content:
                framework = "Flutter"
                evidence.append("Flutter signal found")
                confidence = 90

            components.append(
                {
                    "name": self._component_name(repo_path, folder),
                    "type": component_type,
                    "language": "Dart/Flutter",
                    "framework": framework,
                    "package_file": self._relative(repo_path, pubspec),
                    "component_path": self._relative(repo_path, folder),
                    "port": self._guess_port(folder, default=8080),
                    "start_command": "flutter run -d web-server --web-hostname 0.0.0.0 --web-port 8080"
                    if framework == "Flutter"
                    else "dart run",
                    "build_command": "flutter build web" if framework == "Flutter" else None,
                    "health_path": "/",
                    "confidence": confidence,
                    "evidence": evidence,
                    "runtime": "dart",
                }
            )

        return components

    def _detect_static_frontend_components(self, repo_path: Path, files: list[Path]) -> list[dict[str, Any]]:
        components = []

        package_json_folders = {file.parent for file in self._find_files(files, "package.json")}

        candidate_index_files = [
            file
            for file in files
            if file.name == "index.html"
            and not any(parent in IGNORED_DIRS for parent in file.relative_to(repo_path).parts)
        ]

        for index_file in candidate_index_files:
            folder = index_file.parent

            if self._is_inside_manifest_managed_folder(
                path=folder,
                manifest_folders=package_json_folders,
            ):
                continue

            components.append(
                {
                    "name": self._component_name(repo_path, folder),
                    "type": "frontend",
                    "language": "HTML/CSS/Static",
                    "framework": "Static frontend",
                    "package_file": None,
                    "component_path": self._relative(repo_path, folder),
                    "port": 8080,
                    "start_command": "python -m http.server 8080 --bind 0.0.0.0",
                    "build_command": None,
                    "health_path": "/",
                    "confidence": 70,
                    "evidence": ["index.html found without package manifest"],
                    "runtime": "static",
                }
            )

        return components

    def _is_inside_manifest_managed_folder(
        self,
        path: Path,
        manifest_folders: set[Path],
    ) -> bool:
        try:
            resolved_path = path.resolve()
        except Exception:
            resolved_path = path

        for manifest_folder in manifest_folders:
            try:
                resolved_manifest_folder = manifest_folder.resolve()
            except Exception:
                resolved_manifest_folder = manifest_folder

            if resolved_path == resolved_manifest_folder:
                return True

            try:
                resolved_path.relative_to(resolved_manifest_folder)
                return True
            except ValueError:
                continue

        return False

    def _deduplicate_components(self, components: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not components:
            return []

        package_managed_components = [
            component
            for component in components
            if component.get("package_file")
            and component.get("type") in {"fullstack", "backend", "frontend"}
        ]

        cleaned_components: list[dict[str, Any]] = []

        for component in components:
            component_type = component.get("type")
            package_file = component.get("package_file")
            component_path = str(component.get("component_path") or ".").strip("/")

            is_nested_static_component = (
                component_type == "frontend"
                and package_file is None
                and any(
                    self._path_is_inside_component(
                        child_path=component_path,
                        parent_component=parent_component,
                    )
                    for parent_component in package_managed_components
                )
            )

            if is_nested_static_component:
                continue

            cleaned_components.append(component)

        by_path: dict[str, dict[str, Any]] = {}

        for component in cleaned_components:
            path = component.get("component_path") or "."
            existing = by_path.get(path)

            if not existing:
                by_path[path] = component
                continue

            existing_score = int(existing.get("confidence") or 0)
            new_score = int(component.get("confidence") or 0)

            if component.get("type") == "fullstack":
                by_path[path] = component
            elif existing.get("type") != "fullstack" and new_score > existing_score:
                by_path[path] = component

        return sorted(
            by_path.values(),
            key=lambda item: (
                self._component_priority(item),
                int(item.get("confidence") or 0),
            ),
            reverse=True,
        )

    def _path_is_inside_component(
        self,
        child_path: str,
        parent_component: dict[str, Any],
    ) -> bool:
        parent_path = str(parent_component.get("component_path") or ".").strip("/")
        child_path = str(child_path or ".").strip("/")

        if child_path in {"", "."}:
            return False

        if parent_path in {"", "."}:
            return True

        if child_path == parent_path:
            return False

        return child_path.startswith(parent_path + "/")

    def _component_priority(self, component: dict[str, Any]) -> int:
        component_type = component.get("type")

        if component_type == "fullstack":
            return 4

        if component_type == "backend":
            return 3

        if component_type == "frontend":
            return 2

        return 1

    def _select_primary_component(self, components: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not components:
            return None

        return sorted(
            components,
            key=lambda component: (
                self._component_priority(component),
                int(component.get("confidence") or 0),
            ),
            reverse=True,
        )[0]

    def _detect_project_type(self, components: list[dict[str, Any]], files: list[Path]) -> str:
        component_types = {component.get("type") for component in components}

        if "fullstack" in component_types:
            return "fullstack"

        if "frontend" in component_types and "backend" in component_types:
            return "fullstack"

        if "backend" in component_types:
            return "backend"

        if "frontend" in component_types:
            return "frontend"

        suffixes = {file.suffix.lower() for file in files}

        if suffixes.intersection({".html", ".css", ".js", ".ts", ".tsx", ".jsx"}):
            return "frontend_or_javascript"

        return "unknown"

    def _detect_missing_devops_files(self, repo_path: Path, files: list[Path]) -> list[str]:
        file_names = {file.name for file in files}
        relative_paths = {self._relative(repo_path, file) for file in files}

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
            path.startswith("k8s/")
            or path.startswith("kubernetes/")
            or "/k8s/" in path
            or "/kubernetes/" in path
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
        primary_component: dict[str, Any] | None,
        file_inventory: dict[str, Any],
    ) -> list[str]:
        recommendations = []

        if not components:
            recommendations.append(
                "CloudMind could not confidently detect a runnable application component. "
                "Check that the repository contains a manifest, runtime entrypoint, or README with run instructions."
            )

        if primary_component:
            confidence = int(primary_component.get("confidence") or 0)

            if confidence < 60:
                recommendations.append(
                    "The primary component was detected with low confidence. Add explicit start scripts, a README run section, or standard framework files."
                )

            if not primary_component.get("start_command"):
                recommendations.append(
                    f"Define a start command for the {primary_component.get('name', 'primary')} component."
                )

            if not primary_component.get("port"):
                recommendations.append(
                    f"Define an explicit port for the {primary_component.get('name', 'primary')} component."
                )

            if not primary_component.get("health_path"):
                recommendations.append(
                    "Add a health endpoint such as /health or /api/status for deployment verification."
                )

        if "Dockerfile" in missing_devops_files:
            recommendations.append("Generate a Dockerfile based on the detected primary component.")

        if ".dockerignore" in missing_devops_files:
            recommendations.append("Add a .dockerignore file to avoid copying unnecessary files into the image.")

        if "Docker Compose file" in missing_devops_files:
            recommendations.append("Generate a Docker Compose file for local testing.")

        if "Kubernetes manifests" in missing_devops_files:
            recommendations.append(
                "Generate Kubernetes Deployment, Service, ConfigMap, Secret template, and Ingress files."
            )

        if "Helm chart" in missing_devops_files:
            recommendations.append(
                "Later, package Kubernetes manifests into a Helm chart for reusable deployments."
            )

        if file_inventory.get("total_files", 0) <= 2:
            recommendations.append(
                "The repository appears very small. Make sure the actual application code has been pushed."
            )

        return recommendations

    def _generate_tree_preview(self, repo_path: Path, max_items: int = 120) -> list[str]:
        preview = []

        for path in sorted(repo_path.rglob("*")):
            if path.is_file() and self._should_ignore_path(path, repo_path):
                continue

            relative_parts = path.relative_to(repo_path).parts

            if any(part in IGNORED_DIRS for part in relative_parts):
                continue

            if any(part in LOW_VALUE_DIRS_FOR_PREVIEW for part in relative_parts) and len(preview) > 40:
                continue

            relative = path.relative_to(repo_path)
            prefix = "📁 " if path.is_dir() else "📄 "
            preview.append(prefix + str(relative).replace("\\", "/"))

            if len(preview) >= max_items:
                break

        return preview

    def _detect_fastapi_start_command(self, component_folder: Path, default_port: int = 8000) -> str:
        candidates = [
            component_folder / "main.py",
            component_folder / "app.py",
            component_folder / "server.py",
            component_folder / "app" / "main.py",
            component_folder / "src" / "main.py",
        ]

        for candidate in candidates:
            if not candidate.exists():
                continue

            content = self._safe_read(candidate).lower()

            if "fastapi(" in content:
                module_path = candidate.relative_to(component_folder).with_suffix("")
                module_name = ".".join(module_path.parts)

                return f"uvicorn {module_name}:app --host 0.0.0.0 --port {default_port}"

        return f"uvicorn main:app --host 0.0.0.0 --port {default_port}"

    def _detect_health_path(
        self,
        component_folder: Path,
        source_text: str,
        default: str = "/health",
    ) -> str:
        route_patterns = [
            r"""['"](/health)['"]""",
            r"""['"](/api/health)['"]""",
            r"""['"](/status)['"]""",
            r"""['"](/api/status)['"]""",
            r"""['"](/ready)['"]""",
            r"""['"](/live)['"]""",
        ]

        for pattern in route_patterns:
            match = re.search(pattern, source_text)
            if match:
                return match.group(1)

        readme = self._find_readme(component_folder)
        if readme:
            readme_text = self._safe_read(readme).lower()
            for candidate in ["/health", "/api/health", "/status", "/api/status", "/ready", "/live"]:
                if candidate in readme_text:
                    return candidate

        return default

    def _find_readme(self, folder: Path) -> Path | None:
        for file_name in ["README.md", "readme.md"]:
            path = folder / file_name
            if path.exists():
                return path

        return None

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
            data = json.loads(self._safe_read(file_path))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _package_dependencies(self, package_data: dict[str, Any]) -> dict[str, Any]:
        dependencies = {}

        for key in [
            "dependencies",
            "devDependencies",
            "peerDependencies",
            "optionalDependencies",
        ]:
            value = package_data.get(key)

            if isinstance(value, dict):
                dependencies.update(value)

        return dependencies

    def _dependency_exists(self, content: str, package_name: str) -> bool:
        content = content.lower()
        package_name = package_name.lower()

        patterns = [
            rf'["\']{re.escape(package_name)}(?:\[.*?\])?(?:[=<>~!;\s,"\'])',
            rf"^{re.escape(package_name)}(?:\[.*?\])?[=<>~!\s]",
            rf"\n{re.escape(package_name)}(?:\[.*?\])?[=<>~!\s]",
            rf"{re.escape(package_name)}\s*=",
            rf"\b{re.escape(package_name)}\b",
        ]

        return any(re.search(pattern, content) for pattern in patterns)

    def _guess_port(self, search_path: Path, default: int) -> int:
        content_parts = []
        base_path = search_path if search_path.is_dir() else search_path.parent

        candidate_names = [
            "package.json",
            "main.py",
            "app.py",
            "server.py",
            "server.js",
            "server.ts",
            "index.js",
            "index.ts",
            "app.js",
            "app.ts",
            "vite.config.ts",
            "vite.config.js",
            "next.config.js",
            "application.properties",
            "application.yml",
            "application.yaml",
            ".env",
            ".env.example",
            "README.md",
            "readme.md",
            "Program.cs",
        ]

        for file_name in candidate_names:
            for path in base_path.rglob(file_name):
                relative_parts = path.relative_to(base_path).parts

                if any(part in IGNORED_DIRS for part in relative_parts):
                    continue

                content_parts.append(self._safe_read(path, max_chars=50_000))

        content = "\n".join(content_parts)

        env_port_match = re.search(r"\bPORT\s*=\s*(\d{2,5})\b", content)
        if env_port_match:
            return int(env_port_match.group(1))

        listen_match = re.search(r"(?:listen|port|server\.port|--port)[^\d]{0,20}(\d{2,5})", content, re.IGNORECASE)
        if listen_match:
            port = int(listen_match.group(1))
            if 1 <= port <= 65535:
                return port

        common_ports = [5173, 3000, 8000, 8080, 5000, 4000, 4200, 8501, 7860, 9000]

        for port in common_ports:
            if str(port) in content:
                return port

        return default

    def _read_relevant_source_text(
        self,
        folder: Path,
        suffixes: set[str],
        max_files: int = 60,
        max_chars_per_file: int = 12_000,
    ) -> str:
        parts = []
        count = 0

        if not folder.exists():
            return ""

        for path in sorted(folder.rglob("*")):
            if count >= max_files:
                break

            if not path.is_file():
                continue

            if path.suffix.lower() not in suffixes:
                continue

            try:
                relative_parts = path.relative_to(folder).parts
            except ValueError:
                continue

            if any(part in IGNORED_DIRS for part in relative_parts):
                continue

            parts.append(self._safe_read(path, max_chars=max_chars_per_file))
            count += 1

        return "\n".join(parts)

    def _component_name(self, repo_path: Path, component_folder: Path) -> str:
        if component_folder == repo_path:
            return "app"

        return component_folder.name

    def _relative(self, repo_path: Path, path: Path) -> str:
        try:
            return str(path.relative_to(repo_path)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    def _first_or_none(self, values: list[str]) -> str | None:
        return values[0] if values else None