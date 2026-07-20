from pathlib import Path
from typing import Any

from app.agents.repo_analyzer_agent import RepositoryAnalyzerAgent


class AzureDeploymentAgent:
    """
    Phase 7 agent.

    Responsibilities:
    - analyze repository architecture
    - generate Azure Container Apps deployment scripts
    - keep deployment student-budget friendly
    - target Azure Container Apps Consumption instead of AKS
    """

    def __init__(self):
        self.repo_analyzer = RepositoryAnalyzerAgent()

    def generate_for_repo(
        self,
        repo_url: str,
        branch: str | None = None,
        overwrite: bool = False,
        azure_location: str = "francecentral",
        resource_group: str | None = None,
        container_app_environment: str | None = None,
        image_registry: str = "ghcr.io",
        image_owner: str | None = None,
        image_tag: str = "latest",
        min_replicas: int = 0,
        max_replicas: int = 1,
        cpu: float = 0.25,
        memory: str = "0.5Gi",
    ) -> dict[str, Any]:
        analysis = self.repo_analyzer.analyze(repo_url=repo_url, branch=branch)

        return self.generate_from_analysis(
            analysis=analysis,
            overwrite=overwrite,
            azure_location=azure_location,
            resource_group=resource_group,
            container_app_environment=container_app_environment,
            image_registry=image_registry,
            image_owner=image_owner,
            image_tag=image_tag,
            min_replicas=min_replicas,
            max_replicas=max_replicas,
            cpu=cpu,
            memory=memory,
        )

    def generate_from_analysis(
        self,
        analysis: dict[str, Any],
        overwrite: bool = False,
        azure_location: str = "francecentral",
        resource_group: str | None = None,
        container_app_environment: str | None = None,
        image_registry: str = "ghcr.io",
        image_owner: str | None = None,
        image_tag: str = "latest",
        min_replicas: int = 0,
        max_replicas: int = 1,
        cpu: float = 0.25,
        memory: str = "0.5Gi",
    ) -> dict[str, Any]:
        repo_path = Path(analysis["metadata"]["local_path"])
        components = analysis.get("components", [])

        if not components:
            return {
                "status": "failed",
                "message": "No deployable components were detected. Azure deployment scripts were not generated.",
                "analysis": analysis,
                "generated_files": [],
                "skipped_files": [],
                "recommendations": [
                    "Add standard dependency files such as package.json, requirements.txt, or pyproject.toml.",
                    "Run repository analysis again before generating Azure deployment scripts.",
                ],
            }

        repo_name = self._normalize_name(analysis["repo_name"])
        image_owner = self._normalize_image_owner(image_owner or "your-github-username")

        resource_group = resource_group or f"rg-cloudmind-{repo_name}"
        container_app_environment = container_app_environment or f"cae-cloudmind-{repo_name}"

        azure_dir = repo_path / "azure"
        azure_dir.mkdir(parents=True, exist_ok=True)

        app_definitions = self._build_app_definitions(
            repo_name=repo_name,
            components=components,
            image_registry=image_registry,
            image_owner=image_owner,
            image_tag=image_tag,
        )

        file_map = {
            "deploy-container-app.ps1": self._generate_powershell_script(
                azure_location=azure_location,
                resource_group=resource_group,
                container_app_environment=container_app_environment,
                app_definitions=app_definitions,
                min_replicas=min_replicas,
                max_replicas=max_replicas,
                cpu=cpu,
                memory=memory,
            ),
            "deploy-container-app.sh": self._generate_bash_script(
                azure_location=azure_location,
                resource_group=resource_group,
                container_app_environment=container_app_environment,
                app_definitions=app_definitions,
                min_replicas=min_replicas,
                max_replicas=max_replicas,
                cpu=cpu,
                memory=memory,
            ),
            "README.md": self._generate_azure_readme(
                azure_location=azure_location,
                resource_group=resource_group,
                container_app_environment=container_app_environment,
                app_definitions=app_definitions,
                min_replicas=min_replicas,
                max_replicas=max_replicas,
                cpu=cpu,
                memory=memory,
            ),
        }

        generated_files: list[dict[str, Any]] = []
        skipped_files: list[dict[str, Any]] = []

        for file_name, content in file_map.items():
            target_path = azure_dir / file_name

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
                    "type": "azure_deployment_file",
                }
            )

        return {
            "status": "success",
            "message": "AzureDeploymentAgent completed successfully.",
            "repo_url": analysis["repo_url"],
            "repo_name": analysis["repo_name"],
            "project_type": analysis["project_type"],
            "azure_target": "Azure Container Apps Consumption",
            "azure_location": azure_location,
            "resource_group": resource_group,
            "container_app_environment": container_app_environment,
            "components": components,
            "app_definitions": app_definitions,
            "generated_files": generated_files,
            "skipped_files": skipped_files,
            "analysis": analysis,
            "budget_notes": [
                "Uses Azure Container Apps instead of AKS to reduce student credit usage.",
                "Sets min replicas to 0 so the app can scale down when idle.",
                "Sets max replicas to 1 by default to avoid surprise scaling costs.",
                "Uses small CPU and memory defaults for demo workloads.",
            ],
            "next_step": "Review the generated Azure scripts, then GitAgent can push them to a CloudMind branch and open a pull request.",
        }

    def _build_app_definitions(
        self,
        repo_name: str,
        components: list[dict[str, Any]],
        image_registry: str,
        image_owner: str,
        image_tag: str,
    ) -> list[dict[str, Any]]:
        app_definitions = []

        for component in components:
            component_name = self._normalize_name(
                component.get("name") or component.get("type") or "app"
            )

            app_name = f"{repo_name}-{component_name}"
            image_name = f"{image_registry}/{image_owner}/{repo_name}-{component_name}:{image_tag}"
            target_port = self._container_port(component)

            app_definitions.append(
                {
                    "component_name": component_name,
                    "app_name": app_name,
                    "image": image_name,
                    "target_port": target_port,
                    "external_ingress": True,
                }
            )

        return app_definitions

    def _generate_powershell_script(
        self,
        azure_location: str,
        resource_group: str,
        container_app_environment: str,
        app_definitions: list[dict[str, Any]],
        min_replicas: int,
        max_replicas: int,
        cpu: float,
        memory: str,
    ) -> str:
        app_blocks = []

        for app in app_definitions:
            app_blocks.append(
                f"""Write-Host "Deploying container app: {app["app_name"]}" -ForegroundColor Cyan

$Fqdn = az containerapp create `
  --name "{app["app_name"]}" `
  --resource-group $ResourceGroup `
  --environment $ContainerAppEnvironment `
  --image "{app["image"]}" `
  --target-port {app["target_port"]} `
  --ingress external `
  --min-replicas {min_replicas} `
  --max-replicas {max_replicas} `
  --cpu {cpu} `
  --memory "{memory}" `
  --registry-server "ghcr.io" `
  --registry-username $env:GHCR_USERNAME `
  --registry-password $env:GHCR_TOKEN `
  --query "properties.configuration.ingress.fqdn" `
  --output tsv

Write-Host "Application URL:" -ForegroundColor Green
Write-Host "https://$Fqdn" -ForegroundColor Green
"""
            )

        app_blocks_content = "\n".join(app_blocks)

        return f"""# Generated by CloudMind
# Azure Container Apps eco deployment script
# Target: Azure Container Apps Consumption
# OS: Windows PowerShell

$ErrorActionPreference = "Stop"

$ResourceGroup = "{resource_group}"
$Location = "{azure_location}"
$ContainerAppEnvironment = "{container_app_environment}"

if (-not $env:GHCR_USERNAME) {{
    throw "Missing environment variable GHCR_USERNAME. Set it to your GitHub username, for example: Hedi808"
}}

if (-not $env:GHCR_TOKEN) {{
    throw "Missing environment variable GHCR_TOKEN. Create a GitHub token with read:packages permission and set it here."
}}

Write-Host "Checking Azure CLI login..." -ForegroundColor Cyan
az account show | Out-Null

Write-Host "Installing or updating Azure Container Apps CLI extension..." -ForegroundColor Cyan
az extension add --name containerapp --upgrade

Write-Host "Registering required Azure providers..." -ForegroundColor Cyan
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

Write-Host "Creating resource group: $ResourceGroup" -ForegroundColor Cyan
az group create `
  --name $ResourceGroup `
  --location $Location `
  --output table

Write-Host "Creating Azure Container Apps environment: $ContainerAppEnvironment" -ForegroundColor Cyan
az containerapp env create `
  --name $ContainerAppEnvironment `
  --resource-group $ResourceGroup `
  --location $Location `
  --output table

{app_blocks_content}

Write-Host "Deployment completed." -ForegroundColor Green
Write-Host "Cost control: min replicas is {min_replicas}, max replicas is {max_replicas}, CPU is {cpu}, memory is {memory}." -ForegroundColor Yellow
"""

    def _generate_bash_script(
        self,
        azure_location: str,
        resource_group: str,
        container_app_environment: str,
        app_definitions: list[dict[str, Any]],
        min_replicas: int,
        max_replicas: int,
        cpu: float,
        memory: str,
    ) -> str:
        app_blocks = []

        for app in app_definitions:
            app_blocks.append(
                f"""echo "Deploying container app: {app["app_name"]}"

FQDN=$(az containerapp create \\
  --name "{app["app_name"]}" \\
  --resource-group "$RESOURCE_GROUP" \\
  --environment "$CONTAINER_APP_ENVIRONMENT" \\
  --image "{app["image"]}" \\
  --target-port {app["target_port"]} \\
  --ingress external \\
  --min-replicas {min_replicas} \\
  --max-replicas {max_replicas} \\
  --cpu {cpu} \\
  --memory "{memory}" \\
  --registry-server "ghcr.io" \\
  --registry-username "$GHCR_USERNAME" \\
  --registry-password "$GHCR_TOKEN" \\
  --query "properties.configuration.ingress.fqdn" \\
  --output tsv)

echo "Application URL:"
echo "https://$FQDN"
"""
            )

        app_blocks_content = "\n".join(app_blocks)

        return f"""#!/usr/bin/env bash
# Generated by CloudMind
# Azure Container Apps eco deployment script
# Target: Azure Container Apps Consumption

set -euo pipefail

RESOURCE_GROUP="{resource_group}"
LOCATION="{azure_location}"
CONTAINER_APP_ENVIRONMENT="{container_app_environment}"

if [ -z "${{GHCR_USERNAME:-}}" ]; then
  echo "Missing environment variable GHCR_USERNAME. Set it to your GitHub username, for example: Hedi808"
  exit 1
fi

if [ -z "${{GHCR_TOKEN:-}}" ]; then
  echo "Missing environment variable GHCR_TOKEN. Create a GitHub token with read:packages permission and set it here."
  exit 1
fi

echo "Checking Azure CLI login..."
az account show > /dev/null

echo "Installing or updating Azure Container Apps CLI extension..."
az extension add --name containerapp --upgrade

echo "Registering required Azure providers..."
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

echo "Creating resource group: $RESOURCE_GROUP"
az group create \\
  --name "$RESOURCE_GROUP" \\
  --location "$LOCATION" \\
  --output table

echo "Creating Azure Container Apps environment: $CONTAINER_APP_ENVIRONMENT"
az containerapp env create \\
  --name "$CONTAINER_APP_ENVIRONMENT" \\
  --resource-group "$RESOURCE_GROUP" \\
  --location "$LOCATION" \\
  --output table

{app_blocks_content}

echo "Deployment completed."
echo "Cost control: min replicas is {min_replicas}, max replicas is {max_replicas}, CPU is {cpu}, memory is {memory}."
"""

    def _generate_azure_readme(
        self,
        azure_location: str,
        resource_group: str,
        container_app_environment: str,
        app_definitions: list[dict[str, Any]],
        min_replicas: int,
        max_replicas: int,
        cpu: float,
        memory: str,
    ) -> str:
        app_lines = []
        for app in app_definitions:
            app_lines.append(
                f"- {app['app_name']} -> {app['image']} -> port {app['target_port']}"
            )

        app_lines_content = "\n".join(app_lines)

        return f"""# Azure Deployment

Generated by CloudMind.

## Target

Azure Container Apps Consumption.

This is the recommended student-budget deployment target for this project because it avoids running a full Kubernetes node pool for the first demo.

## Generated apps

{app_lines_content}

## Cost-control defaults

- Resource group: {resource_group}
- Location: {azure_location}
- Container Apps environment: {container_app_environment}
- Min replicas: {min_replicas}
- Max replicas: {max_replicas}
- CPU: {cpu}
- Memory: {memory}

## Prerequisites

Install Azure CLI and log in:

    az login

Set GitHub Container Registry credentials in PowerShell:

    $env:GHCR_USERNAME="Hedi808"
    $env:GHCR_TOKEN="YOUR_GITHUB_TOKEN_WITH_READ_PACKAGES"

Do not commit or share your token.

## Deploy from Windows PowerShell

From the repository root:

    cd azure
    ./deploy-container-app.ps1

## Deploy from Bash

From the repository root:

    cd azure
    chmod +x deploy-container-app.sh
    ./deploy-container-app.sh

## Clean up to protect student credits

When you finish testing, delete the resource group:

    az group delete --name {resource_group} --yes
"""

    def _container_port(self, component: dict[str, Any]) -> int:
        component_type = component.get("type")
        framework = (component.get("framework") or "").lower()

        if component_type == "frontend" and framework in ["react", "vue.js", "angular"]:
            return 80

        return component.get("port") or 8080

    def _normalize_name(self, name: str) -> str:
        name = name.lower().strip()
        name = name.replace("_", "-")
        normalized = "".join(char if char.isalnum() or char == "-" else "-" for char in name)
        normalized = normalized.strip("-")

        return normalized or "app"

    def _normalize_image_owner(self, image_owner: str) -> str:
        return image_owner.strip().lower()