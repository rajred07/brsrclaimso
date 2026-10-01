import { NextResponse } from "next/server";
import path from "path";
import fs from "fs";
import os from "os";
import { execSync } from "child_process";

const PYTHON = path.resolve(process.cwd(), "..", "backend", ".venv", "Scripts", "python.exe");
const DB_PATH = path.resolve(process.cwd(), "..", "backend", "data", "veribrsr.duckdb");

function runPython(script: string): string {
  const tmpFile = path.join(os.tmpdir(), `vb_query_${Date.now()}.py`);
  fs.writeFileSync(tmpFile, script, "utf-8");
  try {
    const out = execSync(`"${PYTHON}" "${tmpFile}"`, { timeout: 15000, encoding: "utf-8" });
    return out;
  } finally {
    try { fs.unlinkSync(tmpFile); } catch {}
  }
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const company  = (searchParams.get("company")  || "").trim();
  const textQ    = (searchParams.get("q")         || "").trim();
  const category = (searchParams.get("category")  || "").trim();
  const period   = (searchParams.get("period")    || "").trim();

  const dbPath = DB_PATH.replace(/\\/g, "\\\\");

  const script = `
import duckdb, json, sys

conn = duckdb.connect(r"${dbPath}", read_only=True)

conditions = []
params = []

company_q  = ${JSON.stringify(company)}
text_q     = ${JSON.stringify(textQ)}
cat_q      = ${JSON.stringify(category)}
period_q   = ${JSON.stringify(period)}

if company_q:
    conditions.append("LOWER(filing_id) LIKE LOWER(?)")
    params.append(f"%{company_q}%")
if text_q:
    conditions.append("(LOWER(canonical_name) LIKE LOWER(?) OR LOWER(source_concept) LIKE LOWER(?))")
    params.append(f"%{text_q}%")
    params.append(f"%{text_q}%")
if cat_q:
    conditions.append("LOWER(category) = LOWER(?)")
    params.append(cat_q)
if period_q:
    conditions.append("LOWER(period) LIKE LOWER(?)")
    params.append(f"%{period_q}%")

where = "WHERE " + " AND ".join(conditions) if conditions else ""
sql = f"""
  SELECT filing_id, canonical_name, category, period, value, unit, dimensions
  FROM normalized_facts {where}
  ORDER BY category, period, canonical_name
  LIMIT 200
"""

rows = conn.execute(sql, params).fetchall()
results = [
    {
        "filing_id": r[0], "canonical_name": r[1],
        "category": r[2], "period": r[3],
        "value": r[4], "unit": r[5], "dimensions": r[6]
    }
    for r in rows
]

# Stats
by_cat   = conn.execute("SELECT category, COUNT(*) FROM normalized_facts GROUP BY category ORDER BY 2 DESC").fetchall()
total    = conn.execute("SELECT COUNT(*) FROM normalized_facts").fetchone()[0]
filings  = [r[0] for r in conn.execute("SELECT DISTINCT filing_id FROM normalized_facts").fetchall()]
periods  = [r[0] for r in conn.execute("SELECT DISTINCT period FROM normalized_facts ORDER BY period").fetchall()]

stats = {
    "by_category": [{"category": r[0], "count": r[1]} for r in by_cat],
    "total_facts": total,
    "filings": filings,
    "periods": periods
}

print(json.dumps({"results": results, "stats": stats, "count": len(results)}))
`;

  try {
    const raw = runPython(script);
    // Extract only the JSON line (ignore warnings like AFC warnings)
    const jsonLine = raw.split("\n").filter(l => l.trim().startsWith("{")).pop() || "{}";
    const data = JSON.parse(jsonLine);
    return NextResponse.json(data);
  } catch (err: any) {
    console.error("Facts API error:", err.message);
    return NextResponse.json({ error: err.message || "Query failed" }, { status: 500 });
  }
}
