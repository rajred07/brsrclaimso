"use client";

import { useState, useRef } from "react";
import Link from "next/link";
import { UploadCloud, CheckCircle2, FileText, ArrowRight, Loader2, Database, ListFilter } from "lucide-react";

export default function UploadWizard() {
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [xbrlFile, setXbrlFile] = useState<File | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [symbol, setSymbol] = useState("");
  const [fy, setFy] = useState("2025-26");
  const [sector, setSector] = useState("IT Services");

  const [isUploading, setIsUploading] = useState(false);
  const [savedFilingId, setSavedFilingId] = useState<string | null>(null);

  const pdfInputRef = useRef<HTMLInputElement>(null);
  const xbrlInputRef = useRef<HTMLInputElement>(null);

  const canSubmit = Boolean(pdfFile || xbrlFile);

  const handlePdfChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setPdfFile(file);
      const name = file.name;
      
      // Auto-detect year from file name
      if (name.includes("2526") || name.includes("2025-26") || name.includes("202526")) {
        setFy("2025-26");
      } else if (name.includes("2425") || name.includes("2024-25") || name.includes("202425")) {
        setFy("2024-25");
      } else if (name.includes("2324") || name.includes("2023-24") || name.includes("202324")) {
        setFy("2023-24");
      } else if (name.includes("2223") || name.includes("2022-23") || name.includes("202223")) {
        setFy("2022-23");
      }

      if (!companyName) {
        // Auto-guess company name from filename
        const cleanName = name.replace(/[_-]/g, " ").replace(/\.pdf$/i, "").replace(/\d+/g, "").trim();
        setCompanyName(cleanName ? cleanName.charAt(0).toUpperCase() + cleanName.slice(1) : "Infosys Ltd.");
      }
    }
  };

  const handleXbrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setXbrlFile(e.target.files[0]);
    }
  };

  const handleSaveFiling = async () => {
    if (!canSubmit) return;
    
    setIsUploading(true);

    const formData = new FormData();
    if (pdfFile) formData.append("pdfFile", pdfFile);
    if (xbrlFile) formData.append("xbrlFile", xbrlFile);
    formData.append("companyName", companyName || "New Company");
    formData.append("symbol", symbol || "INFY");
    formData.append("fy", fy || "2025-26");
    formData.append("sector", sector);

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      
      const data = await res.json();
      if (res.ok && data.success) {
        setSavedFilingId(data.filingId);
      } else {
        alert("Failed to save files: " + (data.error || "Unknown error"));
      }
    } catch (e) {
      console.error(e);
      alert("An error occurred during upload.");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="flex flex-col w-full animate-fade-in max-w-4xl mx-auto py-4">
      {/* Page Header */}
      <div className="text-center pb-6 mb-6 border-b border-[var(--border)]">
        <h1 className="text-[32px] font-bold text-[var(--ink)] leading-tight tracking-tight">
          Save & Register BRSR Filing
        </h1>
        <p className="text-[16px] text-[var(--ink-2)] mt-1.5 max-w-xl mx-auto">
          Upload narrative PDF and XBRL facts. Documents are statically saved to storage and registered in the database without running the pipeline immediately.
        </p>
      </div>

      {savedFilingId ? (
        /* Saved confirmation view */
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-card)] p-8 shadow-[var(--shadow-card)] flex flex-col items-center text-center gap-6">
          <div className="w-16 h-16 rounded-full bg-[var(--success-soft)] text-[var(--success)] border border-[var(--success-border)] flex items-center justify-center">
            <CheckCircle2 className="w-8 h-8" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-[var(--ink)]">Filing Registered in Database!</h2>
            <p className="text-sm text-[var(--ink-2)] mt-1">
              Filing ID: <code className="font-mono font-bold text-[var(--primary)]">{savedFilingId}</code>
            </p>
            <p className="text-xs text-[var(--ink-3)] mt-2">
              Status is marked as <span className="font-bold text-[var(--primary)]">READY</span>. The files are statically stored and ready for verification when you choose to run the pipeline.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row gap-4 mt-2">
            <Link href="/inventory" className="btn-secondary">
              <ListFilter className="w-4 h-4" />
              <span>View in Filings Inventory</span>
            </Link>
            <Link href={`/process/stage?id=${savedFilingId}`} className="btn-primary shadow-md">
              <span>Open Processing Stage</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      ) : (
        /* Upload & Metadata Form */
        <div className="flex flex-col gap-6">
          {/* Metadata Row */}
          <div className="bg-[var(--surface)] p-6 rounded-[var(--radius-card)] border border-[var(--border)] shadow-[var(--shadow-card)] grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-[var(--ink-3)] uppercase tracking-wider">Company Name</label>
              <input
                type="text"
                placeholder="e.g. Infosys Ltd."
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                className="h-10 px-3 bg-[var(--bg)] border border-[var(--border)] rounded-[var(--radius-control)] text-sm text-[var(--ink)] focus:outline-none focus:border-[var(--primary)]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-[var(--ink-3)] uppercase tracking-wider">Symbol / Ticker</label>
              <input
                type="text"
                placeholder="e.g. INFY"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                className="h-10 px-3 bg-[var(--bg)] border border-[var(--border)] rounded-[var(--radius-control)] text-sm text-[var(--ink)] focus:outline-none focus:border-[var(--primary)]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold text-[var(--ink-3)] uppercase tracking-wider">Financial Year (FY)</label>
              </div>
              <input
                type="text"
                placeholder="e.g. 2025-26"
                value={fy}
                onChange={(e) => setFy(e.target.value)}
                className="h-10 px-3 bg-[var(--bg)] border border-[var(--border)] rounded-[var(--radius-control)] text-sm font-semibold text-[var(--ink)] focus:outline-none focus:border-[var(--primary)]"
              />
              <div className="flex flex-wrap gap-1 mt-1">
                {["2025-26", "2024-25", "2023-24", "2022-23"].map((y) => (
                  <button
                    key={y}
                    type="button"
                    onClick={() => setFy(y)}
                    className={`px-1.5 py-0.5 text-[10px] font-bold rounded cursor-pointer transition-colors ${
                      fy === y
                        ? "bg-[var(--primary)] text-white"
                        : "bg-slate-100 text-[var(--ink-2)] hover:bg-slate-200"
                    }`}
                  >
                    {y}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold text-[var(--ink-3)] uppercase tracking-wider">Industry Sector</label>
              <select
                value={sector}
                onChange={(e) => setSector(e.target.value)}
                className="h-10 px-3 bg-[var(--bg)] border border-[var(--border)] rounded-[var(--radius-control)] text-sm text-[var(--ink)] focus:outline-none focus:border-[var(--primary)] cursor-pointer"
              >
                <option>IT Services</option>
                <option>Banking</option>
                <option>Manufacturing</option>
                <option>Conglomerate</option>
                <option>Telecom</option>
                <option>Energy</option>
              </select>
            </div>
          </div>

          {/* Upload Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* PDF Upload */}
            <input 
              type="file" 
              accept=".pdf" 
              ref={pdfInputRef} 
              onChange={handlePdfChange} 
              className="hidden" 
            />
            <div 
              onClick={() => pdfInputRef.current?.click()}
              className={`relative bg-[var(--surface)] rounded-[var(--radius-card)] p-8 border-2 transition-all flex flex-col items-center justify-center text-center cursor-pointer min-h-[260px] shadow-[var(--shadow-card)] group ${
                pdfFile 
                  ? 'border-[var(--success-border)] bg-[var(--success-soft)]/20' 
                  : 'border-dashed border-[#CBD5E1] hover:border-[var(--primary)] hover:bg-[var(--primary-soft)]'
              }`}
            >
              <div className={`w-14 h-14 rounded-full flex items-center justify-center mb-4 transition-transform group-hover:scale-105 ${
                pdfFile ? 'bg-[var(--success-soft)] text-[var(--success)]' : 'bg-[var(--primary-soft)] text-[var(--primary)]'
              }`}>
                {pdfFile ? <CheckCircle2 className="w-7 h-7" /> : <FileText className="w-7 h-7" />}
              </div>
              <h3 className={`text-base font-bold mb-1.5 ${pdfFile ? 'text-[var(--success)]' : 'text-[var(--ink)]'}`}>
                {pdfFile ? pdfFile.name : 'ESG Narrative (PDF)'}
              </h3>
              <p className="text-xs text-[var(--ink-2)] mb-3 max-w-[260px] leading-relaxed">
                {pdfFile ? 'PDF document selected.' : 'Select the unstructured PDF report containing claims.'}
              </p>
              
              {pdfFile ? (
                <div className="flex flex-col items-center gap-1.5">
                  <span className="text-xs font-semibold text-[var(--success)] bg-[var(--success-soft)] px-3 py-1 rounded-full border border-[var(--success-border)]">
                    Attached
                  </span>
                  <span className="text-[11px] text-[var(--primary)] font-semibold mt-1">
                    FY: {fy} (Click metadata above to change)
                  </span>
                </div>
              ) : (
                <span className="btn-secondary text-xs pointer-events-none">
                  Select PDF File
                </span>
              )}
            </div>

            {/* XBRL Upload */}
            <input 
              type="file" 
              accept=".xml" 
              ref={xbrlInputRef} 
              onChange={handleXbrlChange} 
              className="hidden" 
            />
            <div 
              onClick={() => xbrlInputRef.current?.click()}
              className={`relative bg-[var(--surface)] rounded-[var(--radius-card)] p-8 border-2 transition-all flex flex-col items-center justify-center text-center cursor-pointer min-h-[260px] shadow-[var(--shadow-card)] group ${
                xbrlFile 
                  ? 'border-[var(--success-border)] bg-[var(--success-soft)]/20' 
                  : 'border-dashed border-[#CBD5E1] hover:border-[var(--primary)] hover:bg-[var(--primary-soft)]'
              }`}
            >
              <div className={`w-14 h-14 rounded-full flex items-center justify-center mb-4 transition-transform group-hover:scale-105 ${
                xbrlFile ? 'bg-[var(--success-soft)] text-[var(--success)]' : 'bg-[var(--primary-soft)] text-[var(--primary)]'
              }`}>
                {xbrlFile ? <CheckCircle2 className="w-7 h-7" /> : <UploadCloud className="w-7 h-7" />}
              </div>
              <h3 className={`text-base font-bold mb-1.5 ${xbrlFile ? 'text-[var(--success)]' : 'text-[var(--ink)]'}`}>
                {xbrlFile ? xbrlFile.name : 'BRSR Instance (XBRL)'}
              </h3>
              <p className="text-xs text-[var(--ink-2)] mb-4 max-w-[260px] leading-relaxed">
                {xbrlFile ? 'XBRL XML instance selected.' : 'Select the structured XBRL data containing quantitative facts.'}
              </p>
              {!xbrlFile ? (
                <span className="btn-secondary text-xs pointer-events-none">
                  Select XBRL File (Optional)
                </span>
              ) : (
                <span className="text-xs font-semibold text-[var(--success)] bg-[var(--success-soft)] px-3 py-1 rounded-full border border-[var(--success-border)]">
                  Attached
                </span>
              )}
            </div>
          </div>

          {/* Submit Action */}
          <div className="flex flex-col items-center gap-2 mt-2">
            <button 
              onClick={handleSaveFiling}
              disabled={!canSubmit || isUploading}
              className={`h-11 px-8 rounded-[var(--radius-control)] font-semibold text-sm flex items-center justify-center gap-2.5 transition-all ${
                canSubmit && !isUploading
                  ? 'btn-primary shadow-md'
                  : 'bg-slate-200 text-slate-400 cursor-not-allowed border border-slate-300'
              }`}
            >
              {isUploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Saving to Storage & Registering in Database...</span>
                </>
              ) : (
                <>
                  <Database className="w-4 h-4" />
                  <span>Save Documents & Register in Database (Static)</span>
                </>
              )}
            </button>
            <p className="text-xs text-[var(--ink-3)]">
              Files will be stored statically. You can run the extraction pipeline at any time from the inventory.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
