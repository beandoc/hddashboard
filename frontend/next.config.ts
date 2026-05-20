import type { NextConfig } from "next";

const BACKEND = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") || "http://localhost:8080";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // Proxy all backend routes to FastAPI
      { source: "/ocr/:path*",       destination: `${BACKEND}/ocr/:path*` },
      { source: "/api/:path*",       destination: `${BACKEND}/api/:path*` },
      { source: "/analytics/:path*", destination: `${BACKEND}/analytics/:path*` },
      { source: "/entry/:path*",     destination: `${BACKEND}/entry/:path*` },
      { source: "/patients/:path*",  destination: `${BACKEND}/patients/:path*` },
      { source: "/login",            destination: `${BACKEND}/login` },
      { source: "/health",           destination: `${BACKEND}/health` },
    ];
  },
};

export default nextConfig;
