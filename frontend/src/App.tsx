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
import type {
  ChatMessage,
  CloudMindChatResult,
  ConversationState,
  ProjectActionRun,
  ProjectArtifact,
  ProjectContext,
  ProjectDeploymentState,
  ProjectMemoryProject,
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
    label: "Analyze Active Project",
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
    label: "Deploy to Azure",
    message: "Deploy this app to Azure",
    icon: Rocket,
  },
  {
    label: "Check Azure Status",
    message: "Check Azure status",
    icon: Activity,
  },
  {
    label: "Analyze Incident",
    message: "Analyze incident for this Azure app",
    icon: ShieldCheck,
  },
  {
    label: "Plan Remediation",
    message: "Plan remediation for this Azure app",
    icon: AlertTriangle,
  },
  {
    label: "Final Demo Report",
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

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "CloudMind is ready. Add a GitHub repository, analyze it, publish DevOps changes through PRs, deploy to Azure, and track everything in PostgreSQL project memory.",
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
  const latestActions = projectContext?.latest_actions ?? [];
  const latestArtifacts = projectContext?.latest_artifacts ?? [];

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
          : "Unknown";

    const prArtifact = latestArtifacts.find(
      (artifact) => artifact.artifact_type === "github_pull_request",
    );

    return {
      status: latestStatus,
      recommendation:
        demoRecommendation ??
        deploymentRecommendation ??
        "Not available yet",
      azureHealthy: azureHealthy ? "Healthy" : "Unknown",
      logsAvailable: logsAvailable === true ? "Yes" : "Unknown",
      incidentDetected,
      prState: prArtifact?.url ? "PR tracked in memory" : "Not available yet",
      ci:
        latestActions.find((action) => action.action_type === "generate_cicd")
          ?.status ?? "Not available yet",
    };
  }, [
    conversationState,
    latestActions,
    latestArtifacts,
    latestDeployment,
    latestResult,
    latestToolResult,
  ]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

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
    const nextPullRequestUrl = state.latest_pr_url;

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

  const sendMessage = async (messageOverride?: string) => {
    const content = (messageOverride ?? input).trim();

    if (!content || isLoading) {
      return;
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      timestamp: nowLabel(),
    };

    setMessages((current) => [...current, userMessage]);
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
          frontend_phase: "phase_17_project_memory_dashboard",
        },
      });

      const result = response.result;

      setSessionId(result.session_id);
      hydrateFromResult(result);

      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: result.assistant_message || response.message,
        intent: result.intent,
        toolName: result.action?.tool_name,
        status:
          getString(result.tool_result, "status") ??
          result.conversation_state?.latest_result_status ??
          result.status,
        timestamp: nowLabel(),
      };

      setMessages((current) => [...current, assistantMessage]);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "CloudMind frontend could not reach the backend.";

      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `Request failed.\n\n${message}`,
          status: "failed",
          timestamp: nowLabel(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const useDemoProject = () => {
    setProjectMode("demo");
    setRepoUrl(demoProject.repoUrl);
    setResourceGroup(demoProject.resourceGroup);
    setAppName(demoProject.appName);
    setPullRequestUrl(demoProject.pullRequestUrl);
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
    <main className="min-h-screen px-4 py-4 text-slate-100 md:px-6">
      <div className="mx-auto grid max-w-[1800px] gap-4 xl:grid-cols-[360px_minmax(0,1fr)_430px]">
        <aside className="space-y-4">
          <BrandCard />

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
                className="rounded-xl border border-blue-400/30 bg-blue-500/10 px-3 py-2 text-sm text-blue-100 transition hover:bg-blue-500/20"
              >
                Demo Project
              </button>
              <button
                onClick={useNewProject}
                className="rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800"
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

            <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3">
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
              disabled={isLoading}
            />
          </SectionCard>

          <SectionCard title="Runtime Tools" icon={<Cloud className="h-4 w-4" />}>
            <ToolButtonGrid
              actions={runtimeActions}
              onRun={sendMessage}
              disabled={isLoading}
            />
          </SectionCard>
        </aside>

        <section className="flex min-h-[calc(100vh-2rem)] flex-col overflow-hidden rounded-3xl border border-slate-700/70 bg-slate-950/70 shadow-2xl shadow-black/30 backdrop-blur">
          <div className="border-b border-slate-800 px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <Brain className="h-5 w-5 text-blue-300" />
                  <h1 className="text-lg font-semibold">CloudMind Console</h1>
                </div>
                <p className="mt-1 text-sm text-slate-400">
                  Conversational DevOps with PostgreSQL project memory.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={clearChat}
                  className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800"
                >
                  Clear Chat
                </button>
                <button
                  onClick={() => sendMessage("What can you do?")}
                  disabled={isLoading}
                  className="rounded-xl border border-blue-400/30 bg-blue-500/10 px-3 py-2 text-sm text-blue-100 transition hover:bg-blue-500/20 disabled:opacity-50"
                >
                  Help
                </button>
              </div>
            </div>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
            <AnimatePresence initial={false}>
              {messages.map((message) => (
                <ChatBubble key={message.id} message={message} />
              ))}
            </AnimatePresence>

            {isLoading && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-3 rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-300"
              >
                <Loader2 className="h-4 w-4 animate-spin text-blue-300" />
                CloudMind is thinking, calling tools, and updating memory...
              </motion.div>
            )}

            <div ref={chatEndRef} />
          </div>

          <div className="border-t border-slate-800 p-4">
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
                placeholder="Ask CloudMind to analyze, publish PRs, deploy to Azure, check status, or generate the final report..."
                className="min-h-[54px] flex-1 resize-none rounded-2xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-blue-400"
              />
              <button
                onClick={() => sendMessage()}
                disabled={isLoading || !input.trim()}
                className="flex h-[54px] w-[54px] items-center justify-center rounded-2xl bg-blue-500 text-white transition hover:bg-blue-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLoading ? (
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
                  disabled={isLoading}
                  className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 transition hover:bg-slate-800 disabled:opacity-50"
                >
                  {suggestion.label}
                </button>
              ))}
            </div>
          </div>
        </section>

        <aside className="space-y-4">
          <SectionCard
            title="Mission Status"
            icon={<Zap className="h-4 w-4" />}
            action={<StatusPill value={missionStatus.status} />}
          >
            <Metric label="Recommendation" value={missionStatus.recommendation} />
            <Metric label="Azure healthy" value={missionStatus.azureHealthy} />
            <Metric label="Logs available" value={missionStatus.logsAvailable} />
            <Metric
              label="Incident detected"
              value={missionStatus.incidentDetected}
            />
            <Metric label="PR state" value={missionStatus.prState} />
            <Metric label="CI" value={missionStatus.ci} />
          </SectionCard>

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

function BrandCard() {
  return (
    <div className="overflow-hidden rounded-3xl border border-blue-400/20 bg-gradient-to-br from-blue-500/20 via-slate-950 to-emerald-500/10 p-5 shadow-2xl shadow-black/20">
      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-500/20">
          <Bot className="h-7 w-7 text-blue-200" />
        </div>
        <div>
          <h2 className="text-xl font-bold">CloudMind</h2>
          <p className="text-sm text-slate-300">Multi-agent DevOps OS</p>
        </div>
      </div>

      <p className="mt-4 text-sm leading-6 text-slate-300">
        Analyze repos, create GitOps pull requests, deploy to Azure Container
        Apps, verify health, analyze incidents, and keep durable project memory.
      </p>

      <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
        <MiniStat label="GitOps" value="PR" />
        <MiniStat label="Cloud" value="Azure" />
        <MiniStat label="Memory" value="Postgres" />
      </div>
    </div>
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
    <div className="rounded-3xl border border-slate-700/70 bg-slate-950/70 p-4 shadow-xl shadow-black/20 backdrop-blur">
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
      <span className="mb-1 block text-xs font-medium text-slate-400">
        {label}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
        placeholder={placeholder}
        className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-blue-400"
      />
    </label>
  );
}

function ToolButtonGrid({
  actions,
  onRun,
  disabled,
}: {
  actions: {
    label: string;
    message: string;
    icon: LucideIcon;
  }[];
  onRun: (message: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="grid gap-2">
      {actions.map((action) => {
        const Icon = action.icon;

        return (
          <button
            key={action.label}
            onClick={() => onRun(action.message)}
            disabled={disabled}
            className="flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-900/80 px-3 py-2.5 text-left text-sm text-slate-200 transition hover:border-blue-400/50 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
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
        className={`max-w-[86%] rounded-3xl border px-4 py-3 ${
          isUser
            ? "border-blue-400/30 bg-blue-500/20"
            : "border-slate-700 bg-slate-900/80"
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

        {(message.intent || message.toolName || message.status) && (
          <div className="mt-3 flex flex-wrap gap-2">
            {message.intent && <StatusPill value={`Intent: ${message.intent}`} />}
            {message.toolName && (
              <StatusPill value={`Tool: ${message.toolName}`} />
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
          {actions.slice(0, 8).map((action) => (
            <div
              key={action.id}
              className="rounded-2xl border border-slate-800 bg-slate-900/70 p-3"
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
          {artifacts.slice(0, 8).map((artifact) => (
            <div
              key={artifact.id}
              className="rounded-2xl border border-slate-800 bg-slate-900/70 p-3"
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
                    <p className="mt-2 truncate rounded-lg bg-slate-950 px-2 py-1 text-xs text-slate-400">
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
    <div className="border-b border-slate-800 py-2 last:border-b-0">
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
    <div className="rounded-2xl border border-slate-700/70 bg-slate-950/50 p-3">
      <p className="text-[11px] text-slate-500">{label}</p>
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
          normalized.includes("not available")
        ? "warn"
        : normalized.includes("healthy") ||
            normalized.includes("success") ||
            normalized.includes("deployed") ||
            normalized.includes("published") ||
            normalized.includes("synced") ||
            normalized.includes("ready")
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
    <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-4 text-center text-sm text-slate-500">
      {text}
    </div>
  );
}

function JsonPreview({ value }: { value: unknown }) {
  return (
    <details className="group">
      <summary className="cursor-pointer rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800">
        View JSON
      </summary>
      <pre className="mt-3 max-h-[360px] overflow-auto rounded-2xl border border-slate-800 bg-slate-950 p-3 text-xs leading-5 text-slate-300">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
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