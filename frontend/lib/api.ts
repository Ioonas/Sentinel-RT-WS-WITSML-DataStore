const API_BASE = "/admin-api/v1";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status: number, code = "error") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)sentinel_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers.set("x-csrf-token", csrfToken());
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const body = (payload ?? {}) as { message?: string; error?: string };
    throw new ApiError(
      body.message ?? `Error HTTP ${response.status}`,
      response.status,
      body.error ?? "error",
    );
  }

  return payload as T;
}

export type Grant = {
  object_type: string;
  action: "read" | "write" | "delete";
  uid_well?: string | null;
};

export type UserView = {
  id: string;
  email: string;
  display_name: string;
  role: string;
  permissions: string[];
  enabled: boolean;
  must_change_password: boolean;
  created_at: string | null;
  last_login_at: string | null;
};

export type SessionView = { user: UserView; expires_at: string | null };

export type ProfileSessionView = {
  reference: string;
  created_at: string;
  authenticated_at: string;
  expires_at: string;
  current: boolean;
};

export type ServerConfigView = {
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  description: string;
  product_name: string;
  vendor: string;
  version: string;
  schema_version: string;
  api_version: string;
  setup_completed: boolean;
  max_data_nodes: number;
  max_data_points: number;
  growing_timeout_seconds: number;
  change_detection_seconds: number;
  max_request_latest_values: number;
  cascaded_delete: boolean;
  support_uom_conversion: boolean;
  updated_at: string | null;
  updated_by: string | null;
};

export type ServiceAccountView = {
  id: string;
  name: string;
  role: string;
  enabled: boolean;
  grants: Grant[];
  well_scope: string[] | null;
  created_at: string | null;
  last_used_at: string | null;
  rotated_at: string | null;
  can_cascade_delete: boolean;
  replaced_by_id: string | null;
  replacement_expires_at: string | null;
  archived_at?: string | null;
  purge_at?: string | null;
};

export type CredentialView = { secret: string | null; message: string };

export type InvitationSummaryView = {
  id: string;
  email: string;
  role: string;
  created_by: string;
  created_at: string | null;
  expires_at: string;
};

export type InvitationView = {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  token: string | null;
};

export type ObjectView = {
  object_type: string;
  uid: string;
  uid_well: string | null;
  uid_wellbore: string | null;
  name: string | null;
  created_at: string;
  changed_at: string;
  growing: boolean;
};

export type AuditEventView = {
  id: number;
  occurred_at: string;
  actor_id: string | null;
  actor_name: string;
  channel: string;
  action: string;
  object_type: string | null;
  object_uid: string | null;
  result: string;
  correlation_id: string;
  duration_ms: number | null;
  details: Record<string, unknown>;
};

export type AuditPage = { items: AuditEventView[]; next_cursor: number | null };

export type RoleView = { name: string; permissions: string[] };
export type PermissionView = { name: string };
export type AccessView = {
  identity: string;
  kind: string;
  role: string;
  permissions: string[];
  grants: Grant[];
};

export type DependencyHealth = {
  status: string;
  dependencies: Record<string, Record<string, unknown>>;
};

export type HealthView = { status: string };
export type MessageView = { message: string };

export type SetupStatus = { setup_completed: boolean };
