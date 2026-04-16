"use client";

import { useState, useEffect } from "react";
import Shell from "@/components/Shell";
import { apiFetch } from "@/lib/api";
import { Save, AlertCircle, CheckCircle2, FlaskConical, Filter } from "lucide-react";

export default function DataEntryPage() {
  const [patients, setPatients] = useState<any[]>([]);
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7)); // YYYY-MM
  const [data, setData] = useState<Record<number, any>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<{ type: 'success' | 'error', msg: string } | null>(null);

  useEffect(() => {
    setLoading(true);
    apiFetch("/api/patients")
      .then(setPatients)
      .finally(() => setLoading(false));
  }, []);

  const handleInputChange = (patientId: number, field: string, value: string) => {
    setData(prev => ({
      ...prev,
      [patientId]: {
        ...(prev[patientId] || {}),
        [field]: value
      }
    }));
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setStatus(null);
    try {
      const payloads = Object.entries(data).map(([id, values]) => ({
        patient_id: parseInt(id),
        record_month: month,
        ...values
      }));

      await apiFetch("/api/entries/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payloads)
      });

      setStatus({ type: 'success', msg: `Successfully saved ${payloads.length} records for ${month}.` });
      setData({}); // Clear entries after success
    } catch (err) {
      setStatus({ type: 'error', msg: "Failed to save records. Check your connection." });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Shell>
      <div className="mb-12 flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h2 className="text-4xl font-extrabold text-gray-900 tracking-tight">Ward Data Entry</h2>
          <p className="text-gray-400 font-bold uppercase tracking-widest text-[10px] mt-2">Monthly Lab & IDWG Synchronization</p>
        </div>
        
        <div className="flex items-center gap-4 bg-white p-2 rounded-2xl border border-gray-100 shadow-xs">
          <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest pl-4">Target Month</label>
          <input 
            type="month" 
            value={month}
            onChange={e => setMonth(e.target.value)}
            className="p-3 bg-gray-50 rounded-xl border-none outline-hidden font-bold text-[#1a237e]"
          />
        </div>
      </div>

      {status && (
        <div className={`mb-8 p-6 rounded-[1.5rem] flex items-center gap-4 animate-in fade-in slide-in-from-top-4 ${status.type === 'success' ? 'bg-emerald-50 text-emerald-700 border border-emerald-100' : 'bg-red-50 text-red-700 border border-red-100'}`}>
          {status.type === 'success' ? <CheckCircle2 size={24} /> : <AlertCircle size={24} />}
          <span className="font-bold">{status.msg}</span>
        </div>
      )}

      <div className="bg-white rounded-[2rem] shadow-xs border border-gray-100 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-gray-50/50 text-[10px] font-black text-gray-400 uppercase tracking-widest border-b border-gray-100">
                <th className="px-8 py-6">Patient</th>
                <th className="px-6 py-6"><div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-red-500"></div> Hb (g/dL)</div></th>
                <th className="px-6 py-6"><div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-indigo-500"></div> Albumin</div></th>
                <th className="px-6 py-6"><div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-amber-500"></div> Phosphorus</div></th>
                <th className="px-6 py-6"><div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-emerald-500"></div> IDWG (kg)</div></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {loading ? (
                <tr><td colSpan={5} className="py-20 text-center text-gray-400 italic animate-pulse">Loading unit roster...</td></tr>
              ) : patients.map(p => (
                <tr key={p.id} className="hover:bg-indigo-50/30 transition-colors">
                  <td className="px-8 py-6">
                    <div className="font-bold text-gray-900">{p.name}</div>
                    <div className="text-[10px] text-gray-400 font-black tracking-widest">{p.hid}</div>
                  </td>
                  <td className="px-6 py-6">
                    <input 
                      type="number" step="0.1" 
                      placeholder="--"
                      value={data[p.id]?.hb || ""}
                      onChange={e => handleInputChange(p.id, "hb", e.target.value)}
                      className="w-24 p-3 bg-gray-50 border-2 border-transparent rounded-xl focus:border-red-200 focus:bg-white transition-all text-center font-bold"
                    />
                  </td>
                  <td className="px-6 py-6">
                    <input 
                      type="number" step="0.1" 
                      placeholder="--"
                      value={data[p.id]?.albumin || ""}
                      onChange={e => handleInputChange(p.id, "albumin", e.target.value)}
                      className="w-24 p-3 bg-gray-50 border-2 border-transparent rounded-xl focus:border-indigo-200 focus:bg-white transition-all text-center font-bold"
                    />
                  </td>
                  <td className="px-6 py-6">
                    <input 
                      type="number" step="0.1" 
                      placeholder="--"
                      value={data[p.id]?.phosphorus || ""}
                      onChange={e => handleInputChange(p.id, "phosphorus", e.target.value)}
                      className="w-24 p-3 bg-gray-50 border-2 border-transparent rounded-xl focus:border-amber-200 focus:bg-white transition-all text-center font-bold"
                    />
                  </td>
                  <td className="px-6 py-6">
                    <input 
                      type="number" step="0.1" 
                      placeholder="--"
                      value={data[p.id]?.idwg || ""}
                      onChange={e => handleInputChange(p.id, "idwg", e.target.value)}
                      className="w-24 p-3 bg-gray-50 border-2 border-transparent rounded-xl focus:border-emerald-200 focus:bg-white transition-all text-center font-bold"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        
        <div className="p-8 bg-gray-50/50 border-t border-gray-100 flex justify-end">
          <button 
            onClick={handleSubmit}
            disabled={submitting || Object.keys(data).length === 0}
            className="flex items-center gap-3 px-10 py-5 bg-[#1a237e] text-white rounded-2xl font-black shadow-2xl shadow-indigo-900/20 hover:scale-[1.02] active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none"
          >
            {submitting ? "Finalizing Sync..." : "Save Ward Records"}
            <Save size={20} />
          </button>
        </div>
      </div>
    </Shell>
  );
}
