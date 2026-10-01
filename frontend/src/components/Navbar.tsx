"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Navbar() {
  const pathname = usePathname();

  const navLinks = [
    { label: "Dashboard", href: "/" },
    { label: "Inventory", href: "/inventory" },
    { label: "Workspace", href: "/filing/infosys-2022" },
    { label: "Analytics", href: "/analytics" },
    { label: "Settings", href: "/settings" },
  ];

  const isLinkActive = (href: string) => {
    if (href === "/") {
      return pathname === "/";
    }
    if (href.startsWith("/filing")) {
      return pathname.startsWith("/filing");
    }
    return pathname.startsWith(href);
  };

  return (
    <nav className="sticky top-0 z-50 w-full bg-[var(--surface)] border-b border-[var(--border)] shadow-[0_1px_3px_rgba(15,23,42,0.05)]">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="w-8 h-8 rounded-[8px] bg-[var(--primary)] flex items-center justify-center font-bold text-white shadow-sm text-sm group-hover:bg-[var(--primary-hover)] transition-colors">
              V
            </div>
            <span className="font-bold text-xl tracking-tight text-[var(--ink)]">
              VeriBRSR
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-1.5 text-sm font-medium">
            {navLinks.map((link) => {
              const active = isLinkActive(link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`px-3 py-1.5 rounded-[8px] transition-colors ${
                    active
                      ? "text-[var(--primary)] bg-[var(--primary-soft)] font-semibold"
                      : "text-[var(--ink-2)] hover:bg-[#F1F5F9] hover:text-[var(--ink)]"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-xs text-[var(--success)] bg-[var(--success-soft)] px-3 py-1.5 rounded-full border border-[var(--success-border)] flex items-center gap-2 font-semibold">
            <span className="w-2 h-2 rounded-full bg-[var(--success)] animate-pulse-slow"></span>
            System Online
          </div>
          <button
            aria-label="User Account"
            className="w-9 h-9 rounded-full bg-[var(--surface)] border border-[var(--border)] flex items-center justify-center text-[var(--ink-2)] hover:text-[var(--ink)] hover:bg-[#F1F5F9] transition-colors focus-visible:ring-3 focus-visible:ring-[rgba(79,70,229,0.25)] outline-none"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
              <circle cx="12" cy="7" r="4"></circle>
            </svg>
          </button>
        </div>
      </div>
    </nav>
  );
}
