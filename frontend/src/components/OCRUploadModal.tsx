"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import imageCompression from "browser-image-compression";
import { apiFetch } from "@/lib/api";
import {
  X,
  Upload,
  Camera,
  Loader2,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  FlaskConical,
  Eye,
  ChevronRight,
  Scan,
  FileImage,
  RotateCcw,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ExtractedField {
  value: number;
  confidence: "high" | "medium" | "low";
  label: string;
  unit: string;
}

interface OCRResult {
  extracted_fields: Record<string, number>;
  confidence: Record<string, string>;
  field_labels: Record<string, string>;
  field_units: Record<string, string>;
  report_date?: string;
  patient_name_on_report?: string;
  report_type?: string;
  fields_found?: number;
  model?: string;
  error?: string;
}

interface OCRUploadModalProps {
  patientId: number;
  patientName: string;
  month: string; // YYYY-MM
  onApply: (fields: Record<string, string>) => void;
  onClose: () => void;
}

// ─── Confidence colour helpers ────────────────────────────────────────────────

const confidenceBadge = (c: string) => {
  if (c === "high") return "bg-emerald-100 text-emerald-700 border-emerald-200";
  if (c === "medium") return "bg-amber-100 text-amber-700 border-amber-200";
  return "bg-red-100 text-red-600 border-red-200";
};

const confidenceIcon = (c: string) => {
  if (c === "high") return <CheckCircle2 size={12} className="text-emerald-600" />;
  if (c === "medium") return <AlertTriangle size={12} className="text-amber-600" />;
  return <AlertCircle size={12} className="text-red-500" />;
};

// ─── Component ────────────────────────────────────────────────────────────────

export default function OCRUploadModal({
  patientId,
  patientName,
  month,
  onApply,
  onClose,
}: OCRUploadModalProps) {
  const [step, setStep] = useState<"upload" | "processing" | "review" | "error">("upload");
  const [dragOver, setDragOver] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [ocrResult, setOcrResult] = useState<OCRResult | null>(null);
  const [editedValues, setEditedValues] = useState<Record<string, string>>({});
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [processingDot, setProcessingDot] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  // Animate dots during processing
  useEffect(() => {
    if (step !== "processing") return;
    const interval = setInterval(() => setProcessingDot((d) => (d + 1) % 4), 500);
    return () => clearInterval(interval);
  }, [step]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // ── File handling ──────────────────────────────────────────────────────────

  const processFile = useCallback(async (file: File) => {
    if (!file) return;

    // Validate type
    const validTypes = ["image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic"];
    if (!validTypes.includes(file.type)) {
      setErrorMsg("Please upload a JPEG, PNG, or WebP image of the lab report.");
      setStep("error");
      return;
    }

    // Validate size (10 MB)
    if (file.size > 10 * 1024 * 1024) {
      setErrorMsg("File is too large. Please upload an image smaller than 10 MB.");
      setStep("error");
      return;
    }

    // Show preview
    const reader = new FileReader();
    reader.onload = (e) => setPreview(e.target?.result as string);
    reader.readAsDataURL(file);
    setFileName(file.name);

    // Start OCR
    setStep("processing");

    try {
      // Compress image client-side to massively speed up upload & OCR processing
      const options = {
        maxSizeMB: 1, // Target max 1MB
        maxWidthOrHeight: 2000,
        useWebWorker: true,
        fileType: "image/jpeg",
      };
      
      let fileToUpload = file;
      try {
        fileToUpload = await imageCompression(file, options);
      } catch (compErr) {
        console.error("Image compression failed, falling back to original", compErr);
      }

      const formData = new FormData();
      formData.append("patient_id", String(patientId));
      formData.append("file", fileToUpload);

      const res = await fetch("/ocr/extract-report", {
        method: "POST",
        body: formData,
        credentials: "include",
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(detail?.detail || `Server error ${res.status}`);
      }

      const data: OCRResult = await res.json();

      if (data.error) {
        setErrorMsg(data.error);
        setStep("error");
        return;
      }

      if (!data.extracted_fields || Object.keys(data.extracted_fields).length === 0) {
        setErrorMsg(
          "No lab values could be extracted from this image. Please ensure the image is clear and contains blood/biochemistry report data."
        );
        setStep("error");
        return;
      }

      // Pre-populate editable values
      const initValues: Record<string, string> = {};
      Object.entries(data.extracted_fields).forEach(([k, v]) => {
        initValues[k] = String(v);
      });
      setEditedValues(initValues);
      setOcrResult(data);
      setStep("review");
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to connect to the OCR service. Please try again.");
      setStep("error");
    }
  }, [patientId]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) processFile(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) processFile(file);
  };

  // ── Apply extracted values to parent form ──────────────────────────────────

  const handleApply = () => {
    // Only pass fields that have non-empty values
    const toApply: Record<string, string> = {};
    Object.entries(editedValues).forEach(([k, v]) => {
      if (v.trim() !== "") toApply[k] = v;
    });
    onApply(toApply);
    onClose();
  };

  const handleValueEdit = (field: string, value: string) => {
    setEditedValues((prev) => ({ ...prev, [field]: value }));
  };

  const handleRemoveField = (field: string) => {
    setEditedValues((prev) => {
      const next = { ...prev };
      delete next[field];
      return next;
    });
  };

  const handleReset = () => {
    setStep("upload");
    setPreview(null);
    setFileName("");
    setOcrResult(null);
    setEditedValues({});
    setErrorMsg("");
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (cameraInputRef.current) cameraInputRef.current.value = "";
  };

  // ── Count confidence levels for summary ──────────────────────────────────

  const highCount = ocrResult
    ? Object.values(ocrResult.confidence).filter((c) => c === "high").length
    : 0;
  const medCount = ocrResult
    ? Object.values(ocrResult.confidence).filter((c) => c === "medium").length
    : 0;
  const lowCount = ocrResult
    ? Object.values(ocrResult.confidence).filter((c) => c === "low").length
    : 0;

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(15, 23, 42, 0.75)", backdropFilter: "blur(8px)" }}
    >
      <div
        className="relative bg-white rounded-[2rem] shadow-2xl w-full overflow-hidden flex flex-col"
        style={{ maxWidth: 680, maxHeight: "90vh" }}
      >
        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-8 py-6 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-lg">
              <Scan size={20} className="text-white" />
            </div>
            <div>
              <h2 className="font-black text-gray-900 text-lg leading-tight">AI Report Scanner</h2>
              <p className="text-[11px] font-bold text-gray-400 uppercase tracking-widest">{patientName} · {month}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 flex items-center justify-center rounded-xl hover:bg-gray-100 transition-colors text-gray-400 hover:text-gray-700"
          >
            <X size={18} />
          </button>
        </div>

        {/* ── Step: Upload ────────────────────────────────────────────────── */}
        {step === "upload" && (
          <div className="flex-1 overflow-y-auto px-8 py-8">
            {/* Drop zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`
                relative cursor-pointer rounded-[1.5rem] border-2 border-dashed transition-all duration-300 p-12
                flex flex-col items-center justify-center gap-5 text-center
                ${dragOver
                  ? "border-violet-400 bg-violet-50"
                  : "border-gray-200 bg-gray-50 hover:border-violet-300 hover:bg-violet-50/50"
                }
              `}
            >
              <div className={`w-20 h-20 rounded-[1.5rem] flex items-center justify-center transition-all
                ${dragOver ? "bg-violet-100" : "bg-white shadow-md"}`}>
                <FileImage size={36} className={dragOver ? "text-violet-500" : "text-gray-400"} />
              </div>
              <div>
                <p className="font-black text-gray-800 text-lg">
                  {dragOver ? "Drop the image here" : "Upload Report Image"}
                </p>
                <p className="text-gray-400 text-sm mt-1">
                  Drag & drop or click to select · JPEG, PNG, WebP · Max 10 MB
                </p>
              </div>
              <div className="flex items-center gap-2 text-[11px] font-bold text-gray-400 uppercase tracking-widest">
                <div className="w-8 h-px bg-gray-200" />
                or
                <div className="w-8 h-px bg-gray-200" />
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex gap-3 mt-4">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex-1 flex items-center justify-center gap-2 py-4 rounded-2xl border-2 border-gray-200 font-bold text-gray-700 hover:border-violet-300 hover:text-violet-700 hover:bg-violet-50 transition-all"
              >
                <Upload size={18} />
                Choose File
              </button>
              <button
                onClick={() => cameraInputRef.current?.click()}
                className="flex-1 flex items-center justify-center gap-2 py-4 rounded-2xl border-2 border-gray-200 font-bold text-gray-700 hover:border-indigo-300 hover:text-indigo-700 hover:bg-indigo-50 transition-all"
              >
                <Camera size={18} />
                Use Camera
              </button>
            </div>

            {/* Info box */}
            <div className="mt-6 p-5 bg-indigo-50 rounded-2xl border border-indigo-100 flex gap-3">
              <FlaskConical size={18} className="text-indigo-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-bold text-indigo-800 text-sm">Powered by Gemini Vision AI</p>
                <p className="text-indigo-600 text-xs mt-1 leading-relaxed">
                  Upload a clear photo or scan of any blood/biochemistry report. The AI will automatically
                  extract Hb, creatinine, electrolytes, iron panel, PTH, and 30+ other lab values.
                  You can review and edit all extracted values before saving.
                </p>
              </div>
            </div>

            {/* Hidden inputs */}
            <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileChange} />
            <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={handleFileChange} />
          </div>
        )}

        {/* ── Step: Processing ────────────────────────────────────────────── */}
        {step === "processing" && (
          <div className="flex-1 flex flex-col items-center justify-center px-8 py-12 gap-8">
            {/* Image preview thumbnail */}
            {preview && (
              <div className="relative w-48 h-48 rounded-2xl overflow-hidden shadow-xl border border-gray-100">
                <img src={preview} alt="Report" className="w-full h-full object-cover" />
                <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent" />
                {/* Scanning animation overlay */}
                <div
                  className="absolute inset-x-0 h-1 bg-gradient-to-r from-transparent via-violet-400 to-transparent"
                  style={{
                    animation: "scan-line 2s ease-in-out infinite",
                    top: `${25 + (processingDot * 20)}%`,
                  }}
                />
              </div>
            )}

            <div className="text-center">
              <div className="flex items-center justify-center gap-3 mb-4">
                <Loader2 size={28} className="text-violet-500 animate-spin" />
                <span className="font-black text-gray-800 text-xl">Analyzing Report</span>
              </div>
              <p className="text-gray-500 font-medium">
                Gemini Vision is reading your report{".".repeat(processingDot + 1)}
              </p>
              <div className="mt-6 flex flex-col gap-2 text-sm text-gray-400">
                {[
                  "Extracting text from image",
                  "Identifying lab parameters",
                  "Mapping to patient record fields",
                ].map((t, i) => (
                  <div key={t} className="flex items-center gap-2 justify-center">
                    {processingDot > i ? (
                      <CheckCircle2 size={14} className="text-emerald-500" />
                    ) : processingDot === i ? (
                      <Loader2 size={14} className="text-violet-400 animate-spin" />
                    ) : (
                      <div className="w-3.5 h-3.5 rounded-full border-2 border-gray-200" />
                    )}
                    <span className={processingDot > i ? "text-emerald-600 font-semibold" : ""}>{t}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── Step: Review ────────────────────────────────────────────────── */}
        {step === "review" && ocrResult && (
          <>
            <div className="flex-1 overflow-y-auto px-8 py-6">
              {/* Summary bar */}
              <div className="flex items-center gap-3 mb-6 p-4 bg-gray-50 rounded-2xl">
                {preview && (
                  <img src={preview} alt="Report" className="w-14 h-14 rounded-xl object-cover border border-gray-200 flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="font-black text-gray-900 text-sm truncate">{fileName}</p>
                  <p className="text-xs text-gray-400 font-medium mt-0.5">
                    {ocrResult.report_type && ocrResult.report_type !== "unknown"
                      ? `${ocrResult.report_type.charAt(0).toUpperCase() + ocrResult.report_type.slice(1)} Report`
                      : "Lab Report"
                    }
                    {ocrResult.report_date ? ` · ${ocrResult.report_date}` : ""}
                  </p>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  <span className="flex items-center gap-1 text-xs font-bold px-2.5 py-1.5 rounded-lg bg-emerald-100 text-emerald-700 border border-emerald-200">
                    <CheckCircle2 size={11} /> {highCount}
                  </span>
                  {medCount > 0 && (
                    <span className="flex items-center gap-1 text-xs font-bold px-2.5 py-1.5 rounded-lg bg-amber-100 text-amber-700 border border-amber-200">
                      <AlertTriangle size={11} /> {medCount}
                    </span>
                  )}
                  {lowCount > 0 && (
                    <span className="flex items-center gap-1 text-xs font-bold px-2.5 py-1.5 rounded-lg bg-red-100 text-red-600 border border-red-200">
                      <AlertCircle size={11} /> {lowCount}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-black text-gray-400 uppercase tracking-widest">
                  {Object.keys(editedValues).length} Fields Extracted — Review & Edit Before Applying
                </p>
                <button onClick={handleReset} className="flex items-center gap-1.5 text-xs font-bold text-gray-400 hover:text-violet-600 transition-colors">
                  <RotateCcw size={12} /> Rescan
                </button>
              </div>

              {/* Extracted fields table */}
              <div className="rounded-[1.25rem] border border-gray-100 overflow-hidden divide-y divide-gray-50">
                {Object.entries(editedValues).map(([field, value]) => {
                  const label = ocrResult.field_labels?.[field] || field;
                  const unit = ocrResult.field_units?.[field] || "";
                  const conf = ocrResult.confidence?.[field] || "medium";
                  return (
                    <div key={field} className="flex items-center gap-3 px-5 py-3.5 bg-white hover:bg-gray-50/50 transition-colors">
                      {/* Confidence indicator */}
                      <div className={`w-1.5 h-8 rounded-full flex-shrink-0 ${
                        conf === "high" ? "bg-emerald-400" : conf === "medium" ? "bg-amber-400" : "bg-red-400"
                      }`} />

                      {/* Label */}
                      <div className="flex-1 min-w-0">
                        <p className="font-bold text-gray-900 text-sm leading-tight">{label}</p>
                        <p className="text-[11px] text-gray-400 font-mono">{field}</p>
                      </div>

                      {/* Editable value */}
                      <div className="flex items-center gap-2">
                        <input
                          type="number"
                          step="0.01"
                          value={value}
                          onChange={(e) => handleValueEdit(field, e.target.value)}
                          className="w-24 px-3 py-2 text-right font-black text-gray-900 bg-gray-50 border-2 border-transparent rounded-xl focus:border-violet-300 focus:bg-white transition-all text-sm outline-none"
                        />
                        {unit && (
                          <span className="text-[11px] font-bold text-gray-400 w-14 text-left">{unit}</span>
                        )}
                      </div>

                      {/* Confidence badge */}
                      <span className={`flex items-center gap-1 text-[10px] font-black px-2 py-1 rounded-lg border ${confidenceBadge(conf)}`}>
                        {confidenceIcon(conf)}
                        {conf}
                      </span>

                      {/* Remove */}
                      <button
                        onClick={() => handleRemoveField(field)}
                        className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-300 hover:text-red-400 hover:bg-red-50 transition-colors flex-shrink-0"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  );
                })}
              </div>

              {/* Legend */}
              <div className="flex gap-4 mt-4 text-[11px] font-bold text-gray-400">
                <span className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-emerald-400" /> High confidence</span>
                <span className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-amber-400" /> Review recommended</span>
                <span className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-red-400" /> Verify manually</span>
              </div>
            </div>

            {/* Footer actions */}
            <div className="flex gap-3 px-8 py-6 bg-gray-50/50 border-t border-gray-100">
              <button
                onClick={handleReset}
                className="flex items-center gap-2 px-6 py-4 rounded-2xl border-2 border-gray-200 font-bold text-gray-600 hover:border-gray-300 hover:bg-white transition-all"
              >
                <RotateCcw size={16} />
                Try Again
              </button>
              <button
                onClick={handleApply}
                disabled={Object.keys(editedValues).length === 0}
                className="flex-1 flex items-center justify-center gap-2 px-6 py-4 rounded-2xl font-black text-white transition-all disabled:opacity-50 disabled:pointer-events-none hover:scale-[1.01] active:scale-[0.99]"
                style={{ background: "linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)" }}
              >
                <CheckCircle2 size={18} />
                Apply {Object.keys(editedValues).length} Values to Form
                <ChevronRight size={16} />
              </button>
            </div>
          </>
        )}

        {/* ── Step: Error ─────────────────────────────────────────────────── */}
        {step === "error" && (
          <div className="flex-1 flex flex-col items-center justify-center px-8 py-12 gap-6 text-center">
            <div className="w-20 h-20 rounded-[1.5rem] bg-red-50 flex items-center justify-center">
              <AlertCircle size={40} className="text-red-400" />
            </div>
            <div>
              <p className="font-black text-gray-900 text-xl mb-2">Extraction Failed</p>
              <p className="text-gray-500 text-sm leading-relaxed max-w-sm mx-auto">{errorMsg}</p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="px-6 py-3 rounded-2xl border-2 border-gray-200 font-bold text-gray-600 hover:bg-gray-50 transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleReset}
                className="flex items-center gap-2 px-6 py-3 rounded-2xl font-bold text-white transition-all"
                style={{ background: "linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)" }}
              >
                <RotateCcw size={16} />
                Try Again
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Scanning animation CSS */}
      <style>{`
        @keyframes scan-line {
          0%, 100% { opacity: 0; top: 10%; }
          20% { opacity: 1; }
          80% { opacity: 1; }
          50% { top: 85%; }
        }
      `}</style>
    </div>
  );
}
