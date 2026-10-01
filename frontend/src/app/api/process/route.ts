import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

export async function POST() {
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      const frontendPath = process.cwd();
      const backendPath = path.resolve(frontendPath, '../backend');
      
      // Determine the correct python executable path
      let pythonExe = path.join(backendPath, '.venv', 'Scripts', 'python.exe'); // Windows
      if (!fs.existsSync(pythonExe)) {
          pythonExe = path.join(backendPath, '.venv', 'bin', 'python'); // Unix fallback
      }
      
      if (!fs.existsSync(pythonExe)) {
          // Absolute fallback if virtual environment isn't found
          pythonExe = 'python';
      }

      console.log("Spawning pipeline from:", backendPath);
      console.log("Using Python executable:", pythonExe);

      let isClosed = false;

      const child = spawn(pythonExe, ['run_pipeline.py'], {
        cwd: backendPath,
      });

      child.stdout.on('data', (data) => {
        if (!isClosed) controller.enqueue(encoder.encode(data.toString()));
      });

      child.stderr.on('data', (data) => {
        if (!isClosed) controller.enqueue(encoder.encode(data.toString()));
      });

      child.on('close', (code) => {
        if (!isClosed) {
          controller.enqueue(encoder.encode(`\n[PROCESS_COMPLETE] Exit code: ${code}\n`));
          controller.close();
          isClosed = true;
        }
      });
      
      child.on('error', (err) => {
        if (!isClosed) {
          controller.enqueue(encoder.encode(`\n[ERROR] ${err.message}\n`));
          controller.close();
          isClosed = true;
        }
      });
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Transfer-Encoding': 'chunked',
    },
  });
}
