export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function apiFetch(endpoint: string, options: RequestInit = {}) {
  const url = `${API_BASE}${endpoint}`;
  
  // Retrieve the "Clinical Passport" from LocalStorage
  const token = typeof window !== "undefined" ? localStorage.getItem("clinical_token") : null;
  
  const defaultOptions: RequestInit = {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "Authorization": `Bearer ${token}` } : {}),
      ...options.headers,
    },
    // Keep credentials for legacy/session support
    credentials: "include", 
  };

  const response = await fetch(url, defaultOptions);
  
  if (response.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("clinical_token");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return null;
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API error: ${response.status}`);
  }

  return response.json();
}
