"""
VeriBRSR SQLite Database Manager
================================
Manages filings metadata, document paths, and verified claims.
Database: backend/data/veribrsr.db
"""

import sqlite3
import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "veribrsr.db"


def get_connection():
    os.makedirs(DB_PATH.parent, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = get_connection()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS filings (
        id TEXT PRIMARY KEY,
        company_name TEXT NOT NULL,
        symbol TEXT NOT NULL,
        fy TEXT NOT NULL,
        sector TEXT NOT NULL,
        pdf_path TEXT,
        xbrl_path TEXT,
        status TEXT DEFAULT 'READY',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS claims (
        id TEXT PRIMARY KEY,
        filing_id TEXT NOT NULL,
        metric TEXT NOT NULL,
        original_quote TEXT NOT NULL,
        stated_result TEXT,
        unit TEXT,
        ground_truth_current TEXT,
        ground_truth_prior TEXT,
        verdict TEXT NOT NULL,
        math_trace TEXT,
        reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(filing_id) REFERENCES filings(id) ON DELETE CASCADE
    );
    """)

    con.commit()

    # Pre-seed initial default records if table is empty
    count = cur.execute("SELECT COUNT(*) FROM filings").fetchone()[0]
    if count == 0:
        seed_data(con)

    con.close()
    sync_filings_json()


def seed_data(con):
    cur = con.cursor()
    # Delete any existing records to keep ONLY real data
    cur.execute("DELETE FROM claims;")
    cur.execute("DELETE FROM filings;")

    # ONLY Infosys 2021-22 (Real Data)
    cur.execute("""
    INSERT INTO filings (id, company_name, symbol, fy, sector, pdf_path, xbrl_path, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        "infosys-2022",
        "Infosys Ltd.",
        "INFY",
        "2021-22",
        "IT Services",
        "data/raw/infosys-esg-report-2021-22.pdf",
        "data/raw/infosys_brsr_2022.xml",
        "PROCESSED"
    ))

    # Insert verified claims for infosys-2022 from custom_verified_claims.json if exists
    custom_claims_path = Path(__file__).resolve().parent.parent / "data" / "claims" / "custom_verified_claims.json"
    if custom_claims_path.exists():
        with open(custom_claims_path, "r", encoding="utf-8") as f:
            verified_claims = json.load(f)
            for i, c in enumerate(verified_claims):
                cur.execute("""
                INSERT INTO claims (id, filing_id, metric, original_quote, stated_result, unit, ground_truth_current, ground_truth_prior, verdict, math_trace, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    f"c22_{i}",
                    "infosys-2022",
                    c.get("metric", ""),
                    c.get("original_quote", ""),
                    str(c.get("stated_result", "")),
                    c.get("unit", ""),
                    c.get("ground_truth_current", ""),
                    c.get("ground_truth_prior", ""),
                    c.get("verdict", "SUPPORTED"),
                    c.get("math_trace", ""),
                    c.get("reason", "")
                ))

    con.commit()


def sync_filings_json():
    try:
        filings = get_filings()
        json_path = DB_PATH.parent / "filings.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(filings, f, indent=2)
    except Exception as e:
        sys.stderr.write(f"Error syncing filings.json: {e}\n")


def add_filing(filing_id: str, company: str, symbol: str, fy: str, sector: str, pdf_path: str, xbrl_path: str) -> Dict[str, Any]:
    con = get_connection()
    cur = con.cursor()
    cur.execute("""
    INSERT OR REPLACE INTO filings (id, company_name, symbol, fy, sector, pdf_path, xbrl_path, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'READY');
    """, (filing_id, company, symbol, fy, sector, pdf_path, xbrl_path))
    con.commit()
    con.close()
    sync_filings_json()
    return {"id": filing_id, "status": "READY"}


def get_filings() -> List[Dict[str, Any]]:
    con = get_connection()
    cur = con.cursor()
    rows = cur.execute("""
    SELECT 
        f.id, f.company_name, f.symbol, f.fy, f.sector, f.pdf_path, f.xbrl_path, f.status, f.created_at,
        COUNT(c.id) as total_claims,
        SUM(CASE WHEN c.verdict = 'SUPPORTED' THEN 1 ELSE 0 END) as supported_count,
        SUM(CASE WHEN c.verdict = 'INCONSISTENT' THEN 1 ELSE 0 END) as inconsistent_count,
        SUM(CASE WHEN c.verdict = 'INSUFFICIENT_EVIDENCE' THEN 1 ELSE 0 END) as abstain_count
    FROM filings f
    LEFT JOIN claims c ON f.id = c.filing_id
    GROUP BY f.id
    ORDER BY f.created_at DESC;
    """).fetchall()

    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "company": r["company_name"],
            "symbol": r["symbol"],
            "fy": r["fy"],
            "sector": r["sector"],
            "pdf": bool(r["pdf_path"] and os.path.exists(Path(__file__).resolve().parent.parent / r["pdf_path"])),
            "xbrl": bool(r["xbrl_path"] and os.path.exists(Path(__file__).resolve().parent.parent / r["xbrl_path"])),
            "status": r["status"],
            "created_at": r["created_at"],
            "total_claims": r["total_claims"] or 0,
            "supported_count": r["supported_count"] or 0,
            "inconsistent_count": r["inconsistent_count"] or 0,
            "abstain_count": r["abstain_count"] or 0,
        })
    con.close()
    return result


def get_filing(filing_id: str) -> Optional[Dict[str, Any]]:
    con = get_connection()
    cur = con.cursor()
    filing = cur.execute("SELECT * FROM filings WHERE id = ?", [filing_id]).fetchone()
    if not filing:
        con.close()
        return None

    claims_rows = cur.execute("SELECT * FROM claims WHERE filing_id = ?", [filing_id]).fetchall()
    claims = [dict(c) for c in claims_rows]
    con.close()

    return {
        "filing": dict(filing),
        "claims": claims
    }


def save_filing_claims(filing_id: str, claims: List[Dict[str, Any]]):
    con = get_connection()
    cur = con.cursor()
    # Delete old claims for this filing
    cur.execute("DELETE FROM claims WHERE filing_id = ?", [filing_id])
    for i, c in enumerate(claims):
        cur.execute("""
        INSERT INTO claims (id, filing_id, metric, original_quote, stated_result, unit, ground_truth_current, ground_truth_prior, verdict, math_trace, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            f"{filing_id}_{i}",
            filing_id,
            c.get("metric", ""),
            c.get("original_quote", ""),
            str(c.get("stated_result", "")),
            c.get("unit", ""),
            c.get("ground_truth_current", ""),
            c.get("ground_truth_prior", ""),
            c.get("verdict", "SUPPORTED"),
            c.get("math_trace", ""),
            c.get("reason", "")
        ))

    cur.execute("UPDATE filings SET status = 'PROCESSED' WHERE id = ?", [filing_id])
    con.commit()
    con.close()
    sync_filings_json()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        init_db()
    elif len(sys.argv) > 1 and sys.argv[1] == "--list":
        init_db()
        print(json.dumps(get_filings(), indent=2))
    elif len(sys.argv) > 2 and sys.argv[1] == "--get":
        init_db()
        print(json.dumps(get_filing(sys.argv[2]), indent=2))
    else:
        init_db()
