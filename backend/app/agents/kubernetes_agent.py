from pathlib import Path
from typing import Any


class KubernetesAgent:
    """
    Phase 4 agent.

    Responsibilities:
    - generate Kubernetes manifests for detected components
    - create namespace, configmap, secret template, deployment, service, ingress
    - skip existing k8s files unless overwrite=True
    """

    def generate_from_analysis(
        self,
        analysis: dict[str, Any],
        overwrite: bool = False,
        namespace: str = "cloudmind-staging",
        image_registry: str = "ghcr.io",
        image_owner: str | None = None,
        image_tag: str = "latest",
        ingress_host: str | None = None,
    ) -> dict[str, Any]:
        repo_path = Path(analysis["metadata"]["local_path"])
        components = analysis.get("components", [])

        if not components:
            return {
                "status": "failed",
                "message": "No deployable components were detected. Kubernetes files were not generated.",
                "analysis": analysis,
                "generated_files": [],
                "skipped_files": [],
                "recommendations": [
                    "Add standard dependency files such as package.json, requirements.txt, or pyproject.toml.",
                    "Run repository analysis again before generating Kubernetes manifests.",
                ],
            }

        app_name = self._normalize_name(analysis["repo_name"])
        image_owner = image_owner or "your-github-username"
        ingress_host = ingress_host or f"{app_name}.local"

        k8s_dir = repo_path / "k8s"
        k8s_dir.mkdir(parents=True, exist_ok=True)

        generated_files: list[dict[str, Any]] = []
        skipped_files: list[dict[str, Any]] = []

        file_map = {
            "namespace.yaml": self._generate_namespace(namespace),
            "configmap.yaml": self._generate_configmap(app_name, namespace),
            "secret-template.yaml": self._generate_secret_template(app_name, namespace),
            "deployment.yaml": self._generate_deployments(
                app_name=app_name,
                namespace=namespace,
                components=components,
                image_registry=image_registry,
                image_owner=image_owner,
                image_tag=image_tag,
            ),
            "service.yaml": self._generate_services(
                app_name=app_name,
                namespace=namespace,
                components=components,
            ),
            "ingress.yaml": self._generate_ingress(
                app_name=app_name,
                namespace=namespace,
                components=components,
                ingress_host=ingress_host,
            ),
            "kustomization.yaml": self._generate_kustomization(),
        }

        for file_name, content in file_map.items():
            target_path = k8s_dir / file_name

            if target_path.exists() and not overwrite:
                skipped_files.append(
                    {
                        "path": str(target_path),
                        "reason": "File already exists. Use overwrite=true to replace it.",
                    }
                )
                continue

            target_path.write_text(content, encoding="utf-8")
            generated_files.append(
                {
                    "path": str(target_path),
                    "type": "kubernetes_manifest",
                }
            )

        return {
            "status": "success",
            "message": "KubernetesAgent completed successfully.",
            "repo_url": analysis["repo_url"],
            "repo_name": analysis["repo_name"],
            "project_type": analysis["project_type"],
            "namespace": namespace,
            "ingress_host": ingress_host,
            "components": components,
            "generated_files": generated_files,
            "skipped_files": skipped_files,
            "analysis": analysis,
            "next_step": "After reviewing the generated manifests, GitAgent can push them to a CloudMind branch and open a pull request.",
        }

    def generate_for_repo(
        self,
        repo_url: str,
        branch: str | None = None,
        overwrite: bool = False,
        namespace: str = "cloudmind-staging",
        image_registry: str = "ghcr.io",
        image_owner: str | None = None,
        image_tag: str = "latest",
        ingress_host: str | None = None,
    ) -> dict[str, Any]:
        from app.agents.repo_analyzer_agent import RepositoryAnalyzerAgent

        repo_analyzer = RepositoryAnalyzerAgent()
        analysis = repo_analyzer.analyze(repo_url=repo_url, branch=branch)

        return self.generate_from_analysis(
            analysis=analysis,
            overwrite=overwrite,
            namespace=namespace,
            image_registry=image_registry,
            image_owner=image_owner,
            image_tag=image_tag,
            ingress_host=ingress_host,
        )

    def _generate_namespace(self, namespace: str) -> str:
        return f"""# Generated by CloudMind
apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    app.kubernetes.io/managed-by: cloudmind
"""

    def _generate_configmap(self, app_name: str, namespace: str) -> str:
        return f"""# Generated by CloudMind
apiVersion: v1
kind: ConfigMap
metadata:
  name: {app_name}-config
  namespace: {namespace}
  labels:
    app.kubernetes.io/name: {app_name}
    app.kubernetes.io/managed-by: cloudmind
data:
  APP_ENV: "staging"
  LOG_LEVEL: "info"
"""

    def _generate_secret_template(self, app_name: str, namespace: str) -> str:
        return f"""# Generated by CloudMind
# WARNING:
# This is only a template. Do not commit real secrets to Git.
# Replace values using kubectl, sealed-secrets, external-secrets, or your cloud secret manager.
apiVersion: v1
kind: Secret
metadata:
  name: {app_name}-secret
  namespace: {namespace}
  labels:
    app.kubernetes.io/name: {app_name}
    app.kubernetes.io/managed-by: cloudmind
type: Opaque
stringData:
  EXAMPLE_SECRET: "replace-me"
"""

    def _generate_deployments(
        self,
        app_name: str,
        namespace: str,
        components: list[dict[str, Any]],
        image_registry: str,
        image_owner: str,
        image_tag: str,
    ) -> str:
        documents = []

        for component in components:
            component_name = self._normalize_name(component.get("name") or component.get("type") or "app")
            full_name = f"{app_name}-{component_name}"
            port = self._container_port(component)
            image = f"{image_registry}/{image_owner}/{app_name}-{component_name}:{image_tag}"

            documents.append(
                f"""# Generated by CloudMind
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {full_name}
  namespace: {namespace}
  labels:
    app.kubernetes.io/name: {app_name}
    app.kubernetes.io/component: {component_name}
    app.kubernetes.io/managed-by: cloudmind
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {app_name}
      app.kubernetes.io/component: {component_name}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {app_name}
        app.kubernetes.io/component: {component_name}
    spec:
      containers:
        - name: {component_name}
          image: {image}
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: {port}
          envFrom:
            - configMapRef:
                name: {app_name}-config
            - secretRef:
                name: {app_name}-secret
                optional: true
          readinessProbe:
            httpGet:
              path: {self._health_path(component)}
              port: {port}
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 6
          livenessProbe:
            httpGet:
              path: {self._health_path(component)}
              port: {port}
            initialDelaySeconds: 15
            periodSeconds: 20
            failureThreshold: 3
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
"""
            )

        return "\n---\n".join(documents) + "\n"

    def _generate_services(
        self,
        app_name: str,
        namespace: str,
        components: list[dict[str, Any]],
    ) -> str:
        documents = []

        for component in components:
            component_name = self._normalize_name(component.get("name") or component.get("type") or "app")
            full_name = f"{app_name}-{component_name}"
            port = self._service_port(component)
            target_port = self._container_port(component)

            documents.append(
                f"""# Generated by CloudMind
apiVersion: v1
kind: Service
metadata:
  name: {full_name}
  namespace: {namespace}
  labels:
    app.kubernetes.io/name: {app_name}
    app.kubernetes.io/component: {component_name}
    app.kubernetes.io/managed-by: cloudmind
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: {app_name}
    app.kubernetes.io/component: {component_name}
  ports:
    - name: http
      port: {port}
      targetPort: {target_port}
"""
            )

        return "\n---\n".join(documents) + "\n"

    def _generate_ingress(
        self,
        app_name: str,
        namespace: str,
        components: list[dict[str, Any]],
        ingress_host: str,
    ) -> str:
        backend_component = self._select_public_component(components)
        component_name = self._normalize_name(backend_component.get("name") or backend_component.get("type") or "app")
        service_name = f"{app_name}-{component_name}"
        service_port = self._service_port(backend_component)

        return f"""# Generated by CloudMind
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {app_name}-ingress
  namespace: {namespace}
  labels:
    app.kubernetes.io/name: {app_name}
    app.kubernetes.io/managed-by: cloudmind
  annotations:
    kubernetes.io/description: "CloudMind generated ingress for {app_name}"
spec:
  rules:
    - host: {ingress_host}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {service_name}
                port:
                  number: {service_port}
"""

    def _generate_kustomization(self) -> str:
        return """# Generated by CloudMind
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - namespace.yaml
  - configmap.yaml
  - secret-template.yaml
  - deployment.yaml
  - service.yaml
  - ingress.yaml
"""

    def _select_public_component(self, components: list[dict[str, Any]]) -> dict[str, Any]:
        frontend = next((component for component in components if component.get("type") == "frontend"), None)
        if frontend:
            return frontend

        backend = next((component for component in components if component.get("type") == "backend"), None)
        if backend:
            return backend

        return components[0]

    def _container_port(self, component: dict[str, Any]) -> int:
        component_type = component.get("type")
        framework = (component.get("framework") or "").lower()

        if component_type == "frontend" and framework in ["react", "vue.js", "angular"]:
            return 80

        return component.get("port") or 8080

    def _service_port(self, component: dict[str, Any]) -> int:
        component_type = component.get("type")
        framework = (component.get("framework") or "").lower()

        if component_type == "frontend" and framework in ["react", "vue.js", "angular"]:
            return 80

        return component.get("port") or 8080

    def _health_path(self, component: dict[str, Any]) -> str:
        component_type = component.get("type")
        framework = (component.get("framework") or "").lower()

        if component_type == "frontend":
            return "/"

        if framework == "fastapi":
            return "/health"

        return "/"

    def _normalize_name(self, name: str) -> str:
        name = name.lower().strip()
        name = name.replace("_", "-")
        normalized = "".join(char if char.isalnum() or char == "-" else "-" for char in name)
        normalized = normalized.strip("-")

        return normalized or "app"