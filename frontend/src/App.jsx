import { useCallback, useEffect, useMemo, useState } from "react";
import { api, clearTokens, saveTokens } from "./api.js";

const NAV_ITEMS = [
  { id: "overview", label: "Overview", glyph: "◫" },
  { id: "projects", label: "Projects", glyph: "▦" },
  { id: "tasks", label: "Tasks", glyph: "☷" },
  { id: "team", label: "Team", glyph: "♧" },
  { id: "insights", label: "AI insights", glyph: "✳" },
];
const PRIORITIES = ["low", "medium", "high", "critical"];
const STATUSES = ["todo", "in_progress", "done"];
const EMPTY_PROJECT = { name: "", description: "", deadline: "" };
const EMPTY_TASK = {
  project: "", title: "", description: "", assignee: "", due_date: "",
  status: "todo", priority: "medium", estimated_days: "",
};

function pretty(value = "") {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateLabel(value) {
  if (!value) return "No deadline";
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
  });
}

function initials(name = "Smart Task") {
  return name.split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
}

function Avatar({ name, className = "" }) {
  return <span className={`avatar ${className}`}>{initials(name)}</span>;
}

function Progress({ value = 0 }) {
  return (
    <div className="progress-track" aria-label={`${value}% complete`}>
      <span className="progress-fill" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  );
}

function Badge({ children, tone }) {
  return <span className={`badge ${tone || String(children).toLowerCase().replaceAll(" ", "-")}`}>{pretty(String(children))}</span>;
}

function Field({ label, children, className = "" }) {
  return <label className={`field ${className}`}><span>{label}</span>{children}</label>;
}

function AuthScreen({ onAuthenticated, initialError = "" }) {
  const [registering, setRegistering] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initialError);

  async function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      let tokens;
      if (registering) {
        const result = await api.register({
          email: form.get("email"),
          password: form.get("password"),
          first_name: form.get("first_name"),
          last_name: form.get("last_name"),
        });
        tokens = result;
      } else {
        tokens = await api.login(form.get("email"), form.get("password"));
      }
      saveTokens(tokens);
      await onAuthenticated();
    } catch (reason) {
      clearTokens();
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-art">
        <div className="brand"><span className="brand-mark">S</span><span>SmartTask<span className="brand-ai"> AI</span></span></div>
        <div className="auth-message">
          <span className="eyebrow light">A calmer way to get work done</span>
          <h1>Make every project<br />move forward.</h1>
          <p>Bring your team, tasks, and thoughtful AI predictions into one focused workspace.</p>
        </div>
        <div className="auth-orbit"><span>✳</span><i /><i /><i /></div>
        <div className="auth-footnote">Plan with clarity. Deliver with confidence.</div>
      </div>
      <section className="auth-form-wrap">
        <form className="auth-form" onSubmit={submit}>
          <div className="mobile-brand brand"><span className="brand-mark">S</span><span>SmartTask<span className="brand-ai"> AI</span></span></div>
          <span className="eyebrow">{registering ? "GET STARTED" : "WELCOME BACK"}</span>
          <h2>{registering ? "Create your account" : "Sign in to your workspace"}</h2>
          <p className="muted">Your work, priorities, and team — all in one place.</p>
          {registering && <div className="form-grid two">
            <Field label="First name"><input name="first_name" autoComplete="given-name" /></Field>
            <Field label="Last name"><input name="last_name" autoComplete="family-name" /></Field>
          </div>}
          <Field label="Email address"><input name="email" type="email" required maxLength="150" autoComplete="email" placeholder="you@company.com" /></Field>
          <Field label="Password"><input name="password" type="password" required minLength="8" autoComplete={registering ? "new-password" : "current-password"} placeholder="At least 8 characters" /></Field>
          {error && <div className="inline-error" role="alert">{error}</div>}
          <button className="button primary wide" disabled={busy}>{busy ? "Please wait…" : registering ? "Create account" : "Sign in"}<span>→</span></button>
          <p className="auth-toggle">{registering ? "Already have an account?" : "New to SmartTask AI?"}{" "}
            <button type="button" className="text-button" onClick={() => { setRegistering(!registering); setError(""); }}>
              {registering ? "Sign in" : "Create an account"}
            </button>
          </p>
        </form>
      </section>
    </main>
  );
}

function Modal({ title, onClose, children, error }) {
  useEffect(() => {
    function onKey(event) { if (event.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="Close dialog">×</button></div>
        {error && <div className="modal-error" role="alert">{error}</div>}
        {children}
      </section>
    </div>
  );
}

function App() {
  const [user, setUser] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [projects, setProjects] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [team, setTeam] = useState([]);
  const [page, setPage] = useState("overview");
  const [loading, setLoading] = useState(Boolean(sessionStorage.getItem("smarttask.access")));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [modal, setModal] = useState(null);
  const [taskFilter, setTaskFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [mobileNav, setMobileNav] = useState(false);
  const [projectInviteEmail, setProjectInviteEmail] = useState("");
  const [inviteProject, setInviteProject] = useState("");
  const [prediction, setPrediction] = useState(null);
  const [forecastProject, setForecastProject] = useState("");
  const [taskAi, setTaskAi] = useState(null);

  const loadWorkspace = useCallback(async () => {
    const [profile, overview, projectList, taskList, teamList] = await Promise.all([
      api.get("/auth/me/"),
      api.get("/dashboard/"),
      api.get("/projects/"),
      api.get("/tasks/"),
      api.get("/team/"),
    ]);
    setUser(profile);
    setDashboard(overview);
    setProjects(projectList);
    setTasks(taskList);
    setTeam(teamList);
  }, []);

  async function handleAuthenticated() {
    setError("");
    setNotice("");
    await loadWorkspace();
  }

  useEffect(() => {
    if (!sessionStorage.getItem("smarttask.access")) return;
    loadWorkspace().catch((reason) => {
      clearTokens();
      setError(reason.message);
      setUser(null);
    }).finally(() => setLoading(false));
  }, [loadWorkspace]);

  function showError(reason) {
    setError(reason.message || "Something went wrong. Please try again.");
    setNotice("");
  }

  async function runAction(action, successMessage) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await loadWorkspace();
      setModal(null);
      setNotice(successMessage);
    } catch (reason) {
      showError(reason);
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    const refresh = sessionStorage.getItem("smarttask.refresh");
    let logoutError = "";
    try { if (refresh) await api.logout(refresh); } catch (reason) { logoutError = reason.message; }
    clearTokens();
    setModal(null);
    setUser(null);
    setDashboard(null);
    setProjects([]);
    setTasks([]);
    setTeam([]);
    setPage("overview");
    setError(logoutError ? `Signed out on this device, but server sign-out could not be confirmed: ${logoutError}` : "");
  }

  const activeTasks = useMemo(() => {
    const query = search.trim().toLowerCase();
    return tasks.filter((task) => {
      const stateMatch = taskFilter === "all" || task.status === taskFilter;
      const searchMatch = !query || `${task.title} ${task.project_name} ${task.assignee_name || ""}`.toLowerCase().includes(query);
      return stateMatch && searchMatch;
    });
  }, [tasks, taskFilter, search]);

  if (!user && !loading) return <AuthScreen onAuthenticated={handleAuthenticated} initialError={error} />;
  if (loading) return <div className="loading-screen"><span className="spinner" /><span>Opening your workspace…</span></div>;
  if (!user) return <AuthScreen onAuthenticated={handleAuthenticated} initialError={error} />;

  function openProject(project = null) {
    setError("");
    setModal({ type: "project", item: project });
  }

  function openTask(task = null) {
    setError("");
    setTaskAi(null);
    setModal({ type: "task", item: task });
  }

  function goTo(nextPage) {
    setPage(nextPage);
    setMobileNav(false);
    setError("");
    setNotice("");
  }

  async function createProject(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = Object.fromEntries(form.entries());
    if (!body.deadline) body.deadline = null;
    const project = modal.item;
    await runAction(
      () => project ? api.patch(`/projects/${project.id}/`, body) : api.post("/projects/", body),
      project ? "Project updated." : "Project created.",
    );
  }

  async function saveProfile(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await runAction(
      () => api.patch("/auth/me/", {
        first_name: form.get("first_name"),
        last_name: form.get("last_name"),
      }),
      "Profile updated.",
    );
  }

  async function createTask(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = Object.fromEntries(form.entries());
    body.project = Number(body.project);
    body.assignee = body.assignee ? Number(body.assignee) : null;
    body.estimated_days = body.estimated_days ? Number(body.estimated_days) : null;
    body.due_date = body.due_date || null;
    const task = modal.item;
    await runAction(
      () => task ? api.patch(`/tasks/${task.id}/`, body) : api.post("/tasks/", body),
      task ? "Task updated." : "Task created.",
    );
  }

  async function deleteProject(project) {
    if (!window.confirm(`Delete “${project.name}” and its tasks? This cannot be undone.`)) return;
    await runAction(() => api.delete(`/projects/${project.id}/`), "Project deleted.");
  }

  async function deleteTask(task) {
    if (!window.confirm(`Delete “${task.title}”?`)) return;
    await runAction(() => api.delete(`/tasks/${task.id}/`), "Task deleted.");
  }

  async function inviteMember(event) {
    event.preventDefault();
    await runAction(async () => {
      await api.post("/team/", { email: projectInviteEmail, project_id: Number(inviteProject) });
      setProjectInviteEmail("");
    }, "Team member added.");
  }

  async function predictTask(event) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      const [priorityResult, durationResult] = await Promise.all([
        api.post("/predictions/priority/", {
          description: data.get("description"),
          task_type: data.get("task_type"),
        }),
        api.post("/predictions/completion/", {
          complexity: Number(data.get("complexity")),
          effort_points: Number(data.get("effort_points")),
          team_size: Number(data.get("team_size")),
          dependencies: Number(data.get("dependencies")),
        }),
      ]);
      setPrediction({ priority: priorityResult, completion: durationResult });
      setNotice("Predictions generated. The completion estimate uses synthetic data; see the model caveats below.");
    } catch (reason) {
      showError(reason);
    } finally {
      setBusy(false);
    }
  }

  async function forecastDelay(event) {
    event.preventDefault();
    const project = projects.find((item) => item.id === Number(forecastProject));
    if (!project) return;
    if (!project.deadline) {
      showError(new Error("Add a project deadline before forecasting delivery."));
      return;
    }
    const rows = tasks.filter((task) => task.project === project.id);
    const completed = rows.filter((task) => task.status === "done").length;
    const pending = rows.length - completed;
    const overdue = rows.filter((task) => task.status !== "done" && task.due_date && task.due_date < new Date().toISOString().slice(0, 10)).length;
    const days = Math.ceil((new Date(`${project.deadline}T00:00:00`) - new Date()) / 86400000);
    setBusy(true);
    setError("");
    try {
      const result = await api.post("/predictions/delay/", {
        progress: project.progress,
        completed,
        pending,
        overdue,
        days_until_deadline: days,
        complexity: 3,
      });
      setPrediction({ delay: result, project });
    } catch (reason) {
      showError(reason);
    } finally {
      setBusy(false);
    }
  }

  function navigateToTasks(projectId) {
    setSearch("");
    setTaskFilter("all");
    goTo("tasks");
    if (projectId) setSearch(projects.find((project) => project.id === projectId)?.name || "");
  }

  return (
    <div className="app-shell">
      {mobileNav && <button className="nav-scrim" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}
      <aside className={`sidebar ${mobileNav ? "open" : ""}`}>
        <div className="brand sidebar-brand"><span className="brand-mark">S</span><span>SmartTask<span className="brand-ai"> AI</span></span></div>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="side-nav" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => (
            <button key={item.id} className={`nav-item ${page === item.id ? "active" : ""}`} onClick={() => goTo(item.id)}>
              <span className="nav-glyph">{item.glyph}</span><span>{item.label}</span>
              {item.id === "tasks" && dashboard?.pending_count > 0 && <span className="nav-count">{dashboard.pending_count}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-projects">
          <div className="sidebar-section-head"><span>YOUR PROJECTS</span><button onClick={() => openProject()} aria-label="Create project">+</button></div>
          {projects.slice(0, 4).map((project, index) => (
            <button className="project-shortcut" key={project.id} onClick={() => navigateToTasks(project.id)}>
              <span className={`project-dot color-${index % 4}`} />{project.name}
            </button>
          ))}
          {!projects.length && <span className="empty-sidebar">Projects appear here</span>}
        </div>
        <div className="sidebar-bottom">
          <div className="ai-tip"><span className="tip-icon">✳</span><strong>Smarter planning</strong><p>Get a clearer view of your next deadline with AI insights.</p><button onClick={() => goTo("insights")}>Explore AI <span>→</span></button></div>
          <button className="profile-button" onClick={() => { setError(""); setModal({ type: "profile" }); }}>
            <Avatar name={`${user.first_name} ${user.last_name}`} />
            <span className="profile-meta"><strong>{user.first_name || user.email.split("@")[0]}</strong><small>{user.email}</small></span>
            <span className="profile-menu">↗</span>
          </button>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <button className="mobile-menu icon-button" onClick={() => setMobileNav(true)} aria-label="Open navigation">☰</button>
          <div className="breadcrumbs"><span>Workspace</span><b>/</b><strong>{NAV_ITEMS.find((item) => item.id === page)?.label}</strong></div>
          <div className="topbar-actions"><span className="today-label">{new Date().toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</span><button className="button primary small" onClick={() => openTask()}><span>+</span> New task</button></div>
        </header>
        <div className="content">
          {(error || notice) && <div className={`toast ${error ? "error" : "success"}`} role={error ? "alert" : "status"}><span>{error || notice}</span><button onClick={() => { setError(""); setNotice(""); }} aria-label="Dismiss">×</button></div>}
          {page === "overview" && <Overview dashboard={dashboard} projects={projects} tasks={tasks} user={user} onNewProject={() => openProject()} onNewTask={() => openTask()} onNavigate={goTo} onEditTask={openTask} onForecast={() => goTo("insights")} />}
          {page === "projects" && <ProjectsPage projects={projects} onNew={() => openProject()} onEdit={openProject} onDelete={deleteProject} onTasks={navigateToTasks} />}
          {page === "tasks" && <TasksPage tasks={activeTasks} projects={projects} filter={taskFilter} setFilter={setTaskFilter} search={search} setSearch={setSearch} onNew={() => openTask()} onEdit={openTask} onDelete={deleteTask} onToggle={(task) => runAction(() => api.patch(`/tasks/${task.id}/`, { status: task.status === "done" ? "todo" : "done" }), "Task status updated.")} />}
          {page === "team" && <TeamPage team={team} projects={projects} user={user} email={projectInviteEmail} setEmail={setProjectInviteEmail} projectId={inviteProject} setProjectId={setInviteProject} onInvite={inviteMember} busy={busy} />}
          {page === "insights" && <InsightsPage projects={projects} tasks={tasks} prediction={prediction} setPrediction={setPrediction} forecastProject={forecastProject} setForecastProject={setForecastProject} onPredict={predictTask} onForecast={forecastDelay} busy={busy} />}
          <footer className="page-footer"><span>SmartTask AI</span><span>Plan thoughtfully. Deliver confidently.</span></footer>
        </div>
      </main>

      {modal?.type === "project" && <ProjectModal project={modal.item} error={error} busy={busy} onClose={() => setModal(null)} onSubmit={createProject} />}
      {modal?.type === "task" && <TaskModal task={modal.item} projects={projects} busy={busy} taskAi={taskAi} setTaskAi={setTaskAi} error={error} onClose={() => setModal(null)} onSubmit={createTask} />}
      {modal?.type === "profile" && <ProfileModal user={user} error={error} busy={busy} onClose={() => setModal(null)} onSubmit={saveProfile} onLogout={signOut} />}
    </div>
  );
}

function Overview({ dashboard, projects, tasks, user, onNewProject, onNewTask, onNavigate, onEditTask, onForecast }) {
  const greeting = new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening";
  const focusTasks = tasks.filter((task) => task.status !== "done").slice(0, 5);
  return (
    <>
      <section className="welcome-row">
        <div><span className="eyebrow">YOUR WORKSPACE AT A GLANCE</span><h1>{greeting}, {user.first_name || "there"} <span className="wave">✦</span></h1><p>Here’s what’s happening across your projects today.</p></div>
        <button className="button secondary" onClick={onNewProject}><span>+</span> Create project</button>
      </section>
      <section className="stats-grid">
        <StatCard label="Total projects" value={dashboard?.projects_count || 0} note="Across your workspace" icon="▦" color="violet" />
        <StatCard label="Open tasks" value={(dashboard?.pending_count || 0) + (dashboard?.in_progress_count || 0)} note={`${dashboard?.in_progress_count || 0} currently in progress`} icon="☷" color="blue" />
        <StatCard label="Completed" value={dashboard?.completed_count || 0} note="Nice work, keep going" icon="✓" color="green" />
        <StatCard label="Overdue" value={dashboard?.overdue_count || 0} note={dashboard?.overdue_count ? "Needs a little attention" : "You’re all caught up"} icon="◷" color="orange" />
      </section>
      <section className="dashboard-grid">
        <div className="panel projects-panel">
          <PanelHeading title="Your projects" subtitle="A snapshot of active work" action="All projects" onAction={() => onNavigate("projects")} />
          {projects.length ? <div className="project-list">
            {projects.slice(0, 4).map((project, index) => (
              <div className="project-row" key={project.id}>
                <span className={`project-icon color-${index % 4}`}>{project.name.slice(0, 1).toUpperCase()}</span>
                <div className="project-info"><div className="project-title-line"><strong>{project.name}</strong><span>{project.progress}%</span></div><Progress value={project.progress} /><small>{project.task_count} tasks · Due {dateLabel(project.deadline)}</small></div>
                <button className="row-arrow" onClick={() => onNavigate("projects")} aria-label={`Open ${project.name}`}>↗</button>
              </div>
            ))}
          </div> : <EmptyState title="Your first project starts here" text="Create a project to organize work, assign tasks, and track progress." action="Create a project" onClick={onNewProject} />}
        </div>
        <div className="panel progress-panel">
          <PanelHeading title="Project progress" subtitle="Completion across your work" />
          {projects.length ? <div className="chart-area">
            <div className="chart-legend"><span><i className="legend-dot done-dot" />Complete</span><span><i className="legend-dot remaining-dot" />Remaining</span></div>
            <div className="bar-chart">
              {projects.slice(0, 5).map((project, index) => <div className="bar-column" key={project.id}>
                <div className="bar-pair"><span className={`bar-done color-${index % 4}`} style={{ height: `${Math.max(4, project.progress)}%` }} /><span className="bar-remaining" style={{ height: `${Math.max(4, 100 - project.progress)}%` }} /></div>
                <span className="bar-label">{project.name.length > 10 ? `${project.name.slice(0, 9)}…` : project.name}</span>
              </div>)}
            </div>
            <div className="chart-bottom"><span>Project completion</span><button className="text-button" onClick={onForecast}>Explore AI forecasts →</button></div>
          </div> : <div className="chart-empty"><span className="empty-chart-icon">▤</span><p>Your project progress chart will appear here.</p></div>}
        </div>
      </section>
      <section className="panel task-panel">
        <PanelHeading title="Your next tasks" subtitle="Stay focused on what’s next" action="View all tasks" onAction={() => onNavigate("tasks")} />
        {focusTasks.length ? <div className="task-table-wrap"><table className="task-table"><thead><tr><th>TASK</th><th>PROJECT</th><th>PRIORITY</th><th>DUE DATE</th><th>STATUS</th><th /></tr></thead><tbody>
          {focusTasks.map((task) => <tr key={task.id}>
            <td><button className="task-title-button" onClick={() => onEditTask(task)}>{task.title}</button></td>
            <td><span className="table-project">{task.project_name}</span></td>
            <td><Badge>{task.priority}</Badge></td>
            <td className={task.due_date && task.due_date < new Date().toISOString().slice(0, 10) ? "overdue-text" : ""}>{dateLabel(task.due_date)}</td>
            <td><Badge>{task.status}</Badge></td>
            <td><button className="row-arrow" onClick={() => onEditTask(task)} aria-label="Edit task">↗</button></td>
          </tr>)}
        </tbody></table></div> : <EmptyState title="Nothing on your plate yet" text="Add a task to turn your plans into progress." action="Create a task" onClick={onNewTask} />}
      </section>
    </>
  );
}

function StatCard({ label, value, note, icon, color }) {
  return <article className="stat-card"><div className={`stat-icon ${color}`}>{icon}</div><div className="stat-label">{label}</div><div className="stat-value">{value}</div><div className="stat-note">{note}</div></article>;
}

function PanelHeading({ title, subtitle, action, onAction }) {
  return <div className="panel-heading"><div><h2>{title}</h2><p>{subtitle}</p></div>{action && <button className="text-button" onClick={onAction}>{action} <span>→</span></button>}</div>;
}

function EmptyState({ title, text, action, onClick }) {
  return <div className="empty-state"><span className="empty-icon">✳</span><strong>{title}</strong><p>{text}</p>{action && <button className="button secondary small" onClick={onClick}>{action}</button>}</div>;
}

function ProjectsPage({ projects, onNew, onEdit, onDelete, onTasks }) {
  return <>
    <section className="page-heading"><div><span className="eyebrow">PLAN AND TRACK</span><h1>Projects</h1><p>Keep your team aligned from kickoff to delivery.</p></div><button className="button primary" onClick={onNew}><span>+</span> New project</button></section>
    {projects.length ? <div className="project-cards">{projects.map((project, index) => <article className="project-card" key={project.id}>
      <div className="project-card-top"><span className={`project-icon large color-${index % 4}`}>{project.name.slice(0, 1).toUpperCase()}</span><div className="project-card-actions"><button className="icon-button" onClick={() => onEdit(project)} aria-label="Edit project">✎</button><button className="icon-button danger-hover" onClick={() => onDelete(project)} aria-label="Delete project">⌫</button></div></div>
      <h2>{project.name}</h2><p className="project-description">{project.description || "No description yet."}</p>
      <div className="project-card-meta"><span>◷ &nbsp;{dateLabel(project.deadline)}</span><span>☷ &nbsp;{project.task_count} tasks</span></div>
      <div className="project-progress-label"><span>Progress</span><strong>{project.progress}%</strong></div><Progress value={project.progress} />
      <div className="project-card-bottom"><div className="avatar-stack">{project.members.slice(0, 4).map((person) => <Avatar key={person.id} name={person.name} />)}{project.members.length > 4 && <span className="avatar more">+{project.members.length - 4}</span>}</div><button className="text-button" onClick={() => onTasks(project.id)}>View tasks →</button></div>
    </article>)}</div> : <div className="panel"><EmptyState title="No projects yet" text="Create a project to give your tasks a home and your team a shared goal." action="Create your first project" onClick={onNew} /></div>}
  </>;
}

function TasksPage({ tasks, projects, filter, setFilter, search, setSearch, onNew, onEdit, onDelete, onToggle }) {
  return <>
    <section className="page-heading"><div><span className="eyebrow">MAKE STEADY PROGRESS</span><h1>Tasks</h1><p>Every next step, in one clear view.</p></div><button className="button primary" onClick={onNew}><span>+</span> New task</button></section>
    <section className="panel tasks-view-panel">
      <div className="task-toolbar"><div className="filter-tabs">{[["all", "All tasks"], ["todo", "To do"], ["in_progress", "In progress"], ["done", "Completed"]].map(([value, label]) => <button key={value} className={filter === value ? "selected" : ""} onClick={() => setFilter(value)}>{label}</button>)}</div><label className="search-box"><span>⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search tasks…" /></label></div>
      {tasks.length ? <div className="task-table-wrap"><table className="task-table full-task-table"><thead><tr><th>TASK</th><th>PROJECT</th><th>ASSIGNEE</th><th>PRIORITY</th><th>DUE DATE</th><th>STATUS</th><th /></tr></thead><tbody>
        {tasks.map((task) => <tr key={task.id}>
          <td><div className="task-name-cell"><button className={`task-check ${task.status === "done" ? "checked" : ""}`} onClick={() => onToggle(task)} aria-label={`Mark ${task.title} ${task.status === "done" ? "incomplete" : "complete"}`}>{task.status === "done" ? "✓" : ""}</button><button className="task-title-button" onClick={() => onEdit(task)}>{task.title}</button></div></td>
          <td><span className="table-project">{task.project_name}</span></td><td>{task.assignee_name || <span className="muted">Unassigned</span>}</td><td><Badge>{task.priority}</Badge></td><td className={task.due_date && task.due_date < new Date().toISOString().slice(0, 10) && task.status !== "done" ? "overdue-text" : ""}>{dateLabel(task.due_date)}</td><td><Badge>{task.status}</Badge></td>
          <td><div className="inline-actions"><button className="icon-button" onClick={() => onEdit(task)} aria-label="Edit task">✎</button><button className="icon-button danger-hover" onClick={() => onDelete(task)} aria-label="Delete task">⌫</button></div></td>
        </tr>)}
      </tbody></table></div> : <EmptyState title="No tasks match this view" text="Try another filter or add a new task to your workspace." action="Create a task" onClick={onNew} />}
    </section>
  </>;
}

function TeamPage({ team, projects, user, email, setEmail, projectId, setProjectId, onInvite, busy }) {
  return <>
    <section className="page-heading"><div><span className="eyebrow">BETTER WORK, TOGETHER</span><h1>Your team</h1><p>Collaborators across the projects you work on.</p></div></section>
    <div className="team-layout">
      <section className="panel team-panel"><PanelHeading title="Team members" subtitle={`${team.length} collaborators in your workspace`} />
        {team.length ? <div className="member-list">{team.map((member) => <div className="member-row" key={member.id}><Avatar name={member.name} className="member-avatar" /><div className="member-details"><strong>{member.name}</strong><span>{member.email}</span></div><span className="member-project-count">{member.project_ids.length} {member.project_ids.length === 1 ? "project" : "projects"}</span></div>)}</div> : <EmptyState title="Your team starts with you" text="Add someone to a project to see them here." />}
      </section>
      <section className="panel invite-panel"><div className="invite-icon">♧</div><h2>Bring your team in</h2><p>Add an existing SmartTask AI account to one of your projects. They’ll be able to collaborate on its tasks.</p>
        {projects.length ? <form onSubmit={onInvite} className="invite-form">
          <Field label="Project"><select required value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Choose a project</option>{projects.filter((project) => project.owner === user.id).map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></Field>
          <Field label="Member email"><input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="teammate@company.com" /></Field>
          <button className="button primary wide" disabled={busy}>{busy ? "Adding member…" : "Add to project"}<span>→</span></button>
          <small className="form-hint">The person must have registered for SmartTask AI already.</small>
        </form> : <div className="invite-no-project">Create a project before adding teammates.</div>}
      </section>
    </div>
  </>;
}

function InsightsPage({ projects, tasks, prediction, setPrediction, forecastProject, setForecastProject, onPredict, onForecast, busy }) {
  return <>
    <section className="page-heading"><div><span className="eyebrow">THOUGHTFUL, TRANSPARENT AI</span><h1>AI insights</h1><p>Explore model-backed estimates to help you plan the work ahead.</p></div><span className="synthetic-tag">MIXED TRAINING SOURCES · DEMO MODE</span></section>
    <div className="ai-disclaimer"><span>✳</span><div><strong>Use these forecasts as planning signals, not promises.</strong><p>The priority BiLSTM performed below the majority baseline on held-out Jira projects; it is a research demonstration, not a reliable decision tool. Completion-time and delay models use generated synthetic examples. Softmax scores are uncalibrated; none of the models is validated against SmartTask AI project history.</p></div></div>
    <div className="insights-grid">
      <section className="panel prediction-card"><div className="prediction-card-head"><span className="model-icon purple">Aa</span><div><span className="model-type">MODEL 01 · BiLSTM</span><h2>Task priority</h2></div></div><p className="prediction-description">Estimate priority from the task description and task type.</p>
        <form className="prediction-form" onSubmit={onPredict}>
          <Field label="What needs to be done?"><textarea name="description" required minLength="3" maxLength="4000" placeholder="Describe the task and its context…" /></Field>
          <div className="form-grid two"><Field label="Task type"><select name="task_type" defaultValue="other"><option value="bug">Bug</option><option value="improvement">Improvement</option><option value="new_feature">New feature</option><option value="other">Other</option></select></Field><Field label="Complexity"><select name="complexity" defaultValue="3">{[1, 2, 3, 4, 5].map((level) => <option key={level} value={level}>{level} / 5</option>)}</select></Field></div>
          <div className="form-grid two"><Field label="Effort points"><input name="effort_points" type="number" min="1" defaultValue="5" /></Field><Field label="Team size"><input name="team_size" type="number" min="1" defaultValue="2" /></Field></div>
          <Field label="Dependencies"><input name="dependencies" type="number" min="0" defaultValue="1" /></Field>
          <button className="button primary wide" disabled={busy}>{busy ? "Analyzing…" : "Predict priority & duration"}<span>✳</span></button>
        </form>
        {prediction?.priority && <div className="prediction-result"><div className="result-label">PRIORITY PREDICTION <span>{Math.round(prediction.priority.score * 100)}% uncalibrated score</span></div><div className="result-value"><Badge>{prediction.priority.priority}</Badge><small>{prediction.priority.model} · {prediction.priority.training_data === "synthetic_fallback" ? "synthetic fallback" : "public Jira sample"}</small></div><div className="result-label duration-result">ESTIMATED COMPLETION <strong>{prediction.completion.estimated_days} days</strong></div><small className="result-footnote">MLP regression · synthetic data · not a guarantee</small></div>}
      </section>
      <div className="insight-side">
        <section className="panel prediction-card delay-card"><div className="prediction-card-head"><span className="model-icon amber">↗</span><div><span className="model-type">MODEL 03 · DEEP FEEDFORWARD</span><h2>Project delay forecast</h2></div></div><p className="prediction-description">Assess delivery risk using task completion, remaining work, and deadline signals.</p>
          {projects.length ? <form className="delay-form" onSubmit={onForecast}><Field label="Select a project"><select required value={forecastProject} onChange={(event) => setForecastProject(event.target.value)}><option value="">Choose a project</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></Field><button className="button secondary wide" disabled={busy}>{busy ? "Forecasting…" : "Forecast project delivery"}<span>→</span></button></form> : <p className="muted">Create a project and add tasks before generating a forecast.</p>}
          {prediction?.delay && <div className="delay-result"><div className={`forecast-orb ${prediction.delay.forecast}`}><span>{prediction.delay.forecast === "on_time" ? "✓" : "!"}</span></div><div><span className="result-label">{prediction.project.name}</span><strong>{pretty(prediction.delay.forecast)}</strong><small>{Math.round(prediction.delay.score * 100)}% uncalibrated score · synthetic data</small></div></div>}
        </section>
        <section className="panel model-info"><span className="model-info-mark">✳</span><div><strong>Three independent models</strong><p>BiLSTM priority classifier, MLP completion-time regressor, and a deep feedforward delay classifier. Each has its own training run and evaluation report.</p><span className="report-location">Evaluation: deep_learning/experiments/evaluation.json</span></div></section>
        <section className="mini-metric"><div><span className="mini-metric-icon">☷</span><span>Active tasks</span><strong>{tasks.filter((task) => task.status !== "done").length}</strong></div><div><span className="mini-metric-icon orange">◷</span><span>Overdue tasks</span><strong>{tasks.filter((task) => task.status !== "done" && task.due_date && task.due_date < new Date().toISOString().slice(0, 10)).length}</strong></div></section>
      </div>
    </div>
  </>;
}

function ProjectModal({ project, error, busy, onClose, onSubmit }) {
  return <Modal title={project ? "Edit project" : "Create a project"} error={error} onClose={onClose}>
    <form className="modal-form" onSubmit={onSubmit}>
      <Field label="Project name"><input name="name" required maxLength="140" defaultValue={project?.name || ""} placeholder="e.g. Website refresh" autoFocus /></Field>
      <Field label="Description"><textarea name="description" maxLength="5000" defaultValue={project?.description || ""} placeholder="What are you working toward?" /></Field>
      <Field label="Target deadline"><input name="deadline" type="date" defaultValue={project?.deadline || ""} /></Field>
      <div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancel</button><button className="button primary" disabled={busy}>{busy ? "Saving…" : project ? "Save changes" : "Create project"}</button></div>
    </form>
  </Modal>;
}

function ProfileModal({ user, error, busy, onClose, onSubmit, onLogout }) {
  return <Modal title="Your profile" error={error} onClose={onClose}>
    <form className="modal-form" onSubmit={onSubmit}>
      <Field label="Email address"><input value={user.email} readOnly /></Field>
      <div className="form-grid two">
        <Field label="First name"><input name="first_name" maxLength="150" defaultValue={user.first_name || ""} /></Field>
        <Field label="Last name"><input name="last_name" maxLength="150" defaultValue={user.last_name || ""} /></Field>
      </div>
      <div className="modal-actions"><button type="button" className="button secondary" onClick={onLogout}>Sign out</button><button className="button primary" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button></div>
    </form>
  </Modal>;
}

function TaskModal({ task, projects, busy, taskAi, setTaskAi, error, onClose, onSubmit }) {
  const defaultProject = task?.project || projects[0]?.id || "";
  const [projectId, setProjectId] = useState(String(defaultProject));
  const selectedProject = projects.find((project) => project.id === Number(projectId));
  const [estimateBusy, setEstimateBusy] = useState(false);
  const members = selectedProject?.members || [];

  async function estimate(formElement) {
    const form = new FormData(formElement);
    setEstimateBusy(true);
    setTaskAi(null);
    try {
      const [priority, completion] = await Promise.all([
        api.post("/predictions/priority/", {
          description: form.get("description") || form.get("title"),
          task_type: form.get("task_type") || "other",
        }),
        api.post("/predictions/completion/", {
          complexity: Number(form.get("complexity") || 3),
          effort_points: Number(form.get("effort_points") || 5),
          team_size: 1,
          dependencies: 0,
        }),
      ]);
      setTaskAi({ priority, completion });
    } catch (error) {
      setTaskAi({ error: error.message });
    } finally {
      setEstimateBusy(false);
    }
  }

  return <Modal title={task ? "Edit task" : "Create a task"} error={error} onClose={onClose}>
    {!projects.length ? <div className="modal-empty">Create a project first. Tasks need a project to belong to.</div> : <form className="modal-form" onSubmit={onSubmit}>
      <Field label="Task title"><input name="title" required maxLength="180" defaultValue={task?.title || ""} placeholder="e.g. Review onboarding flow" autoFocus /></Field>
      <Field label="Description"><textarea name="description" maxLength="5000" defaultValue={task?.description || ""} placeholder="Add context or acceptance criteria…" /></Field>
      <div className="form-grid two">
        <Field label="Project"><select name="project" required value={projectId} onChange={(event) => setProjectId(event.target.value)}>{projects.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}</select></Field>
        <Field label="Assignee"><select name="assignee" defaultValue={task?.assignee || ""}><option value="">Unassigned</option>{members.map((member) => <option key={member.id} value={member.id}>{member.name}</option>)}</select></Field>
      </div>
      <div className="form-grid two">
        <Field label="Task type"><select name="task_type" defaultValue={task?.task_type || "other"}><option value="bug">Bug</option><option value="improvement">Improvement</option><option value="new_feature">New feature</option><option value="other">Other</option></select></Field>
        <Field label="Priority"><select name="priority" defaultValue={task?.priority || "medium"}>{PRIORITIES.map((value) => <option key={value} value={value}>{pretty(value)}</option>)}</select></Field>
      </div>
      <div className="form-grid two">
        <Field label="Status"><select name="status" defaultValue={task?.status || "todo"}>{STATUSES.map((value) => <option key={value} value={value}>{pretty(value)}</option>)}</select></Field>
      </div>
      <div className="form-grid two">
        <Field label="Due date"><input name="due_date" type="date" defaultValue={task?.due_date || ""} /></Field>
        <Field label="Estimated days"><input name="estimated_days" type="number" min="1" max="365" defaultValue={task?.estimated_days || ""} placeholder="Optional" /></Field>
      </div>
      {taskAi && <div className={`task-ai-result ${taskAi.error ? "error" : ""}`}>{taskAi.error ? taskAi.error : <>AI estimate: <Badge>{taskAi.priority.priority}</Badge> priority · about <strong>{taskAi.completion.estimated_days} days</strong> <small>(synthetic-data model)</small></>}</div>}
      <div className="modal-actions modal-actions-split"><button type="button" className="button ai-button" disabled={estimateBusy || busy} onClick={(event) => estimate(event.currentTarget.closest("form"))}>{estimateBusy ? "Estimating…" : "✳ Estimate with AI"}</button><div><button type="button" className="button secondary" onClick={onClose}>Cancel</button><button className="button primary" disabled={busy}>{busy ? "Saving…" : task ? "Save changes" : "Create task"}</button></div></div>
    </form>}
  </Modal>;
}

export default App;
