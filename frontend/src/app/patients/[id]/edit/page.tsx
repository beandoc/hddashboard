"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import Shell from "@/components/Shell";
import { apiFetch } from "@/lib/api";
import { Save, X, User as UserIcon, Phone, Clock, Calendar } from "lucide-react";
import Link from "next/link";

export default function PatientFormPage() {
  const params = useParams();
  const router = useRouter();
  const isEdit = !!params.id;
  
  const [formData, setFormData] = useState({
    name: "",
    contact: "",
    age: "",
    gender: "Male",
    diagnosis: "",
    hd_slot_1: "",
    hd_slot_2: "",
    hd_slot_3: "",
    clinical_remarks: "",
    is_active: true
  });
  const [loading, setLoading] = useState(isEdit);

  useEffect(() => {
    if (isEdit) {
      apiFetch(`/api/patients/${params.id}`)
        .then(data => {
          setFormData(data);
          setLoading(false);
        })
        .catch(() => {
          setLoading(false);
          alert("Error loading patient data.");
        });
    }
  }, [params.id, isEdit]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const endpoint = isEdit ? `/api/patients/${params.id}` : "/api/patients";
      const method = isEdit ? "PUT" : "POST";
      
      await apiFetch(endpoint, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData)
      });
      
      router.push("/patients");
    } catch (err) {
      alert("Failed to save patient. Please check your connection.");
    }
  };

  if (loading) return <Shell><div className="animate-pulse">Loading patient profile...</div></Shell>;

  return (
    <Shell>
      <div className="max-w-4xl mx-auto">
        <div className="mb-12 flex items-center justify-between">
          <div>
            <h2 className="text-4xl font-extrabold text-gray-900 tracking-tight">
              {isEdit ? "Update Clinical Record" : "New Patient Registry"}
            </h2>
            <p className="text-gray-400 font-bold uppercase tracking-widest text-[10px] mt-2">
              Unit Enrollment & Demographics
            </p>
          </div>
          <Link href="/patients" className="p-4 bg-white rounded-2xl shadow-xs border border-gray-100 hover:bg-gray-50 transition-all text-[#1a237e]">
            <X size={20} />
          </Link>
        </div>

        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Demographic Card */}
          <div className="bg-white rounded-[2rem] p-10 shadow-xs border border-gray-100">
            <h3 className="text-lg font-black text-[#1a237e] mb-8 flex items-center gap-3">
              <UserIcon size={20} /> Demographics & Contact
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              <div className="space-y-3">
                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest px-1">Full Clinical Name</label>
                <input 
                  type="text" 
                  value={formData.name}
                  onChange={e => setFormData({...formData, name: e.target.value})}
                  className="w-full p-4 bg-gray-50 border-2 border-transparent rounded-2xl focus:border-[#1a237e] focus:bg-white outline-hidden transition-all text-gray-900 font-medium"
                  placeholder="e.g. Rahul Sharma"
                  required
                />
              </div>
              <div className="space-y-3">
                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest px-1">Contact Number</label>
                <div className="relative">
                  <Phone size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-300" />
                  <input 
                    type="text" 
                    value={formData.contact}
                    onChange={e => setFormData({...formData, contact: e.target.value})}
                    className="w-full p-4 pl-12 bg-gray-50 border-2 border-transparent rounded-2xl focus:border-[#1a237e] focus:bg-white outline-hidden transition-all text-gray-900 font-medium"
                    placeholder="91XXXXXXXXXX"
                  />
                </div>
              </div>
              <div className="space-y-3">
                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest px-1">Age & Gender</label>
                <div className="flex gap-4">
                  <input 
                    type="number" 
                    value={formData.age}
                    onChange={e => setFormData({...formData, age: e.target.value})}
                    className="w-24 p-4 bg-gray-50 border-2 border-transparent rounded-2xl focus:border-[#1a237e] focus:bg-white outline-hidden transition-all text-gray-900 font-medium"
                    placeholder="Age"
                  />
                  <select 
                    value={formData.gender}
                    onChange={e => setFormData({...formData, gender: e.target.value})}
                    className="flex-1 p-4 bg-gray-50 border-2 border-transparent rounded-2xl focus:border-[#1a237e] focus:bg-white outline-hidden transition-all text-gray-900 font-medium appearance-none"
                  >
                    <option>Male</option>
                    <option>Female</option>
                    <option>Other</option>
                  </select>
                </div>
              </div>
              <div className="space-y-3">
                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest px-1">Primary Diagnosis</label>
                <input 
                  type="text" 
                  value={formData.diagnosis}
                  onChange={e => setFormData({...formData, diagnosis: e.target.value})}
                  className="w-full p-4 bg-gray-50 border-2 border-transparent rounded-2xl focus:border-[#1a237e] focus:bg-white outline-hidden transition-all text-gray-900 font-medium"
                  placeholder="e.g. CKD Category 5"
                />
              </div>
            </div>
          </div>

          {/* Schedule Card */}
          <div className="bg-[#f8f9ff] rounded-[2rem] p-10 shadow-xs border border-indigo-50">
            <h3 className="text-lg font-black text-[#1a237e] mb-8 flex items-center gap-3">
              <Clock size={20} /> Treatment Schedule (HD Slots)
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-10">
              {[1, 2, 3].map(num => (
                <div key={num} className="space-y-3">
                  <label className="text-[10px] font-black text-indigo-300 uppercase tracking-widest px-1">HD Slot {num}</label>
                  <select 
                    value={(formData as any)[`hd_slot_${num}`]}
                    onChange={e => setFormData({...formData, [`hd_slot_${num}`]: e.target.value})}
                    className="w-full p-4 bg-white border-2 border-transparent rounded-2xl focus:border-[#1a237e] outline-hidden transition-all text-gray-900 font-medium shadow-sm"
                  >
                    <option value="">No Slot</option>
                    <option>Mon Morning</option>
                    <option>Mon Afternoon</option>
                    <option>Tue Morning</option>
                    <option>Tue Afternoon</option>
                    <option>Wed Morning</option>
                    <option>Wed Afternoon</option>
                    <option>Thu Morning</option>
                    <option>Thu Afternoon</option>
                    <option>Fri Morning</option>
                    <option>Fri Afternoon</option>
                    <option>Sat Morning</option>
                    <option>Sat Afternoon</option>
                  </select>
                </div>
              ))}
            </div>

            <div className="space-y-3">
              <label className="text-[10px] font-black text-indigo-300 uppercase tracking-widest px-1">Clinical Background & Remarks</label>
              <textarea 
                value={(formData as any).clinical_remarks}
                onChange={e => setFormData({...formData, clinical_remarks: e.target.value})}
                className="w-full p-6 bg-white border-2 border-transparent rounded-3xl focus:border-[#1a237e] outline-hidden transition-all text-gray-900 font-medium shadow-sm min-h-[150px]"
                placeholder="Enter detailed clinical notes, permanent issues, or treatment background..."
              />
            </div>
          </div>

          <div className="flex items-center gap-6">
            <button 
              type="submit"
              className="flex-1 bg-[#1a237e] hover:bg-indigo-900 text-white font-black py-6 rounded-[2rem] shadow-2xl shadow-indigo-900/20 active:scale-[0.98] transition-all flex items-center justify-center gap-3"
            >
              <Save size={20} />
              {isEdit ? "Update Clinical Record" : "Enroll Patient"}
            </button>
            <button 
              type="button"
              onClick={() => {
                if(confirm("Are you sure you want to deactivate this patient?")) {
                  setFormData({...formData, is_active: false});
                  // Submit logic would follow
                }
              }}
              className="px-8 py-6 bg-red-50 text-red-600 font-black rounded-[2rem] hover:bg-red-100 transition-all border border-red-100"
            >
              Deactivate
            </button>
          </div>
        </form>
      </div>
    </Shell>
  );
}
