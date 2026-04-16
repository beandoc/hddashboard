"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Shell from "@/components/Shell";
import { apiFetch } from "@/lib/api";
import { 
  ArrowLeft,
  ChevronRight,
  Droplet,
  Activity,
  Award,
  FlaskConical,
  Scale
} from "lucide-react";
import Link from "next/link";

export default function PatientTimelinePage() {
  const params = useParams();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch(`/api/patients/${params.id}/timeline`)
      .then(setData)
      .finally(() => setLoading(false));
  }, [params.id]);

  if (loading) return <Shell><div className="animate-pulse">Retrieving longitudinal records...</div></Shell>;
  if (!data) return <Shell>Patient not found.</Shell>;

  return (
    <Shell>
      <div className="mb-12 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link href="/patients" className="p-4 bg-white rounded-2xl shadow-xs border border-gray-100 hover:bg-gray-50 transition-all text-[#1a237e]">
            <ArrowLeft size={20} />
          </Link>
          <div>
            <h2 className="text-4xl font-extrabold text-gray-900 tracking-tight">{data.patient.name}</h2>
            <p className="text-gray-400 font-bold uppercase tracking-widest text-[10px] mt-2">Clinical Timeline & Longitudinal Data</p>
          </div>
        </div>
      </div>

      <div className="space-y-12">
        {data.timeline.length > 0 ? (
          data.timeline.map((entry: any, index: number) => (
            <div key={entry.month} className="relative flex flex-col md:flex-row gap-8 group">
              {/* Timeline Line */}
              {index !== data.timeline.length - 1 && (
                <div className="absolute left-8 top-16 bottom-[-48px] w-1 bg-indigo-100 hidden md:block"></div>
              )}
              
              {/* Month Badge */}
              <div className="w-16 h-16 rounded-[1.5rem] bg-[#1a237e] text-white flex flex-col items-center justify-center shrink-0 shadow-lg shadow-indigo-900/20 z-10 transition-transform group-hover:scale-110">
                <span className="text-[10px] font-black uppercase tracking-widest opacity-70 leading-none mb-1">{entry.month.split('-')[1]}</span>
                <span className="text-lg font-black leading-none">{entry.month.split('-')[0].slice(2)}</span>
              </div>

              <div className="flex-1 bg-white rounded-[2rem] p-8 shadow-xs border border-gray-100 transition-all hover:shadow-xl hover:shadow-gray-200/50">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8 pb-6 border-b border-gray-100">
                  <h3 className="text-xl font-black text-[#1a237e] tracking-tight">{entry.label}</h3>
                  <div className="flex flex-wrap gap-2">
                    {entry.hb < 10 && <span className="bg-red-50 text-red-600 px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest">Low Hb</span>}
                    {entry.idwg > 2.5 && <span className="bg-amber-50 text-amber-600 px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest">High IDWG</span>}
                  </div>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
                  <div className="space-y-1">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 flex items-center gap-1.5"><Droplet size={12} className="text-red-500" /> Hemoglobin</p>
                    <p className="text-xl font-black text-gray-900 tabular-nums">{entry.hb || '—'} <span className="text-xs text-gray-400">g/dL</span></p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 flex items-center gap-1.5"><Activity size={12} className="text-[#1a237e]" /> Albumin</p>
                    <p className="text-xl font-black text-gray-900 tabular-nums">{entry.albumin || '—'} <span className="text-xs text-gray-400">g/dL</span></p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 flex items-center gap-1.5"><FlaskConical size={12} className="text-indigo-400" /> Phosphorus</p>
                    <p className="text-xl font-black text-gray-900 tabular-nums">{entry.phosphorus || '—'} <span className="text-xs text-gray-400">mg/dL</span></p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 flex items-center gap-1.5"><Scale size={12} className="text-emerald-500" /> IDWG</p>
                    <p className="text-xl font-black text-gray-900 tabular-nums">{entry.idwg || '—'} <span className="text-xs text-gray-400">kg</span></p>
                  </div>
                </div>

                {entry.issues && (
                  <div className="mt-8 p-6 bg-gray-50 rounded-2xl border border-gray-100 italic text-gray-600 text-sm leading-relaxed">
                    &quot;{entry.issues}&quot;
                  </div>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="py-20 text-center bg-white rounded-[2rem] border-2 border-dashed border-gray-100">
            <p className="text-gray-400 font-bold italic">No longitudinal records found for this patient.</p>
          </div>
        )}

      </div>
    </Shell>
  );
}
