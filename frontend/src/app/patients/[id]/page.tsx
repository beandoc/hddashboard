"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Shell from "@/components/Shell";
import { apiFetch } from "@/lib/api";
import {
  Activity, AlertTriangle, Calendar, ChevronRight,
  Droplet, FlaskConical, Heart, TrendingDown, TrendingUp,
  User, Zap, ShieldAlert, Microscope,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface LatestLabs {
  hb: number | null;
  albumin: number | null;
  phosphorus: number | null;
  calcium: number | null;
  ipth: number | null;
  ferritin: number | null;
  tsat: number | null;
  kt_v: number | null;
  urr: number | null;
  idwg: number | null;
  crp: number | null;
  wbc_count: number | null;
  creatinine: number | null;
  potassium: number | null;
  sodium: number | null;
  nt_probnp: number | null;
  ejection_fraction: number | null;
  record_month: string | null;
}

interface MortalityRisk {
  available: boolean;
  prob_1yr: number | null;
  risk_level: string;
  feature_hash: string | null;
}

interface PatientProfile {
  id: number;
  hid_no: string;
  name: string;
  age: number | null;
  sex: string | null;
  diagnosis: string | null;
  hd_wef_date: string | null;
  access_type: string | null;
  hd_frequency: number | null;
  hd_slot_1: string | null;
  dry_weight: number | null;
  is_active: boolean;
  latest_labs: LatestLabs;
  mortality_risk: MortalityRisk;
  alerts: string[];
  trend_hb: { month: string; value: number }[];
  trend_albumin: { month: string; value: number }[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function riskBadge(level: string) {
  const map: Record<string, string> = {
    "Very High": "bg-red-600 text-white",
    "High":      "bg-orange-500 text-white",
    "Moderate":  "bg-yellow-400 text-gray-900",
    "Low":       "bg-emerald-500 text-white",
    "Unknown":   "bg-gray-400 text-white",
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${map[level] ?? map["Unknown"]}`}>
      {level}
    </span>
  );
}

function LabRow({
  label, value, unit, low, high,
}: {
  label: string; value: number | null; unit: string;
  low?: number | null; high?: number | null;
}) {
  if (value == null) return null;
  const flagLow  = low  != null && value < low;
  const flagHigh = high != null && value > high;
  const flagged  = flagLow || flagHigh;
  return (
    <div className={`flex justify-between items-center py-1.5 border-b border-gray-800 ${flagged ? "text-red-400" : "text-gray-200"}`}>
      <span className="text-sm text-gray-400">{label}</span>
      <span className={`text-sm font-medium tabular-nums ${flagged ? "text-red-400" : ""}`}>
        {typeof value === "number" ? value.toFixed(1) : value}
        <span className="text-gray-500 ml-1">{unit}</span>
        {flagLow  && <TrendingDown className="inline ml-1 w-3 h-3" />}
        {flagHigh && <TrendingUp   className="inline ml-1 w-3 h-3" />}
      </span>
    </div>
  );
}

function SparkBar({ data, color = "#60a5fa" }: { data: { month: string; value: number }[]; color?: string }) {
  if (!data.length) return <p className="text-gray-500 text-xs">No data</p>;
  const max = Math.max(...data.map(d => d.value));
  const min = Math.min(...data.map(d => d.value));
  const range = max - min || 1;
  return (
    <div className="flex items-end gap-0.5 h-10">
      {data.slice(-12).map((d, i) => (
        <div
          key={i}
          title={`${d.month}: ${d.value}`}
          style={{
            height: `${Math.max(10, ((d.value - min) / range) * 100)}%`,
            backgroundColor: color,
            flex: 1,
            borderRadius: 2,
          }}
        />
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PatientProfilePage() {
  const params  = useParams();
  const id      = params?.id as string;
  const [data,  setData]  = useState<PatientProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    apiFetch(`/api/v1/patients/${id}/profile`)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  if (error) return (
    <Shell>
      <div className="flex items-center gap-2 text-red-400 p-8">
        <AlertTriangle className="w-5 h-5" />
        <span>{error}</span>
      </div>
    </Shell>
  );

  if (!data) return (
    <Shell>
      <div className="p-8 text-gray-400 animate-pulse">Loading patient profile…</div>
    </Shell>
  );

  const labs = data.latest_labs;
  const mort = data.mortality_risk;

  return (
    <Shell>
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm text-gray-500 mb-6">
        <Link href="/patients" className="hover:text-gray-300">Patients</Link>
        <ChevronRight className="w-3.5 h-3.5" />
        <span className="text-gray-200">{data.name}</span>
      </nav>

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-semibold text-white">{data.name}</h1>
            {!data.is_active && (
              <span className="px-2 py-0.5 rounded bg-gray-700 text-gray-400 text-xs">Inactive</span>
            )}
          </div>
          <p className="text-gray-400 text-sm">
            HID: <span className="text-gray-200 font-mono">{data.hid_no}</span>
            {data.age && <> · {data.age}y</>}
            {data.sex && <> · {data.sex}</>}
            {data.diagnosis && <> · {data.diagnosis}</>}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {mort.available && riskBadge(mort.risk_level)}
          <Link
            href={`/entry/${id}`}
            className="px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors"
          >
            Enter Monthly Data
          </Link>
          <Link
            href={`/patients/${id}/edit`}
            className="px-3 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-white text-sm font-medium transition-colors"
          >
            Edit Profile
          </Link>
        </div>
      </div>

      {/* Alerts */}
      {data.alerts.length > 0 && (
        <div className="mb-6 rounded-lg border border-red-800 bg-red-950/40 p-4">
          <div className="flex items-center gap-2 mb-2 text-red-400 font-medium text-sm">
            <ShieldAlert className="w-4 h-4" />
            Clinical Alerts
          </div>
          <ul className="space-y-1">
            {data.alerts.map((a, i) => (
              <li key={i} className="text-red-300 text-sm">· {a}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 3-column grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {/* ── Dialysis Info ── */}
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
          <div className="flex items-center gap-2 mb-4 text-gray-400 text-xs font-semibold uppercase tracking-wider">
            <Calendar className="w-3.5 h-3.5" />
            Dialysis Schedule
          </div>
          {[
            ["HD Since",       data.hd_wef_date ?? "—"],
            ["Frequency",      data.hd_frequency ? `${data.hd_frequency}×/week` : "—"],
            ["Slot",           data.hd_slot_1 ?? "—"],
            ["Access",         data.access_type ?? "—"],
            ["Dry Weight",     data.dry_weight ? `${data.dry_weight} kg` : "—"],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between py-1.5 border-b border-gray-800 last:border-0">
              <span className="text-gray-400 text-sm">{k}</span>
              <span className="text-gray-200 text-sm font-medium">{v}</span>
            </div>
          ))}
        </div>

        {/* ── Anemia & Adequacy ── */}
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
          <div className="flex items-center gap-2 mb-4 text-gray-400 text-xs font-semibold uppercase tracking-wider">
            <Droplet className="w-3.5 h-3.5" />
            Anemia & Adequacy
            {labs.record_month && (
              <span className="ml-auto text-gray-600 font-mono text-xs">{labs.record_month}</span>
            )}
          </div>
          <LabRow label="Hemoglobin" value={labs.hb}    unit="g/dL" low={10} high={13} />
          <LabRow label="Ferritin"   value={labs.ferritin} unit="ng/mL" low={200} high={800} />
          <LabRow label="TSAT"       value={labs.tsat}  unit="%" low={20} high={50} />
          <LabRow label="Kt/V"       value={labs.kt_v}  unit="" low={1.2} />
          <LabRow label="URR"        value={labs.urr}   unit="%" low={65} />
          <LabRow label="IDWG"       value={labs.idwg}  unit="kg" high={2.5} />
        </div>

        {/* ── Mineral & Nutrition ── */}
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
          <div className="flex items-center gap-2 mb-4 text-gray-400 text-xs font-semibold uppercase tracking-wider">
            <FlaskConical className="w-3.5 h-3.5" />
            Minerals & Nutrition
          </div>
          <LabRow label="Albumin"    value={labs.albumin}    unit="g/dL" low={3.5} />
          <LabRow label="Phosphorus" value={labs.phosphorus} unit="mg/dL" high={5.5} />
          <LabRow label="Calcium"    value={labs.calcium}    unit="mg/dL" low={8.5} high={10.5} />
          <LabRow label="iPTH"       value={labs.ipth}       unit="pg/mL" low={150} high={600} />
          <LabRow label="CRP"        value={labs.crp}        unit="mg/L" high={10} />
          <LabRow label="Potassium"  value={labs.potassium}  unit="mEq/L" low={3.5} high={5.5} />
        </div>
      </div>

      {/* Trends */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
          <div className="flex items-center gap-2 mb-3 text-gray-400 text-xs font-semibold uppercase tracking-wider">
            <Activity className="w-3.5 h-3.5" />
            Hemoglobin trend (last 12 months)
          </div>
          <SparkBar data={data.trend_hb} color="#60a5fa" />
        </div>
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
          <div className="flex items-center gap-2 mb-3 text-gray-400 text-xs font-semibold uppercase tracking-wider">
            <Activity className="w-3.5 h-3.5" />
            Albumin trend (last 12 months)
          </div>
          <SparkBar data={data.trend_albumin} color="#34d399" />
        </div>
      </div>

      {/* ML Risk panel */}
      {mort.available && (
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-5 mb-8">
          <div className="flex items-center gap-2 mb-4 text-gray-400 text-xs font-semibold uppercase tracking-wider">
            <Microscope className="w-3.5 h-3.5" />
            Mortality Risk Model
          </div>
          <div className="flex items-center gap-6">
            <div>
              <p className="text-gray-500 text-xs mb-1">1-Year Probability</p>
              <p className="text-3xl font-bold text-white">
                {mort.prob_1yr != null ? `${(mort.prob_1yr * 100).toFixed(0)}%` : "—"}
              </p>
            </div>
            <div>
              <p className="text-gray-500 text-xs mb-1">Risk Level</p>
              {riskBadge(mort.risk_level)}
            </div>
            {mort.feature_hash && (
              <div className="ml-auto">
                <p className="text-gray-600 text-xs">Feature snapshot</p>
                <p className="text-gray-600 font-mono text-xs">{mort.feature_hash.slice(0, 12)}…</p>
              </div>
            )}
          </div>
          <p className="text-gray-600 text-xs mt-4">
            This prediction is based on the materialized feature snapshot. Clinicians should exercise
            independent judgement — model predictions are decision-support only.
          </p>
        </div>
      )}

      {/* Quick links to Jinja2 form pages (open server-rendered) */}
      <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
        <div className="flex items-center gap-2 mb-4 text-gray-400 text-xs font-semibold uppercase tracking-wider">
          <Zap className="w-3.5 h-3.5" />
          Actions
        </div>
        <div className="flex flex-wrap gap-3">
          {[
            { href: `/entry/${id}`,      label: "Enter Monthly Data" },
            { href: `/events/${id}`,     label: "Log Clinical Event" },
            { href: `/fluid/${id}`,      label: "Fluid Assessment" },
            { href: `/med-recon/${id}`,  label: "Medication Reconciliation" },
            { href: `/patients/${id}/timeline`, label: "Timeline" },
          ].map(({ href, label }) => (
            <a
              key={href}
              href={href}
              className="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-sm transition-colors"
            >
              {label}
            </a>
          ))}
        </div>
      </div>
    </Shell>
  );
}
