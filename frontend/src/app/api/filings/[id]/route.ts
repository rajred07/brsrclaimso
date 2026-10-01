import { NextResponse } from "next/server";
import { execFile } from "child_process";
import path from "path";
import fs from "fs";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const backendPath = path.resolve(process.cwd(), "..", "backend");
    
    let pythonExe = path.join(backendPath, ".venv", "Scripts", "python.exe");
    if (!fs.existsSync(pythonExe)) {
      pythonExe = path.join(backendPath, ".venv", "bin", "python");
    }
    if (!fs.existsSync(pythonExe)) {
      pythonExe = "python";
    }

    const scriptPath = path.join(backendPath, "src", "db.py");

    return new Promise<Response>((resolve) => {
      execFile(pythonExe, [scriptPath, "--get", id], { cwd: backendPath }, (err, stdout, stderr) => {
        if (err) {
          console.error("db get error:", stderr);
          return resolve(NextResponse.json({ error: "Failed to get filing" }, { status: 500 }));
        }

        try {
          const jsonMatch = stdout.match(/\{[\s\S]*\}/);
          if (jsonMatch) {
            const data = JSON.parse(jsonMatch[0]);
            return resolve(NextResponse.json(data));
          }
          return resolve(NextResponse.json({ error: "Filing not found" }, { status: 404 }));
        } catch (parseErr) {
          console.error("JSON parse error:", parseErr, stdout);
          return resolve(NextResponse.json({ error: "Invalid JSON from db" }, { status: 500 }));
        }
      });
    });
  } catch (error) {
    console.error("api/filings/[id] error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
