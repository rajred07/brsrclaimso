"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import StatusBadge from "@/components/StatusBadge";
import { 
  Search, 
  Check, 
  Minus, 
  AlertCircle, 
  ArrowRight,
  ExternalLink,
  Plus
} from "lucide-react";

interface FilingItem {
  id: string;
  company: string;
  symbol: string;
  fy: string;
  sector: string;
  pdf: boolean;
  xbrl: boolean;
  status: string;
  total_claims?: number;
  supported_count?: number;
  inconsistent_count?: number;
}

export default function InventoryPage() {
  const [filings, setFilings] = useState<FilingItem[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [sectorFilter, setSectorFilter] = useState("All Sectors");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadFilings() {
      try {
        const res = await fetch("/api/filings");
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            setFilings(data);
            return;
          }
        }
      } catch (e) {
        console.error("Failed to load dynamic filings from SQLite:", e);
      } finally {
        setIsLoading(false);
      }

      // Default fallback if database is empty
      setFilings([
        { id: "infosys-2022", company: "Infosys Ltd.", symbol: "INFY", fy: "2021-22", sector: "IT Services", pdf: true, xbrl: true, status: "PROCESSED", total_claims: 7, supported_count: 6 },
      ]);
    }

    loadFilings();
  }, []);

  const filtered = filings.filter((item) => {
    const matchesSearch = 
      item.company.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.symbol.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesSector = sectorFilter === "All Sectors" || item.sector === sectorFilter;
    return matchesSearch && matchesSector;
  });

  return (
    <div className="flex flex-col w-full animate-fade-in">
      {/* Page Header Pattern */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pb-6 mb-8 border-b border-[var(--border)]">
        <div>
          <h1 className="text-[32px] font-bold text-[var(--ink)] leading-tight tracking-tight">
            Filings Inventory
          </h1>
          <p className="text-[16px] text-[var(--ink-2)] mt-1 font-normal">
            Manage and track static BRSR filings stored in database and storage.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/process/new" className="btn-primary">
            <Plus className="w-4 h-4" />
            <span>Upload New Filing</span>
          </Link>
        </div>
      </div>

      {/* Table Card */}
      <div className="bg-[var(--surface)] rounded-[var(--radius-card)] border border-[var(--border)] shadow-[var(--shadow-card)] overflow-hidden">
        {/* Search & Filter Toolbar */}
        <div className="p-4 bg-[#F8FAFC] border-b border-[var(--border)] flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-[var(--ink-3)] absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input 
              type="text" 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search company or symbol..." 
              className="w-full h-11 pl-10 pr-4 bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-control)] text-sm text-[var(--ink)] placeholder:text-[var(--ink-3)] focus:outline-none focus:border-[var(--primary)] focus:ring-3 focus:ring-[rgba(79,70,229,0.25)] transition-all"
            />
          </div>
          <select 
            value={sectorFilter}
            onChange={(e) => setSectorFilter(e.target.value)}
            className="h-11 px-4 bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-control)] text-sm text-[var(--ink-2)] font-medium focus:outline-none focus:border-[var(--primary)] focus:ring-3 focus:ring-[rgba(79,70,229,0.25)] cursor-pointer transition-all"
          >
            <option>All Sectors</option>
            <option>IT Services</option>
            <option>Banking</option>
            <option>Manufacturing</option>
            <option>Conglomerate</option>
            <option>Telecom</option>
            <option>General</option>
          </select>
        </div>
        
        {/* Table with responsive horizontal scroll */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-[var(--ink-2)] border-collapse min-w-[700px]">
            <thead className="bg-[#F8FAFC] text-[var(--ink-3)] font-bold uppercase text-[12px] tracking-[0.05em] border-b border-[var(--border)]">
              <tr>
                <th className="px-6 py-4">Company</th>
                <th className="px-6 py-4">FY</th>
                <th className="px-6 py-4">Sector</th>
                <th className="px-6 py-4">Documents</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {isLoading && (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-[var(--ink-3)]">
                    Loading filings from SQLite database...
                  </td>
                </tr>
              )}
              {!isLoading && filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-[var(--ink-3)]">
                    No matching filings found in database.
                  </td>
                </tr>
              )}
              {filtered.map((row) => (
                <tr key={row.id} className="h-16 hover:bg-[#F8FAFC] transition-colors">
                  <td className="px-6 py-3.5">
                    <div className="font-semibold text-sm text-[var(--ink)]">{row.company}</div>
                    <div className="text-[13px] text-[var(--ink-3)] mt-0.5">{row.symbol}</div>
                  </td>
                  <td className="px-6 py-3.5 font-medium text-[var(--ink-2)]">{row.fy}</td>
                  <td className="px-6 py-3.5">
                    <span className="bg-slate-100 text-slate-600 px-2.5 py-1 rounded-full text-xs font-medium inline-block">
                      {row.sector}
                    </span>
                  </td>
                  <td className="px-6 py-3.5">
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold inline-flex items-center gap-1 border ${
                        row.pdf 
                          ? "bg-[var(--success-soft)] text-[var(--success)] border-[var(--success-border)]"
                          : "bg-[#F1F5F9] text-[var(--ink-3)] border-dashed border-[#CBD5E1]"
                      }`}>
                        {row.pdf ? <Check className="w-3 h-3 stroke-[3]" /> : <Minus className="w-3 h-3 stroke-[2.5]" />}
                        PDF
                      </span>

                      <span className={`px-2 py-0.5 rounded text-xs font-semibold inline-flex items-center gap-1 border ${
                        row.xbrl 
                          ? "bg-[var(--success-soft)] text-[var(--success)] border-[var(--success-border)]"
                          : "bg-[#F1F5F9] text-[var(--ink-3)] border-dashed border-[#CBD5E1]"
                      }`}>
                        {row.xbrl ? <Check className="w-3 h-3 stroke-[3]" /> : <Minus className="w-3 h-3 stroke-[2.5]" />}
                        XBRL
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-3.5">
                    <StatusBadge status={row.status} />
                  </td>
                  <td className="px-6 py-3.5 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link 
                        href={`/process/stage?id=${row.id}`} 
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-[var(--radius-control)] bg-[var(--primary-soft)] text-[var(--primary)] font-semibold text-xs hover:bg-[var(--primary)] hover:text-white transition-all"
                      >
                        {row.status === "READY" ? "Process Pipeline" : "Stage & Inspect"}
                        <ArrowRight className="w-3 h-3" />
                      </Link>
                      {row.status === "PROCESSED" && (
                        <Link 
                          href={`/verify/${row.id}`} 
                          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-[var(--radius-control)] bg-[var(--surface)] border border-[var(--border)] text-[var(--ink)] font-semibold text-xs hover:bg-[#F1F5F9] transition-all"
                        >
                          Results
                          <ExternalLink className="w-3 h-3" />
                        </Link>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
