// All communication with the Flask backend goes through this file (Fetch API).

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:5000").replace(/\/+$/, "");
const TIMEOUT_MS = 25000; // backend may call two weather endpoints, so allow some time

export class ApiError extends Error {
  constructor(message, { status = 0, code = "unknown", details = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details; // e.g. { ph: "Soil pH must be between 0 and 14." }
  }
}

async function request(path, { method = "GET", body, signal } = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, TIMEOUT_MS);

  // Let the caller cancel too (e.g. when the location changes mid-request).
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }

    if (!response.ok) {
      const err = data && data.error;
      throw new ApiError((err && err.message) || `The server returned an error (${response.status}).`, {
        status: response.status,
        code: (err && err.code) || "http_error",
        details: (err && err.details) || null,
      });
    }
    if (data === null) {
      throw new ApiError("The server returned an unreadable response.", {
        status: response.status,
        code: "bad_response",
      });
    }
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (timedOut) {
      throw new ApiError("The request took too long. Please try again.", { code: "timeout" });
    }
    if (signal && signal.aborted) throw error; // cancelled by the caller; callers ignore this
    throw new ApiError(
      `Cannot reach the Smart Crop Advisor server at ${API_BASE}. Make sure the backend is running.`,
      { code: "network" }
    );
  } finally {
    clearTimeout(timer);
  }
}

export const getHealth = (signal) => request("/api/health", { signal });

export const getWeather = (latitude, longitude, signal) =>
  request(`/api/weather?latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}`, {
    signal,
  });

export const searchPlaces = (name, region, signal) => {
  const params = new URLSearchParams({ name });
  if (region) params.set("region", region);
  return request(`/api/geocode?${params.toString()}`, { signal });
};

export const recommendSoil = (values) =>
  request("/api/recommend", { method: "POST", body: { mode: "soil", ...values } });

export const recommendWeather = (values) =>
  request("/api/recommend/weather", { method: "POST", body: values });
