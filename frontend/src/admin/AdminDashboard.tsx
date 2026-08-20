import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  Bot,
  FolderGit2,
  Loader2,
  MessageSquareText,
  RefreshCw,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { getAdminOverview } from "../api/adminApi";
import type { AdminOverview } from "../api/adminApi";
import "./admin.css";


export function AdminDashboard({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOverview(await getAdminOverview());
    } catch {
      setError("CloudMind could not load the administration overview.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void loadOverview();
  }, [loadOverview, open]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="admin-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) onClose();
          }}
        >
          <motion.section
            className="admin-panel"
            role="dialog"
            aria-modal="true"
            aria-label="CloudMind administration"
            initial={{ opacity: 0, y: 24, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 18, scale: 0.98 }}
          >
            <header className="admin-header">
              <div className="admin-title-icon"><ShieldCheck /></div>
              <div>
                <span>ADMIN CONTROL PLANE</span>
                <h2>CloudMind overview</h2>
                <p>Global visibility without mixing user workspaces.</p>
              </div>
              <button className="admin-icon-button" onClick={() => void loadOverview()} aria-label="Refresh overview">
                <RefreshCw className={loading ? "admin-spin" : ""} />
              </button>
              <button className="admin-icon-button" onClick={onClose} aria-label="Close administration">
                <X />
              </button>
            </header>

            {loading && !overview ? (
              <div className="admin-loading"><Loader2 className="admin-spin" /> Loading workspace intelligence…</div>
            ) : error ? (
              <div className="admin-error">{error}<button onClick={() => void loadOverview()}>Try again</button></div>
            ) : overview ? (
              <>
                <div className="admin-metrics">
                  <Metric icon={Users} label="Accounts" value={overview.metrics.users} detail={`${overview.metrics.active_users} active`} tone="blue" />
                  <Metric icon={FolderGit2} label="Projects" value={overview.metrics.projects} detail="isolated by owner" tone="violet" />
                  <Metric icon={MessageSquareText} label="Conversations" value={overview.metrics.conversations} detail={`${overview.metrics.messages} messages`} tone="green" />
                  <Metric icon={Activity} label="Agent actions" value={overview.metrics.agent_actions} detail={`${overview.metrics.pipeline_runs} pipeline runs`} tone="orange" />
                </div>

                <div className="admin-content-grid">
                  <section className="admin-users-card">
                    <div className="admin-section-heading"><div><span>MEMBERS</span><h3>Recent accounts</h3></div><small>{overview.metrics.live_sessions} live sessions</small></div>
                    <div className="admin-user-table">
                      <div className="admin-user-row admin-user-head"><span>User</span><span>Role</span><span>Projects</span><span>Chats</span><span>Status</span></div>
                      {overview.recent_users.map((user) => (
                        <div className="admin-user-row" key={user.id}>
                          <div className="admin-user-identity">
                            {user.avatar_url ? <img src={user.avatar_url} alt="" referrerPolicy="no-referrer" /> : <span>{initials(user.display_name)}</span>}
                            <p><strong>{user.display_name}</strong><small>{user.email}</small></p>
                          </div>
                          <span className={`admin-role admin-role-${user.role}`}>{user.role}</span>
                          <strong>{user.project_count}</strong>
                          <strong>{user.conversation_count}</strong>
                          <span className={user.is_active ? "admin-active" : "admin-inactive"}>{user.is_active ? "Active" : "Disabled"}</span>
                        </div>
                      ))}
                    </div>
                  </section>

                  <aside className="admin-isolation-card">
                    <span><Bot /></span>
                    <small>TENANT SAFETY</small>
                    <h3>Every workspace has a hard boundary.</h3>
                    <p>Projects, chat sessions, LLM traces, and pipeline checkpoints are resolved against the signed-in user.</p>
                    <ul>
                      <li><i /> Legacy projects assigned to admin</li>
                      <li><i /> Repository uniqueness per account</li>
                      <li><i /> Global metrics restricted to admins</li>
                    </ul>
                  </aside>
                </div>
              </>
            ) : null}
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Metric({ icon: Icon, label, value, detail, tone }: { icon: typeof Users; label: string; value: number; detail: string; tone: string }) {
  return <article className={`admin-metric admin-metric-${tone}`}><span><Icon /></span><div><small>{label}</small><strong>{value.toLocaleString()}</strong><p>{detail}</p></div></article>;
}

function initials(name: string): string {
  return name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
}
