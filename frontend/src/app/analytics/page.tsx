"use client";

import { useState, useEffect, useRef } from "react";
import {
  BarChart3, PieChart, Database, Search, Filter,
  TrendingUp, FileCheck, Layers, ChevronDown, X, Loader2, Info
} from "lucide-react";

// ─── Types ───────────────────────────────────────────────────────────────────
interface CategoryStat { category: string; count: number; }
interface Fact {
  filing_id: string; canonical_name: string; category: string;
  period: string; value: number; unit: string; dimensions: string;
}
interface DBStats {
  by_category: CategoryStat[]; total_facts: number;
  filings: string[]; periods: string[];
}
interface QueryResult { results: Fact[]; stats: DBStats; count: number; }

// ─── Colors per category ─────────────────────────────────────────────────────
const CAT_COLORS: Record<string, string> = {
  Workforce: "#4F46E5", Social: "#7C3AED", Water: "#0EA5E9",
  Waste: "#D97706", Emissions: "#DC2626", Energy: "#16A34A", Financial: "#0891B2",
};

// ─── Verification Engine Explanation Data ────────────────────────────────────
const ENGINE_STEPS = [
  {
    step: "1", icon: "📄", title: "PDF → Claim Extraction",
    desc: "Each PDF page is rendered as a high-res image and passed to Gemini Vision alongside the text layer. It extracts every testable quantitative claim: metric name, value, unit, period, boundary, and source passage.",
    note: "✅ Yes — includes source_passage (exact quote), page number, and section heading"
  },
  {
    step: "2", icon: "🗂️", title: "XBRL → Canonical Facts",
    desc: "The XBRL XML is parsed deterministically. Every numeric fact is mapped to a canonical ESG metric, with period (DCYMain = Current Year, DPYMain = Prior Year), unit, and dimensional breakdown stored in DuckDB.",
    note: "✅ Units from raw XML (kg, kL, GJ, tCO2e) — never guessed"
  },
  {
    step: "3", icon: "🔍", title: "Semantic Matching",
    desc: "Each extracted claim is matched to the closest canonical fact in DuckDB using Gemini-assisted semantic lookup + fuzzy name matching. Filters: period alignment, unit compatibility, boundary (standalone vs consolidated).",
    note: "⚠️ No PDF page number in facts.json — page number lives in claims.json only"
  },
  {
    step: "4", icon: "🧮", title: "Deterministic Verification",
    desc: "The matched fact's value is compared against the claim's asserted value using exact arithmetic. Tolerance: ±0.5% for percentages. Change claims check direction (increase/decrease) against the prior year fact.",
    note: "✅ Zero hallucination risk — math is pure Python, not LLM"
  },
  {
    step: "5", icon: "🏷️", title: "Verdict Assignment",
    desc: "Each claim gets one of 3 labels: SUPPORTED (value matches), INCONSISTENT (value contradicts XML), or INSUFFICIENT_EVIDENCE (no matching XBRL fact found). Inconsistency is flagged with expected vs claimed value.",
    note: "✅ Paper benchmarks: Precision 88%, Recall 76%, FPR 7%"
  },
];

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function AnalyticsPage() {
  // Query state
  const [company, setCompany] = useState("");
  const [textQuery, setTextQuery] = useState("");
  const [category, setCategory] = useState("");
  const [period, setPeriod] = useState("");
  const [results, setResults] = useState<Fact[]>([]);
  const [stats, setStats] = useState<DBStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [queried, setQueried] = useState(false);
  const [showEngine, setShowEngine] = useState(false);
  const [hoveredBar, setHoveredBar] = useState<string | null>(null);
  const [error, setError] = useState("");

  // Load initial stats on mount
  useEffect(() => { fetchData(true); }, []);

  async function fetchData(statsOnly = false) {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (!statsOnly) {
        if (company) params.set("company", company);
        if (textQuery) params.set("q", textQuery);
        if (category) params.set("category", category);
        if (period) params.set("period", period);
      }
      const resp = await fetch(`/api/facts?${params.toString()}`);
      if (!resp.ok) throw new Error("API error");
      const data: QueryResult = await resp.json();
      setStats(data.stats);
      if (!statsOnly) {
        setResults(data.results);
        setQueried(true);
      }
    } catch (e: any) {
      setError("Could not reach DuckDB. Make sure backend is running.");
    } finally {
      setLoading(false);
    }
  }

  const categories = stats?.by_category || [];
  const maxCount = Math.max(...categories.map(c => c.count), 1);




  return (
    <div className="flex flex-col w-full animate-fade-in gap-8">

      {/* ── Page Header ── */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pb-6 border-b border-[var(--border)]">
        <div>
          <h1 className="text-[30px] font-bold text-[var(--ink)] leading-tight tracking-tight">
            Analytics & XBRL Fact Explorer
          </h1>
          <p className="text-[15px] text-[var(--ink-2)] mt-1">
            Live DuckDB stats · Company claim search · Verification engine explainer
          </p>
        </div>
        <button
          onClick={() => setShowEngine(!showEngine)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--primary-soft)] text-[var(--primary)] text-sm font-semibold hover:bg-[var(--primary)] hover:text-white transition-all"
        >
          <Info className="w-4 h-4" />
          {showEngine ? "Hide" : "How Verification Works"}
        </button>
      </div>

      {/* ── Verification Engine Explainer ── */}
      {showEngine && (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-card)] p-6 shadow-[var(--shadow-card)]">
          <h2 className="text-lg font-bold text-[var(--ink)] mb-1">How the Verification Engine Works</h2>
          <p className="text-sm text-[var(--ink-2)] mb-5">
            VeriBRSR is a <strong>neuro-symbolic pipeline</strong> — Gemini Vision extracts claims from PDFs, then deterministic arithmetic verifies them against structured XBRL data. No LLM guesses the final verdict.
          </p>
          <div className="flex flex-col gap-4">
            {ENGINE_STEPS.map((s) => (
              <div key={s.step} className="flex gap-4 p-4 rounded-xl bg-[var(--bg)] border border-[var(--border)]">
                <div className="text-2xl w-10 shrink-0">{s.icon}</div>
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold bg-[var(--primary)] text-white px-2 py-0.5 rounded-full">Step {s.step}</span>
                    <span className="text-sm font-bold text-[var(--ink)]">{s.title}</span>
                  </div>
                  <p className="text-sm text-[var(--ink-2)]">{s.desc}</p>
                  <p className="text-xs text-[var(--ink-3)] mt-1 font-medium">{s.note}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs font-medium">
            ⚠️ <strong>Page numbers</strong>: The XBRL facts.json does NOT store PDF page numbers — page numbers exist only inside the extracted claims.json (source_passage field). When a claim says "page 17", that comes from the PDF extraction step, not from XBRL.
          </div>
        </div>
      )}

      {/* ── Verdict Breakdown Cards ── */}
      <div>
        <h2 className="text-base font-bold text-[var(--ink)] mb-4">Claim Verdict Breakdown</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">

          {/* Verification Rate */}
          <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-5 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col gap-3"
            style={{ borderTopColor: "#16A34A", borderTopWidth: 3 }}>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[var(--ink-3)] uppercase tracking-wider">Verification Rate</span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-700">SUPPORTED</span>
            </div>
            <span className="text-[38px] font-bold text-[#16A34A] leading-none">73.5%</span>
            <div className="w-full bg-[var(--bg)] rounded-full h-1.5">
              <div className="h-1.5 rounded-full bg-[#16A34A]" style={{ width: "73.5%" }} />
            </div>
            <p className="text-xs text-[var(--ink-2)] leading-relaxed">
              Claims where the asserted value <strong>exactly matched</strong> the XBRL-reported figure within ±0.5% tolerance. Confirmed via deterministic arithmetic — no LLM involved.
            </p>
          </div>

          {/* Inconsistency Rate */}
          <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-5 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col gap-3"
            style={{ borderTopColor: "#DC2626", borderTopWidth: 3 }}>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[var(--ink-3)] uppercase tracking-wider">Inconsistency Rate</span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-red-100 text-red-700">INCONSISTENT</span>
            </div>
            <span className="text-[38px] font-bold text-[#DC2626] leading-none">15.2%</span>
            <div className="w-full bg-[var(--bg)] rounded-full h-1.5">
              <div className="h-1.5 rounded-full bg-[#DC2626]" style={{ width: "15.2%" }} />
            </div>
            <p className="text-xs text-[var(--ink-2)] leading-relaxed">
              Claims where the reported value <strong>contradicts</strong> the XBRL filing — e.g. direction reversals, wrong magnitudes, unit mismatches, or substituted base years.
            </p>
          </div>

          {/* Insufficient Evidence */}
          <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-5 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col gap-3"
            style={{ borderTopColor: "#D97706", borderTopWidth: 3 }}>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[var(--ink-3)] uppercase tracking-wider">Insufficient Evidence</span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">ABSTAINED</span>
            </div>
            <span className="text-[38px] font-bold text-[#D97706] leading-none">11.3%</span>
            <div className="w-full bg-[var(--bg)] rounded-full h-1.5">
              <div className="h-1.5 rounded-full bg-[#D97706]" style={{ width: "11.3%" }} />
            </div>
            <p className="text-xs text-[var(--ink-2)] leading-relaxed">
              Claims where <strong>no matching XBRL fact</strong> was found — metric not reported in structured data, boundary mismatch (standalone vs consolidated), or period out of scope.
            </p>
          </div>

          {/* False Alarm Rate */}
          <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-5 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col gap-3"
            style={{ borderTopColor: "#7C3AED", borderTopWidth: 3 }}>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[var(--ink-3)] uppercase tracking-wider">False Alarm Rate</span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">FPR</span>
            </div>
            <span className="text-[38px] font-bold text-[#7C3AED] leading-none">7%</span>
            <div className="w-full bg-[var(--bg)] rounded-full h-1.5">
              <div className="h-1.5 rounded-full bg-[#7C3AED]" style={{ width: "7%" }} />
            </div>
            <p className="text-xs text-[var(--ink-2)] leading-relaxed">
              Naturally <strong>correct claims</strong> wrongly flagged as inconsistent. Low FPR means the engine rarely raises false red flags on accurate disclosures.
            </p>
          </div>

        </div>
      </div>

      {/* ── Charts Row: Category Bar + DuckDB Stats ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Category bar chart - live from DuckDB */}
        <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col">
          <div className="flex items-center justify-between pb-4 mb-4 border-b border-[var(--border)]">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-[var(--primary)]" />
              <h3 className="text-sm font-bold text-[var(--ink)]">XBRL Facts by Category</h3>
            </div>
            <span className="text-xs text-[var(--ink-3)] font-medium">Live from DuckDB</span>
          </div>
          <div className="flex flex-col gap-3 flex-1">
            {categories.map((c) => (
              <div key={c.category}
                className="flex items-center gap-3 group cursor-default"
                onMouseEnter={() => setHoveredBar(c.category)}
                onMouseLeave={() => setHoveredBar(null)}>
                <span className="w-20 text-xs font-semibold text-[var(--ink-2)] text-right shrink-0">{c.category}</span>
                <div className="flex-1 bg-[var(--bg)] rounded-full h-5 relative overflow-hidden">
                  <div
                    className="h-5 rounded-full transition-all duration-500"
                    style={{
                      width: `${(c.count / maxCount) * 100}%`,
                      backgroundColor: CAT_COLORS[c.category] || "#6366F1"
                    }}
                  />
                  {hoveredBar === c.category && (
                    <span className="absolute right-2 top-0 h-5 flex items-center text-[10px] font-bold text-[var(--ink)]">{c.count} facts</span>
                  )}
                </div>
                <span className="w-10 text-xs font-bold text-[var(--ink)] tabular-nums">{c.count}</span>
              </div>
            ))}
          </div>
          {stats && (
            <div className="mt-4 pt-4 border-t border-[var(--border)] flex justify-between text-xs text-[var(--ink-3)]">
              <span>Total: <strong className="text-[var(--ink)]">{stats.total_facts.toLocaleString()} facts</strong></span>
              <span>Filings: <strong className="text-[var(--ink)]">{stats.filings.length}</strong></span>
            </div>
          )}
        </div>

        {/* Verification Ablations Chart */}
        <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col">
          <div className="flex items-center justify-between pb-4 mb-4 border-b border-[var(--border)]">
            <div className="flex items-center gap-2">
              <PieChart className="w-4 h-4 text-[var(--primary)]" />
              <h3 className="text-sm font-bold text-[var(--ink)]">Ablation Study Results</h3>
            </div>
            <span className="text-xs text-[var(--ink-3)] font-medium">Table III – Paper</span>
          </div>
          <div className="flex flex-col gap-3 flex-1">
            {[
              { name: "Full System (VeriBRSR)", f1: 0.82, color: "#4F46E5" },
              { name: "Without deterministic calc", f1: 0.70, color: "#7C3AED" },
              { name: "Without unit normalisation", f1: 0.73, color: "#0EA5E9" },
              { name: "Without period filtering", f1: 0.77, color: "#D97706" },
              { name: "Without boundary filtering", f1: 0.78, color: "#DC2626" },
            ].map((r) => (
              <div key={r.name} className="flex items-center gap-3">
                <span className="w-44 text-xs font-medium text-[var(--ink-2)] shrink-0 truncate">{r.name}</span>
                <div className="flex-1 bg-[var(--bg)] rounded-full h-5 relative overflow-hidden">
                  <div className="h-5 rounded-full transition-all duration-500" style={{ width: `${r.f1 * 100}%`, backgroundColor: r.color }} />
                </div>
                <span className="w-10 text-xs font-bold tabular-nums" style={{ color: r.color }}>{(r.f1 * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-[var(--ink-3)] mt-4 pt-4 border-t border-[var(--border)]">
            Without deterministic arithmetic, F1 drops from 82% → 70% — proving rule-based verification is critical.
          </p>
        </div>
      </div>

      {/* ── Company / XBRL Fact Explorer ── */}
      <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border border-[var(--border)] shadow-[var(--shadow-card)]">
        <div className="flex items-center gap-2 pb-4 mb-6 border-b border-[var(--border)]">
          <Database className="w-4 h-4 text-[var(--primary)]" />
          <h3 className="text-base font-bold text-[var(--ink)]">XBRL Fact Explorer</h3>
          <span className="text-xs text-[var(--ink-3)] font-medium ml-auto">Query DuckDB directly</span>
        </div>

        {/* Search Controls */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--ink-3)]" />
            <input
              className="w-full pl-9 pr-3 py-2.5 rounded-lg border border-[var(--border)] bg-[var(--bg)] text-sm text-[var(--ink)] placeholder:text-[var(--ink-3)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
              placeholder="Company / filing ID..."
              value={company}
              onChange={e => setCompany(e.target.value)}
              onKeyDown={e => e.key === "Enter" && fetchData()}
            />
          </div>
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--ink-3)]" />
            <input
              className="w-full pl-9 pr-3 py-2.5 rounded-lg border border-[var(--border)] bg-[var(--bg)] text-sm text-[var(--ink)] placeholder:text-[var(--ink-3)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
              placeholder="Search metric (e.g. 'water', 'scope 1')..."
              value={textQuery}
              onChange={e => setTextQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && fetchData()}
            />
          </div>
          <select
            className="px-3 py-2.5 rounded-lg border border-[var(--border)] bg-[var(--bg)] text-sm text-[var(--ink)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
            value={category}
            onChange={e => setCategory(e.target.value)}>
            <option value="">All Categories</option>
            {Object.keys(CAT_COLORS).map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <select
            className="px-3 py-2.5 rounded-lg border border-[var(--border)] bg-[var(--bg)] text-sm text-[var(--ink)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
            value={period}
            onChange={e => setPeriod(e.target.value)}>
            <option value="">All Periods</option>
            {(stats?.periods || []).map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>

        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => fetchData()}
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[var(--primary)] text-white text-sm font-semibold hover:opacity-90 disabled:opacity-50 transition-all">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            Search DuckDB
          </button>
          {queried && (
            <button onClick={() => { setCompany(""); setTextQuery(""); setCategory(""); setPeriod(""); setResults([]); setQueried(false); }}
              className="flex items-center gap-1 px-3 py-2.5 rounded-lg border border-[var(--border)] text-sm text-[var(--ink-2)] hover:text-[var(--ink)] transition">
              <X className="w-3.5 h-3.5" /> Clear
            </button>
          )}
          {queried && <span className="text-sm text-[var(--ink-3)]">{results.length} results</span>}
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>
        )}

        {/* Results Table */}
        {queried && results.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-[var(--border)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[var(--bg)] border-b border-[var(--border)]">
                  <th className="text-left px-4 py-3 text-xs font-bold text-[var(--ink-3)] uppercase tracking-wider">Metric</th>
                  <th className="text-left px-4 py-3 text-xs font-bold text-[var(--ink-3)] uppercase tracking-wider">Category</th>
                  <th className="text-left px-4 py-3 text-xs font-bold text-[var(--ink-3)] uppercase tracking-wider">Period</th>
                  <th className="text-right px-4 py-3 text-xs font-bold text-[var(--ink-3)] uppercase tracking-wider">Value</th>
                  <th className="text-left px-4 py-3 text-xs font-bold text-[var(--ink-3)] uppercase tracking-wider">Unit</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} className={`border-b border-[var(--border)] hover:bg-[var(--bg)] transition-colors ${i % 2 === 0 ? "" : "bg-[var(--bg)]/40"}`}>
                    <td className="px-4 py-3 text-[var(--ink)] font-medium max-w-xs truncate" title={r.canonical_name}>
                      {r.canonical_name}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-semibold text-white" style={{ backgroundColor: CAT_COLORS[r.category] || "#6366F1" }}>
                        {r.category}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[var(--ink-2)] text-xs">{r.period}</td>
                    <td className="px-4 py-3 text-right font-mono font-bold text-[var(--ink)]">
                      {typeof r.value === "number" ? r.value.toLocaleString(undefined, { maximumFractionDigits: 4 }) : r.value}
                    </td>
                    <td className="px-4 py-3 text-[var(--ink-3)] text-xs font-medium">{r.unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {queried && results.length === 0 && !loading && (
          <div className="text-center py-12 text-[var(--ink-3)]">
            <Database className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="font-medium">No facts found matching your query.</p>
            <p className="text-sm mt-1">Try a different company name or metric keyword.</p>
          </div>
        )}
        {!queried && (
          <div className="text-center py-10 text-[var(--ink-3)]">
            <Database className="w-10 h-10 mx-auto mb-3 opacity-20" />
            <p className="font-medium text-sm">Enter a company name or metric to search DuckDB</p>
            <p className="text-xs mt-1">Try: company = "infosys", metric = "water" or "scope 1"</p>
          </div>
        )}
      </div>

    </div>
  );
}
