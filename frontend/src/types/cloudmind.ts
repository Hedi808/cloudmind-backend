export type ChatRole = "user" | "assistant" | "system";

export interface CloudMindChatRequest {
  message: string;
  session_id?: string | null;
  repo_url?: string | null;
  resource_group?: string | null;
  app_name?: string | null;
  pull_request_url?: string | null;
  approval_confirmed?: boolean;
  context?: Record<string, unknown>;
}

export interface SuggestedAction {
  label: string;
  message: string;
}

export interface ConversationState {
  project_id?: string | null;
  project_name?: string | null;
  repo_url?: string | null;
  repo_analysis?: Record<string, unknown> | null;
  resource_group?: string | null;
  app_name?: string | null;
  azure_environment_name?: string | null;
  health_path?: string | null;
  latest_pr_url?: string | null;
  latest_pr_number?: number | null;
  latest_intent?: string | null;
  latest_action?: string | null;
  latest_result_status?: string | null;
  latest_app_url?: string | null;
  ghcr_image?: string | null;
}

export interface CloudMindAction {
  executed: boolean;
  tool_name?: string | null;
  requires_approval?: boolean;
  missing_fields?: string[];
  reason?: string | null;
  action_run_id?: string | null;
}

export interface ProjectMemoryProject {
  id: string;
  name?: string | null;
  repo_url: string;
  repo_owner?: string | null;
  repo_name?: string | null;
  default_branch?: string | null;
  detected_language?: string | null;
  detected_framework?: string | null;
  project_type?: string | null;
  port?: number | null;
  start_command?: string | null;
  ghcr_image?: string | null;
  azure_resource_group?: string | null;
  azure_app_name?: string | null;
  azure_environment_name?: string | null;
  azure_app_url?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProjectDeploymentState {
  id: string;
  project_id: string;
  provider: string;
  resource_group?: string | null;
  app_name?: string | null;
  environment_name?: string | null;
  image?: string | null;
  url?: string | null;
  health_status?: string | null;
  last_checked_at?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProjectActionRun {
  id: string;
  project_id?: string | null;
  session_id?: string | null;
  action_type: string;
  tool_name?: string | null;
  status: string;
  approval_required: boolean;
  approval_confirmed: boolean;
  input_json?: Record<string, unknown> | null;
  output_json?: Record<string, unknown> | null;
  error?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface ProjectArtifact {
  id: string;
  project_id: string;
  action_run_id?: string | null;
  artifact_type: string;
  name?: string | null;
  path?: string | null;
  url?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at?: string | null;
}

export interface ProjectContext {
  project: ProjectMemoryProject;
  latest_deployment?: ProjectDeploymentState | null;
  latest_actions: ProjectActionRun[];
  latest_artifacts: ProjectArtifact[];
}

export interface ProjectListResponse {
  status: string;
  message: string;
  total: number;
  limit: number;
  offset: number;
  projects: ProjectMemoryProject[];
}

export interface ProjectDetailResponse {
  status: string;
  message: string;
  project: ProjectMemoryProject;
  context: ProjectContext;
}

export interface WorkflowPlanRequest {
  project_id?: string | null;
  repo_url?: string | null;
}

export interface WorkflowStep {
  id: string;
  title: string;
  description: string;
  category: string;
  status: string;
  requires_approval: boolean;
  can_execute_now: boolean;
  tool_intent?: string | null;
  user_message?: string | null;
  depends_on: string[];
  evidence: string[];
  reason: string;
}

export interface WorkflowDefinition {
  id: string;
  title: string;
  description: string;
}

export interface WorkflowSummary {
  total_steps: number;
  completed: number;
  required: number;
  blocked: number;
  optional: number;
  progress_percent: number;
}

export interface WorkflowPlanResponse {
  status: string;
  message: string;
  project?: ProjectMemoryProject | null;
  workflow?: WorkflowDefinition | null;
  next_step?: WorkflowStep | null;
  steps: WorkflowStep[];
  summary: WorkflowSummary;
  safety?: Record<string, unknown> | null;
}

export interface CloudMindChatResult {
  status: string;
  message: string;
  phase: string;
  session_id: string;
  project_id?: string | null;
  intent: string;
  assistant_message: string;
  action: CloudMindAction;
  tool_result?: Record<string, unknown> | null;
  conversation_state: ConversationState;
  project_context?: ProjectContext | null;
  suggested_actions: SuggestedAction[];
  safety: {
    human_approval_required_for_write_actions: boolean;
    approval_confirmed: boolean;
    direct_main_push: boolean;
    auto_merge: boolean;
    auto_deploy?: boolean;
    auto_deploy_without_approval?: boolean;
  };
}

export interface CloudMindChatResponse {
  status: string;
  message: string;
  result: CloudMindChatResult;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  intent?: string;
  toolName?: string | null;
  status?: string;
  timestamp: string;
}