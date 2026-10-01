"use client";

import { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, AlertCircle, Loader2, ArrowRight } from "lucide-react";

function RunningContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filingId = searchParams.get("id") || "infosys-2022";

  const [currentStep, setCurrentStep] = useState(0);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const hasStarted = useRef(false);

  const steps = [
    { label: "Parsing XBRL Taxonomy & Extracting Ground Truth", script: "src/xbrl_parse.py", index: 0 },
    { label: "Mathematical Normalization of Variables", script: "src/normalize.py", index: 1 },
    { label: "Running Layout Analysis on PDF", script: "src/ingest.py", index: 2 },
    { label: "LLM Phase: Identifying Quantitative Claims", script: "src/extract_claims.py", index: 3 },
  ];

  useEffect(() => {
    if (hasStarted.current) return;
    hasStarted.current = true;

    const runPipeline = async () => {
      try {
        const response = await fetch('/api/process', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filingId })
        });

        if (!response.body) throw new Error("No response body");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let done = false;

        while (!done) {
          const { value, done: readerDone } = await reader.read();
          done = readerDone;
          
          if (value) {
            const chunk = decoder.decode(value);

            if (chunk.includes("Running Phase: src/ingest.py")) {
              setCurrentStep(2);
            } else if (chunk.includes("Running Phase: src/extract_claims.py")) {
              setCurrentStep(3);
            } else if (chunk.includes("Running Phase: src/xbrl_parse.py")) {
              setCurrentStep(0);
            } else if (chunk.includes("Running Phase: src/normalize.py")) {
              setCurrentStep(1);
            } else if (chunk.includes("PIPELINE COMPLETE!")) {
              setCurrentStep(4);
              setIsComplete(true);
            } else if (chunk.includes("[ERROR]")) {
              setError("Pipeline encountered an error. Check console logs.");
              setIsComplete(true);
            }
          }
        }
      } catch (err) {
        console.error(err);
        setError("Failed to connect to the neuro-symbolic engine.");
      }
    };

    runPipeline();
  }, [filingId]);

  return (
    <div className="flex flex-col items-center justify-center w-full animate-fade-in max-w-3xl mx-auto py-6">
      <div className="w-full flex flex-col gap-8">
        
        {/* Status Header */}
        <div className="text-center flex flex-col items-center">
          <div className={`w-16 h-16 rounded-full flex items-center justify-center mb-4 transition-colors ${
            isComplete && !error 
              ? 'bg-[var(--success-soft)] text-[var(--success)] border border-[var(--success-border)]' 
              : error 
              ? 'bg-[var(--danger-soft)] text-[var(--danger)] border border-[var(--danger-border)]' 
              : 'bg-[var(--primary-soft)] text-[var(--primary)] border border-[var(--primary-soft)]'
          }`}>
            {isComplete && !error ? (
              <CheckCircle2 className="w-8 h-8" />
            ) : error ? (
              <AlertCircle className="w-8 h-8" />
            ) : (
              <Loader2 className="w-8 h-8 animate-spin" />
            )}
          </div>
          <h1 className="text-[32px] font-bold text-[var(--ink)] leading-tight tracking-tight">
            {isComplete && !error ? "Verification Complete!" : error ? "Verification Failed" : "Pipeline Execution in Progress"}
          </h1>
          <p className="text-[14px] text-[var(--ink-2)] mt-1">
            Target Filing: <code className="font-mono font-bold text-[var(--primary)]">{filingId}</code>
          </p>
          <p className="text-[15px] text-[var(--ink-2)] mt-2 max-w-lg">
            {isComplete && !error
              ? "The neuro-symbolic engine has successfully finished processing and verified all claims."
              : error 
              ? error
              : "Please wait while the neuro-symbolic engine extracts and normalizes the data against DuckDB."}
          </p>
        </div>

        {/* Steps Card */}
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-card)] p-8 flex flex-col gap-6 shadow-[var(--shadow-card)]">
          {steps.map((step) => {
            const isDone = currentStep > step.index;
            const isActive = currentStep === step.index;
            const isWaiting = currentStep < step.index;

            return (
              <div key={step.index} className="flex items-center gap-4 relative">
                {step.index < steps.length - 1 && (
                  <div className={`absolute left-[19px] top-[38px] w-[2px] h-8 ${isDone ? 'bg-[var(--success)]' : 'bg-[var(--border)]'}`}></div>
                )}

                <div className="flex-shrink-0 relative z-10">
                  {isDone && (
                    <div className="w-10 h-10 rounded-full bg-[var(--success-soft)] flex items-center justify-center text-[var(--success)] border border-[var(--success-border)]">
                      <CheckCircle2 className="w-5 h-5" />
                    </div>
                  )}
                  {isActive && (
                    <div className="w-10 h-10 rounded-full bg-[var(--primary-soft)] flex items-center justify-center text-[var(--primary)] border border-[var(--primary)]">
                      <Loader2 className="w-5 h-5 animate-spin" />
                    </div>
                  )}
                  {isWaiting && (
                    <div className="w-10 h-10 rounded-full bg-[#F1F5F9] flex items-center justify-center text-[var(--ink-3)] border border-[var(--border)]">
                      <span className="font-bold text-xs">{step.index + 1}</span>
                    </div>
                  )}
                </div>
                
                <div className="flex-1 flex flex-col">
                  <span className={`text-sm font-semibold ${
                    isDone ? 'text-[var(--ink)]' : isActive ? 'text-[var(--primary)]' : 'text-[var(--ink-3)]'
                  }`}>
                    {step.label}
                  </span>
                  <span className={`text-xs ${isDone ? 'text-[var(--ink-3)]' : isActive ? 'text-[var(--primary)]' : 'text-[var(--ink-3)]'}`}>
                    {isActive ? "Currently processing..." : isDone ? "Completed successfully." : "Waiting in queue..."}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* View Results Button */}
        <div className="flex justify-center">
          {isComplete && !error && (
            <button 
              onClick={() => router.push(`/filing/${filingId}`)}
              className="btn-primary px-8 h-11 text-base shadow-md"
            >
              <span>View Verification Results ({filingId})</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
        
      </div>
    </div>
  );
}

export default function PipelineRunning() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-sm text-[var(--ink-3)]">Loading pipeline runner...</div>}>
      <RunningContent />
    </Suspense>
  );
}
