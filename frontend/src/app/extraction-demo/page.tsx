"use client";

import { useState } from "react";
import StatusBadge from "@/components/StatusBadge";
import { FileText, CheckCircle2, ArrowRight, Loader2, Database } from "lucide-react";

interface DemoClaim {
  verdict: string;
  metric: string;
  original_quote: string;
  math_trace?: {
    value_compare: string | number;
    value_current: string | number;
    calculated_result: number;
  };
  stated_result?: string | number;
  reason?: string;
}

export default function ExtractionDemo() {
  const [isProcessing, setIsProcessing] = useState(false);
  const [results, setResults] = useState<DemoClaim[] | null>(null);

  const handleProcessClick = async () => {
    setIsProcessing(true);
    try {
      const response = await fetch('/api/demo', { method: 'POST' });
      const data = await response.json();
      setResults(data);
    } catch (err) {
      console.error(err);
      alert("Failed to run verification engine.");
    } finally {
      setIsProcessing(false);
    }
  };

  const mockXml = `<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:in-bse-brsr="http://www.bseindia.com/xbrl/brsr/2022-03-31">

  <!-- Energy Consumption -->
  <in-bse-brsr:EnergyConsumptionTotal contextRef="FY22" unitRef="GJ">650476.00</in-bse-brsr:EnergyConsumptionTotal>
  <in-bse-brsr:EnergyConsumptionTotal contextRef="FY21" unitRef="GJ">671660.00</in-bse-brsr:EnergyConsumptionTotal>

  <!-- Renewable Energy -->
  <in-bse-brsr:EnergyConsumptionRenewable contextRef="FY22" unitRef="GJ">266119.00</in-bse-brsr:EnergyConsumptionRenewable>

  <!-- Greenhouse Gas Emissions -->
  <in-bse-brsr:Scope1Emissions contextRef="FY22" unitRef="tCO2e">8965.00</in-bse-brsr:Scope1Emissions>
  <in-bse-brsr:Scope2Emissions contextRef="FY22" unitRef="tCO2e">51717.00</in-bse-brsr:Scope2Emissions>

</xbrli:xbrl>`;

  return (
    <div className="flex flex-col w-full animate-fade-in">
      {/* Page Header Pattern */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pb-6 mb-8 border-b border-[var(--border)]">
        <div>
          <h1 className="text-[32px] font-bold text-[var(--ink)] leading-tight tracking-tight">
            Neuro-Symbolic Engine Demo
          </h1>
          <p className="text-[16px] text-[var(--ink-2)] mt-1 font-normal max-w-3xl">
            Interactive benchmark demonstration on the real Infosys ESG Report, verifying prose PDF claims against structured XBRL ground truth facts.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* PDF View Panel */}
        <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col min-h-[620px]">
          <div className="flex items-center gap-3 mb-4 pb-4 border-b border-[var(--border)]">
            <div className="w-9 h-9 rounded-[var(--radius-control)] bg-[var(--primary-soft)] flex items-center justify-center text-[var(--primary)]">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-[var(--ink)]">Unstructured Narrative</h3>
              <p className="text-xs text-[var(--ink-3)] font-medium">infosys-esg-report-2021-22.pdf</p>
            </div>
          </div>
          
          <div className="flex-1 min-h-[420px] w-full rounded-[var(--radius-control)] overflow-hidden border border-[var(--border)] bg-[#F8FAFC]">
            <iframe 
              src="/infosys-esg-report-2021-22.pdf#page=13" 
              className="w-full h-full" 
              title="Infosys PDF Report"
            />
          </div>
        </div>

        {/* Results Panel */}
        <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col min-h-[620px] relative overflow-hidden">
          <div className="flex items-center gap-3 mb-4 pb-4 border-b border-[var(--border)] z-10 relative">
            <div className="w-9 h-9 rounded-[var(--radius-control)] bg-[var(--success-soft)] flex items-center justify-center text-[var(--success)]">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-[var(--ink)]">Verification Engine Output</h3>
              <p className="text-xs text-[var(--ink-3)] font-medium">Neuro-Symbolic Math Trace</p>
            </div>
          </div>

          {!results && !isProcessing && (
            <div className="flex-1 flex flex-col items-center justify-between text-center z-10 relative">
              <div className="w-full h-[360px] overflow-y-auto bg-slate-900 p-5 rounded-[var(--radius-control)] border border-slate-800 text-left font-mono text-emerald-400 text-xs whitespace-pre-wrap shadow-inner relative group">
                <div className="absolute top-3 right-3 text-[11px] bg-slate-800 px-2 py-0.5 rounded text-slate-400 flex items-center gap-1">
                  <Database className="w-3 h-3" />
                  brsr_facts.duckdb
                </div>
                {mockXml}
              </div>
              
              <button 
                onClick={handleProcessClick}
                className="btn-primary w-full h-11 text-sm shadow-md mt-4"
              >
                <span>Process & Verify Claims</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {isProcessing && (
            <div className="flex-1 flex flex-col items-center justify-center text-center z-10 relative">
              <div className="w-16 h-16 bg-[var(--primary-soft)] border border-[var(--primary-soft)] rounded-full flex items-center justify-center mb-4 text-[var(--primary)]">
                <Loader2 className="w-8 h-8 animate-spin" />
              </div>
              <h4 className="font-bold text-[var(--ink)] text-base mb-1">Processing Claims...</h4>
              <p className="text-xs text-[var(--ink-2)] max-w-xs">
                The Neuro-Symbolic Engine is mapping metrics and querying the DuckDB facts database.
              </p>
            </div>
          )}

          {results && (
            <div className="flex-1 overflow-y-auto pr-1 space-y-4 pb-2 z-10 relative">
              {results.map((claim, idx) => {
                const isSupp = claim.verdict === "SUPPORTED";
                const isInc = claim.verdict === "INCONSISTENT";
                
                return (
                  <div 
                    key={idx} 
                    className={`p-4 rounded-[var(--radius-control)] border transition-all ${
                      isSupp 
                        ? "bg-[var(--success-soft)] border-[var(--success-border)]" 
                        : isInc 
                        ? "bg-[var(--danger-soft)] border-[var(--danger-border)]" 
                        : "bg-[var(--warning-soft)] border-[var(--warning-border)]"
                    }`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <StatusBadge status={claim.verdict} />
                      <span className="text-xs font-semibold bg-white/70 px-2 py-0.5 rounded border border-black/5 text-[var(--ink)]">
                        {claim.metric}
                      </span>
                    </div>
                    
                    <p className="text-xs font-medium mb-3 italic text-[var(--ink)] pl-2.5 border-l-2 border-current">
                      &ldquo;{claim.original_quote}&rdquo;
                    </p>
                    
                    <div className="bg-white/80 rounded-lg p-2.5 text-xs font-mono space-y-1 text-[var(--ink)] border border-black/5">
                      {claim.math_trace ? (
                        <>
                          <div className="flex justify-between text-[var(--ink-2)]"><span>DB Previous (FY21):</span> <span>{claim.math_trace.value_compare}</span></div>
                          <div className="flex justify-between text-[var(--ink-2)]"><span>DB Current (FY22):</span> <span>{claim.math_trace.value_current}</span></div>
                          <div className="h-px bg-slate-200 my-1"></div>
                          <div className="flex justify-between font-bold text-[var(--primary)]"><span>Python Calc:</span> <span>{claim.math_trace.calculated_result.toFixed(2)}</span></div>
                          <div className="flex justify-between font-bold text-[var(--primary)]"><span>LLM Stated:</span> <span>{claim.stated_result}</span></div>
                        </>
                      ) : (
                        <div className="text-center py-1 text-[var(--ink-3)]">No DB Facts Found</div>
                      )}
                    </div>
                    
                    <p className="text-[11px] font-semibold mt-2.5 text-[var(--ink-2)]">
                      Engine Log: {claim.reason}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
