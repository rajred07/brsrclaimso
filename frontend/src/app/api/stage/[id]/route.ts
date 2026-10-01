import { NextResponse } from "next/server";
import path from "path";
import fs from "fs";
import { execFile } from "child_process";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const backendPath = path.resolve(process.cwd(), "..", "backend");

    // 1. Resolve Filing Metadata
    let company = "Infosys Ltd.";
    let symbol = "INFY";
    let fy = "2025-26";
    let sector = "IT Services";
    let status = "READY";
    let pdfFileName = "";
    let xbrlFileName = "";
    let xmlFullPath = "";
    let pdfFullPath = "";

    if (id === "infosys-2022") {
      company = "Infosys Ltd.";
      symbol = "INFY";
      fy = "2021-22";
      sector = "IT Services";
      status = "PROCESSED";
      pdfFileName = "infosys-esg-report-2021-22.pdf";
      xbrlFileName = "infosys_brsr_2022.xml";
      xmlFullPath = path.join(backendPath, "data", "raw", "infosys_brsr_2022.xml");
      pdfFullPath = path.join(backendPath, "data", "raw", "infosys-esg-report-2021-22.pdf");
    }

    const filingsJsonPath = path.join(backendPath, "data", "filings.json");
    if (fs.existsSync(filingsJsonPath)) {
      try {
        const filings = JSON.parse(fs.readFileSync(filingsJsonPath, "utf-8"));
        const f = filings.find((x: any) => x.id === id);
        if (f) {
          company = f.company || company;
          symbol = f.symbol || symbol;
          fy = f.fy || fy;
          sector = f.sector || sector;
          status = f.status || status;
        }
      } catch (e) {
        console.error("Error reading filings.json:", e);
      }
    }

    // Check filing-specific directory in backend/data/filings/[id]
    const filingDir = path.join(backendPath, "data", "filings", id);
    if (fs.existsSync(filingDir)) {
      const files = fs.readdirSync(filingDir);
      const xmlFile = files.find(f => f.toLowerCase().endsWith(".xml"));
      if (xmlFile) {
        xbrlFileName = xmlFile;
        xmlFullPath = path.join(filingDir, xmlFile);
      }
      const pdfFile = files.find(f => f.toLowerCase().endsWith(".pdf"));
      if (pdfFile) {
        pdfFileName = pdfFile;
        pdfFullPath = path.join(filingDir, pdfFile);
      }
    }

    // 2. Read real XML preview from THIS filing's XML file
    let xmlContent = "";
    if (xmlFullPath && fs.existsSync(xmlFullPath)) {
      try {
        const fullXml = fs.readFileSync(xmlFullPath, "utf-8");
        const lines = fullXml.split("\n");
        const factLines = lines
          .filter(l => l.includes("in-bse-brsr:") || l.includes("in-capmkt:") || l.includes("context") || l.includes("unitRef") || l.includes("<context") || l.includes("</context"))
          .slice(0, 50);
        xmlContent = factLines.join("\n") || fullXml.slice(0, 2500);
      } catch (e) {
        console.error("Error reading XML file:", e);
      }
    }

    // 3. Resolve DuckDB Facts
    interface StageFact {
      canonical_name: string;
      period: string;
      value: number | string;
      unit: string;
    }

    let duckdbFacts: StageFact[] = [];
    let xbrlProcessed = false;

    if (id === "infosys-2022") {
      // Demonstration filing: pre-processed
      const parsedDuckDbPath = path.join(backendPath, "data", "parsed", "brsr_facts.duckdb");
      if (fs.existsSync(parsedDuckDbPath)) {
        let pythonExe = path.join(backendPath, ".venv", "Scripts", "python.exe");
        if (!fs.existsSync(pythonExe)) pythonExe = "python";

        const pyDuckDbScript = `
import duckdb, json, os
db_path = r"${parsedDuckDbPath.replace(/\\/g, '/')}"
if os.path.exists(db_path):
    con = duckdb.connect(db_path, read_only=True)
    df = con.execute("SELECT canonical_name, period, value, unit FROM normalized_facts ORDER BY canonical_name, period DESC").df()
    print("DUCKDB_START")
    print(df.to_json(orient='records'))
    con.close()
else:
    print("DUCKDB_START[]")
`;
        duckdbFacts = await new Promise<StageFact[]>((resolve) => {
          execFile(pythonExe, ["-c", pyDuckDbScript], { cwd: backendPath }, (err, stdout) => {
            if (!err && stdout.includes("DUCKDB_START")) {
              try {
                const rawJson = stdout.split("DUCKDB_START")[1].trim();
                return resolve(JSON.parse(rawJson));
              } catch (e) {}
            }
            resolve([]);
          });
        });
        xbrlProcessed = duckdbFacts.length > 0;
      }
    } else {
      // For any newly uploaded filing: only check facts.json if an XML file actually exists!
      const hasActualXml = Boolean(xmlFullPath && fs.existsSync(xmlFullPath));
      if (hasActualXml) {
        const factsJsonPath = path.join(filingDir, "facts.json");
        if (fs.existsSync(factsJsonPath)) {
          try {
            duckdbFacts = JSON.parse(fs.readFileSync(factsJsonPath, "utf-8"));
            xbrlProcessed = duckdbFacts.length > 0;
          } catch (e) {
            duckdbFacts = [];
          }
        }
      } else {
        duckdbFacts = [];
        xbrlProcessed = false;
      }
    }

    // 4. Resolve Extracted Claims
    interface StageClaim {
      metric: string;
      operation: string;
      stated_result?: number | string;
      asserted_value?: number;
      unit: string;
      original_quote?: string;
      period_current?: string;
    }

    let extractedClaims: StageClaim[] = [];
    let pdfProcessed = false;

    if (id === "infosys-2022") {
      // Demonstration filing: pre-processed claims
      extractedClaims = [
        { metric: "energy_consumption", operation: "value_equality", stated_result: "650476.0", unit: "GJ", original_quote: "our total energy consumption was 650,476 GJ", current_period: "FY22" },
        { metric: "energy_consumption", operation: "percentage_change", stated_result: "3.15", unit: "%", original_quote: "representing a 3.15% reduction compared to 671,660 GJ in Fiscal 2021", current_period: "FY22" },
        { metric: "energy_consumption", operation: "value_equality", stated_result: "671660.0", unit: "GJ", original_quote: "671,660 GJ in Fiscal 2021", current_period: "FY21" },
        { metric: "renewable_energy_consumption", operation: "value_equality", stated_result: "266119.0", unit: "GJ", original_quote: "Our renewable energy consumption accounted for 266,119 GJ", current_period: "FY22" },
        { metric: "scope1_emissions", operation: "value_equality", stated_result: "8965.0", unit: "tCO2e", original_quote: "Our Scope 1 direct greenhouse gas emissions were 8,965 tCO2e", current_period: "FY22" },
        { metric: "scope2_emissions", operation: "value_equality", stated_result: "51717.0", unit: "tCO2e", original_quote: "Scope 2 emissions stood at 51,717 tCO2e", current_period: "FY22" },
        { metric: "water_withdrawal", operation: "percentage_change", stated_result: "25.0", unit: "%", original_quote: "a 25% reduction in municipal water withdrawal", current_period: "FY22" }
      ];
      pdfProcessed = true;
    } else {
      // For newly uploaded filing: check if claims.json exists in its filingDir
      let filingClaimsPath = path.join(filingDir, "claims.json");
      if (!fs.existsSync(filingClaimsPath)) {
        filingClaimsPath = path.join(filingDir, "extracted_claims.json");
      }
      
      if (fs.existsSync(filingClaimsPath)) {
        try {
          const rawClaims = JSON.parse(fs.readFileSync(filingClaimsPath, "utf-8"));
          extractedClaims = Array.isArray(rawClaims) ? rawClaims : (rawClaims.claims || []);
          pdfProcessed = extractedClaims.length > 0;
        } catch (e) {
          extractedClaims = [];
        }
      }
    }

    return NextResponse.json({
      filingId: id,
      filing: {
        id,
        company,
        symbol,
        fy,
        sector,
        status,
        pdfFileName,
        xbrlFileName,
        hasPdf: Boolean(pdfFullPath && fs.existsSync(pdfFullPath)),
        hasXbrl: Boolean(xmlFullPath && fs.existsSync(xmlFullPath))
      },
      xmlContent,
      duckdbFacts,
      extractedClaims,
      xbrlProcessed,
      pdfProcessed,
      readyForVerification: xbrlProcessed && pdfProcessed
    });
  } catch (err) {
    console.error("api/stage error:", err);
    return NextResponse.json({ error: "Failed to load staging data" }, { status: 500 });
  }
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const backendPath = path.resolve(process.cwd(), "..", "backend");
    const filingDir = path.join(backendPath, "data", "filings", id);

    const contentType = request.headers.get("content-type") || "";
    if (contentType.includes("multipart/form-data")) {
      const formData = await request.formData();
      const xbrlFile = formData.get("xbrlFile") as File | null;
      if (xbrlFile && xbrlFile.size > 0) {
        if (!fs.existsSync(filingDir)) {
          fs.mkdirSync(filingDir, { recursive: true });
        }
        const xbrlFilename = `brsr_${xbrlFile.name.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
        const targetPath = path.join(filingDir, xbrlFilename);
        const buffer = Buffer.from(await xbrlFile.arrayBuffer());
        fs.writeFileSync(targetPath, buffer);

        // Update filings.json
        const filingsJsonPath = path.join(backendPath, "data", "filings.json");
        if (fs.existsSync(filingsJsonPath)) {
          try {
            const filings = JSON.parse(fs.readFileSync(filingsJsonPath, "utf-8"));
            const f = filings.find((x: any) => x.id === id);
            if (f) {
              f.xbrl = true;
              fs.writeFileSync(filingsJsonPath, JSON.stringify(filings, null, 2));
            }
          } catch (e) {}
        }

        return NextResponse.json({
          success: true,
          message: "XBRL XML file uploaded and attached successfully.",
          filename: xbrlFilename
        });
      }
      return NextResponse.json({ error: "No XML file provided" }, { status: 400 });
    }

    const body = await request.json();
    const action = body.action;

    let pythonExe = path.join(backendPath, ".venv", "Scripts", "python.exe");
    if (!fs.existsSync(pythonExe)) pythonExe = "python";

    if (action === "process_xbrl") {
      // Find the XML file in filing directory or fallback
      let xmlFullPath = "";
      if (fs.existsSync(filingDir)) {
        const files = fs.readdirSync(filingDir);
        const xmlFile = files.find(f => f.toLowerCase().endsWith(".xml"));
        if (xmlFile) xmlFullPath = path.join(filingDir, xmlFile);
      }
      if (!xmlFullPath && id === "infosys-2022") {
        xmlFullPath = path.join(backendPath, "data", "raw", "infosys_brsr_2022.xml");
      }

      if (!xmlFullPath || !fs.existsSync(xmlFullPath)) {
        return NextResponse.json({ error: "No XBRL XML file uploaded for this filing" }, { status: 400 });
      }

      const scriptPath = path.join(backendPath, "src", "xbrl_pipeline.py");
      const duckdbPath = path.join(backendPath, "data", "parsed", "brsr_facts.duckdb");
      const factsJsonOut = path.join(filingDir, "facts.json");

      return new Promise<Response>((resolve) => {
        execFile(pythonExe, [scriptPath, xmlFullPath, id, factsJsonOut, duckdbPath], { cwd: backendPath }, (err, stdout, stderr) => {
          if (err) {
            console.error("XBRL processing error:", stderr, stdout);
            return resolve(NextResponse.json({ error: "Failed to process XBRL" }, { status: 500 }));
          }

          let facts = [];
          if (fs.existsSync(factsJsonOut)) {
            try {
              facts = JSON.parse(fs.readFileSync(factsJsonOut, "utf-8"));
            } catch (e) {}
          }

          return resolve(NextResponse.json({
            success: true,
            factsCount: facts.length,
            facts
          }));
        });
      });
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 });
  } catch (err) {
    console.error("api/stage POST error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
