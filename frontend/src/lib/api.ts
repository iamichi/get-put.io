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

export type JobSummary = {
  id: string;
  label: string;
  mode: "all" | "folder";
  target_path: string;
  status: "draft" | "running" | "completed" | "failed";
  last_run: string;
};

export type DashboardResponse = {
  product_name: string;
  tagline: string;
  connections: ConnectionStatus[];
  folders: FolderNode[];
  destinations: string[];
  jobs: JobSummary[];
};

export type SyncPreviewResponse = {
  title: string;
  command_preview: string;
  steps: string[];
  warnings: string[];
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export async function fetchDashboard(): Promise<DashboardResponse> {
  const response = await fetch(`${API_BASE_URL}/api/dashboard`);
  if (!response.ok) {
    throw new Error("Unable to load dashboard");
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
    throw new Error("Unable to preview sync");
  }

  return response.json();
}

