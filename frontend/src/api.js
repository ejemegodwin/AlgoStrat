// The one module that knows how to reach the API: base URL, bearer
// token header, and FastAPI's error shape ({ "detail": "..." }).
// Everything else calls api() and never touches fetch directly.

const BASE_URL =
  import.meta.env.VITE_API_URL ??
  (window.location.hostname === "localhost" && window.location.port === "5173"
    ? "http://localhost:8000"
    : window.location.origin);

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function api(path, { method = "GET", body, token } = {}) {
  const headers = {};
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") {
        detail = data.detail;
      }
    } catch {
      // Non-JSON error body (proxy failure, etc.) — keep the status text.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}
