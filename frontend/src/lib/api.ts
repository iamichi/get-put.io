export type ConnectionStatus = {
  service: string;
  connected: boolean;
  summary: string;
};

export type FolderNode = {
  id: string;
  name: string;
  path: string;
  child_count: number;
};

export type BreadcrumbNode = {
  name: string;
  path: string;
};

export type PutioBrowser = {
  current_path: string;
  parent_path?: string | null;
  breadcrumbs: BreadcrumbNode[];
  entries: FolderNode[];
};

export type JobSummary = {
  id: string;
  label: string;
  mode: "all" | "folder";
  target_path: string;
  status: "queued" | "running" | "completed" | "failed";
  last_run: string;
  refresh_triggered: boolean;
};

export type RecurringSchedule = {
  id: string;
  name: string;
  enabled: boolean;
  mode: "all" | "folder";
  folder_path?: string | null;
  destination_path: string;
  schedule_type: "interval" | "daily";
  interval_hours: number;
  daily_time: string;
  next_run_at?: string | null;
  last_run_at?: string | null;
  last_job_id?: string | null;
};

export type PutioToken = {
  access_token: string;
  token_type: string;
  expires_in?: number | null;
  expiry?: string | null;
  refresh_token?: string | null;
  scope?: string | null;
};

export type PutioSettings = {
  app_id: string;
  client_secret: string;
  redirect_uri: string;
  token?: PutioToken | null;
  oauth_state?: string | null;
  account_username?: string | null;
  account_user_id?: number | null;
  connected_at?: string | null;
};

export type JellyfinSettings = {
  enabled: boolean;
  base_url: string;
  api_key: string;
  refresh_after_sync: boolean;
  refresh_only_on_change: boolean;
  selected_library_ids: string[];
};

export type SyncDefaults = {
  destination_path: string;
};

export type AppSettings = {
  putio: PutioSettings;
  jellyfin: JellyfinSettings;
  sync_defaults: SyncDefaults;
};

export type DashboardResponse = {
  product_name: string;
  tagline: string;
  settings: AppSettings;
  connections: ConnectionStatus[];
  folders: FolderNode[];
  putio_browser: PutioBrowser;
  jellyfin_libraries: JellyfinLibrary[];
  destinations: string[];
  jobs: JobSummary[];
  schedules: RecurringSchedule[];
  putio_connected: boolean;
  jellyfin_enabled: boolean;
};

export type SyncPreviewResponse = {
  title: string;
  command_preview: string;
  command_parts: string[];
  steps: string[];
  warnings: string[];
};

export type JobDetail = {
  id: string;
  label: string;
  mode: "all" | "folder";
  folder_path?: string | null;
  destination_path: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  command_preview: string;
  warnings: string[];
  log_lines: string[];
  refresh_requested: boolean;
  refresh_triggered: boolean;
  files_changed: boolean;
  error_message?: string | null;
};

export type JellyfinLibrary = {
  id: string;
  name: string;
  collection_type?: string | null;
  locations: string[];
  refresh_status?: string | null;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function readError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    return payload.detail ?? "Request failed";
  } catch {
    return "Request failed";
  }
}

export async function fetchDashboard(): Promise<DashboardResponse> {
  const response = await fetch(`${API_BASE_URL}/api/dashboard`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function browsePutio(path: string): Promise<PutioBrowser> {
  const response = await fetch(`${API_BASE_URL}/api/putio/browser?path=${encodeURIComponent(path)}`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function previewSync(payload: {
  mode: "all" | "folder";
  folder_path?: string;
  destination_path: string;
}): Promise<SyncPreviewResponse> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  return response.json();
}

export async function fetchJellyfinLibraries(): Promise<JellyfinLibrary[]> {
  const response = await fetch(`${API_BASE_URL}/api/jellyfin/libraries`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const payload = await response.json();
  return payload.libraries;
}

export async function runSync(payload: {
  mode: "all" | "folder";
  folder_path?: string;
  destination_path: string;
}): Promise<JobDetail> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function fetchSchedules(): Promise<RecurringSchedule[]> {
  const response = await fetch(`${API_BASE_URL}/api/schedules`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const payload = await response.json();
  return payload.schedules;
}

export async function createSchedule(payload: Omit<RecurringSchedule, "id" | "next_run_at" | "last_run_at" | "last_job_id">): Promise<RecurringSchedule> {
  const response = await fetch(`${API_BASE_URL}/api/schedules`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function updateSchedule(
  scheduleId: string,
  payload: Omit<RecurringSchedule, "id" | "next_run_at" | "last_run_at" | "last_job_id">,
): Promise<RecurringSchedule> {
  const response = await fetch(`${API_BASE_URL}/api/schedules/${scheduleId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function deleteSchedule(scheduleId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/schedules/${scheduleId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}

export async function runSchedule(scheduleId: string): Promise<JobDetail> {
  const response = await fetch(`${API_BASE_URL}/api/schedules/${scheduleId}/run`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function fetchJobs(): Promise<JobDetail[]> {
  const response = await fetch(`${API_BASE_URL}/api/jobs`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const payload = await response.json();
  return payload.jobs;
}

export async function saveSettings(settings: AppSettings): Promise<AppSettings> {
  const response = await fetch(`${API_BASE_URL}/api/settings`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ settings }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const payload = await response.json();
  return payload.settings;
}

export async function startPutioAuth(): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/auth/putio/start`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const payload = await response.json();
  return payload.auth_url;
}

export async function disconnectPutio(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/auth/putio/disconnect`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}

export async function testJellyfin(): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/jellyfin/test`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const payload = await response.json();
  return payload.message;
}
