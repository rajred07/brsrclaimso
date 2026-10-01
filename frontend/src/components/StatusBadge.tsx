import React from "react";

export type StatusType = 
  | "supported" 
  | "inconsistent" 
  | "insufficient" 
  | "SUPPORTED" 
  | "INCONSISTENT" 
  | "INSUFFICIENT_EVIDENCE" 
  | "INSUFFICIENT"
  | string;

interface StatusBadgeProps {
  status: StatusType;
  children?: React.ReactNode;
  className?: string;
  showDot?: boolean;
}

export default function StatusBadge({
  status,
  children,
  className = "",
  showDot = true,
}: StatusBadgeProps) {
  const normalized = (status || "").toLowerCase();

  const isSupported = normalized.includes("support") || normalized.includes("clear") || normalized.includes("pass") || normalized.includes("ready") || normalized.includes("processed");
  const isInconsistent = normalized.includes("inconsistent") || normalized.includes("flagged") || normalized.includes("fail") || normalized.includes("error");
  const isInsufficient = normalized.includes("insufficient") || normalized.includes("abstain") || normalized.includes("missing") || normalized.includes("warn");

  // Determine variant styling
  let badgeClasses = "";
  let dotClass = "";
  let defaultLabel = "";

  if (isSupported && !isInconsistent && !isInsufficient) {
    badgeClasses = "bg-[var(--success-soft)] border-[var(--success-border)] text-[var(--success)]";
    dotClass = "bg-[var(--success)]";
    defaultLabel = "Supported";
  } else if (isInconsistent) {
    badgeClasses = "bg-[var(--danger-soft)] border-[var(--danger-border)] text-[var(--danger)]";
    dotClass = "bg-[var(--danger)]";
    defaultLabel = "Inconsistent";
  } else {
    // Insufficient / abstention
    badgeClasses = "bg-[var(--warning-soft)] border-[var(--warning-border)] text-[var(--warning)]";
    dotClass = "bg-[var(--warning)]";
    defaultLabel = "Insufficient Evidence";
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[12px] font-semibold tracking-normal transition-colors ${badgeClasses} ${className}`}
    >
      {showDot && (
        <span
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotClass}`}
          aria-hidden="true"
        />
      )}
      <span>{children ?? defaultLabel}</span>
    </span>
  );
}
