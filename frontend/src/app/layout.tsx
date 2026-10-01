import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Navbar from "@/components/Navbar";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "VeriBRSR | Automated Claim Verification",
  description: "Evidence-grounded verification of quantitative BRSR claims",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-[var(--bg)] text-[var(--ink)] font-sans">
        <Navbar />
        <main className="flex-1 flex flex-col w-full max-w-7xl mx-auto px-6 lg:px-8 py-8 animate-fade-in">
          {children}
        </main>
      </body>
    </html>
  );
}
