"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { apiFetch } from "@/lib/api";
import { 
  Users, 
  Activity, 
  TrendingDown, 
  Droplet, 
  Calendar, 
  AlertCircle,
  Clock,
  ArrowUpRight,
  ChevronRight
} from "lucide-react";

export default function DashboardPage() {
  const [data, setData] = useState<any>(null);
  const [lastSync, setLastSync] = useState<string>("");
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchData = async () => {
    setIsRefreshing(true);
    try {
      const result = await apiFetch("/api/dashboard");
      setData(result);
      setLastSync(new Date().toLocaleTimeString());
    } catch (err) {
      console.error("Dashboard refresh failed", err);
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (!data) return <Shell><div className="animate-pulse flex flex-col gap-4">Loading clinical insights...</div></Shell>;

  const metrics = data.metrics;

  const MetricCard = ({ icon: Icon, title, value, color, highlighted = false, names = [] }: any) => (
    <div className={`relative group bg-white rounded-3xl p-6 shadow-xs border border-gray-100 transition-all duration-300 hover:shadow-xl hover:shadow-gray-200/50 hover:-translate-y-1 ${highlighted ? 'ring-2 ring-red-500/20 bg-red-50/10' : ''}`}>
      <div className="flex items-start justify-between mb-4">
        <div className={`p-4 rounded-2xl ${color} bg-opacity-10 text-opacity-100`}>
          <Icon size={24} className={color.replace('bg-', 'text-')} />
        </div>
        {highlighted && (
          <span className="flex h-3 w-3 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
          </span>
        )}
      </div>
      <div className="space-y-1">
        <h3 className="text-4xl font-black text-gray-900 tracking-tight">{value}</h3>
        <p className="text-sm font-bold text-gray-400 uppercase tracking-widest">{title}</p>
      </div>
      
      {names.length > 0 && (
        <div className="absolute inset-0 bg-white/95 backdrop-blur-sm rounded-3xl p-6 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-center border-2 border-indigo-100 shadow-2xl z-10">
          <p className="text-[10px] font-black text-indigo-400 uppercase tracking-widest mb-3">Flagged Patients</p>
          <ul className="text-sm font-bold text-gray-700 space-y-2">
            {names.slice(0, 5).map((n: string) => <li key={n} className="flex items-center gap-2"><div className="w-1.5 h-1.5 rounded-full bg-indigo-500"></div>{n}</li>)}
            {names.length > 5 && <li className="text-gray-400 text-xs">+ {names.length - 5} more</li>}
          </ul>
        </div>
      )}
    </div>
  );

  return (
    <Shell>
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-12">
        <div>
          <div className="flex items-center gap-3 text-emerald-500 mb-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
            <p className="text-xs font-black uppercase tracking-[0.2em]">Live Monitoring Active</p>
          </div>
          <h2 className="text-4xl font-extrabold text-gray-900 tracking-tight">Clinic Intelligence</h2>
        </div>
        
        <div className="flex items-center gap-4 bg-white px-6 py-4 rounded-3xl shadow-xs border border-gray-100">
          <Clock size={20} className="text-indigo-400" />
          <div className="text-right">
            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest leading-none mb-1">Last Sync</p>
            <p className="text-sm font-black text-[#1a237e] tabular-nums">{lastSync}</p>
          </div>
          <button 
            onClick={fetchData} 
            className={`ml-4 p-2 rounded-full transition-all ${isRefreshing ? 'animate-spin text-indigo-600' : 'text-gray-400 hover:bg-gray-50 hover:text-indigo-600'}`}
          >
            <Activity size={20} />
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
        <MetricCard icon={Users} title="Patient Registry" value={metrics.total} color="bg-indigo-500" />
        <MetricCard icon={Calendar} title="Today's Dialysis" value={metrics.todays_hd.count} names={metrics.todays_hd.names} color="bg-emerald-500" />
        <MetricCard icon={AlertCircle} title="Non-AVF Access" value={metrics.non_avf.count} names={metrics.non_avf.names} highlighted={metrics.non_avf.count > 0} color="bg-amber-500" />
        <MetricCard icon={Activity} title="High IDWG (>2.5kg)" value={metrics.high_idwg.count} names={metrics.high_idwg.names} highlighted={metrics.high_idwg.count > 0} color="bg-rose-500" />
        <MetricCard icon={TrendingDown} title="Low Albumin (<3.5)" value={metrics.low_albumin.count} names={metrics.low_albumin.names} highlighted={metrics.low_albumin.count > 0} color="bg-orange-500" />
        <MetricCard icon={Droplet} title="Hb Drop Alert" value={metrics.hb_drop_alert.count} names={metrics.hb_drop_alert.names} highlighted={metrics.hb_drop_alert.count > 0} color="bg-red-500" />
      </div>

      <section className="mt-16 grid grid-cols-1 lg:grid-cols-3 gap-10">
        <div className="lg:col-span-2 bg-white rounded-[2rem] p-10 shadow-xs border border-gray-100">
          <div className="flex items-center justify-between mb-10">
            <h3 className="text-2xl font-black text-gray-900 tracking-tight">High Priority Clinical Alerts</h3>
            <span className="bg-red-50 text-red-600 text-[10px] font-black uppercase tracking-widest px-4 py-1.5 rounded-full">Require Action</span>
          </div>
          <div className="divide-y divide-gray-100">
            {metrics.hb_drop_alert.names.length > 0 ? metrics.hb_drop_alert.names.map((name: string) => (
              <div key={name} className="py-6 flex items-center justify-between group cursor-pointer hover:px-2 transition-all">
                <div className="flex items-center gap-6">
                  <div className="w-12 h-12 rounded-2xl bg-red-50 flex items-center justify-center text-red-500">
                    <Droplet size={20} />
                  </div>
                  <div>
                    <h4 className="font-bold text-gray-900 group-hover:text-red-500 transition-colors">{name}</h4>
                    <p className="text-xs text-gray-400 font-medium">Significant Hemoglobin drop detected since last month</p>
                  </div>
                </div>
                <ChevronRight size={20} className="text-gray-300 group-hover:text-red-500 group-hover:translate-x-1 transition-all" />
              </div>
            )) : <p className="text-gray-400 font-medium italic py-4">No critical Hb alerts today.</p>}
          </div>
        </div>

        <div className="bg-[#1a237e] rounded-[2rem] p-10 text-white shadow-2xl shadow-indigo-900/40 relative overflow-hidden">
          <div className="absolute top-0 right-0 p-8 opacity-10">
             <Calendar size={160} />
          </div>
          <div className="relative z-10">
            <h3 className="text-2xl font-black tracking-tight mb-8">Scheduling Utility</h3>
            <p className="text-indigo-200 text-sm font-medium mb-10 leading-relaxed">System has identified <b>{metrics.todays_hd.count} patients</b> scheduled for dialysis slots today.</p>
            <div className="space-y-4">
              {metrics.todays_hd.names.slice(0, 4).map((name: string) => (
                <div key={name} className="bg-white/10 backdrop-blur-md rounded-2xl p-4 flex items-center justify-between border border-white/10">
                  <span className="font-bold">{name}</span>
                  <div className="p-2 rounded-lg bg-emerald-500 text-white cursor-pointer hover:bg-emerald-400 transition-colors">
                    <ArrowUpRight size={14} />
                  </div>
                </div>
              ))}
            </div>
            <button className="w-full mt-10 py-4 bg-white text-[#1a237e] font-black rounded-2xl uppercase tracking-widest text-xs hover:bg-indigo-50 active:scale-[0.98] transition-all">
              Send Mass Reminders
            </button>
          </div>
        </div>
      </section>
    </Shell>
  );
}
