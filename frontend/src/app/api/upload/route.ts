import { NextResponse } from 'next/server';
import path from 'path';
import fs from 'fs';
import { spawn } from 'child_process';

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    
    const pdfFile = formData.get('pdfFile') as File | null;
    const xbrlFile = formData.get('xbrlFile') as File | null;
    const companyName = (formData.get('companyName') as string) || "Uploaded Entity";
    const symbol = (formData.get('symbol') as string) || "UPLOAD";
    const fy = (formData.get('fy') as string) || "2023-24";
    const sector = (formData.get('sector') as string) || "General";

    // Auto-generate a clean filing slug id
    const cleanCompany = companyName.toLowerCase().replace(/[^a-z0-9]/g, "-").replace(/-+/g, "-");
    const cleanFy = fy.toLowerCase().replace(/[^a-z0-9]/g, "");
    const filingId = `${cleanCompany}-${cleanFy}-${Date.now().toString().slice(-4)}`;

    const backendPath = path.resolve(process.cwd(), '../backend');
    const filingStorageDir = path.join(backendPath, 'data', 'filings', filingId);
    
    if (!fs.existsSync(filingStorageDir)) {
      fs.mkdirSync(filingStorageDir, { recursive: true });
    }

    let pdfRelativePath = "";
    let xbrlRelativePath = "";

    // Statically save PDF file without running pipeline
    if (pdfFile && pdfFile.size > 0) {
      const pdfBuffer = Buffer.from(await pdfFile.arrayBuffer());
      const pdfFilename = `report_${pdfFile.name.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
      const pdfFullPath = path.join(filingStorageDir, pdfFilename);
      fs.writeFileSync(pdfFullPath, pdfBuffer);
      pdfRelativePath = path.relative(backendPath, pdfFullPath).replace(/\\/g, '/');
    }

    // Statically save XBRL file without running pipeline
    if (xbrlFile && xbrlFile.size > 0) {
      const xbrlBuffer = Buffer.from(await xbrlFile.arrayBuffer());
      const xbrlFilename = `brsr_${xbrlFile.name.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
      const xbrlFullPath = path.join(filingStorageDir, xbrlFilename);
      fs.writeFileSync(xbrlFullPath, xbrlBuffer);
      xbrlRelativePath = path.relative(backendPath, xbrlFullPath).replace(/\\/g, '/');
    }

    // Also update legacy data/raw for backward compatibility
    if (pdfRelativePath) {
      const legacyRaw = path.join(backendPath, 'data', 'raw');
      fs.mkdirSync(legacyRaw, { recursive: true });
      fs.copyFileSync(path.join(backendPath, pdfRelativePath), path.join(legacyRaw, 'uploaded.pdf'));
    }
    if (xbrlRelativePath) {
      const legacyRaw = path.join(backendPath, 'data', 'raw');
      fs.mkdirSync(legacyRaw, { recursive: true });
      fs.copyFileSync(path.join(backendPath, xbrlRelativePath), path.join(legacyRaw, 'uploaded.xml'));
    }

    // Determine python executable path
    let pythonExe = path.join(backendPath, '.venv', 'Scripts', 'python.exe');
    if (!fs.existsSync(pythonExe)) {
      pythonExe = path.join(backendPath, '.venv', 'bin', 'python');
    }
    if (!fs.existsSync(pythonExe)) {
      pythonExe = 'python';
    }

    // Register filing in SQLite database via src/db.py
    const pyCode = `
import sys
from pathlib import Path
sys.path.append(r"${path.join(backendPath, 'src').replace(/\\/g, '/')}")
import db
db.init_db()
db.add_filing("${filingId}", "${companyName}", "${symbol}", "${fy}", "${sector}", "${pdfRelativePath}", "${xbrlRelativePath}")
print("REGISTERED")
`;

    return new Promise<Response>((resolve) => {
      const py = spawn(pythonExe, ['-c', pyCode], { cwd: backendPath });
      
      py.on('close', (code) => {
        if (code === 0) {
          resolve(NextResponse.json({
            success: true,
            filingId,
            status: "READY",
            message: "Filing statically stored in storage and registered in SQLite database. Pipeline was NOT triggered.",
            pdfPath: pdfRelativePath,
            xbrlPath: xbrlRelativePath
          }));
        } else {
          resolve(NextResponse.json({
            success: true,
            filingId,
            status: "SAVED_FILES_ONLY",
            message: "Files saved to disk, but db registration returned non-zero."
          }));
        }
      });
    });

  } catch (err) {
    console.error("Upload error:", err);
    return NextResponse.json({ error: 'Upload failed' }, { status: 500 });
  }
}
