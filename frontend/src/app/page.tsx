"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { apiFetch, API_BASE } from "@/lib/api";
import { 
  Users, 
  Activity, 
  TrendingDown, 
  Droplet, 
  Calendar, 
  AlertCircle,
  Clock,
  ArrowUpRight,
  ChevronRight,
  ShieldCheck,
  Zap,
  TestTube,
  Beef,
  Microscope,
  Stethoscope
} from "lucide-react";

export default function DashboardPage() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastSync, setLastSync] = useState<string>("");
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchData = async () => {
    setIsRefreshing(true);
    try {
      const result = await apiFetch("/api/dashboard");
      if (result) {
        setData(result);
        setError(null);
        setLastSync(new Date().toLocaleTimeString());
      }
    } catch (err: any) {
      console.error("Dashboard refresh failed", err);
      setError(err.message || "Failed to connect to clinic server.");
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (error) return (
    <Shell>
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-6">
        <div className="p-4 bg-red-50 rounded-2xl mb-6">
          <AlertCircle size={40} className="text-red-500" />
        </div>
        <h3 className="text-xl font-black text-gray-900 mb-2">Connection Disrupted</h3>
        <p className="text-gray-500 font-medium mb-2 max-w-sm">{error}</p>
        <p className="text-[10px] text-gray-400 uppercase tracking-widest font-black mb-8">Targeting: {API_BASE}</p>
        <button 
          onClick={fetchData} 
          className="px-8 py-4 bg-[#1a237e] text-white font-black rounded-2xl uppercase tracking-widest text-xs hover:bg-indigo-900 transition-all"
        >
          Try Reconnecting
        </button>
      </div>
    </Shell>
  );

  if (!data) return <Shell><div className="flex items-center justify-center min-h-[60vh] text-indigo-400 font-bold animate-pulse">Initializing Clinical Intelligence...</div></Shell>;

  const metrics = data.metrics;

  const MetricCard = ({ icon: Icon, title, value, color, highlighted = false, names = [] }: any) => (
    <div className={`relative group bg-white rounded-2xl p-6 shadow-sm border border-gray-100 transition-all duration-300 hover:shadow-xl hover:shadow-gray-200/50 hover:-translate-y-1 ${highlighted ? 'ring-2 ring-red-500/20 bg-red-50/5' : ''}`}>
      <div className="flex items-start justify-between mb-4">
        <div className={`p-3 rounded-xl ${color} bg-opacity-10 text-opacity-100`}>
          <Icon size={20} className={color.replace('bg-', 'text-')} />
        </div>
        {highlighted && (
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
          </span>
        )}
      </div>
      <div className="space-y-0.5">
        <h3 className="text-3xl font-black text-gray-900 tabular-nums">{value}</h3>
        <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest">{title}</p>
      </div>
      
      {names.length > 0 && (
        <div className="absolute inset-x-0 bottom-0 top-0 bg-white/95 backdrop-blur-sm rounded-2xl p-6 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-center border-2 border-indigo-100 shadow-2xl z-10 pointer-events-none group-hover:pointer-events-auto">
          <p className="text-[10px] font-black text-indigo-400 uppercase tracking-widest mb-3">Flagged Patients</p>
          <ul className="text-xs font-bold text-gray-700 space-y-1.5 overflow-y-auto max-h-[80%]">
            {names.slice(0, 8).map((n: string) => <li key={n} className="flex items-center gap-2 truncate"><div className="shrink-0 w-1.5 h-1.5 rounded-full bg-indigo-500"></div>{n}</li>)}
            {names.length > 8 && <li className="text-gray-400 text-[10px]">+ {names.length - 8} more</li>}
          </ul>
        </div>
      )}
    </div>
  );

  const SectionTitle = ({ children, icon: Icon }: any) => (
    <div className="flex items-center gap-3 mb-6">
      <div className="p-2 bg-gray-50 rounded-lg text-gray-400">
        <Icon size={16} />
      </div>
      <h3 className="text-sm font-black text-gray-400 uppercase tracking-widest">{children}</h3>
      <div className="h-px bg-gray-100 grow ml-4"></div>
    </div>
  );

  return (
    <Shell>
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-12">
        <div>
          <div className="flex items-center gap-3 text-emerald-500 mb-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
            <p className="text-xs font-black uppercase tracking-[0.2em]">Clinical Heartbeat Active</p>
          </div>
          <h2 className="text-4xl font-black text-gray-900 tracking-tight">Ward Intelligence</h2>
        </div>
        
        <div className="flex items-center gap-4 bg-white/50 backdrop-blur-md px-6 py-4 rounded-2xl shadow-sm border border-white/40">
          <div className="flex items-center gap-3 pr-4 border-r border-gray-100">
            <Clock size={16} className="text-indigo-400" />
            <p className="text-sm font-black text-[#1a237e] tabular-nums">{lastSync}</p>
          </div>
          <button 
            onClick={fetchData} 
            className={`p-2 rounded-xl transition-all ${isRefreshing ? 'animate-spin text-indigo-600' : 'text-gray-400 hover:bg-gray-100 hover:text-indigo-600'}`}
          >
            <Activity size={18} />
          </button>
        </div>
      </header>

      {/* Ward Dynamics */}
      <SectionTitle icon={Users}>Ward Dynamics</SectionTitle>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
        <MetricCard icon={Users} title="Total Patients" value={metrics.total} color="bg-indigo-600" />
        <MetricCard icon={Calendar} title="Today's Dialysis" value={metrics.todays_hd.count} names={metrics.todays_hd.names} color="bg-emerald-600" />
        <MetricCard icon={AlertCircle} title="Non-AVF Access" value={metrics.non_avf.count} names={metrics.non_avf.names} highlighted={metrics.non_avf.count > 0} color="bg-amber-600" />
        <MetricCard icon={ShieldCheck} title="Vaccine Due" value={metrics.vaccine_due.count} names={metrics.vaccine_due.names} highlighted={metrics.vaccine_due.count > 0} color="bg-purple-600" />
      </div>

      {/* Clinical Risks */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 mb-12">
        {/* Anemia & Nutrition */}
        <section>
          <SectionTitle icon={Droplet}>Anemia & Nutrition</SectionTitle>
          <div className="grid grid-cols-2 gap-6">
            <MetricCard icon={Droplet} title="Hb Drop Alert" value={metrics.hb_drop_alert.count} names={metrics.hb_drop_alert.names} highlighted={metrics.hb_drop_alert.count > 0} color="bg-red-600" />
            <MetricCard icon={TrendingDown} title="Low Albumin" value={metrics.low_albumin.count} names={metrics.low_albumin.names} highlighted={metrics.low_albumin.count > 0} color="bg-orange-600" />
            <MetricCard icon={TestTube} title="IV Iron Rec" value={metrics.iv_iron.count} names={metrics.iv_iron.names} color="bg-pink-600" />
            <MetricCard icon={Beef} title="Low Protein" value={metrics.low_protein.count} names={metrics.low_protein.names} color="bg-slate-600" />
          </div>
        </section>

        {/* Bone & Fluid Health */}
        <section>
          <SectionTitle icon={Activity}>Bone & Fluid Health</SectionTitle>
          <div className="grid grid-cols-2 gap-6">
            <MetricCard icon={Activity} title="High IDWG" value={metrics.high_idwg.count} names={metrics.high_idwg.names} highlighted={metrics.high_idwg.count > 3} color="bg-rose-600" />
            <MetricCard icon={Zap} title="Intensification" value={metrics.dialysis_intensification.count} names={metrics.dialysis_intensification.names} highlighted={metrics.dialysis_intensification.count > 0} color="bg-yellow-500" />
            <MetricCard icon={Microscope} title="High Phosphorus" value={metrics.high_phosphorus.count} names={metrics.high_phosphorus.names} color="bg-cyan-600" />
            <MetricCard icon={Stethoscope} title="Low Calcium" value={metrics.low_calcium.count} names={metrics.low_calcium.names} color="bg-sky-600" />
          </div>
        </section>
      </div>

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-10">
        <div className="lg:col-span-2 bg-white rounded-3xl p-8 border border-gray-100 shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-xl font-black text-gray-900">Priority Clinical Feed</h3>
            <span className="p-1 px-3 bg-red-50 text-red-600 text-[10px] font-black rounded-lg uppercase tracking-widest">Urgent Reviews</span>
          </div>
          
          <div className="space-y-4">
             {/* Combined Feed */}
             {[...metrics.hb_drop_alert.names, ...metrics.dialysis_intensification.names].slice(0, 5).map((name: string) => (
               <div key={name} className="flex items-center justify-between p-4 rounded-2xl bg-gray-50/50 hover:bg-gray-50 transition-colors border border-transparent hover:border-gray-200 group cursor-pointer">
                 <div className="flex items-center gap-4">
                   <div className="w-10 h-10 rounded-xl bg-white shadow-sm flex items-center justify-center text-red-500">
                     <AlertCircle size={18} />
                   </div>
                   <div>
                     <p className="font-bold text-gray-900 group-hover:text-red-600 transition-colors">{name}</p>
                     <p className="text-[10px] font-bold text-gray-400 uppercase tracking-tighter">Immediate Clinical Audit Required</p>
                   </div>
                 </div>
                 <ChevronRight size={16} className="text-gray-300 transition-transform group-hover:translate-x-1" />
               </div>
             ))}
             {metrics.hb_drop_alert.names.length === 0 && metrics.dialysis_intensification.names.length === 0 && (
               <div className="text-center py-12">
                 <p className="text-gray-400 text-sm font-medium italic italic">Ward status optimal. No urgent interventions identified.</p>
               </div>
             )}
          </div>
        </div>

        <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm">
           <h3 className="text-xl font-black text-gray-900 mb-6">Liver & Metabolic</h3>
           <div className="space-y-6">
              <div>
                <div className="flex justify-between items-end mb-2">
                  <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest">Elevated LFTs</p>
                  <p className="text-xl font-black text-amber-500 tabular-nums">{metrics.elevated_liver.count}</p>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-amber-500 transition-all duration-1000" 
                    style={{ width: `${(metrics.elevated_liver.count / metrics.total) * 100}%` }}
                  ></div>
                </div>
              </div>
              
              <div>
                <div className="flex justify-between items-end mb-2">
                  <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest">Secondary PTH Alert</p>
                  <p className="text-xl font-black text-purple-500 tabular-nums">{metrics.high_ipth.count}</p>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-purple-500 transition-all duration-1000" 
                    style={{ width: `${(metrics.high_ipth.count / metrics.total) * 100}%` }}
                  ></div>
                </div>
              </div>

              <div className="pt-4 mt-4 border-t border-gray-50 flex items-center justify-between">
                <div>
                   <p className="text-sm font-black text-gray-900">Ward Stability</p>
                   <p className="text-[10px] text-gray-400 font-bold uppercase tracking-tight">Current Month Composite</p>
                </div>
                <div className="text-right">
                   <p className="text-2xl font-black text-emerald-500">92%</p>
                </div>
              </div>
           </div>
        </div>
      </section>
    </Shell>
  );
}
