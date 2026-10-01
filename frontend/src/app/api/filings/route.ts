import { NextResponse } from "next/server";
import { execFile } from "child_process";
import path from "path";
import fs from "fs";

export async function GET() {
  try {
    const backendPath = path.resolve(process.cwd(), "..", "backend");
    const filingsJsonPath = path.join(backendPath, "data", "filings.json");

    // Fast-path: read directly from synced filings.json
    if (fs.existsSync(filingsJsonPath)) {
      try {
        const fileContent = fs.readFileSync(filingsJsonPath, "utf-8");
        const filings = JSON.parse(fileContent);
        if (Array.isArray(filings)) {
          return NextResponse.json(filings);
        }
      } catch (readErr) {
        console.warn("filings.json read warning, falling back to python:", readErr);
      }
    }
    
    let pythonExe = path.join(backendPath, ".venv", "Scripts", "python.exe");
    if (!fs.existsSync(pythonExe)) {
      pythonExe = path.join(backendPath, ".venv", "bin", "python");
    }
    if (!fs.existsSync(pythonExe)) {
      pythonExe = "python";
    }

    const scriptPath = path.join(backendPath, "src", "db.py");

    return new Promise<Response>((resolve) => {
      execFile(pythonExe, [scriptPath, "--list"], { cwd: backendPath }, (err, stdout, stderr) => {
        if (err) {
          console.error("db list error:", stderr);
          return resolve(NextResponse.json({ error: "Failed to list filings" }, { status: 500 }));
        }

        try {
          // Extract JSON array matching [{ ... }]
          const jsonMatch = stdout.match(/\[\s*\{[\s\S]*\}\s*\]/);
          if (jsonMatch) {
            const filings = JSON.parse(jsonMatch[0]);
            return resolve(NextResponse.json(filings));
          } else if (stdout.trim().startsWith("[")) {
            const filings = JSON.parse(stdout.trim());
            return resolve(NextResponse.json(filings));
          }
          return resolve(NextResponse.json([]));
        } catch (parseErr) {
          console.error("JSON parse error:", parseErr, stdout);
          return resolve(NextResponse.json({ error: "Invalid JSON from db" }, { status: 500 }));
        }
      });
    });
  } catch (error) {
    console.error("api/filings error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
