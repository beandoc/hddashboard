// Support hidden spaces in Vercel env vars
const rawApiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const API_BASE = rawApiUrl.trim().replace(/\/$/, ""); 

export async function apiFetch(endpoint: string, options: RequestInit = {}, retries = 3) {
  const url = `${API_BASE}${endpoint}`;
  const token = typeof window !== "undefined" ? localStorage.getItem("clinical_token") : null;
  
  const headers = { 
    "Content-Type": "application/json",
    ...options.headers 
  } as any;
  
  if (token) headers["Authorization"] = `Bearer ${token}`;

  for (let i = 0; i < retries; i++) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s patience

      const res = await fetch(url, { 
        ...options, 
        headers,
        signal: controller.signal,
        credentials: "include" 
      });
      clearTimeout(timeoutId);

      // Handle Render Cold Starts / Wake-ups (502 / 503)
      if (res.status === 503 || res.status === 502) {
        if (i < retries - 1) {
          await new Promise(r => setTimeout(r, 4000));
          continue;
        }
      }

      // Selective Logout: ONLY on true 401 Unauthorized
      if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("clinical_token");
        window.location.href = "/login";
        return null; // Stop propagation
      }

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server error: ${res.status}`);
      }

      return res.json();
    } catch (error: any) {
      if (i === retries - 1) throw error;
      // Network failures or timeouts: Wait and retry without logging out
      await new Promise(r => setTimeout(r, 3000));
    }
  }
}
