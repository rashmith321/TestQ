// Thin wrapper around the FastAPI backend. All errors become ApiError with a readable message.
const BASE = import.meta.env.VITE_API_BASE || "";

export class ApiError extends Error {
  constructor(message, code = "error", details = {}) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, options);
  } catch {
    throw new ApiError("Can't reach the backend. Start it with: uvicorn main:app --port 8000", "backend_unreachable");
  }
  let body = null;
  try {
    body = await response.json();
  } catch {
    /* non-JSON body */
  }
  if (!response.ok) {
    const err = body?.error;
    const detail = body?.detail;
    const message =
      err?.message ||
      (typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : null) ||
      `Request failed (HTTP ${response.status}).`;
    throw new ApiError(message, err?.code || `http_${response.status}`, err?.details);
  }
  return body;
}

export function startAnalysis(profileUrl) {
  return request("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_url: profileUrl }),
  });
}

export function getJob(jobId) {
  return request(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export async function downloadJson(filename) {
  let response;
  try {
    response = await fetch(`${BASE}/api/download/${encodeURIComponent(filename)}`);
  } catch {
    throw new ApiError("Can't reach the backend to download the file.");
  }
  if (!response.ok) throw new ApiError("The JSON file is no longer on the server. Run the analysis again.");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Client-side mirror of the backend check, for instant feedback. The backend stays authoritative.
export function quickValidate(raw) {
  const value = raw.trim();
  if (!value) return "Enter a LeetCode profile URL.";
  let url;
  try {
    url = new URL(value.includes("://") ? value : `https://${value}`);
  } catch {
    return "That doesn't look like a URL.";
  }
  if (!["leetcode.com", "www.leetcode.com"].includes(url.hostname.toLowerCase()))
    return "Use a leetcode.com profile URL, like https://leetcode.com/u/username/.";
  return null;
}
