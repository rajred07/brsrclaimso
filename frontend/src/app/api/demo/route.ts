import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

export async function POST() {
  try {
    const frontendPath = process.cwd();
    const backendPath = path.resolve(frontendPath, '../backend');
    
    // Determine the correct python executable path
    let pythonExe = path.join(backendPath, '.venv', 'Scripts', 'python.exe');
    if (!fs.existsSync(pythonExe)) {
        pythonExe = path.join(backendPath, '.venv', 'bin', 'python');
    }
    if (!fs.existsSync(pythonExe)) {
        pythonExe = 'python';
    }

    // Run the verification engine
    await new Promise((resolve, reject) => {
        const child = spawn(pythonExe, ['src/verify_engine.py'], { cwd: backendPath });
        
        child.on('close', (code) => {
            if (code === 0) resolve(code);
            else reject(new Error(`Process exited with code ${code}`));
        });
        
        child.on('error', (err) => reject(err));
    });

    // Read the output
    const outputFilePath = path.join(backendPath, 'data', 'claims', 'verified_claims.json');
    const data = fs.readFileSync(outputFilePath, 'utf8');
    
    return NextResponse.json(JSON.parse(data));
    
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: 'Failed to run verification engine' }, { status: 500 });
  }
}
