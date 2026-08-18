import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  Bot,
  BrainCircuit,
  Check,
  ChevronDown,
  Cloud,
  Code2,
  Eye,
  EyeOff,
  GitPullRequest,
  Loader2,
  LockKeyhole,
  LogOut,
  Menu,
  Network,
  ShieldCheck,
  Sparkles,
  UserRound,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import {
  API_BASE_URL,
  getAuthConfig,
  getAuthErrorMessage,
  getCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
} from "../api/authApi";
import type { AuthConfig, AuthUser } from "../api/authApi";
import "./auth.css";


type AuthMode = "signin" | "register";

export function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isChecking, setIsChecking] = useState(true);
  const [mode, setMode] = useState<AuthMode>("register");
  const [oauthMessage, setOauthMessage] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const authError = params.get("auth_error");
    const authSuccess = params.get("auth") === "google_success";

    if (authError) {
      setOauthMessage(authError);
      setMode("signin");
    }

    void getCurrentUser()
      .then((currentUser) => {
        setUser(currentUser);
        if (authSuccess && !currentUser) {
          setOauthMessage("Google sign-in completed, but the CloudMind session was not created.");
        }
      })
      .catch((error) => setOauthMessage(getAuthErrorMessage(error)))
      .finally(() => setIsChecking(false));

    if (authError || authSuccess) {
      window.history.replaceState({}, "", window.location.pathname);
    }

    const handleUnauthorized = () => setUser(null);
    window.addEventListener("cloudmind:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("cloudmind:unauthorized", handleUnauthorized);
  }, []);

  if (isChecking) {
    return <AuthLoadingScreen />;
  }

  if (!user) {
    return (
      <LandingPage
        mode={mode}
        oauthMessage={oauthMessage}
        onModeChange={(nextMode) => {
          setMode(nextMode);
          setOauthMessage(null);
        }}
        onAuthenticated={setUser}
      />
    );
  }

  return (
    <div className="auth-console-shell">
      <ConsoleAccountBar
        user={user}
        onSignOut={async () => {
          try {
            await logoutUser();
          } finally {
            setUser(null);
          }
        }}
      />
      <div className="auth-console-content">{children}</div>
    </div>
  );
}

function AuthLoadingScreen() {
  return (
    <div className="auth-loading-screen">
      <motion.div
        className="auth-loading-orb"
        animate={{ rotate: 360 }}
        transition={{ duration: 2.4, repeat: Infinity, ease: "linear" }}
      >
        <BrainCircuit />
      </motion.div>
      <span>Waking CloudMind</span>
    </div>
  );
}

function LandingPage({
  mode,
  oauthMessage,
  onModeChange,
  onAuthenticated,
}: {
  mode: AuthMode;
  oauthMessage: string | null;
  onModeChange: (mode: AuthMode) => void;
  onAuthenticated: (user: AuthUser) => void;
}) {
  const authCardRef = useRef<HTMLDivElement>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const focusAuth = (nextMode: AuthMode) => {
    onModeChange(nextMode);
    authCardRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <main className="auth-landing">
      <div className="auth-aurora auth-aurora-one" />
      <div className="auth-aurora auth-aurora-two" />
      <div className="auth-grid" />

      <nav className="auth-nav">
        <CloudMindLogo />
        <div className="auth-nav-links">
          <a href="#capabilities">Capabilities</a>
          <a href="#safety">Safety</a>
          <a href="#architecture">Architecture</a>
        </div>
        <div className="auth-nav-actions">
          <button className="auth-button auth-button-ghost" onClick={() => focusAuth("signin")}>
            Sign in
          </button>
          <button className="auth-button auth-button-primary" onClick={() => focusAuth("register")}>
            Start building <ArrowRight size={16} />
          </button>
        </div>
        <button
          className="auth-mobile-menu"
          aria-label="Toggle navigation"
          onClick={() => setMobileMenuOpen((current) => !current)}
        >
          {mobileMenuOpen ? <X /> : <Menu />}
        </button>
      </nav>

      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            className="auth-mobile-panel"
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
          >
            <a href="#capabilities" onClick={() => setMobileMenuOpen(false)}>Capabilities</a>
            <a href="#safety" onClick={() => setMobileMenuOpen(false)}>Safety</a>
            <button onClick={() => focusAuth("signin")}>Sign in</button>
            <button onClick={() => focusAuth("register")}>Create account</button>
          </motion.div>
        )}
      </AnimatePresence>

      <section className="auth-hero">
        <motion.div
          className="auth-hero-copy"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7 }}
        >
          <div className="auth-eyebrow">
            <span><Sparkles size={14} /></span>
            Local Llama intelligence · Human-controlled execution
          </div>
          <h1>
            Your cloud operations,
            <span> finally thinking together.</span>
          </h1>
          <p className="auth-hero-lead">
            CloudMind turns a production goal into an auditable multi-agent workflow—from repository analysis and GitOps to Azure deployment, health verification, and incident response.
          </p>
          <div className="auth-hero-actions">
            <button className="auth-button auth-button-primary auth-button-large" onClick={() => focusAuth("register")}>
              Launch CloudMind <ArrowRight size={18} />
            </button>
            <a className="auth-button auth-button-ghost auth-button-large" href="https://github.com/Hedi808" target="_blank" rel="noreferrer">
              <GitPullRequest size={18} /> View GitHub
            </a>
          </div>
          <div className="auth-trust-row">
            <span><Check size={14} /> Runs Llama locally</span>
            <span><Check size={14} /> Approval-gated writes</span>
            <span><Check size={14} /> PostgreSQL audit trail</span>
          </div>
        </motion.div>

        <motion.div
          ref={authCardRef}
          className="auth-card-wrap"
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.7, delay: 0.12 }}
        >
          <AuthCard
            mode={mode}
            oauthMessage={oauthMessage}
            onModeChange={onModeChange}
            onAuthenticated={onAuthenticated}
          />
        </motion.div>
      </section>

      <section className="auth-proof-strip" aria-label="CloudMind integrations">
        <span>POWERING SAFE WORKFLOWS ACROSS</span>
        <div><GitPullRequest /> GitHub</div>
        <div><Cloud /> Azure</div>
        <div><Code2 /> Docker</div>
        <div><Network /> Kubernetes</div>
        <div><BrainCircuit /> Ollama</div>
      </section>

      <section className="auth-capabilities" id="capabilities">
        <div className="auth-section-heading">
          <span>One goal. A coordinated team.</span>
          <h2>DevOps agents that know where their authority ends.</h2>
        </div>
        <div className="auth-feature-grid">
          <FeatureCard icon={BrainCircuit} accent="blue" title="AI coordination" text="Llama understands intent, remembers context, and creates structured plans for specialist agents." />
          <FeatureCard icon={ShieldCheck} accent="green" title="Policy before action" text="Deterministic controls review every plan. Cloud and Git writes stop for human approval." />
          <FeatureCard icon={Zap} accent="violet" title="Durable execution" text="Pipelines pause for pull requests, builds, approvals, and incidents—then resume from saved checkpoints." />
        </div>
      </section>

      <section className="auth-architecture" id="architecture">
        <div className="auth-orbit-visual">
          <div className="auth-orbit auth-orbit-outer"><span /><span /><span /></div>
          <div className="auth-orbit auth-orbit-inner"><span /><span /></div>
          <div className="auth-orbit-core"><Bot /><strong>CloudMind</strong><small>Coordinator</small></div>
        </div>
        <div className="auth-architecture-copy" id="safety">
          <span className="auth-kicker">Built for trust</span>
          <h2>AI reasoning without surrendering control.</h2>
          <p>CloudMind separates language-model reasoning from execution authority. The AI can propose. Specialist agents can verify. Only approved workflows can write.</p>
          <ul>
            <li><LockKeyhole /><span><strong>Secure sessions</strong> with server-side revocation and HttpOnly cookies.</span></li>
            <li><ShieldCheck /><span><strong>Human checkpoints</strong> before GitHub or Azure mutations.</span></li>
            <li><Network /><span><strong>Full traceability</strong> across messages, agents, tools, and deployment evidence.</span></li>
          </ul>
        </div>
      </section>

      <footer className="auth-footer">
        <CloudMindLogo />
        <p>Policy-governed multi-agent DevOps, built with care.</p>
        <span>© {new Date().getFullYear()} CloudMind</span>
      </footer>
    </main>
  );
}

function AuthCard({
  mode,
  oauthMessage,
  onModeChange,
  onAuthenticated,
}: {
  mode: AuthMode;
  oauthMessage: string | null;
  onModeChange: (mode: AuthMode) => void;
  onAuthenticated: (user: AuthUser) => void;
}) {
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(oauthMessage);
  const [config, setConfig] = useState<AuthConfig | null>(null);

  useEffect(() => {
    setError(oauthMessage);
  }, [oauthMessage]);

  useEffect(() => {
    void getAuthConfig().then(setConfig).catch(() => setConfig(null));
  }, []);

  const passwordScore = [
    password.length >= 8,
    /[A-Za-z]/.test(password),
    /\d/.test(password),
  ].filter(Boolean).length;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const response = mode === "register"
        ? await registerUser({ display_name: displayName, email, password })
        : await loginUser({ email, password });
      onAuthenticated(response.user);
    } catch (submitError) {
      setError(getAuthErrorMessage(submitError));
    } finally {
      setIsSubmitting(false);
    }
  };

  const startGoogle = () => {
    if (!config?.google_enabled) {
      setError("Google sign-in is ready in CloudMind. Add the Google OAuth client ID and secret to backend/.env to enable it.");
      return;
    }
    window.location.assign(`${API_BASE_URL}/api/auth/google/start`);
  };

  return (
    <div className="auth-card">
      <div className="auth-card-glow" />
      <div className="auth-card-heading">
        <span className="auth-card-icon"><UserRound /></span>
        <div>
          <span>{mode === "register" ? "Create your workspace" : "Welcome back"}</span>
          <small>{mode === "register" ? "Start orchestrating in under a minute." : "Your agents are ready when you are."}</small>
        </div>
      </div>

      <div className="auth-tabs" role="tablist">
        <button role="tab" aria-selected={mode === "signin"} className={mode === "signin" ? "active" : ""} onClick={() => { onModeChange("signin"); setError(null); }} type="button">Sign in</button>
        <button role="tab" aria-selected={mode === "register"} className={mode === "register" ? "active" : ""} onClick={() => { onModeChange("register"); setError(null); }} type="button">Register</button>
      </div>

      <button className="auth-google-button" type="button" onClick={startGoogle}>
        <GoogleMark /> Continue with Google
        {config && !config.google_enabled ? <span className="auth-setup-badge">Setup</span> : null}
      </button>

      <div className="auth-divider"><span>or continue with email</span></div>

      <form className="auth-form" onSubmit={submit}>
        <AnimatePresence initial={false}>
          {mode === "register" && (
            <motion.label initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
              <span>Your name</span>
              <div className="auth-input-wrap"><UserRound /><input autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Ada Lovelace" required /></div>
            </motion.label>
          )}
        </AnimatePresence>

        <label>
          <span>Email address</span>
          <div className="auth-input-wrap"><span className="auth-at">@</span><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" required /></div>
        </label>

        <label>
          <span>Password</span>
          <div className="auth-input-wrap"><LockKeyhole /><input type={showPassword ? "text" : "password"} autoComplete={mode === "register" ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={mode === "register" ? "8+ characters, including a number" : "Enter your password"} minLength={mode === "register" ? 8 : 1} required /><button type="button" className="auth-password-toggle" onClick={() => setShowPassword((current) => !current)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff /> : <Eye />}</button></div>
          {mode === "register" && password && <div className="auth-password-strength"><i className={passwordScore >= 1 ? "on" : ""} /><i className={passwordScore >= 2 ? "on" : ""} /><i className={passwordScore >= 3 ? "on" : ""} /><span>{passwordScore === 3 ? "Ready" : "Use 8+ characters, letters and numbers"}</span></div>}
        </label>

        {mode === "signin" && <div className="auth-form-options"><label><input type="checkbox" /> Remember me</label><button type="button" onClick={() => setError("Password reset will be added with email verification in the next authentication phase.")}>Forgot password?</button></div>}

        <AnimatePresence>
          {error && <motion.div className="auth-error" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>{error}</motion.div>}
        </AnimatePresence>

        <button className="auth-submit" type="submit" disabled={isSubmitting}>
          {isSubmitting ? <><Loader2 className="auth-spin" /> Securing session...</> : <>{mode === "register" ? "Create CloudMind account" : "Enter CloudMind"}<ArrowRight /></>}
        </button>
      </form>

      <p className="auth-legal">By continuing, you agree to use CloudMind responsibly and keep human approval enabled for production changes.</p>
    </div>
  );
}

function ConsoleAccountBar({ user, onSignOut }: { user: AuthUser; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const initials = user.display_name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();

  return (
    <header className="auth-account-bar">
      <div className="auth-account-brand"><span><Bot /></span><strong>CloudMind</strong><small>Secure workspace</small></div>
      <div className="auth-account-status"><i /> Local AI online <span>·</span> Approval policy active</div>
      <div className="auth-account-menu-wrap">
        <button className="auth-account-button" onClick={() => setOpen((current) => !current)}>
          {user.avatar_url ? <img src={user.avatar_url} alt="" referrerPolicy="no-referrer" /> : <span>{initials}</span>}
          <div><strong>{user.display_name}</strong><small>{user.email}</small></div>
          <ChevronDown />
        </button>
        <AnimatePresence>
          {open && (
            <motion.div className="auth-account-dropdown" initial={{ opacity: 0, y: -8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8, scale: 0.98 }}>
              <div><span>{initials}</span><p><strong>{user.display_name}</strong><small>{user.auth_provider === "google" ? "Google account" : "Email account"}</small></p></div>
              <button onClick={onSignOut}><LogOut /> Sign out</button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </header>
  );
}

function CloudMindLogo() {
  return <div className="auth-logo"><span><Bot /></span><div><strong>CloudMind</strong><small>Multi-agent DevOps OS</small></div></div>;
}

function FeatureCard({ icon: Icon, accent, title, text }: { icon: typeof Bot; accent: string; title: string; text: string }) {
  return <motion.article className={`auth-feature-card auth-feature-${accent}`} whileHover={{ y: -6 }}><span><Icon /></span><h3>{title}</h3><p>{text}</p><div>Explore capability <ArrowRight /></div></motion.article>;
}

function GoogleMark() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M21.6 12.2c0-.7-.1-1.4-.2-2H12v3.9h5.4a4.6 4.6 0 0 1-2 3v2.5h3.2c1.9-1.7 3-4.3 3-7.4Z"/><path fill="#34A853" d="M12 22c2.7 0 5-.9 6.6-2.4l-3.2-2.5c-.9.6-2 1-3.4 1a5.8 5.8 0 0 1-5.5-4H3.2v2.6A10 10 0 0 0 12 22Z"/><path fill="#FBBC05" d="M6.5 14a6 6 0 0 1 0-3.9V7.5H3.2a10 10 0 0 0 0 9.2L6.5 14Z"/><path fill="#EA4335" d="M12 6c1.5 0 2.9.5 4 1.6l3-3A10 10 0 0 0 3.2 7.5l3.3 2.6A5.8 5.8 0 0 1 12 6Z"/></svg>;
}
