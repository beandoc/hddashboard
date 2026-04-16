"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, API_BASE } from "@/lib/api";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      console.log(`DEBUG: Final JSON Login attempt at ${API_BASE}/login`);
      
      const response = await fetch(`${API_BASE}/login`, {
        method: "POST",
        body: JSON.stringify({ username, password }),
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        credentials: "include",
      });

      if (response.ok) {
        console.log("DEBUG: Login response was OK.");
        router.push("/");
      } else {
        const text = await response.text();
        console.log(`DEBUG: Server rejected with ${response.status}. Body:`, text);
        try {
          const data = JSON.parse(text);
          setError(data.detail || `Clinical access denied (Status: ${response.status})`);
        } catch (e) {
          setError(`Server Error (Status: ${response.status}). Check Console logs.`);
        }
      }
    } catch (err: any) {
      console.error("DEBUG: Request failed entirely:", err);
      setError(`Connection failed: ${err.message || "Network Error"}. Please check if the clinical backend is awake.`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-linear-to-br from-[#1a237e] to-[#0d47a1] p-4">
      <div className="w-full max-auto max-w-md bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl overflow-hidden border border-white/20 transition-all duration-300 hover:-translate-y-1">
        <div className="p-8 text-center">
          <div className="text-5xl mb-4">🏥</div>
          <h1 className="text-3xl font-bold text-[#1a237e] mb-2 text-balance leading-tight">HD Dashboard</h1>
          <p className="text-gray-500 text-sm mb-8">Nephrology Unit Management System</p>
          
          {error && (
            <div className="bg-red-50 text-red-600 p-4 rounded-xl text-sm mb-6 border border-red-100 animate-in fade-in slide-in-from-top-2 duration-300">
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-6 text-left">
            <div>
              <label className="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2 px-1">
                Clinical ID / Username
              </label>
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full p-4 bg-gray-50 border-2 border-transparent rounded-xl focus:border-[#007bff] focus:bg-white outline-hidden transition-all text-gray-900"
                placeholder="Enter username"
                autoFocus
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2 px-1">
                Secure Password
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full p-4 bg-gray-50 border-2 border-transparent rounded-xl focus:border-[#007bff] focus:bg-white outline-hidden transition-all text-gray-900"
                placeholder="••••••••"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[#1a237e] hover:bg-[#0d47a1] text-white py-4 rounded-xl font-bold text-lg shadow-lg shadow-indigo-500/20 active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none"
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>
          
          <div className="mt-8 text-gray-400 text-[10px] uppercase tracking-widest font-medium">
            CH(SC) CLINICAL DATA DIVISION © 2026
          </div>
        </div>
      </div>
    </div>
  );
}
