import { FormEvent, startTransition, useEffect, useRef, useState } from "react";
import {
  AppSettings,
  cancelJob,
  createSchedule,
  DashboardResponse,
  deleteSchedule,
  JobDetail,
  PutioBrowser,
  RecurringSchedule,
  browsePutio,
  disconnectPutio,
  fetchDashboard,
  fetchJobs,
  runSchedule,
  runSync,
  saveSettings,
  savePutioManualToken,
  startPutioAuth,
  testJellyfin,
  updateSchedule,
} from "./lib/api";

type SyncMode = "all" | "folder";
type AppTab = "putio" | "sync" | "jellyfin" | "jobs";
type ScheduleDraft = Omit<RecurringSchedule, "id" | "next_run_at" | "last_run_at" | "last_job_id">;

const defaultScheduleDraft: ScheduleDraft = {
  name: "Nightly sync",
  enabled: true,
  mode: "folder",
  folder_path: "/Movies",
  destination_path: "",
  schedule_type: "daily",
  interval_hours: 6,
  daily_time: "03:00",
};

const fallbackDashboard: DashboardResponse = {
  product_name: "get-put.io",
  tagline: "A calmer control plane for syncing cloud media into local libraries.",
  settings: {
    putio: {
      app_id: "",
      client_secret: "",
      redirect_uri: "http://localhost:8000/api/auth/putio/callback",
      token: null,
      oauth_state: null,
      account_username: null,
      account_user_id: null,
      connected_at: null,
    },
    jellyfin: {
      enabled: false,
      base_url: "",
      api_key: "",
      refresh_after_sync: true,
      refresh_only_on_change: true,
      selected_library_ids: [],
    },
    sync_defaults: {
      destination_path: "",
    },
  },
  connections: [],
  folders: [],
  putio_browser: {
    current_path: "/",
    parent_path: null,
    breadcrumbs: [],
    entries: [],
  },
  jellyfin_libraries: [],
  destinations: [],
  jobs: [],
  schedules: [],
  putio_connected: false,
  jellyfin_enabled: false,
};

export default function App() {
  const [dashboard, setDashboard] = useState<DashboardResponse>(fallbackDashboard);
  const [jobs, setJobs] = useState<JobDetail[]>([]);
  const [putioBrowser, setPutioBrowser] = useState<PutioBrowser>(fallbackDashboard.putio_browser);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<AppTab>("putio");
  const [mode, setMode] = useState<SyncMode>("folder");
  const [folderPath, setFolderPath] = useState("/Movies");
  const [destination, setDestination] = useState("");
  const [settingsDraft, setSettingsDraft] = useState<AppSettings>(fallbackDashboard.settings);
  const [settingsSaved, setSettingsSaved] = useState<string | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [jellyfinMessage, setJellyfinMessage] = useState<string | null>(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [jobMessage, setJobMessage] = useState<string | null>(null);
  const [browserLoading, setBrowserLoading] = useState(false);
  const [scheduleDraft, setScheduleDraft] = useState<ScheduleDraft>(defaultScheduleDraft);
  const [editingScheduleId, setEditingScheduleId] = useState<string | null>(null);
  const [scheduleSaving, setScheduleSaving] = useState(false);
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [scheduleMessage, setScheduleMessage] = useState<string | null>(null);
  const [manualToken, setManualToken] = useState("");
  const [manualTokenSaving, setManualTokenSaving] = useState(false);
  const seededRef = useRef(false);
  const browserPathRef = useRef("/");
  const legacyDefaultDestination = "/media/staging";

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const [dashboardResult, jobsResult] = await Promise.all([fetchDashboard(), fetchJobs()]);
        if (!active) {
          return;
        }

        let browserResult = dashboardResult.putio_browser;
        if (
          dashboardResult.putio_connected &&
          browserPathRef.current !== "/" &&
          browserPathRef.current !== dashboardResult.putio_browser.current_path
        ) {
          try {
            browserResult = await browsePutio(browserPathRef.current);
          } catch {
            browserResult = dashboardResult.putio_browser;
            browserPathRef.current = "/";
          }
        }

        startTransition(() => {
          setDashboard(dashboardResult);
          setJobs(jobsResult);
          setPutioBrowser(browserResult);
          if (!seededRef.current) {
            const normalizedDestination =
              dashboardResult.settings.sync_defaults.destination_path === legacyDefaultDestination
                ? ""
                : dashboardResult.settings.sync_defaults.destination_path;
            setSettingsDraft({
              ...dashboardResult.settings,
              sync_defaults: { destination_path: normalizedDestination },
            });
            setDestination(normalizedDestination);
            setFolderPath(browserResult.entries[0]?.path ?? "/");
            setScheduleDraft((current) => ({
              ...current,
              folder_path: browserResult.entries[0]?.path ?? "/",
              destination_path: normalizedDestination,
            }));
            seededRef.current = true;
          }
          setError(null);
        });
      } catch (loadError) {
        if (!active) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Unable to load the dashboard.");
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 3000);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  async function handleRunNow() {
    setRunError(null);
    setJobMessage(null);
    const trimmedDestination = destination.trim();
    if (!trimmedDestination) {
      setRunError("Enter a full local destination path before running a sync.");
      return;
    }
    if (!trimmedDestination.startsWith("/")) {
      setRunError("Destination path must be a full absolute local path.");
      return;
    }
    try {
      const job = await runSync({
        mode,
        folder_path: mode === "folder" ? folderPath : undefined,
        destination_path: trimmedDestination,
      });
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
    } catch (issue) {
      setRunError(issue instanceof Error ? issue.message : "Unable to run job.");
    }
  }

  async function handleCancelJob(jobId: string) {
    setRunError(null);
    setJobMessage(null);
    try {
      const job = await cancelJob(jobId);
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
      setJobMessage("Sync cancelled.");
    } catch (issue) {
      setRunError(issue instanceof Error ? issue.message : "Unable to cancel job.");
    }
  }

  async function handleSaveSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setScheduleSaving(true);
    setScheduleError(null);
    setScheduleMessage(null);
    const trimmedDestination = destination.trim();
    if (!trimmedDestination) {
      setScheduleSaving(false);
      setScheduleError("Enter a full local destination path before saving a recurring job.");
      return;
    }
    if (!trimmedDestination.startsWith("/")) {
      setScheduleSaving(false);
      setScheduleError("Recurring jobs require a full absolute local destination path.");
      return;
    }

    const payload: ScheduleDraft = {
      ...scheduleDraft,
      mode,
      folder_path: mode === "folder" ? folderPath : null,
      destination_path: trimmedDestination,
    };

    try {
      if (editingScheduleId) {
        await updateSchedule(editingScheduleId, payload);
        setScheduleMessage("Recurring job updated.");
      } else {
        await createSchedule(payload);
        setScheduleMessage("Recurring job created.");
      }
      setEditingScheduleId(null);
      setScheduleDraft({
        ...defaultScheduleDraft,
        mode,
        folder_path: mode === "folder" ? folderPath : null,
        destination_path: destination,
      });
    } catch (issue) {
      setScheduleError(issue instanceof Error ? issue.message : "Unable to save recurring job.");
    } finally {
      setScheduleSaving(false);
    }
  }

  async function handleRunSchedule(scheduleId: string) {
    setScheduleError(null);
    try {
      const job = await runSchedule(scheduleId);
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
      setScheduleMessage("Recurring job triggered.");
    } catch (issue) {
      setScheduleError(issue instanceof Error ? issue.message : "Unable to trigger schedule.");
    }
  }

  async function handleDeleteSchedule(scheduleId: string) {
    setScheduleError(null);
    try {
      await deleteSchedule(scheduleId);
      if (editingScheduleId === scheduleId) {
        setEditingScheduleId(null);
        setScheduleDraft(defaultScheduleDraft);
      }
      setScheduleMessage("Recurring job deleted.");
    } catch (issue) {
      setScheduleError(issue instanceof Error ? issue.message : "Unable to delete schedule.");
    }
  }

  function handleEditSchedule(schedule: RecurringSchedule) {
    setEditingScheduleId(schedule.id);
    setMode(schedule.mode);
    setFolderPath(schedule.folder_path ?? "/");
    setDestination(schedule.destination_path);
    setScheduleDraft({
      name: schedule.name,
      enabled: schedule.enabled,
      mode: schedule.mode,
      folder_path: schedule.folder_path ?? null,
      destination_path: schedule.destination_path,
      schedule_type: schedule.schedule_type,
      interval_hours: schedule.interval_hours,
      daily_time: schedule.daily_time,
    });
  }

  function resetScheduleEditor() {
    setEditingScheduleId(null);
    setScheduleDraft({
      ...defaultScheduleDraft,
      mode,
      folder_path: mode === "folder" ? folderPath : null,
      destination_path: destination,
    });
  }

  async function handleSaveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSettingsSaving(true);
    setSettingsSaved(null);
    setSettingsError(null);
    try {
      const saved = await saveSettings(settingsDraft);
      setSettingsDraft(saved);
      setSettingsSaved("Settings saved.");
    } catch (issue) {
      setSettingsError(issue instanceof Error ? issue.message : "Unable to save settings.");
    } finally {
      setSettingsSaving(false);
    }
  }

  async function handleStartPutioAuth() {
    setAuthBusy(true);
    setSettingsError(null);
    try {
      const authUrl = await startPutioAuth();
      window.location.assign(authUrl);
    } catch (issue) {
      setSettingsError(issue instanceof Error ? issue.message : "Unable to start Put.io auth.");
      setAuthBusy(false);
    }
  }

  async function handleDisconnectPutio() {
    setAuthBusy(true);
    try {
      await disconnectPutio();
      browserPathRef.current = "/";
      setPutioBrowser(fallbackDashboard.putio_browser);
      setManualToken("");
      setSettingsSaved("Put.io disconnected.");
    } catch (issue) {
      setSettingsError(issue instanceof Error ? issue.message : "Unable to disconnect Put.io.");
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleTestJellyfin() {
    setJellyfinMessage(null);
    setSettingsError(null);
    try {
      const message = await testJellyfin();
      setJellyfinMessage(message);
    } catch (issue) {
      setSettingsError(issue instanceof Error ? issue.message : "Unable to test Jellyfin.");
    }
  }

  async function handleSaveManualToken() {
    setSettingsError(null);
    setManualTokenSaving(true);
    try {
      await savePutioManualToken(manualToken);
      setSettingsSaved("Put.io token saved.");
      setManualToken("");
    } catch (issue) {
      setSettingsError(issue instanceof Error ? issue.message : "Unable to save Put.io token.");
    } finally {
      setManualTokenSaving(false);
    }
  }

  async function handleBrowse(path: string) {
    setBrowserLoading(true);
    try {
      const browser = await browsePutio(path);
      browserPathRef.current = browser.current_path;
      setPutioBrowser(browser);
      if (mode === "folder") {
        setFolderPath(browser.current_path);
      }
    } catch (issue) {
      setSettingsError(issue instanceof Error ? issue.message : "Unable to browse Put.io.");
    } finally {
      setBrowserLoading(false);
    }
  }

  function handleLibraryToggle(libraryId: string, checked: boolean) {
    setSettingsDraft((current) => ({
      ...current,
      jellyfin: {
        ...current.jellyfin,
        selected_library_ids: checked
          ? [...current.jellyfin.selected_library_ids, libraryId]
          : current.jellyfin.selected_library_ids.filter((id) => id !== libraryId),
      },
    }));
  }

  function handleUseLibraryLocation(location: string) {
    setDestination(location);
    setSettingsDraft((current) => ({
      ...current,
      sync_defaults: { destination_path: location },
    }));
  }

  const selectedJob = jobs[0];
  const activeSyncJob = jobs.find((job) => job.status === "running" || job.status === "queued");
  const latestFinishedJob = jobs.find((job) => job.status === "completed" || job.status === "failed");
  const syncFocusJob = activeSyncJob ?? selectedJob;
  const selectedLibraryIds = new Set(settingsDraft.jellyfin.selected_library_ids);
  const selectedLibraries = dashboard.jellyfin_libraries.filter((library) =>
    selectedLibraryIds.has(library.id),
  );
  const nativeRedirectUri = "http://localhost:8000/api/auth/putio/callback";
  const containerRedirectUri = "http://localhost:8787/api/auth/putio/callback";
  const formatTimestamp = (value?: string | null) => {
    if (!value) {
      return "Never";
    }
    return new Date(value).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  };
  const destinationValidationError = !destination.trim()
    ? "Full local path required."
    : !destination.trim().startsWith("/")
      ? "Use an absolute local path."
      : null;
  const tabs: Array<{ id: AppTab; label: string; note: string }> = [
    { id: "putio", label: "Put.io", note: dashboard.putio_connected ? "Connected" : "Needs auth" },
    {
      id: "sync",
      label: "Sync",
      note: activeSyncJob ? "Running now" : latestFinishedJob ? "Recent activity" : "Ready",
    },
    {
      id: "jellyfin",
      label: "Jellyfin",
      note: settingsDraft.jellyfin.enabled ? "Hook ready" : "Optional",
    },
    {
      id: "jobs",
      label: "Jobs",
      note: dashboard.schedules.length ? `${dashboard.schedules.length} scheduled` : "Manual only",
    },
  ];

  return (
    <div className="page-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />

      <main className="layout">
        <section className="hero panel">
          <div className="hero-copy">
            <p className="eyebrow">Cloud intake for local libraries</p>
            <h1>{dashboard.product_name}</h1>
            <p className="lede">{dashboard.tagline}</p>
            <div className="hero-actions">
              <button className="primary-button" onClick={handleStartPutioAuth} type="button">
                {dashboard.putio_connected ? "Reconnect Put.io" : "Connect Put.io"}
              </button>
              <button className="ghost-button" onClick={handleTestJellyfin} type="button">
                Test Jellyfin hook
              </button>
            </div>
          </div>

          <div className="hero-matrix">
            <div className="signal-card">
              <span className="signal-label">Mode</span>
              <strong>{mode === "all" ? "Library sweep" : "Folder lane"}</strong>
            </div>
            <div className="signal-card">
              <span className="signal-label">Put.io path</span>
              <strong>{mode === "all" ? "/" : folderPath}</strong>
            </div>
            <div className="signal-card">
              <span className="signal-label">Jellyfin intent</span>
              <strong>{selectedLibraries.length ? `${selectedLibraries.length} libraries` : "Global hook"}</strong>
            </div>
          </div>
        </section>

        <section className="tab-strip" aria-label="Primary views">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={activeTab === tab.id ? "tab-button active" : "tab-button"}
              onClick={() => setActiveTab(tab.id)}
              type="button"
            >
              <span>{tab.label}</span>
              <small>{tab.note}</small>
            </button>
          ))}
        </section>

        <section className="feedback-stack" aria-live="polite">
          {error && <p className="error-banner">{error}</p>}
          {runError && <p className="error-banner">{runError}</p>}
          {settingsError && <p className="error-banner">{settingsError}</p>}
          {scheduleError && <p className="error-banner">{scheduleError}</p>}
          {settingsSaved && <p className="success-banner">{settingsSaved}</p>}
          {jellyfinMessage && <p className="success-banner">{jellyfinMessage}</p>}
          {jobMessage && <p className="success-banner">{jobMessage}</p>}
          {scheduleMessage && <p className="success-banner">{scheduleMessage}</p>}
        </section>

        {activeTab === "putio" && (
          <section className="status-grid single-panel tab-panel">
            <article className="panel settings-panel">
              <div className="section-heading">
                <h2>Put.io link</h2>
                <span className="small-note">
                  {dashboard.putio_connected ? "Connected" : "OAuth required"}
                </span>
              </div>
              <form className="settings-form" onSubmit={handleSaveSettings}>
                <label>
                  <span>Put.io client ID</span>
                  <input
                    onChange={(event) =>
                      setSettingsDraft((current) => ({
                        ...current,
                        putio: { ...current.putio, app_id: event.target.value },
                      }))
                    }
                    value={settingsDraft.putio.app_id}
                  />
                </label>
                <label>
                  <span>Put.io client secret</span>
                  <input
                    onChange={(event) =>
                      setSettingsDraft((current) => ({
                        ...current,
                        putio: { ...current.putio, client_secret: event.target.value },
                      }))
                    }
                    type="password"
                    value={settingsDraft.putio.client_secret}
                  />
                </label>
                <label>
                  <span>OAuth redirect URI</span>
                  <input
                    onChange={(event) =>
                      setSettingsDraft((current) => ({
                        ...current,
                        putio: { ...current.putio, redirect_uri: event.target.value },
                      }))
                    }
                    value={settingsDraft.putio.redirect_uri}
                  />
                </label>
                <div className="browser-panel">
                  <div className="section-heading compact-heading">
                    <h3>Put.io setup</h3>
                    <span className="small-note">Helper values</span>
                  </div>
                  <div className="location-list">
                    <a
                      className="path-chip path-link"
                      href="https://app.put.io/oauth/new"
                      rel="noreferrer"
                      target="_blank"
                    >
                      Create new app on Put.io
                    </a>
                    <button
                      className="path-chip"
                      onClick={() =>
                        setSettingsDraft((current) => ({
                          ...current,
                          putio: { ...current.putio, redirect_uri: nativeRedirectUri },
                        }))
                      }
                      type="button"
                    >
                      Use native callback
                    </button>
                    <button
                      className="path-chip"
                      onClick={() =>
                        setSettingsDraft((current) => ({
                          ...current,
                          putio: { ...current.putio, redirect_uri: containerRedirectUri },
                        }))
                      }
                      type="button"
                    >
                      Use container callback
                    </button>
                  </div>
                  <div className="preview-block">
                    <h3>Suggested Put.io app values</h3>
                    <ul>
                      <li>Name: `get-put.io`</li>
                      <li>Description: `Self-hosted Put.io sync portal for Jellyfin libraries.`</li>
                      <li>Website for native mode: `http://localhost:5173`</li>
                      <li>Callback for native mode: `http://localhost:8000/api/auth/putio/callback`</li>
                      <li>Callback for Docker/container mode: `http://localhost:8787/api/auth/putio/callback`</li>
                    </ul>
                  </div>
                </div>
                <div className="inline-actions">
                  <button className="primary-button" disabled={settingsSaving} type="submit">
                    {settingsSaving ? "Saving..." : "Save integration settings"}
                  </button>
                  <button
                    className="ghost-button"
                    disabled={authBusy}
                    onClick={dashboard.putio_connected ? handleDisconnectPutio : handleStartPutioAuth}
                    type="button"
                  >
                    {dashboard.putio_connected ? "Disconnect Put.io" : "Start Put.io login"}
                  </button>
                </div>
                <p className="muted-copy">
                  {dashboard.putio_connected
                    ? `Connected as ${dashboard.settings.putio.account_username ?? "Put.io user"}.`
                    : "Create a Put.io app, save the client ID and secret here, then start the browser login."}
                </p>
                <div className="preview-block">
                  <h3>Manual token fallback</h3>
                  <p>
                    If you prefer, you can paste the OAuth token from Put.io's Secrets page instead of
                    doing the browser login flow.
                  </p>
                  <div className="manual-token-row">
                    <input
                      onChange={(event) => setManualToken(event.target.value)}
                      placeholder="Paste Put.io OAuth token"
                      type="password"
                      value={manualToken}
                    />
                    <button
                      className="ghost-button small-button"
                      disabled={manualTokenSaving || !manualToken.trim()}
                      onClick={() => void handleSaveManualToken()}
                      type="button"
                    >
                      {manualTokenSaving ? "Saving..." : "Use token"}
                    </button>
                  </div>
                </div>
              </form>
            </article>
          </section>
        )}

        {activeTab === "sync" && (
          <section className="workspace-grid tab-panel">
            <article className="panel composer-panel">
              <div className="section-heading">
                <h2>Compose a sync</h2>
                <span className="small-note">Run directly</span>
              </div>

              <form className="sync-form">
                <label>
                  <span>Transfer mode</span>
                  <div className="mode-toggle">
                    <button
                      className={mode === "folder" ? "mode-option active" : "mode-option"}
                      onClick={() => {
                        setMode("folder");
                        if (folderPath === "/") {
                          setFolderPath(putioBrowser.current_path || "/");
                        }
                      }}
                      type="button"
                    >
                      Specific folder
                    </button>
                    <button
                      className={mode === "all" ? "mode-option active" : "mode-option"}
                      onClick={() => {
                        setMode("all");
                        setFolderPath("/");
                      }}
                      type="button"
                    >
                      Everything
                    </button>
                  </div>
                </label>

                <label>
                  <span>Put.io path</span>
                  <input
                    disabled={mode === "all"}
                    onChange={(event) => setFolderPath(event.target.value)}
                    placeholder="/Movies"
                    value={mode === "all" ? "/" : folderPath}
                  />
                </label>

                <div className="browser-panel">
                  <div className="section-heading compact-heading">
                    <h3>Put.io browser</h3>
                    <span className="small-note">
                      {browserLoading ? "Loading" : putioBrowser.current_path}
                    </span>
                  </div>
                  <p className="muted-copy">
                    The browser shows folders for the current Put.io level only. Double-click a folder to go
                    deeper, or use the breadcrumb trail to move back up.
                  </p>
                  <div className="breadcrumb-row">
                    {putioBrowser.breadcrumbs.map((crumb) => (
                      <button
                        className="breadcrumb-chip"
                        key={crumb.path}
                        onClick={() => handleBrowse(crumb.path)}
                        type="button"
                      >
                        {crumb.name}
                      </button>
                    ))}
                    {putioBrowser.parent_path && (
                      <button
                        className="breadcrumb-chip"
                        onClick={() => handleBrowse(putioBrowser.parent_path ?? "/")}
                        type="button"
                      >
                        Up
                      </button>
                    )}
                  </div>
                  <div className="folder-list browser-list">
                    {putioBrowser.entries.map((entry) => (
                      <button
                        className={`folder-chip ${entry.path === folderPath ? "selected" : ""}`}
                        key={entry.id}
                        onClick={() => {
                          setMode("folder");
                          setFolderPath(entry.path);
                        }}
                        onDoubleClick={() => void handleBrowse(entry.path)}
                        type="button"
                      >
                        <span>{entry.name}</span>
                        <small>{entry.path}</small>
                      </button>
                    ))}
                    {!putioBrowser.entries.length && (
                      <p className="empty-state">
                        {dashboard.putio_connected
                          ? "No folders found at this level."
                          : "Connect Put.io to browse folders."}
                      </p>
                    )}
                  </div>
                </div>

                <label>
                  <span>Destination path</span>
                  <input
                    onChange={(event) => {
                      const nextValue = event.target.value;
                      setDestination(nextValue);
                      setSettingsDraft((current) => ({
                        ...current,
                        sync_defaults: { destination_path: nextValue },
                      }));
                    }}
                    placeholder="/full/path/on/this/machine"
                    required
                    value={destination}
                  />
                  <p className="muted-copy">
                    Requires a full local path on the machine running get-put.io.
                  </p>
                  {destinationValidationError && (
                    <p className="field-hint invalid">{destinationValidationError}</p>
                  )}
                </label>

                <div className="inline-actions">
                  <button
                    className="primary-button"
                    disabled={!dashboard.putio_connected || destinationValidationError !== null}
                    onClick={handleRunNow}
                    type="button"
                  >
                    Run sync now
                  </button>
                </div>
              </form>
            </article>

            <article className="panel preview-panel">
              <div className="section-heading">
                <h2>Sync activity</h2>
                <span className="small-note">{activeSyncJob ? "Live" : "Latest run"}</span>
              </div>

              <div className="status-grid sync-status-grid">
                <div className="signal-card">
                  <span className="signal-label">Status</span>
                  <strong>{syncFocusJob ? syncFocusJob.status : "Idle"}</strong>
                </div>
                <div className="signal-card">
                  <span className="signal-label">Last run</span>
                  <strong>{formatTimestamp(latestFinishedJob?.finished_at ?? latestFinishedJob?.started_at)}</strong>
                </div>
                <div className="signal-card">
                  <span className="signal-label">Current target</span>
                  <strong>{syncFocusJob ? (syncFocusJob.mode === "all" ? "/" : syncFocusJob.folder_path ?? "/") : (mode === "all" ? "/" : folderPath)}</strong>
                </div>
              </div>

              {syncFocusJob ? (
                <div className="preview-content">
                  <div className="job-row sync-summary">
                    <div>
                      <strong>{syncFocusJob.label}</strong>
                      <p>
                        Destination: {syncFocusJob.destination_path}
                      </p>
                      <p>
                        Started: {formatTimestamp(syncFocusJob.started_at ?? syncFocusJob.created_at)} · Finished:{" "}
                        {formatTimestamp(syncFocusJob.finished_at)}
                      </p>
                    </div>
                    <span
                      className={
                        syncFocusJob.status === "completed"
                          ? "status-pill online"
                          : syncFocusJob.status === "running"
                            ? "status-pill running"
                            : syncFocusJob.status === "cancelled"
                              ? "status-pill cancelled"
                            : "status-pill muted"
                      }
                    >
                      {syncFocusJob.status}
                    </span>
                  </div>

                  {(syncFocusJob.status === "queued" || syncFocusJob.status === "running") && (
                    <div className="inline-actions">
                      <button
                        className="ghost-button"
                        onClick={() => void handleCancelJob(syncFocusJob.id)}
                        type="button"
                      >
                        Cancel sync
                      </button>
                    </div>
                  )}

                  <div className="preview-block">
                    <h3>Warnings</h3>
                    {syncFocusJob.warnings.length ? (
                      <ul>
                        {syncFocusJob.warnings.map((warning) => (
                          <li key={warning}>{warning}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>No current warnings.</p>
                    )}
                  </div>

                  <div className="preview-block">
                    <h3>Run log</h3>
                    <code className="log-block">
                      {syncFocusJob.log_lines.length
                        ? syncFocusJob.log_lines.join("\n")
                        : syncFocusJob.status === "queued"
                          ? "Job queued. Waiting for runner output."
                          : "No log lines yet."}
                    </code>
                  </div>
                </div>
              ) : (
                <div className="empty-preview">
                  <p>Choose a scope and destination, then run a sync to see its status and logs here.</p>
                </div>
              )}
            </article>
          </section>
        )}

        {activeTab === "jellyfin" && (
          <section className="status-grid single-panel tab-panel">
            <article className="panel settings-panel">
              <div className="section-heading">
                <h2>Jellyfin hook</h2>
                <span className="small-note">
                  {settingsDraft.jellyfin.enabled ? "Library-aware" : "Disabled"}
                </span>
              </div>
              <form className="settings-form" onSubmit={handleSaveSettings}>
                <label className="toggle-row">
                  <input
                    checked={settingsDraft.jellyfin.enabled}
                    onChange={(event) =>
                      setSettingsDraft((current) => ({
                        ...current,
                        jellyfin: { ...current.jellyfin, enabled: event.target.checked },
                      }))
                    }
                    type="checkbox"
                  />
                  <span>Enable Jellyfin integration</span>
                </label>
                <label>
                  <span>Jellyfin base URL</span>
                  <input
                    onChange={(event) =>
                      setSettingsDraft((current) => ({
                        ...current,
                        jellyfin: { ...current.jellyfin, base_url: event.target.value },
                      }))
                    }
                    placeholder="http://192.168.1.20:8096"
                    value={settingsDraft.jellyfin.base_url}
                  />
                </label>
                <label>
                  <span>Jellyfin API key</span>
                  <input
                    onChange={(event) =>
                      setSettingsDraft((current) => ({
                        ...current,
                        jellyfin: { ...current.jellyfin, api_key: event.target.value },
                      }))
                    }
                    type="password"
                    value={settingsDraft.jellyfin.api_key}
                  />
                </label>
                <label className="toggle-row">
                  <input
                    checked={settingsDraft.jellyfin.refresh_after_sync}
                    onChange={(event) =>
                      setSettingsDraft((current) => ({
                        ...current,
                        jellyfin: {
                          ...current.jellyfin,
                          refresh_after_sync: event.target.checked,
                        },
                      }))
                    }
                    type="checkbox"
                  />
                  <span>Refresh library after sync</span>
                </label>
                <label className="toggle-row">
                  <input
                    checked={settingsDraft.jellyfin.refresh_only_on_change}
                    onChange={(event) =>
                      setSettingsDraft((current) => ({
                        ...current,
                        jellyfin: {
                          ...current.jellyfin,
                          refresh_only_on_change: event.target.checked,
                        },
                      }))
                    }
                    type="checkbox"
                  />
                  <span>Only refresh when files changed</span>
                </label>

                <div className="library-picker">
                  <div className="section-heading compact-heading">
                    <h3>Jellyfin libraries</h3>
                    <span className="small-note">
                      {dashboard.jellyfin_libraries.length ? "Selectable" : "Connect to load"}
                    </span>
                  </div>
                  {dashboard.jellyfin_libraries.map((library) => (
                    <div className="library-card" key={library.id}>
                      <label className="toggle-row">
                        <input
                          checked={selectedLibraryIds.has(library.id)}
                          onChange={(event) =>
                            handleLibraryToggle(library.id, event.target.checked)
                          }
                          type="checkbox"
                        />
                        <span>
                          {library.name}
                          {library.collection_type ? ` · ${library.collection_type}` : ""}
                        </span>
                      </label>
                      <div className="location-list">
                        {library.locations.map((location) => (
                          <button
                            className="path-chip"
                            key={location}
                            onClick={() => handleUseLibraryLocation(location)}
                            type="button"
                          >
                            {location}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="inline-actions">
                  <button className="primary-button" disabled={settingsSaving} type="submit">
                    Save hook settings
                  </button>
                  <button className="ghost-button" onClick={handleTestJellyfin} type="button">
                    Test connection
                  </button>
                </div>
                <p className="muted-copy">
                  Use a full base URL and an admin API key. Library selection scopes your intent and
                  path choices, but Jellyfin still exposes only a global refresh endpoint.
                </p>
              </form>
            </article>
          </section>
        )}

        {activeTab === "jobs" && (
          <section className="jobs-grid tab-panel">
            <article className="panel">
              <div className="section-heading">
                <h2>Recurring jobs</h2>
                <span className="small-note">
                  {dashboard.schedules.length ? `${dashboard.schedules.length} saved` : "No schedules yet"}
                </span>
              </div>

              <form className="settings-form" onSubmit={handleSaveSchedule}>
                <label>
                  <span>Schedule name</span>
                  <input
                    onChange={(event) =>
                      setScheduleDraft((current) => ({ ...current, name: event.target.value }))
                    }
                    value={scheduleDraft.name}
                  />
                </label>

                <label className="toggle-row">
                  <input
                    checked={scheduleDraft.enabled}
                    onChange={(event) =>
                      setScheduleDraft((current) => ({ ...current, enabled: event.target.checked }))
                    }
                    type="checkbox"
                  />
                  <span>Enable recurring job</span>
                </label>

                <label>
                  <span>Schedule type</span>
                  <div className="mode-toggle">
                    <button
                      className={
                        scheduleDraft.schedule_type === "daily"
                          ? "mode-option active"
                          : "mode-option"
                      }
                      onClick={() =>
                        setScheduleDraft((current) => ({ ...current, schedule_type: "daily" }))
                      }
                      type="button"
                    >
                      Daily
                    </button>
                    <button
                      className={
                        scheduleDraft.schedule_type === "interval"
                          ? "mode-option active"
                          : "mode-option"
                      }
                      onClick={() =>
                        setScheduleDraft((current) => ({ ...current, schedule_type: "interval" }))
                      }
                      type="button"
                    >
                      Interval
                    </button>
                  </div>
                </label>

                {scheduleDraft.schedule_type === "daily" ? (
                  <label>
                    <span>Daily run time</span>
                    <input
                      onChange={(event) =>
                        setScheduleDraft((current) => ({
                          ...current,
                          daily_time: event.target.value,
                        }))
                      }
                      type="time"
                      value={scheduleDraft.daily_time}
                    />
                  </label>
                ) : (
                  <label>
                    <span>Interval hours</span>
                    <input
                      max={168}
                      min={1}
                      onChange={(event) =>
                        setScheduleDraft((current) => ({
                          ...current,
                          interval_hours: Number(event.target.value) || 1,
                        }))
                      }
                      type="number"
                      value={scheduleDraft.interval_hours}
                    />
                  </label>
                )}

              <p className="muted-copy">
                This saves the current sync selection:{" "}
                {mode === "all" ? "all Put.io content" : folderPath} to {destination}.
              </p>
              {destinationValidationError !== null && (
                <p className="field-hint invalid">
                  Set the destination path in the Sync tab before saving a recurring job.
                </p>
              )}

              <div className="inline-actions">
                  <button
                    className="primary-button"
                    disabled={scheduleSaving || destinationValidationError !== null}
                    type="submit"
                  >
                    {scheduleSaving
                      ? "Saving..."
                      : editingScheduleId
                        ? "Update recurring job"
                        : "Save recurring job"}
                  </button>
                  {destinationValidationError !== null && (
                    <button
                      className="ghost-button"
                      onClick={() => setActiveTab("sync")}
                      type="button"
                    >
                      Open Sync tab
                    </button>
                  )}
                  <button className="ghost-button" onClick={resetScheduleEditor} type="button">
                    Clear editor
                  </button>
                </div>
              </form>

              <div className="jobs-list schedule-list">
                {dashboard.schedules.map((schedule) => (
                  <div className="job-row schedule-row" key={schedule.id}>
                    <div>
                      <strong>{schedule.name}</strong>
                      <p>
                        {schedule.mode === "all" ? "Full library" : schedule.folder_path} to{" "}
                        {schedule.destination_path}
                      </p>
                      <p>
                        {schedule.schedule_type === "daily"
                          ? `Daily at ${schedule.daily_time}`
                          : `Every ${schedule.interval_hours} hour${schedule.interval_hours === 1 ? "" : "s"}`}
                      </p>
                      <p>
                        Next run: {schedule.next_run_at ?? "disabled"} · Last run:{" "}
                        {schedule.last_run_at ?? "never"}
                      </p>
                    </div>
                    <div className="row-actions">
                      <span className={schedule.enabled ? "status-pill online" : "status-pill muted"}>
                        {schedule.enabled ? "enabled" : "paused"}
                      </span>
                      <button
                        className="ghost-button small-button"
                        onClick={() => handleEditSchedule(schedule)}
                        type="button"
                      >
                        Edit
                      </button>
                      <button
                        className="ghost-button small-button"
                        onClick={() => void handleRunSchedule(schedule.id)}
                        type="button"
                      >
                        Run now
                      </button>
                      <button
                        className="ghost-button small-button"
                        onClick={() => void handleDeleteSchedule(schedule.id)}
                        type="button"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
                {!dashboard.schedules.length && (
                  <p className="empty-state">
                    Save the current sync selection as a recurring job to schedule it.
                  </p>
                )}
              </div>
            </article>

            <article className="panel">
              <div className="section-heading">
                <h2>Recent jobs</h2>
                <span className="small-note">{loading ? "Loading" : "Polling every 3s"}</span>
              </div>
              <div className="jobs-list">
                {jobs.map((job) => (
                  <div className="job-row" key={job.id}>
                    <div>
                      <strong>{job.label}</strong>
                      <p>
                        {job.mode === "all" ? "Full library" : job.folder_path} to{" "}
                        {job.destination_path}
                      </p>
                    </div>
                    <span
                      className={job.status === "completed" ? "status-pill online" : "status-pill muted"}
                    >
                      {job.status}
                    </span>
                  </div>
                ))}
              </div>
              {selectedJob && (
                <div className="preview-block">
                  <h3>Latest job log</h3>
                  <code className="log-block">
                    {selectedJob.log_lines.length
                      ? selectedJob.log_lines.join("\n")
                      : selectedJob.command_preview}
                  </code>
                </div>
              )}
            </article>
          </section>
        )}
      </main>
    </div>
  );
}
