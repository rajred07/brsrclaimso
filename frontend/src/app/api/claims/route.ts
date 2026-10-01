import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export async function GET() {
  try {
    // Read the cached_claims_v2.json file from the backend folder
    const backendDir = path.resolve(process.cwd(), "..", "backend");
    const cacheFile = path.join(backendDir, "cached_claims_v2.json");

    if (!fs.existsSync(cacheFile)) {
      return NextResponse.json(
        { error: "Cache file not found. Please run the backend script first." },
        { status: 404 }
      );
    }

    const fileContent = fs.readFileSync(cacheFile, "utf-8");
    const data = JSON.parse(fileContent);

    return NextResponse.json(data);
  } catch (error) {
    console.error("Error reading claims:", error);
    return NextResponse.json(
      { error: "Failed to read backend claims data." },
      { status: 500 }
    );
  }
}
