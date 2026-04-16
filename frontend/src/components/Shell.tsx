"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { 
  Users, 
  LayoutDashboard, 
  FileEdit, 
  LogOut, 
  Menu, 
  X,
  PlusCircle,
  Bell,
  MessageSquareText
} from "lucide-react";
import { apiFetch } from "@/lib/api";

export default function Shell({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<any>(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    apiFetch("/api/me")
      .then((data) => {
        if (!data?.logged_in) {
          router.push("/login");
        } else {
          setUser(data);
        }
      })
      .catch(() => router.push("/login"));
  }, [router]);

  if (!user) return <div className="min-h-screen bg-gray-50 flex items-center justify-center">Loading Clinical Environment...</div>;

  const navItems = [
    { name: "Dashboard", href: "/", icon: LayoutDashboard },
    { name: "Patients", href: "/patients", icon: Users },
    { name: "Data Entry", href: "/entry", icon: FileEdit },
  ];

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col md:flex-row">
      {/* Sidebar - Desktop */}
      <aside className="hidden md:flex flex-col w-64 bg-[#1a237e] text-white p-6 shrink-0 transition-all">
        <div className="flex items-center gap-3 mb-10 pb-6 border-b border-indigo-500/30">
          <div className="text-3xl">🏥</div>
          <div>
            <h1 className="font-bold tracking-tight">HD Dashboard</h1>
            <p className="text-[10px] text-indigo-300 uppercase tracking-widest font-bold">Nephrology Unit</p>
          </div>
        </div>

        <nav className="flex-1 space-y-2">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center gap-4 px-4 py-3.5 rounded-xl transition-all font-medium ${
                  isActive 
                    ? "bg-white text-[#1a237e] shadow-lg shadow-indigo-900/20" 
                    : "text-indigo-100 hover:bg-white/10"
                }`}
              >
                <item.icon size={20} />
                {item.name}
              </Link>
            );
          })}
        </nav>

        <div className="mt-10 pt-6 border-t border-indigo-500/30">
          <div className="flex items-center gap-3 px-4 mb-6">
            <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center font-bold text-lg">
              {user.username?.[0].toUpperCase()}
            </div>
            <div className="overflow-hidden">
              <p className="text-sm font-bold truncate">{user.full_name}</p>
              <p className="text-[10px] text-indigo-300 uppercase tracking-widest font-bold">{user.role}</p>
            </div>
          </div>
          <button 
            onClick={() => {
              const url = `https://wa.me/9665183839?text=Hello Doctor, I have a question regarding the HD Dashboard.`;
              window.open(url, "_blank");
            }}
            className="flex items-center gap-3 px-4 py-2 bg-white/10 hover:bg-white/20 rounded-xl text-xs font-bold transition-all text-indigo-100"
          >
            <MessageSquareText size={16} />
            Contact Admin
          </button>
          <button 
            onClick={() => {
              if (typeof window !== "undefined") {
                localStorage.removeItem("clinical_token");
              }
              window.location.href = "/login";
            }}
            className="w-full flex items-center gap-4 px-4 py-3 rounded-xl text-indigo-200 hover:text-white hover:bg-white/10 transition-all font-medium"
          >
            <LogOut size={20} />
            Logout
          </button>
        </div>
      </aside>

      {/* Mobile Nav */}
      <div className="md:hidden bg-[#1a237e] text-white p-4 flex items-center justify-between shadow-lg z-50">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🏥</span>
          <span className="font-bold">HD Dashboard</span>
        </div>
        <button onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}>
          {isMobileMenuOpen ? <X size={28} /> : <Menu size={28} />}
        </button>
      </div>

      {isMobileMenuOpen && (
        <div className="md:hidden fixed inset-0 top-[64px] bg-[#1a237e] z-40 p-6 flex flex-col animate-in fade-in slide-in-from-top-full duration-300">
           <nav className="flex-1 space-y-4">
            {navItems.map((item) => (
              <Link
                key={item.name}
                href={item.href}
                onClick={() => setIsMobileMenuOpen(false)}
                className={`flex items-center gap-4 px-6 py-4 rounded-2xl text-lg font-bold ${
                  pathname === item.href ? "bg-white text-[#1a237e]" : "text-white"
                }`}
              >
                <item.icon size={24} />
                {item.name}
              </Link>
            ))}
          </nav>
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-4 md:p-10">
        <div className="max-w-7xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
