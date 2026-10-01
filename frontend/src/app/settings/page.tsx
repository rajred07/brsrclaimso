"use client";

import { useState } from "react";
import { 
  ShieldCheck, 
  Sliders, 
  Droplet, 
  Zap, 
  Cloud, 
  Trash2, 
  Users,
  Check
} from "lucide-react";

export default function SettingsPage() {
  const [domains, setDomains] = useState([
    { id: "water", label: "Water Usage & Intensity", checked: true, Icon: Droplet },
    { id: "energy", label: "Energy Consumption", checked: true, Icon: Zap },
    { id: "emissions", label: "Scope 1 & 2 Emissions", checked: true, Icon: Cloud },
    { id: "waste", label: "Waste Generation", checked: false, Icon: Trash2 },
    { id: "workforce", label: "Workforce Diversity", checked: false, Icon: Users },
  ]);

  const [tolerance, setTolerance] = useState(0.5);

  const toggleDomain = (id: string) => {
    setDomains(prev => prev.map(d => d.id === id ? { ...d, checked: !d.checked } : d));
  };

  return (
    <div className="flex flex-col w-full animate-fade-in">
      {/* Page Header Pattern */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pb-6 mb-8 border-b border-[var(--border)]">
        <div>
          <h1 className="text-[32px] font-bold text-[var(--ink)] leading-tight tracking-tight">
            Configuration Engine
          </h1>
          <p className="text-[16px] text-[var(--ink-2)] mt-1 font-normal">
            Adjust processing parameters, domains, and mathematical tolerances.
          </p>
        </div>
      </div>

      {/* Two Cards Side by Side (Equal Height, Stack on Mobile) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-stretch mb-8">
        {/* Card 1: Active Verification Domains */}
        <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col justify-between h-full">
          <div>
            <div className="flex items-center gap-2 pb-4 mb-6 border-b border-[var(--border)]">
              <ShieldCheck className="w-5 h-5 text-[var(--primary)]" />
              <h2 className="text-base font-bold text-[var(--ink)]">
                Active Verification Domains
              </h2>
            </div>
            
            <div className="flex flex-col gap-4">
              {domains.map(({ id, label, checked, Icon }) => (
                <label 
                  key={id} 
                  onClick={() => toggleDomain(id)}
                  className="flex items-center justify-between p-2.5 rounded-[var(--radius-control)] hover:bg-[#F8FAFC] cursor-pointer transition-colors group"
                >
                  <div className="flex items-center gap-3">
                    <Icon className={`w-4 h-4 transition-colors ${checked ? "text-[var(--primary)]" : "text-[var(--ink-3)]"}`} />
                    <span className={`text-sm font-semibold transition-colors ${checked ? "text-[var(--ink)]" : "text-[var(--ink-2)] group-hover:text-[var(--ink)]"}`}>
                      {label}
                    </span>
                  </div>

                  {/* Toggle Switch */}
                  <div 
                    role="switch"
                    aria-checked={checked}
                    className={`w-11 h-6 rounded-full transition-colors duration-150 ease-in-out relative shrink-0 ${checked ? "bg-[var(--primary)]" : "bg-[#CBD5E1]"}`}
                  >
                    <div 
                      className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow-sm transition-transform duration-150 ease-in-out ${checked ? "translate-x-6" : "translate-x-1"}`}
                    />
                  </div>
                </label>
              ))}
            </div>
          </div>

          <p className="text-[13px] text-[var(--ink-2)] mt-6 pt-4 border-t border-[var(--border)]">
            Only active domain rules are executed during cross-document extraction.
          </p>
        </div>

        {/* Card 2: System Tolerances */}
        <div className="bg-[var(--surface)] rounded-[var(--radius-card)] p-6 border border-[var(--border)] shadow-[var(--shadow-card)] flex flex-col justify-between h-full">
          <div>
            <div className="flex items-center gap-2 pb-4 mb-6 border-b border-[var(--border)]">
              <Sliders className="w-5 h-5 text-[var(--primary)]" />
              <h2 className="text-base font-bold text-[var(--ink)]">
                System Tolerances
              </h2>
            </div>
            
            <div className="flex flex-col gap-6">
              {/* Tolerance Slider */}
              <div className="flex flex-col gap-2">
                <div className="flex justify-between items-center">
                  <label className="text-sm font-semibold text-[var(--ink)]">
                    Math Deviation Margin
                  </label>
                  <span className="text-xs font-bold text-[var(--primary)] bg-[var(--primary-soft)] px-2.5 py-0.5 rounded-full border border-[var(--primary-soft)]">
                    ±{tolerance}%
                  </span>
                </div>
                <p className="text-[13px] text-[var(--ink-2)] leading-relaxed">
                  Allowed percentage point difference before flagging a claim as INCONSISTENT.
                </p>
                <div className="pt-2">
                  <input 
                    type="range" 
                    min="0" 
                    max="5" 
                    value={tolerance} 
                    onChange={(e) => setTolerance(parseFloat(e.target.value))}
                    step="0.1" 
                    className="w-full h-1.5 bg-[#E2E8F0] rounded-full appearance-none cursor-pointer accent-[var(--primary)]"
                  />
                </div>
              </div>

              {/* Abstention Threshold Select */}
              <div className="flex flex-col gap-2 pt-2">
                <div className="flex justify-between items-center">
                  <label className="text-sm font-semibold text-[var(--ink)]">
                    Abstention Threshold
                  </label>
                  <span className="text-xs font-bold text-[var(--primary)] bg-[var(--primary-soft)] px-2.5 py-0.5 rounded-full border border-[var(--primary-soft)]">
                    Low (Aggressive)
                  </span>
                </div>
                <p className="text-[13px] text-[var(--ink-2)] leading-relaxed">
                  Controls how aggressively the LLM maps prose claims to XBRL concepts before returning INSUFFICIENT_EVIDENCE.
                </p>
                <select className="h-11 px-3.5 bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-control)] text-sm text-[var(--ink)] font-medium focus:outline-none focus:border-[var(--primary)] focus:ring-3 focus:ring-[rgba(79,70,229,0.25)] transition-all cursor-pointer">
                  <option>Low (Favor Recall)</option>
                  <option>Medium (Balanced)</option>
                  <option>High (Favor Precision)</option>
                </select>
              </div>
            </div>
          </div>

          <p className="text-[13px] text-[var(--ink-2)] mt-6 pt-4 border-t border-[var(--border)]">
            Changes apply to newly triggered extraction jobs immediately.
          </p>
        </div>
      </div>

      {/* Save Button (Full width on mobile, aligned right on desktop, sticky bottom on mobile) */}
      <div className="sticky bottom-4 md:static z-20 flex justify-end bg-[var(--bg)] py-2 md:py-0">
        <button className="btn-primary w-full md:w-auto shadow-md">
          <Check className="w-4 h-4" />
          <span>Save Configuration</span>
        </button>
      </div>
    </div>
  );
}
