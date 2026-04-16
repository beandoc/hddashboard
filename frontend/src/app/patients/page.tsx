"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { apiFetch } from "@/lib/api";
import { 
  Search, 
  MessageCircle, 
  History, 
  Edit, 
  UserPlus,
  Filter
} from "lucide-react";
import Link from "next/link";

export default function PatientsPage() {
  const [patients, setPatients] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch(`/api/patients?q=${search}`)
      .then(setPatients)
      .finally(() => setLoading(false));
  }, [search]);

  const sendSchedule = async (id: number) => {
    try {
      const res = await apiFetch(`/api/send-schedule/${id}`, { method: "POST" });
      alert(res.message);
    } catch (err) {
      alert("Failed to send schedule.");
    }
  };

  return (
    <Shell>
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-12">
        <div>
          <h2 className="text-4xl font-extrabold text-gray-900 tracking-tight">Patient Registry</h2>
          <p className="text-gray-400 font-bold uppercase tracking-widest text-[10px] mt-2">Managing {patients.length} active patients</p>
        </div>
        <Link 
          href="/patients/new"
          className="bg-[#1a237e] text-white px-8 py-4 rounded-2xl font-black text-xs uppercase tracking-widest flex items-center gap-3 hover:bg-[#0d47a1] shadow-xl shadow-indigo-900/20 active:scale-[0.98] transition-all"
        >
          <UserPlus size={18} />
          Add New Patient
        </Link>
      </div>

      <div className="bg-white rounded-[2rem] p-4 md:p-8 shadow-xs border border-gray-100 mb-10">
        <div className="relative mb-8">
          <Search className="absolute left-6 top-1/2 -translate-y-1/2 text-gray-400" size={20} />
          <input
            type="text"
            placeholder="Search by name, HID, or contact..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-16 pr-6 p-5 bg-gray-50 border-2 border-transparent rounded-[1.5rem] focus:border-indigo-100 focus:bg-white outline-hidden transition-all text-gray-900 font-bold"
          />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-separate border-spacing-y-4">
            <thead>
              <tr className="text-[10px] font-black text-gray-400 uppercase tracking-[0.2em]">
                <th className="px-6 py-2">HID</th>
                <th className="px-6 py-2">Patient Name</th>
                <th className="px-6 py-2">Access Type</th>
                <th className="px-6 py-2">Contact</th>
                <th className="px-6 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="text-center py-20 text-gray-400 font-bold italic animate-pulse">Synchronizing records...</td></tr>
              ) : patients.map((p) => (
                <tr key={p.id} className="group hover:-translate-y-0.5 transition-all">
                  <td className="px-6 py-5 bg-gray-50/50 rounded-l-[1.2rem] font-black text-[#1a237e] tabular-nums text-sm border-y border-l border-transparent group-hover:bg-indigo-50/50 group-hover:border-indigo-100 transition-all">{p.hid}</td>
                  <td className="px-6 py-5 bg-gray-50/50 border-y border-transparent group-hover:bg-indigo-50/50 group-hover:border-indigo-100 transition-all">
                    <span className="font-bold text-gray-900">{p.name}</span>
                    <span className="ml-2 px-2 py-0.5 bg-gray-200 text-gray-500 rounded text-[10px] uppercase font-black tracking-widest">{p.sex?.[0]}</span>
                  </td>
                  <td className="px-6 py-5 bg-gray-50/50 border-y border-transparent group-hover:bg-indigo-50/50 group-hover:border-indigo-100 transition-all">
                    <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest ${p.access === 'AVF' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                      {p.access || 'No Access Data'}
                    </span>
                  </td>
                  <td className="px-6 py-5 bg-gray-50/50 border-y border-transparent group-hover:bg-indigo-50/50 group-hover:border-indigo-100 transition-all font-bold text-gray-500 text-sm tabular-nums">{p.contact || '—'}</td>
                  <td className="px-6 py-5 bg-gray-50/50 rounded-r-[1.2rem] border-y border-r border-transparent group-hover:bg-indigo-50/50 group-hover:border-indigo-100 transition-all text-right">
                    <div className="flex items-center justify-end gap-2">
                       <button 
                        onClick={() => sendSchedule(p.id)}
                        title="Send Schedule"
                        className="p-3 text-emerald-500 hover:bg-emerald-500 hover:text-white rounded-xl transition-all"
                      >
                        <MessageCircle size={18} />
                      </button>
                      <Link 
                        href={`/patients/${p.id}/timeline`}
                        title="Timeline"
                        className="p-3 text-indigo-500 hover:bg-indigo-500 hover:text-white rounded-xl transition-all"
                      >
                        <History size={18} />
                      </Link>
                      <Link 
                        href={`/patients/${p.id}/edit`}
                        title="Edit"
                        className="p-3 text-gray-400 hover:bg-gray-100 hover:text-gray-900 rounded-xl transition-all"
                      >
                        <Edit size={18} />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Shell>
  );
}
