export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001";

export async function apiFetch(
  path: string,
  token: string | null,
  opts: RequestInit = {},
) {
  const res = await fetch(`${API_BASE}/api${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    let detail = "";
    try {
      detail = JSON.stringify(await res.json());
    } catch {
      /* ignore */
    }
    const err = new Error(`API ${res.status} ${detail}`);
    // @ts-expect-error attach status for callers
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

/**
 * POST a multipart body (e.g. a file upload). Unlike apiFetch we must NOT set
 * Content-Type — the browser adds it with the correct multipart boundary.
 */
export async function apiUpload(
  path: string,
  token: string | null,
  formData: FormData,
) {
  const res = await fetch(`${API_BASE}/api${path}`, {
    method: "POST",
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: formData,
    cache: "no-store",
  });

  if (!res.ok) {
    let detail = "";
    try {
      detail = JSON.stringify(await res.json());
    } catch {
      /* ignore */
    }
    const err = new Error(`API ${res.status} ${detail}`);
    // @ts-expect-error attach status for callers
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}
