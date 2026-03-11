import { FormEvent, useEffect, useRef, useState, startTransition } from "react";
import {
  AppSettings,
  DashboardResponse,
  JobDetail,
  SyncPreviewResponse,
  disconnectPutio,
  fetchDashboard,
  fetchJobs,
  previewSync,
  runSync,
  saveSettings,
  startPutioAuth,
  testJellyfin,
} from "./lib/api";

type SyncMode = "all" | "folder";

const fallbackDashboard: DashboardResponse = {
  product_name: "get-put.io",
  tagline: "A calmer control plane for syncing cloud media into local libraries.",
  settings: {
    putio: {
      app_id: "",
      client_secret: "",
      redirect_uri: "http://localhost:8787/api/auth/putio/callback",
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
    },
    sync_defaults: {
      destination_path: "/media/staging",
    },
  },
  connections: [],
  folders: [],
  destinations: [],
  jobs: [],
  putio_connected: false,
  jellyfin_enabled: false,
};

export default function App() {
  const [dashboard, setDashboard] = useState<DashboardResponse>(fallbackDashboard);
  const [jobs, setJobs] = useState<JobDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<SyncMode>("folder");
  const [folderPath, setFolderPath] = useState("/Movies");
  const [destination, setDestination] = useState("/media/staging");
  const [preview, setPreview] = useState<SyncPreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [settingsDraft, setSettingsDraft] = useState<AppSettings>(fallbackDashboard.settings);
  const [settingsSaved, setSettingsSaved] = useState<string | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [jellyfinMessage, setJellyfinMessage] = useState<string | null>(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const seededRef = useRef(false);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const [dashboardResult, jobsResult] = await Promise.all([
          fetchDashboard(),
          fetchJobs(),
        ]);
        if (!active) {
          return;
        }
        startTransition(() => {
          setDashboard(dashboardResult);
          setJobs(jobsResult);
          if (!seededRef.current) {
            setSettingsDraft(dashboardResult.settings);
            setDestination(
              dashboardResult.settings.sync_defaults.destination_path ||
                dashboardResult.destinations[1] ||
                "/media/staging",
            );
            setFolderPath(dashboardResult.folders[1]?.path ?? "/Movies");
            seededRef.current = true;
          }
          setError(null);
        });
      } catch (loadError) {
        if (!active) {
          return;
        }
        setError(
          loadError instanceof Error
            ? loadError.message
            : "API unavailable. The shell is still usable while the backend comes online.",
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    setLoading(true);
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 3000);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  async function handlePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPreviewLoading(true);
    setPreviewError(null);

    try {
      const result = await previewSync({
        mode,
        folder_path: mode === "folder" ? folderPath : undefined,
        destination_path: destination,
      });
      setPreview(result);
    } catch {
      setPreviewError("Could not generate a sync preview.");
    } finally {
      setPreviewLoading(false);
    }
  }

  async function handleRunNow() {
    setRunError(null);
    try {
      const job = await runSync({
        mode,
        folder_path: mode === "folder" ? folderPath : undefined,
        destination_path: destination,
      });
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
    } catch (runIssue) {
      setRunError(runIssue instanceof Error ? runIssue.message : "Unable to run job.");
    }
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
    } catch (saveError) {
      setSettingsError(saveError instanceof Error ? saveError.message : "Unable to save settings.");
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
    } catch (authError) {
      setSettingsError(authError instanceof Error ? authError.message : "Unable to start Put.io auth.");
      setAuthBusy(false);
    }
  }

  async function handleDisconnectPutio() {
    setAuthBusy(true);
    try {
      await disconnectPutio();
      setSettingsSaved("Put.io disconnected.");
    } catch (disconnectError) {
      setSettingsError(
        disconnectError instanceof Error ? disconnectError.message : "Unable to disconnect Put.io.",
      );
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
    } catch (testError) {
      setSettingsError(
        testError instanceof Error ? testError.message : "Unable to test Jellyfin connection.",
      );
    }
  }

  const selectedJob = jobs[0];

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
              <span className="signal-label">Target</span>
              <strong>{destination}</strong>
            </div>
            <div className="signal-card">
              <span className="signal-label">Runtime</span>
              <strong>LXC / macOS</strong>
            </div>
          </div>
        </section>

        <section className="status-grid">
          <article className="panel settings-panel">
            <div className="section-heading">
              <h2>Put.io link</h2>
              <span className="small-note">
                {dashboard.putio_connected ? "Connected" : "OAuth required"}
              </span>
            </div>
            <form className="settings-form" onSubmit={handleSaveSettings}>
              <label>
                <span>Put.io app ID</span>
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
                  : "Create a Put.io app, save the credentials here, then start the browser login."}
              </p>
            </form>
          </article>

          <article className="panel settings-panel">
            <div className="section-heading">
              <h2>Jellyfin hook</h2>
              <span className="small-note">
                {settingsDraft.jellyfin.enabled ? "Optional post-sync action" : "Disabled"}
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
              <div className="inline-actions">
                <button className="primary-button" disabled={settingsSaving} type="submit">
                  Save hook settings
                </button>
                <button className="ghost-button" onClick={handleTestJellyfin} type="button">
                  Test connection
                </button>
              </div>
              <p className="muted-copy">
                Use a full base URL and an admin API key. Username and password are not required.
              </p>
            </form>
          </article>
        </section>

        <section className="workspace-grid">
          <article className="panel composer-panel">
            <div className="section-heading">
              <h2>Compose a sync</h2>
              <span className="small-note">Preview first</span>
            </div>

            <form className="sync-form" onSubmit={handlePreview}>
              <label>
                <span>Default destination path</span>
                <input
                  onChange={(event) =>
                    setSettingsDraft((current) => ({
                      ...current,
                      sync_defaults: { destination_path: event.target.value },
                    }))
                  }
                  value={settingsDraft.sync_defaults.destination_path}
                />
              </label>

              <label>
                <span>Transfer mode</span>
                <div className="mode-toggle">
                  <button
                    className={mode === "folder" ? "mode-option active" : "mode-option"}
                    onClick={() => setMode("folder")}
                    type="button"
                  >
                    Specific folder
                  </button>
                  <button
                    className={mode === "all" ? "mode-option active" : "mode-option"}
                    onClick={() => setMode("all")}
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
                  value={folderPath}
                />
              </label>

              <label>
                <span>Destination path</span>
                <input
                  list="destinations"
                  onChange={(event) => setDestination(event.target.value)}
                  placeholder="/media/staging"
                  value={destination}
                />
                <datalist id="destinations">
                  {dashboard.destinations.map((item) => (
                    <option key={item} value={item} />
                  ))}
                </datalist>
              </label>

              <div className="inline-actions">
                <button className="primary-button" disabled={previewLoading} type="submit">
                  {previewLoading ? "Building preview..." : "Preview rclone plan"}
                </button>
                <button className="ghost-button" onClick={handleRunNow} type="button">
                  Run sync now
                </button>
              </div>
            </form>

            {previewError && <p className="error-banner">{previewError}</p>}
            {error && <p className="error-banner">{error}</p>}
            {runError && <p className="error-banner">{runError}</p>}
            {settingsError && <p className="error-banner">{settingsError}</p>}
            {settingsSaved && <p className="success-banner">{settingsSaved}</p>}
            {jellyfinMessage && <p className="success-banner">{jellyfinMessage}</p>}
          </article>

          <article className="panel preview-panel">
            <div className="section-heading">
              <h2>Command preview</h2>
              <span className="small-note">What will actually run</span>
            </div>

            {preview ? (
              <div className="preview-content">
                <code>{preview.command_preview}</code>
                <div className="preview-block">
                  <h3>Steps</h3>
                  <ul>
                    {preview.steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ul>
                </div>
                <div className="preview-block">
                  <h3>Warnings</h3>
                  {preview.warnings.length ? (
                    <ul>
                      {preview.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>No immediate warnings.</p>
                  )}
                </div>
              </div>
            ) : (
              <div className="empty-preview">
                <p>Choose a scope and destination, then preview the generated `rclone` plan.</p>
              </div>
            )}
          </article>
        </section>

        <section className="jobs-grid">
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
      </main>
    </div>
  );
}
