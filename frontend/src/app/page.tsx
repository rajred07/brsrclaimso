import Link from "next/link";
import StatusBadge from "@/components/StatusBadge";
import { 
  FileCheck2, 
  AlertTriangle, 
  FolderCheck, 
  ArrowUp, 
  UploadCloud, 
  Clock, 
  ArrowRight,
  Layers,
  CheckCircle2
} from "lucide-react";

export default function Dashboard() {
  const recentActivities = [
    { 
      id: "infosys-2022", 
      company: "Infosys Ltd.", 
      year: "FY 2021-22", 
      claims: 7, 
      issues: 0, 
      time: "Verified",
      link: "/verify/infosys-2022" 
    },
  ];

  return (
    <div className="flex flex-col w-full animate-fade-in">
      {/* Page Header Pattern */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pb-6 mb-8 border-b border-[var(--border)]">
        <div>
          <h1 className="text-[32px] font-bold text-[var(--ink)] leading-tight tracking-tight">
            Reviewer Dashboard
          </h1>
          <p className="text-[16px] text-[var(--ink-2)] mt-1 font-normal">
            Overview of processed BRSR filings and recent verification activity.
          </p>
        </div>
        <Link
          href="/verify/infosys-2022"
          className="btn-primary"
        >
          <ArrowRight className="w-4 h-4" />
          <span>Open Workspace Demo</span>
        </Link>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {/* Card 1: Total Claims */}
        <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col justify-between relative">
          <div className="flex items-start justify-between">
            <span className="text-[12px] font-bold text-[var(--ink-3)] uppercase tracking-[0.05em]">
              Total Claims Checked
            </span>
            <div className="w-10 h-10 rounded-full bg-[var(--primary-soft)] text-[var(--primary)] flex items-center justify-center shrink-0">
              <FileCheck2 className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-4">
            <div className="text-[36px] font-bold text-[var(--ink)] leading-none">
              7
            </div>
            <div className="text-sm font-semibold text-[var(--success)] flex items-center gap-1.5 mt-3">
              <ArrowUp className="w-4 h-4 stroke-[2.5]" />
              <span>100% verified against DuckDB</span>
            </div>
          </div>
        </div>

        {/* Card 2: Inconsistency Rate */}
        <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col justify-between relative">
          <div className="flex items-start justify-between">
            <span className="text-[12px] font-bold text-[var(--ink-3)] uppercase tracking-[0.05em]">
              Inconsistency Rate
            </span>
            <div className="w-10 h-10 rounded-full bg-[var(--danger-soft)] text-[var(--danger)] flex items-center justify-center shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-4">
            <div className="text-[36px] font-bold text-[var(--success)] leading-none">
              0.0%
            </div>
            <div className="text-sm font-medium text-[var(--ink-2)] flex items-center gap-1.5 mt-3">
              <CheckCircle2 className="w-4 h-4 text-[var(--success)] shrink-0" />
              <span>6 Supported, 1 Abstain</span>
            </div>
          </div>
        </div>

        {/* Card 3: Filings Processed */}
        <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col justify-between relative">
          <div className="flex items-start justify-between">
            <span className="text-[12px] font-bold text-[var(--ink-3)] uppercase tracking-[0.05em]">
              Filings Processed
            </span>
            <div className="w-10 h-10 rounded-full bg-[var(--success-soft)] text-[var(--success)] flex items-center justify-center shrink-0">
              <FolderCheck className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-4">
            <div className="text-[36px] font-bold text-[var(--ink)] leading-none">
              1
            </div>
            <div className="text-sm font-medium text-[var(--ink-2)] flex items-center gap-1.5 mt-3">
              <Layers className="w-4 h-4 text-[var(--ink-3)] shrink-0" />
              <span>Infosys FY 2021-22</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid: Upload & Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main Upload Zone */}
        <Link
          href="/process/new"
          className="lg:col-span-2 bg-[var(--surface)] rounded-[var(--radius-card)] p-8 border-2 border-dashed border-[#CBD5E1] hover:border-[var(--primary)] hover:bg-[var(--primary-soft)] transition-all flex flex-col items-center justify-center min-h-[320px] text-center cursor-pointer group shadow-[var(--shadow-card)]"
        >
          <div className="w-16 h-16 rounded-full bg-[var(--primary-soft)] text-[var(--primary)] flex items-center justify-center mb-5 group-hover:scale-105 transition-transform">
            <UploadCloud className="w-8 h-8" />
          </div>
          <h3 className="text-xl font-bold text-[var(--ink)] mb-1.5">
            Process New Filing
          </h3>
          <p className="text-[var(--ink-2)] max-w-md mb-2 text-sm leading-relaxed">
            Click here to upload the Annual Report PDF and the corresponding BRSR XBRL instance file.
          </p>
          <span className="text-xs font-semibold text-[var(--ink-3)] tracking-wider uppercase mb-5">
            PDF + XBRL/XML
          </span>
          <div className="btn-secondary group-hover:border-[var(--primary)] group-hover:text-[var(--primary)] pointer-events-none">
            Open Upload Wizard
          </div>
        </Link>

        {/* Recent Activity */}
        <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col">
          <div className="flex items-center gap-2 pb-4 mb-4 border-b border-[var(--border)]">
            <Clock className="w-4 h-4 text-[var(--primary)]" />
            <h3 className="text-base font-bold text-[var(--ink)]">
              Recent Activity
            </h3>
          </div>
          <div className="flex flex-col gap-3">
            {recentActivities.map((item, i) => {
              const isFlagged = item.issues > 0;
              return (
                <Link
                  href={item.link || "/filing/infosys-2022"}
                  key={i}
                  className={`p-3.5 rounded-[12px] bg-[var(--surface)] hover:bg-[#F8FAFC] border border-[var(--border)] border-l-[3px] ${
                    isFlagged ? "border-l-[var(--danger)]" : "border-l-[var(--success)]"
                  } hover:shadow-md transition-all group flex flex-col gap-2`}
                >
                  <div className="flex justify-between items-center">
                    <span className="font-semibold text-sm text-[var(--ink)] group-hover:text-[var(--primary)] transition-colors">
                      {item.company}
                    </span>
                    <span className="text-[12px] text-[var(--ink-3)]">
                      {item.time}
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-[var(--ink-2)] font-medium">
                      {item.year} • {item.claims} claims
                    </span>
                    {isFlagged ? (
                      <StatusBadge status="inconsistent">
                        {item.issues} flagged
                      </StatusBadge>
                    ) : (
                      <StatusBadge status="supported">
                        All clear
                      </StatusBadge>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
