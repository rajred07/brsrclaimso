import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const text = body.text;

    if (!text || typeof text !== "string") {
      return NextResponse.json({ error: "No text provided" }, { status: 400 });
    }

    const backendPath = path.resolve(process.cwd(), "..", "backend");
    
    // Determine python executable path
    let pythonExe = path.join(backendPath, ".venv", "Scripts", "python.exe");
    if (!fs.existsSync(pythonExe)) {
      pythonExe = path.join(backendPath, ".venv", "bin", "python");
    }
    if (!fs.existsSync(pythonExe)) {
      pythonExe = "python";
    }

    const scriptPath = path.join(backendPath, "verify_custom_text.py");
    const tempInputPath = path.join(backendPath, "data", "claims", "temp_input.txt");

    // Write text to a temporary file to avoid shell escaping issues with quotes/newlines
    fs.mkdirSync(path.dirname(tempInputPath), { recursive: true });
    fs.writeFileSync(tempInputPath, text, "utf-8");

    return new Promise<Response>((resolve) => {
      const pyProcess = spawn(pythonExe, [scriptPath, "--file", tempInputPath], {
        cwd: backendPath,
      });

      let stdout = "";
      let stderr = "";

      pyProcess.stdout.on("data", (data) => {
        stdout += data.toString();
      });

      pyProcess.stderr.on("data", (data) => {
        stderr += data.toString();
      });

      pyProcess.on("close", (code) => {
        const resultPath = path.join(backendPath, "data", "claims", "custom_verified_claims.json");
        if (fs.existsSync(resultPath)) {
          const content = fs.readFileSync(resultPath, "utf-8");
          try {
            const parsed = JSON.parse(content);
            resolve(NextResponse.json({ success: true, claims: parsed, stdout }));
            return;
          } catch (e) {
            console.error(e);
          }
        }

        if (code !== 0) {
          resolve(NextResponse.json({ error: "Verification failed", stderr, stdout }, { status: 500 }));
        } else {
          resolve(NextResponse.json({ success: true, claims: [], stdout }));
        }
      });
    });
  } catch (error) {
    console.error("verify-text API error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
