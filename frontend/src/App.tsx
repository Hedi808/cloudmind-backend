import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  Bot,
  Brain,
  CheckCircle2,
  Cloud,
  Code2,
  Database,
  FileText,
  GitPullRequest,
  History,
  Link as LinkIcon,
  Loader2,
  PlayCircle,
  RefreshCw,
  Rocket,
  Send,
  Server,
  Settings2,
  ShieldCheck,
  Terminal,
  XCircle,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { sendCloudMindMessage } from "./api/cloudmindApi";
import { listPipelineRuns, runOrResumePipeline } from "./api/pipelineApi";
import { getProject, listProjects } from "./api/projectsApi";
import { getWorkflowPlan } from "./api/workflowsApi";
import type {
  ChatMessage,
  CloudMindChatResult,
  ConversationState,
  PipelineRunRecord,
  PipelineRunResponse,
  ProjectActionRun,
  ProjectArtifact,
  ProjectContext,
  ProjectDeploymentState,
  ProjectMemoryProject,
  WorkflowPlanResponse,
  WorkflowStep,
} from "./types/cloudmind";

const createSessionId = (): string => crypto.randomUUID();

const nowLabel = () =>
  new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

const demoProject = {
  repoUrl: "https://github.com/Hedi808/test-3s.git",
  resourceGroup: "rg-cloudmind-test-3s",
  appName: "test-3s-backend",
  pullRequestUrl: "https://github.com/Hedi808/test-3s/pull/8",
};

const emptyProject = {
  repoUrl: "",
  resourceGroup: "",
  appName: "",
  pullRequestUrl: "",
};

const repositoryActions = [
  {
    label: "Analyze Project",
    message: "Analyze this repository",
    icon: Code2,
  },
  {
    label: "Generate Docker",
    message: "Generate Docker files for this repo",
    icon: Terminal,
  },
  {
    label: "Generate Kubernetes",
    message: "Generate Kubernetes manifests for this repo",
    icon: Server,
  },
  {
    label: "Prepare Deployment",
    message: "Prepare this repo for deployment",
    icon: Settings2,
  },
  {
    label: "Generate CI/CD",
    message: "Generate CI/CD for this repo",
    icon: GitPullRequest,
  },
  {
    label: "Generate Azure Files",
    message: "Generate Azure deployment files for this repo",
    icon: Cloud,
  },
];

const runtimeActions = [
  {
    label: "Plan Pipeline",
    message: "__workflow_plan__",
    icon: Zap,
  },
  {
    label: "Run Pipeline",
    message: "__run_full_pipeline__",
    icon: PlayCircle,
  },
  {
    label: "Deploy Azure",
    message: "Deploy this app to Azure",
    icon: Rocket,
  },
  {
    label: "Azure Status",
    message: "Check Azure status",
    icon: Activity,
  },
  {
    label: "Analyze Incident",
    message: "Analyze incident for this Azure app",
    icon: ShieldCheck,
  },
  {
    label: "Final Report",
    message: "Generate the final demo report",
    icon: FileText,
  },
];

export default function App() {
  const [sessionId, setSessionId] = useState<string>(() => createSessionId());
  const [projectMode, setProjectMode] = useState<"demo" | "custom">("custom");

  const [repoUrl, setRepoUrl] = useState("");
  const [resourceGroup, setResourceGroup] = useState("");
  const [appName, setAppName] = useState("");
  const [pullRequestUrl, setPullRequestUrl] = useState("");
  const [approvalConfirmed, setApprovalConfirmed] = useState(false);

  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isPipelineRunning, setIsPipelineRunning] = useState(false);

  const [savedProjects, setSavedProjects] = useState<ProjectMemoryProject[]>([]);
  const [isProjectsLoading, setIsProjectsLoading] = useState(false);

  const [workflowPlan, setWorkflowPlan] =
    useState<WorkflowPlanResponse | null>(null);
  const [isWorkflowLoading, setIsWorkflowLoading] = useState(false);
  const [pipelineRunId, setPipelineRunId] = useState<string | null>(null);
  const [pipelineCheckpointStatus, setPipelineCheckpointStatus] = useState<
    string | null
  >(null);

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "CloudMind is ready. Select a project, plan the pipeline, deploy safely, verify health, and generate a final demo report.",
      timestamp: nowLabel(),
    },
  ]);

  const [latestResult, setLatestResult] = useState<CloudMindChatResult | null>(
    null,
  );
  const [latestToolResult, setLatestToolResult] =
    useState<Record<string, unknown> | null>(null);
  const [conversationState, setConversationState] =
    useState<ConversationState | null>(null);
  const [projectContext, setProjectContext] = useState<ProjectContext | null>(
    null,
  );

  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const project = projectContext?.project ?? null;
  const latestDeployment = projectContext?.latest_deployment ?? null;
  const latestActions = useMemo(
    () => projectContext?.latest_actions ?? [],
    [projectContext],
  );
  const latestArtifacts = useMemo(
    () => projectContext?.latest_artifacts ?? [],
    [projectContext],
  );
  const selectedProjectId = project?.id ?? conversationState?.project_id ?? null;

  const missionStatus = useMemo(() => {
    const toolResultStatus = getString(latestResult?.tool_result, "status");
    const demoRecommendation = getString(
      latestResult?.tool_result,
      "demo_recommendation",
    );
    const deploymentRecommendation = getString(
      latestResult?.tool_result,
      "deployment_recommendation",
    );
    const logsAvailable = getBoolean(
      latestResult?.tool_result,
      "logs_available",
    );
    const latestToolHealthy = getBoolean(latestToolResult, "healthy");
    const latestToolIncidentDetected = getBoolean(
      latestToolResult,
      "incident_detected",
    );

    const latestStatus =
      toolResultStatus ??
      pipelineCheckpointStatus ??
      workflowPlan?.status ??
      conversationState?.latest_result_status ??
      latestDeployment?.health_status ??
      "Not available yet";

    const azureHealthy =
      latestDeployment?.health_status === "healthy" ||
      latestToolHealthy === true ||
      toolResultStatus === "deployed";

    const incidentDetected =
      latestToolIncidentDetected === true
        ? "Yes"
        : latestToolIncidentDetected === false
          ? "No"
          : workflowPlan?.steps.find((step) => step.id === "analyze_incident")
                ?.status === "completed"
            ? "Checked"
            : "Unknown";

    const prArtifact = latestArtifacts.find(
      (artifact) => artifact.artifact_type === "github_pull_request",
    );

    return {
      status: latestStatus,
      recommendation:
        workflowPlan?.message ??
        demoRecommendation ??
        deploymentRecommendation ??
        "Not available yet",
      azureHealthy: azureHealthy ? "Healthy" : "Unknown",
      logsAvailable: logsAvailable === true ? "Yes" : "Unknown",
      incidentDetected,
      prState: prArtifact?.url ? "PR tracked" : "Not available yet",
      ci:
        workflowPlan?.steps.find((step) => step.id === "generate_cicd")
          ?.status ??
        latestActions.find((action) => action.action_type === "generate_cicd")
          ?.status ??
        "Not available yet",
    };
  }, [
    conversationState,
    latestActions,
    latestArtifacts,
    latestDeployment,
    latestResult,
    latestToolResult,
    pipelineCheckpointStatus,
    workflowPlan,
  ]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading, isWorkflowLoading, isPipelineRunning]);

  const appendAssistantMessage = (content: string, status?: string) => {
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content,
        timestamp: nowLabel(),
        status,
      },
    ]);
  };

  const loadSavedProjects = async () => {
    setIsProjectsLoading(true);

    try {
      const response = await listProjects();
      setSavedProjects(response.projects);
    } catch {
      setSavedProjects([]);
    } finally {
      setIsProjectsLoading(false);
    }
  };

  const restoreLatestPipelineRun = async (projectId: string) => {
    setPipelineRunId(null);
    setPipelineCheckpointStatus(null);

    try {
      const response = await listPipelineRuns(projectId);
      const activeRun = response.items.find(
        (run) => !isTerminalPipelineRun(run),
      );
      const latestRun = activeRun ?? response.items[0] ?? null;

      setPipelineRunId(activeRun?.id ?? null);
      setPipelineCheckpointStatus(latestRun?.checkpoint_status ?? null);
    } catch {
      setPipelineRunId(null);
      setPipelineCheckpointStatus(null);
    }
  };

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadSavedProjects();
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, []);

  const loadWorkflowPlan = async (
    options?: {
      projectId?: string | null;
      repo?: string | null;
      addChatMessage?: boolean;
    },
  ): Promise<WorkflowPlanResponse | null> => {
    const projectId = options?.projectId ?? selectedProjectId;
    const repo = options?.repo ?? repoUrl;

    if (!projectId && !repo) {
      appendAssistantMessage(
        "I need a saved project or repository URL before I can plan the full pipeline.",
        "missing_context",
      );

      return null;
    }

    setIsWorkflowLoading(true);

    try {
      const response = await getWorkflowPlan({
        project_id: projectId || null,
        repo_url: projectId ? null : repo || null,
      });

      setWorkflowPlan(response);

      if (options?.addChatMessage !== false) {
        appendAssistantMessage(formatWorkflowPlanMessage(response), response.status);
      }

      return response;
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Could not load workflow plan.";

      appendAssistantMessage(`Could not load workflow plan.\n\n${message}`, "failed");

      return null;
    } finally {
      setIsWorkflowLoading(false);
    }
  };

  const hydrateFromProjectContext = (context: ProjectContext) => {
    setProjectContext(context);

    const memoryProject = context.project;
    const deployment = context.latest_deployment;
    const latestPrUrl = findLatestPullRequestUrl(context.latest_artifacts);

    setRepoUrl(memoryProject.repo_url ?? "");
    setResourceGroup(
      memoryProject.azure_resource_group ?? deployment?.resource_group ?? "",
    );
    setAppName(memoryProject.azure_app_name ?? deployment?.app_name ?? "");
    setPullRequestUrl(latestPrUrl ?? "");
  };

  const hydrateFromResult = (result: CloudMindChatResult) => {
    setLatestResult(result);
    setLatestToolResult(result.tool_result ?? null);
    setConversationState(result.conversation_state ?? null);
    setProjectContext(result.project_context ?? null);

    const state = result.conversation_state ?? {};
    const memoryProject = result.project_context?.project;
    const deployment = result.project_context?.latest_deployment;

    const nextRepoUrl = state.repo_url ?? memoryProject?.repo_url;
    const nextResourceGroup =
      state.resource_group ??
      memoryProject?.azure_resource_group ??
      deployment?.resource_group;
    const nextAppName =
      state.app_name ?? memoryProject?.azure_app_name ?? deployment?.app_name;
    const nextPullRequestUrl =
      state.latest_pr_url ??
      findLatestPullRequestUrl(result.project_context?.latest_artifacts ?? []);

    if (nextRepoUrl) {
      setRepoUrl(nextRepoUrl);
    }

    if (nextResourceGroup) {
      setResourceGroup(nextResourceGroup);
    }

    if (nextAppName) {
      setAppName(nextAppName);
    }

    if (nextPullRequestUrl) {
      setPullRequestUrl(nextPullRequestUrl);
    }
  };

  const selectSavedProject = async (selectedProject: ProjectMemoryProject) => {
    setIsProjectsLoading(true);
    setPipelineRunId(null);
    setPipelineCheckpointStatus(null);

    try {
      const response = await getProject(selectedProject.id);
      hydrateFromProjectContext(response.context);
      setProjectMode("custom");

      await Promise.all([
        loadWorkflowPlan({
          projectId: response.project.id,
          repo: response.project.repo_url,
          addChatMessage: false,
        }),
        restoreLatestPipelineRun(response.project.id),
      ]);

      appendAssistantMessage(
        `Loaded saved project from PostgreSQL memory.\n\nProject: ${
          response.project.name ?? response.project.repo_name
        }\nRepository: ${response.project.repo_url}`,
        "loaded",
      );
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Could not load saved project.";

      appendAssistantMessage(`Could not load saved project.\n\n${message}`, "failed");
    } finally {
      setIsProjectsLoading(false);
    }
  };

  const executeChatCommand = async (
    content: string,
    options?: {
      addUserMessage?: boolean;
    },
  ): Promise<CloudMindChatResult | null> => {
    if (options?.addUserMessage !== false) {
      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        timestamp: nowLabel(),
      };

      setMessages((current) => [...current, userMessage]);
    }

    setInput("");
    setIsLoading(true);

    try {
      const response = await sendCloudMindMessage({
        message: content,
        session_id: sessionId,
        repo_url: repoUrl || null,
        resource_group: resourceGroup || null,
        app_name: appName || null,
        pull_request_url: pullRequestUrl || null,
        approval_confirmed: approvalConfirmed,
        context: {
          project_mode: projectMode,
          frontend_phase: "phase_21b_llm_conversation_agent",
        },
      });

      const result = response.result;

      setSessionId(result.session_id);
      hydrateFromResult(result);
      void loadSavedProjects();

      const nextProjectId = result.project_id ?? result.project_context?.project?.id;
      const nextRepo = result.conversation_state?.repo_url ?? repoUrl;

      if (nextProjectId || nextRepo) {
        void loadWorkflowPlan({
          projectId: nextProjectId,
          repo: nextRepo,
          addChatMessage: false,
        });
      }

      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: result.assistant_message || response.message,
        intent: result.intent,
        toolName: result.action?.tool_name,
        aiProvider: getString(result.tool_result, "provider"),
        aiModel: getString(result.tool_result, "model"),
        aiFallback: getBoolean(result.tool_result, "fallback_used") ?? false,
        status:
          getString(result.tool_result, "status") ??
          result.conversation_state?.latest_result_status ??
          result.status,
        timestamp: nowLabel(),
      };

      setMessages((current) => [...current, assistantMessage]);

      return result;
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "CloudMind frontend could not reach the backend.";

      appendAssistantMessage(`Request failed.\n\n${message}`, "failed");

      return null;
    } finally {
      setIsLoading(false);
    }
  };

  const sendMessage = async (
    messageOverride?: string,
  ): Promise<CloudMindChatResult | null> => {
    const content = (messageOverride ?? input).trim();

    if (!content || isLoading || isWorkflowLoading || isPipelineRunning) {
      return null;
    }

    if (content === "__workflow_plan__") {
      await loadWorkflowPlan({ addChatMessage: true });
      return null;
    }

    if (content === "__run_full_pipeline__") {
      await runFullPipeline();
      return null;
    }

    return executeChatCommand(content, { addUserMessage: true });
  };

  const runNextWorkflowStep = async () => {
    const nextMessage = workflowPlan?.next_step?.user_message;

    if (!nextMessage) {
      return;
    }

    await executeChatCommand(nextMessage, { addUserMessage: true });
  };

  const runFullPipeline = async () => {
    if (isPipelineRunning || isLoading || isWorkflowLoading) {
      return;
    }

    if (!pipelineRunId && !selectedProjectId && !repoUrl) {
      appendAssistantMessage(
        "I need a saved project or repository URL before I can start a pipeline run.",
        "missing_context",
      );
      return;
    }

    setIsPipelineRunning(true);

    appendAssistantMessage(
      pipelineRunId
        ? `Resuming saved pipeline run ${pipelineRunId}. CloudMind will verify its current checkpoint before taking another action.`
        : "Starting a durable pipeline run. CloudMind will save every checkpoint and pause for PR review, CI, image publication, or human approval when required.",
      pipelineRunId ? "pipeline_resuming" : "pipeline_started",
    );

    try {
      const result = await runOrResumePipeline({
        run_id: pipelineRunId,
        project_id: selectedProjectId,
        repo_url: repoUrl || null,
        resource_group: resourceGroup || null,
        app_name: appName || null,
        app_url:
          latestDeployment?.url ?? conversationState?.latest_app_url ?? null,
        health_path: conversationState?.health_path ?? null,
        pull_request_url: pullRequestUrl || null,
        approval_confirmed: approvalConfirmed,
        max_steps: 8,
        dry_run: false,
        run_optional: false,
        run_optional_reporting: true,
        stop_after_gitops: true,
        overwrite: true,
        publish_to_github: true,
        session_id: sessionId,
      });

      const activeRun =
        result.pipeline_run && !isTerminalPipelineRun(result.pipeline_run)
          ? result.pipeline_run
          : null;

      setPipelineRunId(activeRun?.id ?? null);
      setPipelineCheckpointStatus(result.checkpoint_status ?? result.status);
      setApprovalConfirmed(false);
      hydrateFromPipelineResult(result);
      appendAssistantMessage(formatPipelineRunMessage(result), result.status);
      void loadSavedProjects();

      const nextProjectId =
        result.project_id ?? getString(result.pipeline_context, "project_id");
      const nextRepo = result.repo_url ?? getString(result.pipeline_context, "repo_url");

      if (nextProjectId) {
        try {
          const projectResponse = await getProject(nextProjectId);
          hydrateFromProjectContext(projectResponse.context);
        } catch {
          // The pipeline response still contains enough context to keep the UI usable.
        }
      }

      if (result.workflow_plan) {
        setWorkflowPlan(result.workflow_plan);
      } else if (nextProjectId || nextRepo) {
        await loadWorkflowPlan({
          projectId: nextProjectId,
          repo: nextRepo,
          addChatMessage: false,
        });
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "CloudMind could not run or resume the saved pipeline.";

      appendAssistantMessage(`Pipeline request failed.\n\n${message}`, "failed");
    } finally {
      setIsPipelineRunning(false);
    }
  };

  const hydrateFromPipelineResult = (result: PipelineRunResponse) => {
    const context = result.pipeline_context;
    const nextRepoUrl = result.repo_url ?? getString(context, "repo_url");
    const nextResourceGroup = getString(context, "resource_group");
    const nextAppName = getString(context, "app_name");
    const nextPullRequestUrl =
      result.pipeline_run?.pull_request_url ??
      getString(context, "pull_request_url");

    if (nextRepoUrl) {
      setRepoUrl(nextRepoUrl);
    }

    if (nextResourceGroup) {
      setResourceGroup(nextResourceGroup);
    }

    if (nextAppName) {
      setAppName(nextAppName);
    }

    if (nextPullRequestUrl) {
      setPullRequestUrl(nextPullRequestUrl);
    }
  };

  const useDemoProject = () => {
    setProjectMode("demo");
    setRepoUrl(demoProject.repoUrl);
    setResourceGroup(demoProject.resourceGroup);
    setAppName(demoProject.appName);
    setPullRequestUrl(demoProject.pullRequestUrl);
    setWorkflowPlan(null);
    setPipelineRunId(null);
    setPipelineCheckpointStatus(null);
  };

  const useNewProject = () => {
    setProjectMode("custom");
    setRepoUrl(emptyProject.repoUrl);
    setResourceGroup(emptyProject.resourceGroup);
    setAppName(emptyProject.appName);
    setPullRequestUrl(emptyProject.pullRequestUrl);
    setProjectContext(null);
    setConversationState(null);
    setLatestResult(null);
    setLatestToolResult(null);
    setWorkflowPlan(null);
    setPipelineRunId(null);
    setPipelineCheckpointStatus(null);
    setSessionId(createSessionId());
  };

  const clearChat = () => {
    setMessages([
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content:
          "Chat cleared locally. PostgreSQL project memory is still preserved.",
        timestamp: nowLabel(),
      },
    ]);
  };

  return (
    <main className="h-screen overflow-hidden px-4 py-4 text-slate-100 md:px-5">
      <div className="mx-auto grid h-full max-w-[1900px] gap-4 xl:grid-cols-[340px_minmax(640px,1fr)_420px]">
        <aside className="custom-scrollbar min-h-0 space-y-4 overflow-y-auto pr-1">
          <BrandCard workflowPlan={workflowPlan} />

          <SavedProjectsPanel
            projects={savedProjects}
            selectedProjectId={selectedProjectId}
            isLoading={isProjectsLoading}
            onRefresh={() => void loadSavedProjects()}
            onSelect={(savedProject) => void selectSavedProject(savedProject)}
          />

          <SectionCard
            title="Project Context"
            icon={<Database className="h-4 w-4" />}
            action={
              <StatusPill
                value={projectMode === "demo" ? "Demo" : "Custom"}
                compact
              />
            }
          >
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={useDemoProject}
                className="rounded-2xl border border-blue-400/25 bg-blue-500/10 px-3 py-2.5 text-sm text-blue-100 transition hover:bg-blue-500/20"
              >
                Demo Project
              </button>
              <button
                onClick={useNewProject}
                className="rounded-2xl border border-slate-700/80 bg-slate-950/70 px-3 py-2.5 text-sm text-slate-200 transition hover:bg-slate-800"
              >
                New Project
              </button>
            </div>

            <div className="mt-4 space-y-3">
              <Field
                label="GitHub repository"
                value={repoUrl}
                onChange={setRepoUrl}
                placeholder="https://github.com/Hedi808/H-M.git"
              />
              <Field
                label="Azure resource group"
                value={resourceGroup}
                onChange={setResourceGroup}
                placeholder="rg-cloudmind-h-m"
              />
              <Field
                label="Azure app name"
                value={appName}
                onChange={setAppName}
                placeholder="h-m-backend"
              />
              <Field
                label="Pull request URL"
                value={pullRequestUrl}
                onChange={setPullRequestUrl}
                placeholder="https://github.com/.../pull/1"
              />
            </div>

            <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-2xl border border-amber-400/25 bg-amber-400/10 p-3">
              <input
                type="checkbox"
                checked={approvalConfirmed}
                onChange={(event) =>
                  setApprovalConfirmed(event.currentTarget.checked)
                }
                className="mt-1 h-4 w-4 accent-amber-400"
              />
              <span>
                <span className="block text-sm font-semibold text-amber-100">
                  Human approval confirmed
                </span>
                <span className="mt-1 block text-xs leading-5 text-amber-100/70">
                  Required for GitHub PR creation and Azure runtime deployment.
                </span>
              </span>
            </label>
          </SectionCard>

          <SectionCard
            title="Repository Tools"
            icon={<Code2 className="h-4 w-4" />}
          >
            <ToolButtonGrid
              actions={repositoryActions}
              onRun={sendMessage}
              disabled={isLoading || isWorkflowLoading || isPipelineRunning}
            />
          </SectionCard>

          <SectionCard title="Runtime Tools" icon={<Cloud className="h-4 w-4" />}>
            <ToolButtonGrid
              actions={runtimeActions}
              onRun={sendMessage}
              disabled={isLoading || isWorkflowLoading || isPipelineRunning}
              highlightSecond
            />
          </SectionCard>
        </aside>

        <section className="glass-card flex min-h-0 flex-col overflow-hidden rounded-[2rem]">
          <div className="border-b border-slate-700/40 px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <div className="rounded-2xl border border-blue-400/20 bg-blue-400/10 p-2">
                    <Brain className="h-4 w-4 text-blue-200" />
                  </div>
                  <div>
                    <h1 className="text-base font-semibold text-slate-50">
                      CloudMind Console
                    </h1>
                    <p className="mt-0.5 text-xs text-slate-400">
                      Safe conversational DevOps with memory and workflow execution.
                    </p>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <StatusPill
                  value={
                    isPipelineRunning
                      ? "Pipeline running"
                      : pipelineCheckpointStatus ?? workflowPlan?.status ?? "Ready"
                  }
                  compact
                />
                <button
                  onClick={clearChat}
                  className="rounded-2xl border border-slate-700/80 bg-slate-950/70 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800"
                >
                  Clear
                </button>
                <button
                  onClick={() => sendMessage("What can you do?")}
                  disabled={isLoading || isWorkflowLoading || isPipelineRunning}
                  className="rounded-2xl border border-blue-400/25 bg-blue-500/10 px-3 py-2 text-sm text-blue-100 transition hover:bg-blue-500/20 disabled:opacity-50"
                >
                  Help
                </button>
              </div>
            </div>
          </div>

          <div className="grid-noise custom-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5">
            <AnimatePresence initial={false}>
              {messages.map((message) => (
                <ChatBubble key={message.id} message={message} />
              ))}
            </AnimatePresence>

            {(isLoading || isWorkflowLoading || isPipelineRunning) && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-3 rounded-3xl border border-blue-400/20 bg-blue-500/10 px-4 py-3 text-sm text-blue-100"
              >
                <Loader2 className="h-4 w-4 animate-spin text-blue-300" />
                {isPipelineRunning
                  ? "CloudMind is running the full pipeline executor..."
                  : isWorkflowLoading
                    ? "CloudMind is planning the workflow from PostgreSQL memory..."
                    : "CloudMind AI is reasoning with the project context..."}
              </motion.div>
            )}

            <div ref={chatEndRef} />
          </div>

          <div className="border-t border-slate-700/40 bg-slate-950/70 p-4">
            <div className="flex gap-3">
              <textarea
                value={input}
                onChange={(event) => setInput(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void sendMessage();
                  }
                }}
                placeholder="Ask CloudMind to analyze, deploy, verify, run pipeline, or generate the final report..."
                className="custom-scrollbar min-h-[54px] max-h-32 flex-1 resize-none rounded-3xl border border-slate-700/80 bg-slate-950/90 px-4 py-3 text-sm text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-blue-400"
              />
              <button
                onClick={() => sendMessage()}
                disabled={
                  isLoading ||
                  isWorkflowLoading ||
                  isPipelineRunning ||
                  !input.trim()
                }
                className="flex h-[54px] w-[54px] items-center justify-center rounded-3xl bg-blue-500 text-white shadow-lg shadow-blue-500/20 transition hover:bg-blue-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLoading || isWorkflowLoading || isPipelineRunning ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <Send className="h-5 w-5" />
                )}
              </button>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              {(latestResult?.suggested_actions ?? []).map((suggestion) => (
                <button
                  key={`${suggestion.label}-${suggestion.message}`}
                  onClick={() => sendMessage(suggestion.message)}
                  disabled={isLoading || isWorkflowLoading || isPipelineRunning}
                  className="rounded-full border border-slate-700/80 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 transition hover:bg-slate-800 disabled:opacity-50"
                >
                  {suggestion.label}
                </button>
              ))}
            </div>
          </div>
        </section>

        <aside className="custom-scrollbar min-h-0 space-y-4 overflow-y-auto pr-1">
          <MissionStatusPanel missionStatus={missionStatus} />

          <WorkflowPanel
            workflowPlan={workflowPlan}
            isLoading={isWorkflowLoading}
            isPipelineRunning={isPipelineRunning}
            approvalConfirmed={approvalConfirmed}
            pipelineRunId={pipelineRunId}
            pipelineCheckpointStatus={pipelineCheckpointStatus}
            onRefresh={() => void loadWorkflowPlan({ addChatMessage: true })}
            onRunNext={() => void runNextWorkflowStep()}
            onRunPipeline={() => void runFullPipeline()}
          />

          <ProjectMemoryPanel
            project={project}
            conversationState={conversationState}
          />

          <DeploymentPanel deployment={latestDeployment} />

          <ActionHistoryPanel actions={latestActions} />

          <ArtifactPanel artifacts={latestArtifacts} />

          <SectionCard
            title="Latest Tool Result"
            icon={<FileText className="h-4 w-4" />}
          >
            <JsonPreview
              value={latestToolResult ?? { message: "No tool result yet." }}
            />
          </SectionCard>
        </aside>
      </div>
    </main>
  );
}

function BrandCard({ workflowPlan }: { workflowPlan: WorkflowPlanResponse | null }) {
  return (
    <div className="relative overflow-hidden rounded-[2rem] border border-blue-400/20 bg-gradient-to-br from-blue-500/20 via-slate-950 to-emerald-500/10 p-5 shadow-2xl shadow-black/20">
      <div className="absolute -right-12 -top-12 h-36 w-36 rounded-full bg-blue-500/20 blur-3xl" />
      <div className="absolute -bottom-16 left-4 h-32 w-32 rounded-full bg-emerald-500/10 blur-3xl" />

      <div className="relative flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-3xl bg-blue-500/20 ring-1 ring-blue-300/20">
          <Bot className="h-7 w-7 text-blue-200" />
        </div>
        <div>
          <h2 className="text-xl font-bold tracking-tight">CloudMind</h2>
          <p className="text-sm text-slate-300">Multi-agent DevOps OS</p>
        </div>
      </div>

      <p className="relative mt-4 text-sm leading-6 text-slate-300">
        From repository analysis to GitOps, Azure deployment, health checks,
        incident analysis, and persistent PostgreSQL memory.
      </p>

      <div className="relative mt-5 grid grid-cols-3 gap-2 text-center text-xs">
        <MiniStat label="GitOps" value="PR" />
        <MiniStat label="Cloud" value="Azure" />
        <MiniStat
          label="Progress"
          value={`${workflowPlan?.summary.progress_percent ?? 0}%`}
        />
      </div>
    </div>
  );
}

function SavedProjectsPanel({
  projects,
  selectedProjectId,
  isLoading,
  onRefresh,
  onSelect,
}: {
  projects: ProjectMemoryProject[];
  selectedProjectId: string | null;
  isLoading: boolean;
  onRefresh: () => void;
  onSelect: (project: ProjectMemoryProject) => void;
}) {
  return (
    <SectionCard
      title="Saved Projects"
      icon={<Database className="h-4 w-4" />}
      action={
        <IconButton
          label={isLoading ? "Loading" : "Refresh"}
          onClick={onRefresh}
          disabled={isLoading}
        />
      }
    >
      {projects.length === 0 ? (
        <EmptyState text="No saved projects yet. Analyze a repository first." />
      ) : (
        <div className="space-y-2">
          {projects.map((item) => {
            const selected = item.id === selectedProjectId;

            return (
              <button
                key={item.id}
                onClick={() => onSelect(item)}
                className={`w-full rounded-3xl border p-3 text-left transition ${
                  selected
                    ? "border-blue-400/60 bg-blue-500/15 shadow-lg shadow-blue-500/10"
                    : "border-slate-800 bg-slate-950/50 hover:border-blue-400/40 hover:bg-slate-900"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-100">
                      {item.name ?? item.repo_name ?? "Unnamed project"}
                    </p>
                    <p className="mt-1 truncate text-xs text-slate-500">
                      {item.detected_framework ?? "Unknown"} ·{" "}
                      {item.project_type ?? "unknown"}
                    </p>
                  </div>
                  <StatusPill
                    value={item.azure_app_url ? "Deployed" : "Tracked"}
                    compact
                  />
                </div>

                <p className="mt-2 truncate text-xs text-slate-400">
                  {item.repo_url}
                </p>
              </button>
            );
          })}
        </div>
      )}
    </SectionCard>
  );
}

function MissionStatusPanel({
  missionStatus,
}: {
  missionStatus: {
    status: string;
    recommendation: string;
    azureHealthy: string;
    logsAvailable: string;
    incidentDetected: string;
    prState: string;
    ci: string;
  };
}) {
  return (
    <SectionCard
      title="Mission Status"
      icon={<Zap className="h-4 w-4" />}
      action={<StatusPill value={missionStatus.status} compact />}
    >
      <div className="rounded-3xl border border-emerald-400/20 bg-emerald-400/10 p-4">
        <p className="text-xs uppercase tracking-[0.2em] text-emerald-200/70">
          Recommendation
        </p>
        <p className="mt-2 text-sm font-semibold leading-6 text-emerald-50">
          {missionStatus.recommendation}
        </p>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <HealthTile label="Azure" value={missionStatus.azureHealthy} />
        <HealthTile label="Incident" value={missionStatus.incidentDetected} />
        <HealthTile label="PR" value={missionStatus.prState} />
        <HealthTile label="CI/CD" value={missionStatus.ci} />
      </div>
    </SectionCard>
  );
}

function WorkflowPanel({
  workflowPlan,
  isLoading,
  isPipelineRunning,
  approvalConfirmed,
  pipelineRunId,
  pipelineCheckpointStatus,
  onRefresh,
  onRunNext,
  onRunPipeline,
}: {
  workflowPlan: WorkflowPlanResponse | null;
  isLoading: boolean;
  isPipelineRunning: boolean;
  approvalConfirmed: boolean;
  pipelineRunId: string | null;
  pipelineCheckpointStatus: string | null;
  onRefresh: () => void;
  onRunNext: () => void;
  onRunPipeline: () => void;
}) {
  const nextStep = workflowPlan?.next_step ?? null;
  const requiresApproval = nextStep?.requires_approval === true;
  const approvalMissing = requiresApproval && !approvalConfirmed;
  const pipelineButtonLabel = isPipelineRunning
    ? "Running Pipeline..."
    : pipelineRunId
      ? "Resume Saved Pipeline"
      : "Run Full Pipeline";

  return (
    <SectionCard
      title="Workflow Plan"
      icon={<Zap className="h-4 w-4" />}
      action={
        <IconButton
          label={isLoading ? "Planning" : "Refresh"}
          onClick={onRefresh}
          disabled={isLoading || isPipelineRunning}
        />
      }
    >
      {!workflowPlan ? (
        <div className="space-y-3">
          <EmptyState text="No workflow plan yet. Click Run Pipeline or Plan Pipeline." />
          {pipelineCheckpointStatus && (
            <PipelineCheckpointCard
              runId={pipelineRunId}
              checkpointStatus={pipelineCheckpointStatus}
            />
          )}
          <PrimaryButton
            onClick={onRunPipeline}
            disabled={isLoading || isPipelineRunning}
            label={pipelineButtonLabel}
          />
        </div>
      ) : (
        <div className="space-y-4">
          <WorkflowChart workflowPlan={workflowPlan} />

          {pipelineCheckpointStatus && (
            <PipelineCheckpointCard
              runId={pipelineRunId}
              checkpointStatus={pipelineCheckpointStatus}
            />
          )}

          <PrimaryButton
            onClick={onRunPipeline}
            disabled={isLoading || isPipelineRunning}
            label={pipelineButtonLabel}
          />

          {nextStep && (
            <div className="rounded-3xl border border-blue-400/25 bg-blue-500/10 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-blue-100">
                    Next: {nextStep.title}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-blue-100/70">
                    {nextStep.reason}
                  </p>
                </div>
                <StatusPill
                  value={requiresApproval ? "Approval" : "Safe"}
                  compact
                />
              </div>

              {approvalMissing && (
                <p className="mt-3 rounded-2xl border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-xs leading-5 text-amber-100">
                  Tick the approval checkbox before running this step.
                </p>
              )}

              {nextStep.user_message && (
                <button
                  onClick={onRunNext}
                  disabled={isLoading || isPipelineRunning || approvalMissing}
                  className="mt-3 w-full rounded-2xl border border-blue-400/30 bg-blue-500/20 px-3 py-2 text-sm font-medium text-blue-50 transition hover:bg-blue-500/30 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Run Next Recommended Step
                </button>
              )}
            </div>
          )}

          <div className="space-y-2">
            {workflowPlan.steps.map((step, index) => (
              <WorkflowStepCard key={step.id} step={step} index={index + 1} />
            ))}
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function PipelineCheckpointCard({
  runId,
  checkpointStatus,
}: {
  runId: string | null;
  checkpointStatus: string;
}) {
  return (
    <div className="rounded-3xl border border-violet-400/25 bg-violet-500/10 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-[0.16em] text-violet-200/70">
            Persisted pipeline
          </p>
          <p className="mt-1 truncate font-mono text-xs text-violet-100">
            {runId ?? "Latest run"}
          </p>
        </div>
        <StatusPill value={formatStatusLabel(checkpointStatus)} compact />
      </div>
    </div>
  );
}

function WorkflowChart({
  workflowPlan,
}: {
  workflowPlan: WorkflowPlanResponse;
}) {
  const progress = Math.min(
    Math.max(workflowPlan.summary.progress_percent, 0),
    100,
  );
  const radius = 43;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (progress / 100) * circumference;

  return (
    <div className="rounded-[1.7rem] border border-slate-800 bg-slate-950/60 p-4">
      <div className="flex items-center gap-4">
        <div className="relative h-28 w-28 shrink-0">
          <svg className="h-28 w-28 -rotate-90" viewBox="0 0 112 112">
            <circle
              cx="56"
              cy="56"
              r={radius}
              stroke="rgba(30, 41, 59, 0.95)"
              strokeWidth="10"
              fill="transparent"
            />
            <circle
              cx="56"
              cy="56"
              r={radius}
              stroke="rgb(52, 211, 153)"
              strokeWidth="10"
              fill="transparent"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-bold text-slate-50">{progress}%</span>
            <span className="text-[11px] text-slate-500">ready</span>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-50">
                {workflowPlan.workflow?.title ?? "Deployment Pipeline"}
              </p>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                {workflowPlan.message}
              </p>
            </div>
            <StatusPill value={workflowPlan.status} compact />
          </div>

          <div className="mt-4 grid grid-cols-4 gap-2">
            <MiniStat label="Done" value={String(workflowPlan.summary.completed)} />
            <MiniStat
              label="Required"
              value={String(workflowPlan.summary.required)}
            />
            <MiniStat
              label="Blocked"
              value={String(workflowPlan.summary.blocked)}
            />
            <MiniStat
              label="Optional"
              value={String(workflowPlan.summary.optional)}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function WorkflowStepCard({
  step,
  index,
}: {
  step: WorkflowStep;
  index: number;
}) {
  return (
    <details className="soft-card rounded-3xl p-3">
      <summary className="cursor-pointer list-none">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl border border-slate-700 bg-slate-950 text-xs font-semibold text-slate-300">
            {index}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-100">
              {step.title}
            </p>
            <p className="mt-1 truncate text-xs text-slate-500">
              {step.category} ·{" "}
              {step.depends_on.length > 0
                ? `depends on ${step.depends_on.join(", ")}`
                : "no dependency"}
            </p>
          </div>
          <StatusPill value={step.status} compact />
        </div>
      </summary>

      <div className="mt-3 space-y-2 pl-11 text-xs leading-5 text-slate-400">
        <p>{step.description}</p>
        <p className="text-slate-500">{step.reason}</p>

        {step.requires_approval && (
          <StatusPill value="Requires approval" compact />
        )}

        {step.evidence.length > 0 && (
          <div className="rounded-2xl bg-slate-950/80 p-3">
            <p className="mb-1 text-slate-500">Evidence</p>
            <ul className="list-inside list-disc space-y-1">
              {step.evidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}

function SectionCard({
  title,
  icon,
  action,
  children,
}: {
  title: string;
  icon: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="glass-card rounded-[2rem] p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
          <span className="text-blue-300">{icon}</span>
          {title}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  placeholder: string;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-slate-400">
        {label}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
        placeholder={placeholder}
        className="w-full rounded-2xl border border-slate-700/80 bg-slate-950/80 px-3 py-2.5 text-sm text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-blue-400"
      />
    </label>
  );
}

function ToolButtonGrid({
  actions,
  onRun,
  disabled,
  highlightSecond = false,
}: {
  actions: {
    label: string;
    message: string;
    icon: LucideIcon;
  }[];
  onRun: (message: string) => Promise<CloudMindChatResult | null>;
  disabled: boolean;
  highlightSecond?: boolean;
}) {
  return (
    <div className="grid gap-2">
      {actions.map((action, index) => {
        const Icon = action.icon;
        const highlighted = highlightSecond && index === 1;

        return (
          <button
            key={action.label}
            onClick={() => void onRun(action.message)}
            disabled={disabled}
            className={`flex items-center gap-3 rounded-2xl border px-3 py-2.5 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${
              highlighted
                ? "border-emerald-400/25 bg-emerald-500/15 text-emerald-50 hover:bg-emerald-500/25"
                : "border-slate-700/80 bg-slate-950/60 text-slate-200 hover:border-blue-400/40 hover:bg-slate-900"
            }`}
          >
            <Icon className="h-4 w-4 text-blue-300" />
            <span>{action.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[86%] rounded-[1.6rem] border px-4 py-3 ${
          isUser
            ? "border-blue-400/25 bg-blue-500/15"
            : "border-slate-700/70 bg-slate-950/75"
        }`}
      >
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-400">
            {isUser ? (
              <Code2 className="h-3.5 w-3.5" />
            ) : (
              <Bot className="h-3.5 w-3.5 text-blue-300" />
            )}
            {isUser ? "You" : "CloudMind"}
          </div>
          <span className="text-[11px] text-slate-500">
            {message.timestamp}
          </span>
        </div>

        <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6 text-slate-100">
          {message.content}
        </pre>

        {(message.intent ||
          message.toolName ||
          message.aiProvider ||
          message.aiModel ||
          message.status) && (
          <div className="mt-3 flex flex-wrap gap-2">
            {message.intent && <StatusPill value={`Intent: ${message.intent}`} />}
            {message.toolName && (
              <StatusPill value={`Tool: ${message.toolName}`} />
            )}
            {message.aiProvider && (
              <StatusPill
                value={`${message.aiFallback ? "Fallback" : "AI"}: ${message.aiProvider}${message.aiModel ? ` / ${message.aiModel}` : ""}`}
              />
            )}
            {message.status && <StatusPill value={message.status} />}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function ProjectMemoryPanel({
  project,
  conversationState,
}: {
  project: ProjectMemoryProject | null;
  conversationState: ConversationState | null;
}) {
  return (
    <SectionCard
      title="Project Memory"
      icon={<Database className="h-4 w-4" />}
      action={<StatusPill value={project ? "Synced" : "Waiting"} compact />}
    >
      <Metric
        label="Project ID"
        value={project?.id ?? conversationState?.project_id ?? "Not available"}
      />
      <Metric
        label="Name"
        value={project?.name ?? conversationState?.project_name ?? "Not available"}
      />
      <Metric
        label="Repo"
        value={project?.repo_url ?? conversationState?.repo_url ?? "Not available"}
      />
      <Metric
        label="Language"
        value={project?.detected_language ?? "Not available"}
      />
      <Metric
        label="Framework"
        value={project?.detected_framework ?? "Not available"}
      />
      <Metric label="Port" value={project?.port?.toString() ?? "Not available"} />
      <Metric
        label="GHCR image"
        value={project?.ghcr_image ?? conversationState?.ghcr_image ?? "Not available"}
      />
      <Metric
        label="Azure URL"
        value={
          project?.azure_app_url ??
          conversationState?.latest_app_url ??
          "Not available"
        }
        isLink
      />
    </SectionCard>
  );
}

function DeploymentPanel({
  deployment,
}: {
  deployment: ProjectDeploymentState | null;
}) {
  return (
    <SectionCard
      title="Latest Deployment"
      icon={<Cloud className="h-4 w-4" />}
      action={
        <StatusPill value={deployment?.health_status ?? "Waiting"} compact />
      }
    >
      <Metric label="Provider" value={deployment?.provider ?? "Not available"} />
      <Metric
        label="Resource group"
        value={deployment?.resource_group ?? "Not available"}
      />
      <Metric label="App name" value={deployment?.app_name ?? "Not available"} />
      <Metric
        label="Environment"
        value={deployment?.environment_name ?? "Not available"}
      />
      <Metric label="Image" value={deployment?.image ?? "Not available"} />
      <Metric label="URL" value={deployment?.url ?? "Not available"} isLink />
      <Metric
        label="Last checked"
        value={formatDate(deployment?.last_checked_at)}
      />
    </SectionCard>
  );
}

function ActionHistoryPanel({ actions }: { actions: ProjectActionRun[] }) {
  return (
    <SectionCard title="Action History" icon={<History className="h-4 w-4" />}>
      {actions.length === 0 ? (
        <EmptyState text="No stored action runs yet." />
      ) : (
        <div className="space-y-2">
          {actions.slice(0, 7).map((action) => (
            <div
              key={action.id}
              className="rounded-2xl border border-slate-800 bg-slate-950/60 p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-100">
                    {action.action_type}
                  </p>
                  <p className="mt-1 truncate text-xs text-slate-500">
                    {action.tool_name ?? "No tool"} ·{" "}
                    {formatDate(action.started_at)}
                  </p>
                </div>
                <StatusPill value={action.status} compact />
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

function ArtifactPanel({ artifacts }: { artifacts: ProjectArtifact[] }) {
  return (
    <SectionCard title="Artifacts" icon={<GitPullRequest className="h-4 w-4" />}>
      {artifacts.length === 0 ? (
        <EmptyState text="No stored artifacts yet." />
      ) : (
        <div className="space-y-2">
          {artifacts.slice(0, 7).map((artifact) => (
            <div
              key={artifact.id}
              className="rounded-2xl border border-slate-800 bg-slate-950/60 p-3"
            >
              <div className="flex items-start gap-3">
                <ArtifactIcon type={artifact.artifact_type} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-100">
                    {artifact.name ?? artifact.artifact_type}
                  </p>
                  <p className="mt-1 truncate text-xs text-slate-500">
                    {artifact.artifact_type} · {formatDate(artifact.created_at)}
                  </p>

                  {artifact.path && (
                    <p className="mt-2 truncate rounded-xl bg-slate-950 px-2 py-1 text-xs text-slate-400">
                      {artifact.path}
                    </p>
                  )}

                  {artifact.url && (
                    <a
                      href={artifact.url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 inline-flex items-center gap-1 text-xs text-blue-300 hover:text-blue-200"
                    >
                      <LinkIcon className="h-3 w-3" />
                      Open artifact
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

function ArtifactIcon({ type }: { type: string }) {
  if (type.includes("pull_request")) {
    return <GitPullRequest className="mt-0.5 h-4 w-4 text-purple-300" />;
  }

  if (type.includes("deployment")) {
    return <Cloud className="mt-0.5 h-4 w-4 text-blue-300" />;
  }

  if (type.includes("incident")) {
    return <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-300" />;
  }

  return <FileText className="mt-0.5 h-4 w-4 text-slate-300" />;
}

function HealthTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-3">
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className="mt-1 truncate text-sm font-semibold text-slate-100">
        {value}
      </p>
    </div>
  );
}

function Metric({
  label,
  value,
  isLink = false,
}: {
  label: string;
  value: string;
  isLink?: boolean;
}) {
  const finalValue = value || "Not available";

  return (
    <div className="border-b border-slate-800/80 py-2 last:border-b-0">
      <p className="text-xs text-slate-500">{label}</p>
      {isLink && finalValue.startsWith("http") ? (
        <a
          href={finalValue}
          target="_blank"
          rel="noreferrer"
          className="mt-1 block break-words text-sm text-blue-300 hover:text-blue-200"
        >
          {finalValue}
        </a>
      ) : (
        <p className="mt-1 break-words text-sm text-slate-200">{finalValue}</p>
      )}
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-700/70 bg-slate-950/50 p-2.5">
      <p className="text-[10px] text-slate-500">{label}</p>
      <p className="mt-1 font-semibold text-slate-100">{value}</p>
    </div>
  );
}

function StatusPill({
  value,
  compact = false,
}: {
  value: string;
  compact?: boolean;
}) {
  const normalized = value.toLowerCase();

  const kind =
    normalized.includes("failed") || normalized.includes("error")
      ? "bad"
      : normalized.includes("warning") ||
          normalized.includes("unknown") ||
          normalized.includes("waiting") ||
          normalized.includes("not available") ||
          normalized.includes("blocked") ||
          normalized.includes("approval")
        ? "warn"
        : normalized.includes("healthy") ||
            normalized.includes("success") ||
            normalized.includes("deployed") ||
            normalized.includes("published") ||
            normalized.includes("synced") ||
            normalized.includes("ready") ||
            normalized.includes("loaded") ||
            normalized.includes("tracked") ||
            normalized.includes("completed") ||
            normalized.includes("complete")
          ? "good"
          : "neutral";

  const styles = {
    good: "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
    warn: "border-amber-400/30 bg-amber-400/10 text-amber-200",
    bad: "border-red-400/30 bg-red-400/10 text-red-200",
    neutral: "border-slate-700 bg-slate-900 text-slate-300",
  };

  const Icon =
    kind === "good"
      ? CheckCircle2
      : kind === "bad"
        ? XCircle
        : kind === "warn"
          ? AlertTriangle
          : RefreshCw;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border ${
        styles[kind]
      } ${compact ? "px-2 py-1 text-[11px]" : "px-2.5 py-1 text-xs"}`}
    >
      <Icon className={compact ? "h-3 w-3" : "h-3.5 w-3.5"} />
      {value}
    </span>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-center text-sm text-slate-500">
      {text}
    </div>
  );
}

function IconButton({
  label,
  onClick,
  disabled,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="rounded-full border border-slate-700/80 bg-slate-950/70 px-2.5 py-1 text-xs text-slate-300 transition hover:bg-slate-800 disabled:opacity-50"
    >
      {label}
    </button>
  );
}

function PrimaryButton({
  label,
  onClick,
  disabled,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="w-full rounded-2xl bg-emerald-500 px-3 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-500/15 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {label}
    </button>
  );
}

function JsonPreview({ value }: { value: unknown }) {
  return (
    <details className="group">
      <summary className="cursor-pointer rounded-2xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-900">
        View JSON
      </summary>
      <pre className="custom-scrollbar mt-3 max-h-[360px] overflow-auto rounded-2xl border border-slate-800 bg-slate-950 p-3 text-xs leading-5 text-slate-300">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}

function formatWorkflowPlanMessage(plan: WorkflowPlanResponse): string {
  const nextStep = plan.next_step
    ? `\n\nNext step: ${plan.next_step.title}\nReason: ${plan.next_step.reason}`
    : "";

  return `Workflow plan loaded.

Status: ${plan.status}
Progress: ${plan.summary.progress_percent}%
Completed: ${plan.summary.completed}/${plan.summary.total_steps}
Required: ${plan.summary.required}
Blocked: ${plan.summary.blocked}
Optional: ${plan.summary.optional}

${plan.message}${nextStep}`;
}

function formatPipelineRunMessage(result: PipelineRunResponse): string {
  const checkpoint = result.checkpoint_status
    ? `\nCheckpoint: ${formatStatusLabel(result.checkpoint_status)}`
    : "";
  const run = result.run_id ? `\nRun ID: ${result.run_id}` : "";
  const pullRequestUrl =
    result.pipeline_run?.pull_request_url ??
    getString(result.pipeline_context, "pull_request_url");
  const pullRequest = pullRequestUrl
    ? `\nPull request: ${pullRequestUrl}`
    : "";
  const executed = result.executed_steps.length
    ? `\n\nExecuted now:\n${result.executed_steps
        .map((step) => `- ${step.title}: ${step.message}`)
        .join("\n")}`
    : "";

  const guidance: Record<string, string> = {
    waiting_for_pr_merge:
      "Review and merge the pull request, then click Resume Saved Pipeline.",
    waiting_for_ci:
      "CI is still running. Click Resume Saved Pipeline to check it again.",
    waiting_for_image:
      "CloudMind is waiting for the GHCR image. Click Resume Saved Pipeline to recheck it.",
    waiting_for_deployment_approval:
      "Tick Human approval confirmed, then click Resume Saved Pipeline to deploy to Azure.",
    waiting_for_approval:
      "Tick Human approval confirmed, then click Resume Saved Pipeline.",
    pipeline_complete: "The required workflow is complete.",
    workflow_ready: "The required workflow is ready.",
    pipeline_failed: "Inspect the failed checkpoint before starting a new run.",
    active_incident_detected:
      "Deployment progression stopped because an active incident was detected.",
    checkpoint_error:
      "The run remains saved. Resolve the verification error, then resume it.",
  };
  const nextAction = guidance[result.status]
    ? `\n\nNext action: ${guidance[result.status]}`
    : "";

  return `${result.message}${run}${checkpoint}${pullRequest}${executed}${nextAction}`;
}

function isTerminalPipelineRun(run: PipelineRunRecord): boolean {
  return ["completed", "failed", "blocked_incident", "cancelled"].includes(
    run.status,
  );
}

function formatStatusLabel(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function findLatestPullRequestUrl(artifacts: ProjectArtifact[]): string | null {
  const prArtifact = artifacts.find(
    (artifact) => artifact.artifact_type === "github_pull_request",
  );

  if (!prArtifact) {
    return null;
  }

  return (
    prArtifact.url ??
    getString(prArtifact.metadata_json, "url") ??
    getString(prArtifact.metadata_json, "html_url") ??
    getString(prArtifact.metadata_json, "pull_request_url")
  );
}

function formatDate(value?: string | null) {
  if (!value) {
    return "Not available";
  }

  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function getString(
  source: Record<string, unknown> | null | undefined,
  key: string,
): string | null {
  const value = source?.[key];

  if (typeof value === "string") {
    return value;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return null;
}

function getBoolean(
  source: Record<string, unknown> | null | undefined,
  key: string,
): boolean | null {
  const value = source?.[key];

  if (typeof value === "boolean") {
    return value;
  }

  return null;
}
