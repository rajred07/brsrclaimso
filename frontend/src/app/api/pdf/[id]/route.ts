import { NextResponse } from "next/server";
import path from "path";
import fs from "fs";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const backendPath = path.resolve(process.cwd(), "..", "backend");
    
    let targetPdfPath = "";

    // 1. Direct match in frontend/public
    const publicPdfPath = path.join(process.cwd(), "public", "infosys-esg-report-2021-22.pdf");
    if (id === "infosys-2022" && fs.existsSync(publicPdfPath)) {
      targetPdfPath = publicPdfPath;
    }

    // 2. Check filing-specific directory in backend/data/filings/[id]
    if (!targetPdfPath) {
      const filingDir = path.join(backendPath, "data", "filings", id);
      if (fs.existsSync(filingDir)) {
        const files = fs.readdirSync(filingDir);
        const pdfFile = files.find(f => f.toLowerCase().endsWith(".pdf"));
        if (pdfFile) {
          targetPdfPath = path.join(filingDir, pdfFile);
        }
      }
    }

    // 3. Fallback to backend/data/raw/infosys-esg-report-2021-22.pdf
    if (!targetPdfPath) {
      const rawPdfPath = path.join(backendPath, "data", "raw", "infosys-esg-report-2021-22.pdf");
      if (fs.existsSync(rawPdfPath)) {
        targetPdfPath = rawPdfPath;
      }
    }

    // 4. Fallback to root or uploaded.pdf
    if (!targetPdfPath) {
      const uploadedPdfPath = path.join(backendPath, "data", "raw", "uploaded.pdf");
      if (fs.existsSync(uploadedPdfPath)) {
        targetPdfPath = uploadedPdfPath;
      }
    }

    if (!targetPdfPath || !fs.existsSync(targetPdfPath)) {
      return NextResponse.json({ error: "PDF document not found" }, { status: 404 });
    }

    const fileBuffer = fs.readFileSync(targetPdfPath);

    return new Response(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `inline; filename="${path.basename(targetPdfPath)}"`,
        "Cache-Control": "public, max-age=3600",
      },
    });
  } catch (error) {
    console.error("api/pdf/[id] error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
