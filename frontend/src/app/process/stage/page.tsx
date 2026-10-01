"use client";

import { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import StatusBadge from "@/components/StatusBadge";
import { 
  FileCode, 
  FileText, 
  Database, 
  ArrowRight, 
  CheckCircle2, 
  Loader2, 
  Play, 
  Cpu, 
  ArrowLeft,
  Sparkles,
  Inbox,
  UploadCloud
} from "lucide-react";

interface FactItem {
  canonical_name: string;
  category?: string;
  period: string;
  value: number | string;
  unit: string;
}

interface ClaimItem {
  metric: string;
  operation: string;
  stated_result?: number | string;
  asserted_value?: number;
  unit: string;
  original_quote?: string;
  source_passage?: string;
  period_current?: string;
  current_period?: string;
}

interface FilingMetadata {
  id: string;
  company: string;
  symbol: string;
  fy: string;
  sector: string;
  status: string;
  pdfFileName: string;
  xbrlFileName: string;
  hasPdf: boolean;
  hasXbrl: boolean;
}

function StageInspectorContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filingId = searchParams.get("id") || "infosys-2022";

  // Active sub-navbar tab
  const [activeTab, setActiveTab] = useState<"claims" | "xml" | "duckdb">("xml");

  // Filing metadata
  const [filingInfo, setFilingInfo] = useState<FilingMetadata>({
    id: filingId,
    company: "Infosys Ltd.",
    symbol: "INFY",
    fy: "2021-22",
    sector: "IT Services",
    status: "READY",
    pdfFileName: "infosys-esg-report-2021-22.pdf",
    xbrlFileName: "infosys_brsr_2022.xml",
    hasPdf: true,
    hasXbrl: true
  });

  // Processing state for the 2 modular steps
  const [xbrlProcessed, setXbrlProcessed] = useState(false);
  const [pdfProcessed, setPdfProcessed] = useState(false);
  const [isProcessingXbrl, setIsProcessingXbrl] = useState(false);
  const [isProcessingPdf, setIsProcessingPdf] = useState(false);

  // Staged data
  const [xmlContent, setXmlContent] = useState("");
  const [duckdbFacts, setDuckdbFacts] = useState<FactItem[]>([]);
  const [extractedClaims, setExtractedClaims] = useState<ClaimItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState<string>("All");
  const [metricSearch, setMetricSearch] = useState<string>("");
  const [isAttachingXbrl, setIsAttachingXbrl] = useState(false);
  const xbrlUploadRef = useRef<HTMLInputElement>(null);

  // Initial load from backend stage endpoint
  useEffect(() => {
    async function loadStageData() {
      try {
        const res = await fetch(`/api/stage/${filingId}`);
        if (res.ok) {
          const data = await res.json();
          if (data.filing) {
            setFilingInfo(data.filing);
          }
          setXmlContent(data.xmlContent || "");
          setDuckdbFacts(data.duckdbFacts || []);
          setExtractedClaims(data.extractedClaims || []);

          const xbrlDone = Boolean(data.xbrlProcessed);
          const pdfDone = Boolean(data.pdfProcessed);
          setXbrlProcessed(xbrlDone);
          setPdfProcessed(pdfDone);

          // Focus on appropriate tab
          if (pdfDone) {
            setActiveTab("claims");
          } else if (data.filing && !data.filing.hasXbrl) {
            setActiveTab("claims");
          } else if (xbrlDone) {
            setActiveTab("duckdb");
          } else {
            setActiveTab("xml");
          }
        }
      } catch (e) {
        console.error("Failed to load staging data:", e);
      } finally {
        setIsLoading(false);
      }
    }

    loadStageData();
  }, [filingId]);

  // Handler 1: Run real XBRL pipeline on demand
  const handleProcessXbrl = async () => {
    setIsProcessingXbrl(true);
    try {
      const res = await fetch(`/api/stage/${filingId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "process_xbrl" })
      });
      if (res.ok) {
        const data = await res.json();
        if (data.facts && Array.isArray(data.facts)) {
          setDuckdbFacts(data.facts);
        }
        setXbrlProcessed(true);
        setActiveTab("duckdb");
      } else {
        alert("Failed to process XBRL instance.");
      }
    } catch (e) {
      console.error("Error processing XBRL:", e);
      alert("Error triggering XBRL processing.");
    } finally {
      setIsProcessingXbrl(false);
    }
  };

  // Handler 2: Upload and attach XBRL XML on the fly
  const handleAttachXbrl = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setIsAttachingXbrl(true);
      const formData = new FormData();
      formData.append("xbrlFile", e.target.files[0]);
      try {
        const res = await fetch(`/api/stage/${filingId}`, {
          method: "POST",
          body: formData
        });
        if (res.ok) {
          window.location.reload();
        } else {
          alert("Failed to upload XBRL file.");
        }
      } catch (err) {
        console.error("Upload error:", err);
        alert("Error attaching XBRL file.");
      } finally {
        setIsAttachingXbrl(false);
      }
    }
  };

  // Handler 3: Process PDF narrative (kept manual / unrun for now as requested)
  const handleProcessPdf = async () => {
    alert("PDF processing for this filing is currently held as requested. Run XBRL pipeline to inspect facts.");
  };

  const bothReady = xbrlProcessed && pdfProcessed;

  return (
    <div className="flex flex-col w-full animate-fade-in max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pb-6 mb-6 border-b border-[var(--border)]">
        <div className="flex items-center gap-3">
          <Link
            href="/inventory"
            className="w-9 h-9 rounded-[var(--radius-control)] bg-[var(--surface)] border border-[var(--border)] flex items-center justify-center text-[var(--ink-2)] hover:text-[var(--ink)] hover:bg-[#F1F5F9] transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-[30px] font-bold text-[var(--ink)] leading-tight tracking-tight">
              Pre-Verification Stage & Inspector
            </h1>
            <p className="text-[15px] text-[var(--ink-2)] mt-0.5">
              Filing: <code className="font-mono font-bold text-[var(--primary)]">{filingInfo.id}</code> ({filingInfo.company} - FY {filingInfo.fy})
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-[var(--ink-3)]">Pipeline Readiness:</span>
          {bothReady ? (
            <StatusBadge status="supported">Ready for Symbolic Engine</StatusBadge>
          ) : (
            <StatusBadge status="insufficient">Steps Pending</StatusBadge>
          )}
        </div>
      </div>

      {/* Main Split Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        
        {/* LEFT PANEL (5 cols): 2 Processing Options + Final Verification Button */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          
          {/* Card 1: Process XBRL */}
          <div className={`bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border transition-all shadow-[var(--shadow-card)] ${
            xbrlProcessed ? "border-[var(--success-border)]" : "border-[var(--border)]"
          }`}>
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div className={`w-9 h-9 rounded-[var(--radius-control)] flex items-center justify-center ${
                  xbrlProcessed ? "bg-[var(--success-soft)] text-[var(--success)]" : "bg-[var(--primary-soft)] text-[var(--primary)]"
                }`}>
                  <FileCode className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-[var(--ink)]">Option 1: Process XBRL Instance</h3>
                  <p className="text-xs font-mono truncate max-w-[200px]" title={filingInfo.xbrlFileName || "No XBRL uploaded"}>
                    {filingInfo.hasXbrl ? filingInfo.xbrlFileName : (
                      <span className="text-amber-600 font-sans font-medium">No XBRL Uploaded</span>
                    )}
                  </p>
                </div>
              </div>

              {!filingInfo.hasXbrl ? (
                <span className="text-xs font-semibold text-amber-700 bg-amber-50 px-2.5 py-0.5 rounded-full border border-amber-200">
                  Not Attached
                </span>
              ) : xbrlProcessed ? (
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--success)] bg-[var(--success-soft)] px-2 py-0.5 rounded-full border border-[var(--success-border)]">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {duckdbFacts.length} Facts Ready
                </span>
              ) : (
                <span className="text-xs font-medium text-[var(--ink-3)] bg-[#F1F5F9] px-2 py-0.5 rounded">
                  Not Run (Pending)
                </span>
              )}
            </div>

            <p className="text-xs text-[var(--ink-2)] mb-4 leading-relaxed">
              {filingInfo.hasXbrl
                ? "Parses this filing's uploaded XML taxonomy, extracts numerical facts, and loads them into DuckDB normalized relational tables."
                : "This filing was registered without an XBRL file. You can still extract and inspect claims from the PDF narrative below."}
            </p>

            {!filingInfo.hasXbrl ? (
              <div className="flex flex-col gap-2">
                <input 
                  type="file" 
                  accept=".xml" 
                  ref={xbrlUploadRef} 
                  onChange={handleAttachXbrl} 
                  className="hidden" 
                />
                <button
                  type="button"
                  onClick={() => xbrlUploadRef.current?.click()}
                  disabled={isAttachingXbrl}
                  className="w-full h-10 rounded-[var(--radius-control)] font-semibold text-xs flex items-center justify-center gap-2 bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-indigo-100 transition-all shadow-xs cursor-pointer"
                >
                  {isAttachingXbrl ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Uploading & Attaching XBRL...</span>
                    </>
                  ) : (
                    <>
                      <UploadCloud className="w-4 h-4 text-indigo-600" />
                      <span>+ Attach XBRL File for this Filing</span>
                    </>
                  )}
                </button>
              </div>
            ) : (
              <button
                onClick={handleProcessXbrl}
                disabled={isProcessingXbrl}
                className={`w-full h-10 rounded-[var(--radius-control)] font-semibold text-xs flex items-center justify-center gap-2 transition-all ${
                  xbrlProcessed 
                    ? "btn-secondary text-[var(--success)] hover:bg-[#F8FAFC]" 
                    : "btn-primary"
                }`}
              >
                {isProcessingXbrl ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Parsing XBRL & Normalizing into DuckDB...</span>
                  </>
                ) : xbrlProcessed ? (
                  <>
                    <CheckCircle2 className="w-4 h-4 text-[var(--success)]" />
                    <span>XBRL Processed ({duckdbFacts.length} Facts) • Click to Re-run</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Run XBRL Pipeline</span>
                  </>
                )}
              </button>
            )}
          </div>

          {/* Card 2: Process PDF */}
          <div className={`bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border transition-all shadow-[var(--shadow-card)] ${
            pdfProcessed ? "border-[var(--success-border)]" : "border-[var(--border)]"
          }`}>
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div className={`w-9 h-9 rounded-[var(--radius-control)] flex items-center justify-center ${
                  pdfProcessed ? "bg-[var(--success-soft)] text-[var(--success)]" : "bg-[#F1F5F9] text-[var(--ink-3)]"
                }`}>
                  <FileText className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-[var(--ink)]">Option 2: Process PDF Narrative</h3>
                  <p className="text-xs text-[var(--ink-3)] font-mono truncate max-w-[200px]" title={filingInfo.pdfFileName}>
                    {filingInfo.pdfFileName}
                  </p>
                </div>
              </div>

              {pdfProcessed ? (
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--success)] bg-[var(--success-soft)] px-2 py-0.5 rounded-full border border-[var(--success-border)]">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {extractedClaims.length} Claims Ready
                </span>
              ) : (
                <span className="text-xs font-medium text-[var(--ink-3)] bg-[#F1F5F9] px-2 py-0.5 rounded">
                  Not Run (Pending)
                </span>
              )}
            </div>

            <p className="text-xs text-[var(--ink-2)] mb-4 leading-relaxed">
              Performs layout OCR analysis and extracts formal testable quantitative claims tuples c = (m, o, r, u).
            </p>

            <button
              onClick={handleProcessPdf}
              disabled={isProcessingPdf}
              className={`w-full h-10 rounded-[var(--radius-control)] font-semibold text-xs flex items-center justify-center gap-2 transition-all ${
                pdfProcessed 
                  ? "btn-secondary text-[var(--success)] hover:bg-[#F8FAFC]" 
                  : "bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300"
              }`}
            >
              {isProcessingPdf ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Extracting Claims...</span>
                </>
              ) : pdfProcessed ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-[var(--success)]" />
                  <span>PDF Claims Extracted (Click to Re-run)</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Process PDF Narrative</span>
                </>
              )}
            </button>
          </div>

          {/* Action: Run Verification Engine */}
          <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Cpu className="w-5 h-5 text-[var(--primary)]" />
              <h3 className="font-bold text-sm text-[var(--ink)]">Step 3: Verification Execution</h3>
            </div>
            <p className="text-xs text-[var(--ink-2)] leading-relaxed">
              Feeds both the extracted claims and DuckDB ground truth into the symbolic math verification engine to produce exact verdicts.
            </p>

            <button
              onClick={() => router.push(`/verify/${filingId}`)}
              disabled={!bothReady}
              className={`w-full h-11 rounded-[var(--radius-control)] font-bold text-sm flex items-center justify-center gap-2 shadow-md transition-all ${
                bothReady 
                  ? "btn-primary" 
                  : "bg-slate-200 text-slate-400 cursor-not-allowed border border-slate-300"
              }`}
            >
              <Sparkles className="w-4 h-4" />
              <span>Run Verification Engine</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

        </div>

        {/* RIGHT PANEL (7 cols): Sub-Navbar + Tab Content Inspector */}
        <div className="lg:col-span-7 bg-[var(--surface)] rounded-[var(--radius-card)] border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col min-h-[620px] overflow-hidden">
          
          {/* Sub-Navbar on same page to jump between PDF Claims, Raw XML, and DuckDB Facts */}
          <div className="bg-[#F8FAFC] p-3 border-b border-[var(--border)] flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-1.5 bg-white p-1 rounded-[var(--radius-control)] border border-[var(--border)]">
              <button
                onClick={() => setActiveTab("xml")}
                className={`px-3 py-1.5 rounded-[var(--radius-control)] text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                  activeTab === "xml" 
                    ? "bg-[var(--primary)] text-white shadow-sm" 
                    : "text-[var(--ink-2)] hover:bg-[#F1F5F9]"
                }`}
              >
                <FileCode className="w-3.5 h-3.5" />
                <span>Raw XBRL (XML)</span>
              </button>

              <button
                onClick={() => setActiveTab("duckdb")}
                className={`px-3 py-1.5 rounded-[var(--radius-control)] text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                  activeTab === "duckdb" 
                    ? "bg-[var(--primary)] text-white shadow-sm" 
                    : "text-[var(--ink-2)] hover:bg-[#F1F5F9]"
                }`}
              >
                <Database className="w-3.5 h-3.5" />
                <span>DuckDB Parsed Facts ({duckdbFacts.length})</span>
              </button>

              <button
                onClick={() => setActiveTab("claims")}
                className={`px-3 py-1.5 rounded-[var(--radius-control)] text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                  activeTab === "claims" 
                    ? "bg-[var(--primary)] text-white shadow-sm" 
                    : "text-[var(--ink-2)] hover:bg-[#F1F5F9]"
                }`}
              >
                <FileText className="w-3.5 h-3.5" />
                <span>PDF Extracted Claims ({extractedClaims.length})</span>
              </button>
            </div>

            <span className="text-[11px] font-bold text-[var(--ink-3)] uppercase tracking-wider pr-2">
              Inspector View
            </span>
          </div>

          {/* Inspector Body */}
          <div className="p-6 flex-1 overflow-y-auto flex flex-col">
            {isLoading && (
              <div className="flex items-center justify-center h-64 text-sm text-[var(--ink-3)]">
                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                Loading staging components...
              </div>
            )}

            {/* TAB 1: Raw XBRL XML Preview */}
            {!isLoading && activeTab === "xml" && (
              <div className="flex flex-col gap-3 h-full">
                <div className="flex items-center justify-between pb-2 border-b border-[var(--border)]">
                  <span className="text-xs font-bold text-[var(--ink-3)] uppercase tracking-wider">
                    Raw XBRL Instance Tag Stream
                  </span>
                  <span className="text-xs text-[var(--ink-3)] font-mono truncate max-w-[280px]">
                    {filingInfo.xbrlFileName || "No XBRL Uploaded"}
                  </span>
                </div>

                {!filingInfo.hasXbrl ? (
                  <div className="flex flex-col items-center justify-center p-14 text-center text-[var(--ink-3)] gap-4 bg-[#F8FAFC] rounded-[var(--radius-control)] border border-dashed border-[var(--border)] min-h-[420px]">
                    <div className="w-14 h-14 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center">
                      <FileCode className="w-7 h-7" />
                    </div>
                    <div>
                      <p className="text-base font-bold text-[var(--ink)]">No XBRL XML Attached to this Filing</p>
                      <p className="text-xs text-[var(--ink-2)] mt-1 max-w-sm">
                        This filing was registered with only a PDF. You can attach an official SEBI/BSE XBRL instance file now to verify claims against DuckDB facts.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => xbrlUploadRef.current?.click()}
                      disabled={isAttachingXbrl}
                      className="btn-primary text-xs shadow-sm flex items-center gap-2 cursor-pointer"
                    >
                      <UploadCloud className="w-4 h-4" />
                      <span>Upload XBRL File Now</span>
                    </button>
                  </div>
                ) : (
                  <div className="w-full flex-1 min-h-[460px] bg-slate-900 rounded-[var(--radius-control)] p-4 font-mono text-xs text-emerald-400 overflow-x-auto whitespace-pre leading-relaxed shadow-inner">
                    {xmlContent || "<!-- No XML preview available -->"}
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: DuckDB Parsed Facts Table */}
            {!isLoading && activeTab === "duckdb" && (
              <div className="flex flex-col gap-4">
                <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
                  <span className="text-xs font-bold text-[var(--ink-3)] uppercase tracking-wider">
                    Normalized Facts in DuckDB (<code className="text-[var(--primary)]">normalized_facts</code>)
                  </span>
                  {xbrlProcessed ? (
                    <span className="text-xs font-semibold text-[var(--success)] bg-[var(--success-soft)] px-2.5 py-0.5 rounded-full border border-[var(--success-border)]">
                      {duckdbFacts.length} Facts Ready
                    </span>
                  ) : (
                    <span className="text-xs font-medium text-[var(--ink-3)] bg-slate-100 px-2 py-0.5 rounded">
                      Not Run Yet
                    </span>
                  )}
                </div>

                {duckdbFacts.length === 0 ? (
                  <div className="flex flex-col items-center justify-center p-14 text-center text-[var(--ink-3)] gap-3 bg-[#F8FAFC] rounded-[var(--radius-control)] border border-dashed border-[var(--border)]">
                    <Database className="w-10 h-10 opacity-30 text-[var(--primary)]" />
                    <p className="text-sm font-semibold text-[var(--ink)]">No DuckDB Facts Extracted Yet</p>
                    <p className="text-xs text-[var(--ink-3)] max-w-sm">
                      Click &ldquo;Run XBRL Pipeline&rdquo; on the left to parse <code className="font-mono text-[var(--primary)]">{filingInfo.xbrlFileName}</code> into DuckDB.
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col gap-3">
                    {/* Filter Bar */}
                    <div className="flex flex-wrap items-center justify-between gap-2 bg-[#F8FAFC] p-2.5 rounded-[var(--radius-control)] border border-[var(--border)]">
                      <div className="flex flex-wrap gap-1">
                        {["All", "Energy", "Emissions", "Water", "Waste", "Workforce", "Financial", "Social"].map((cat) => (
                          <button
                            key={cat}
                            onClick={() => setSelectedCategory(cat)}
                            className={`px-2.5 py-1 text-xs font-semibold rounded-[var(--radius-control)] transition-colors ${
                              selectedCategory === cat
                                ? "bg-[var(--primary)] text-white shadow-xs"
                                : "text-[var(--ink-2)] hover:bg-[#E2E8F0] bg-white border border-[var(--border)]"
                            }`}
                          >
                            {cat}
                          </button>
                        ))}
                      </div>
                      <input
                        type="text"
                        placeholder="Search metric..."
                        value={metricSearch}
                        onChange={(e) => setMetricSearch(e.target.value)}
                        className="px-3 py-1 text-xs border border-[var(--border)] rounded-[var(--radius-control)] bg-white text-[var(--ink)] w-48 focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
                      />
                    </div>

                    <div className="overflow-x-auto rounded-[var(--radius-control)] border border-[var(--border)] max-h-[520px] overflow-y-auto">
                      <table className="w-full text-left text-xs text-[var(--ink-2)] border-collapse">
                        <thead className="bg-[#F8FAFC] text-[var(--ink-3)] font-bold uppercase tracking-wider border-b border-[var(--border)] sticky top-0 z-10">
                          <tr>
                            <th className="px-3 py-2.5">Category</th>
                            <th className="px-4 py-2.5">Canonical Metric</th>
                            <th className="px-4 py-2.5">Reporting Period</th>
                            <th className="px-4 py-2.5 text-right">Value (Float)</th>
                            <th className="px-3 py-2.5">Standard Unit</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[var(--border)]">
                          {duckdbFacts
                            .filter((f) => {
                              const matchesCat =
                                selectedCategory === "All" ||
                                (f.category && f.category.toLowerCase() === selectedCategory.toLowerCase());
                              const matchesSearch =
                                !metricSearch ||
                                f.canonical_name.toLowerCase().includes(metricSearch.toLowerCase());
                              return matchesCat && matchesSearch;
                            })
                            .map((f, i) => {
                              const catColors: Record<string, string> = {
                                Energy: "bg-amber-50 text-amber-700 border-amber-200",
                                Emissions: "bg-purple-50 text-purple-700 border-purple-200",
                                Water: "bg-sky-50 text-sky-700 border-sky-200",
                                Waste: "bg-emerald-50 text-emerald-700 border-emerald-200",
                                Workforce: "bg-indigo-50 text-indigo-700 border-indigo-200",
                                Financial: "bg-slate-100 text-slate-700 border-slate-300",
                                Social: "bg-pink-50 text-pink-700 border-pink-200"
                              };
                              const badgeStyle = catColors[f.category || ""] || "bg-gray-100 text-gray-700 border-gray-200";

                              return (
                                <tr key={i} className="hover:bg-[#F8FAFC]">
                                  <td className="px-3 py-2">
                                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${badgeStyle}`}>
                                      {f.category || "General"}
                                    </span>
                                  </td>
                                  <td className="px-4 py-2 font-mono font-bold text-[var(--ink)]">
                                    {f.canonical_name}
                                  </td>
                                  <td className="px-4 py-2 text-[var(--ink-2)]">
                                    {f.period}
                                  </td>
                                  <td className="px-4 py-2 text-right font-mono font-bold text-[var(--primary)]">
                                    {typeof f.value === "number" ? f.value.toLocaleString() : f.value}
                                  </td>
                                  <td className="px-3 py-2 font-semibold text-[var(--ink-3)]">
                                    {f.unit}
                                  </td>
                                </tr>
                              );
                            })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: PDF Extracted Claims */}
            {!isLoading && activeTab === "claims" && (
              <div className="flex flex-col gap-4">
                <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
                  <span className="text-xs font-bold text-[var(--ink-3)] uppercase tracking-wider">
                    Unstructured Claims Extracted from PDF Narrative
                  </span>
                  {pdfProcessed ? (
                    <span className="text-xs font-semibold text-[var(--primary)] bg-[var(--primary-soft)] px-2.5 py-0.5 rounded-full">
                      {extractedClaims.length} Claims Found
                    </span>
                  ) : (
                    <span className="text-xs font-medium text-[var(--ink-3)] bg-slate-100 px-2 py-0.5 rounded">
                      Not Run Yet
                    </span>
                  )}
                </div>

                {extractedClaims.length === 0 ? (
                  <div className="flex flex-col items-center justify-center p-14 text-center text-[var(--ink-3)] gap-3 bg-[#F8FAFC] rounded-[var(--radius-control)] border border-dashed border-[var(--border)]">
                    <FileText className="w-10 h-10 opacity-30 text-[var(--ink-2)]" />
                    <p className="text-sm font-semibold text-[var(--ink)]">No Claims Extracted Yet</p>
                    <p className="text-xs text-[var(--ink-3)] max-w-sm">
                      PDF narrative processing is held. You can inspect the raw XML tags and run the XBRL pipeline on the left.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {extractedClaims.map((claim, idx) => {
                      const quote = claim.original_quote || claim.source_passage || "";
                      const val = claim.stated_result ?? claim.asserted_value ?? "";
                      const period = claim.period_current || claim.current_period || "FY22";
                      return (
                        <div key={idx} className="p-4 rounded-[var(--radius-control)] bg-[#F8FAFC] border border-[var(--border)] flex flex-col gap-2">
                          <div className="flex justify-between items-start">
                            <span className="font-mono text-xs font-bold text-[var(--primary)]">
                              {claim.metric}
                            </span>
                            <span className="text-xs font-bold bg-white px-2 py-0.5 rounded border border-[var(--border)] text-[var(--ink)]">
                              {val} {claim.unit}
                            </span>
                          </div>
                          <p className="text-xs text-[var(--ink)] italic pl-2.5 border-l-2 border-[var(--primary)] leading-relaxed">
                            &ldquo;{quote}&rdquo;
                          </p>
                          <div className="flex justify-between text-[11px] text-[var(--ink-3)] pt-1">
                            <span>Operation: <strong className="text-[var(--ink-2)]">{claim.operation}</strong></span>
                            <span>Period: <strong className="text-[var(--ink-2)]">{period}</strong></span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

          </div>
        </div>

      </div>
    </div>
  );
}

export default function StageInspectorPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-sm text-[var(--ink-3)]">Loading stage inspector...</div>}>
      <StageInspectorContent />
    </Suspense>
  );
}
