import StatusBadge from "@/components/StatusBadge";
import { Info } from "lucide-react";

export default function EvidenceCard({
  id,
  claimQuote,
  metric,
  status,
  reportedValue,
  baseValue,
  mathTrace,
  explanation
}: {
  id: string;
  claimQuote: string;
  metric: string;
  status: "SUPPORTED" | "INCONSISTENT" | "INSUFFICIENT_EVIDENCE";
  reportedValue: string;
  baseValue: string;
  mathTrace: string;
  explanation: string;
}) {
  return (
    <div 
      id={`claim-${id}`} 
      className="bg-[var(--surface)] rounded-[var(--radius-card)] p-5 border border-[var(--border)] hover:border-[var(--primary)] hover:shadow-md transition-all flex flex-col gap-4 shadow-[var(--shadow-card)]"
    >
      {/* Header */}
      <div className="flex justify-between items-start gap-4">
        <div className="flex flex-col gap-1">
          <span className="text-[12px] font-bold text-[var(--ink-3)] uppercase tracking-[0.05em]">
            {metric}
          </span>
          <p className="text-sm font-semibold text-[var(--ink)] italic leading-snug">
            &ldquo;{claimQuote}&rdquo;
          </p>
        </div>
        <StatusBadge status={status} />
      </div>

      <div className="h-px w-full bg-[var(--border)]"></div>

      {/* Ground Truth & Math */}
      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-bold text-[var(--ink-3)] uppercase tracking-wider">
            XBRL Ground Truth
          </span>
          <div className="flex flex-col gap-1.5 text-xs text-[var(--ink-2)] bg-[#F8FAFC] p-3 rounded-[var(--radius-control)] border border-[var(--border)]">
            <div className="flex justify-between items-center">
              <span className="text-[var(--ink-2)] font-medium">Current:</span>
              <span className="font-mono font-bold text-[var(--ink)]">{reportedValue}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-[var(--ink-2)] font-medium">Base Year:</span>
              <span className="font-mono font-bold text-[var(--ink)]">{baseValue}</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-bold text-[var(--ink-3)] uppercase tracking-wider">
            Math Trace
          </span>
          <div className="flex flex-col gap-1 bg-[var(--primary-soft)] p-3 rounded-[var(--radius-control)] border border-[var(--primary-soft)] h-full justify-center">
            <code className="font-mono font-bold text-[var(--primary)] block text-center text-xs break-all">
              {mathTrace}
            </code>
          </div>
        </div>
      </div>

      {/* Explanation */}
      <div className="bg-[#F8FAFC] p-3 rounded-[var(--radius-control)] border border-[var(--border)] flex items-start gap-2.5">
        <Info className="w-4 h-4 text-[var(--ink-3)] mt-0.5 shrink-0" />
        <p className="text-[13px] font-normal text-[var(--ink-2)] leading-relaxed">
          {explanation}
        </p>
      </div>
    </div>
  );
}
