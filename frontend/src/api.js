const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api";

export function saveTokens(tokens) {
  sessionStorage.setItem("smarttask.access", tokens.access);
  sessionStorage.setItem("smarttask.refresh", tokens.refresh);
}

export function clearTokens() {
  sessionStorage.removeItem("smarttask.access");
  sessionStorage.removeItem("smarttask.refresh");
}

async function decode(response) {
  if (response.status === 204 || response.status === 205) return null;
  const body = await response.text();
  if (!body) return null;
  try {
    return JSON.parse(body);
  } catch {
    return { detail: body };
  }
}

function messageFrom(data, status) {
  if (typeof data?.detail === "string") return data.detail;
  if (data && typeof data === "object") {
    const first = Object.values(data).flat(Infinity).find((value) => typeof value === "string");
    if (first) return first;
  }
  return `Request failed (${status}).`;
}

async function send(path, options = {}, retry = true) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const access = sessionStorage.getItem("smarttask.access");
  if (access) headers.set("Authorization", `Bearer ${access}`);
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers });
  } catch {
    throw new Error("Cannot reach the API. Start the Django server and try again.");
  }
  if (response.status === 401 && retry && !path.includes("/auth/token")) {
    const refresh = sessionStorage.getItem("smarttask.refresh");
    if (refresh) {
      try {
        const renewed = await fetch(`${API_URL}/auth/token/refresh/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh }),
        });
        if (renewed.ok) {
          const tokens = await decode(renewed);
          saveTokens({ access: tokens.access, refresh: tokens.refresh || refresh });
          return send(path, options, false);
        }
      } catch {
        clearTokens();
      }
    }
    clearTokens();
  }
  const data = await decode(response);
  if (!response.ok) throw new Error(messageFrom(data, response.status));
  return data;
}

export const api = {
  get: (path) => send(path),
  post: (path, body) => send(path, { method: "POST", body: JSON.stringify(body) }),
  patch: (path, body) => send(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: (path) => send(path, { method: "DELETE" }),
  login: (email, password) =>
    send("/auth/token/", { method: "POST", body: JSON.stringify({ username: email, password }) }, false),
  register: (body) =>
    send("/auth/register/", { method: "POST", body: JSON.stringify(body) }, false),
  logout: (refresh) => send("/auth/logout/", { method: "POST", body: JSON.stringify({ refresh }) }, false),
};
