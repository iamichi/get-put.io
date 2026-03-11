import { FormEvent, useEffect, useState, startTransition } from "react";
import {
  DashboardResponse,
  SyncPreviewResponse,
  fetchDashboard,
  previewSync,
} from "./lib/api";

type SyncMode = "all" | "folder";

const fallbackDashboard: DashboardResponse = {
  product_name: "get-put.io",
  tagline: "A calmer control plane for syncing cloud media into local libraries.",
  connections: [],
  folders: [],
  destinations: [],
  jobs: [],
};

export default function App() {
  const [dashboard, setDashboard] = useState<DashboardResponse>(fallbackDashboard);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<SyncMode>("folder");
  const [folderPath, setFolderPath] = useState("/Movies");
  const [destination, setDestination] = useState("/media/staging");
  const [preview, setPreview] = useState<SyncPreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchDashboard()
      .then((result) => {
        if (!active) {
          return;
        }
        startTransition(() => {
          setDashboard(result);
          setDestination(result.destinations[1] ?? "/media/staging");
          setFolderPath(result.folders[1]?.path ?? "/Movies");
          setError(null);
        });
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setError("API unavailable. The shell is still usable while the backend comes online.");
      })
      .finally(() => {
        if (!active) {
          return;
        }
        setLoading(false);
      });

    return () => {
      active = false;
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
              <button className="primary-button" type="button">
                Connect Put.io
              </button>
              <button className="ghost-button" type="button">
                Inspect Jellyfin link
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
          <article className="panel">
            <div className="section-heading">
              <h2>Service links</h2>
              <span className="small-note">{loading ? "Checking" : "Live view"}</span>
            </div>
            <div className="connection-list">
              {dashboard.connections.map((connection) => (
                <div className="connection-row" key={connection.service}>
                  <div>
                    <strong>{connection.service}</strong>
                    <p>{connection.summary}</p>
                  </div>
                  <span
                    className={
                      connection.connected ? "status-pill online" : "status-pill muted"
                    }
                  >
                    {connection.connected ? "Ready" : "Pending"}
                  </span>
                </div>
              ))}
              {!dashboard.connections.length && (
                <p className="empty-state">Connections will appear after the backend loads.</p>
              )}
            </div>
          </article>

          <article className="panel">
            <div className="section-heading">
              <h2>Folder lane</h2>
              <span className="small-note">Put.io scope</span>
            </div>
            <div className="folder-list">
              {dashboard.folders.map((folder) => (
                <button
                  className={`folder-chip ${folder.path === folderPath ? "selected" : ""}`}
                  key={folder.id}
                  type="button"
                  onClick={() => {
                    setMode(folder.path === "/" ? "all" : "folder");
                    setFolderPath(folder.path);
                  }}
                >
                  <span>{folder.name}</span>
                  <small>{folder.child_count} items</small>
                </button>
              ))}
            </div>
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
                <button className="ghost-button" type="button">
                  Save draft job
                </button>
              </div>
            </form>

            {previewError && <p className="error-banner">{previewError}</p>}
            {error && <p className="error-banner">{error}</p>}
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
              <h2>Draft jobs</h2>
              <span className="small-note">Future scheduler inputs</span>
            </div>
            <div className="jobs-list">
              {dashboard.jobs.map((job) => (
                <div className="job-row" key={job.id}>
                  <div>
                    <strong>{job.label}</strong>
                    <p>
                      {job.mode === "all" ? "Full library" : "Folder-scoped"} to {job.target_path}
                    </p>
                  </div>
                  <span className="status-pill muted">{job.status}</span>
                </div>
              ))}
            </div>
          </article>
        </section>
      </main>
    </div>
  );
}

