import asyncio
import websockets
import json
import subprocess
import os
import sys
import platform
import threading
import re
import importlib.util
import http

# ==================================================================================
# CLOUD COMPILER SERVER (Python, C, C++) - RENDER COMPATIBLE
# ==================================================================================

def install_package(package_name, websocket=None, loop=None):
    """Attempt to install a python package via pip."""
    try:
        if importlib.util.find_spec(package_name) is not None:
            return
        
        msg = f"Installing missing package: {package_name}..."
        print(msg)
        if websocket and loop:
             asyncio.run_coroutine_threadsafe(
                websocket.send(json.dumps({'type': 'status', 'msg': msg})), 
                loop
            )

        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
    except Exception as e:
        error_msg = f"Failed to install {package_name}: {e}"
        print(error_msg)
        if websocket and loop:
             asyncio.run_coroutine_threadsafe(
                websocket.send(json.dumps({'type': 'stdout', 'data': f"\n[Error] {error_msg}\n"})), 
                loop
            )

def check_and_install_packages(code, websocket=None, loop=None):
    """Scan Python code for imports and install them if missing."""
    imports = re.findall(r'^\s*import\s+(\w+)', code, re.MULTILINE)
    from_imports = re.findall(r'^\s*from\s+(\w+)', code, re.MULTILINE)
    unique_packages = set(imports + from_imports)
    for pkg in unique_packages:
        if pkg in ['os', 'sys', 'time', 'random', 'math', 'json', 'asyncio', 'threading', 'platform', 'subprocess', 're']:
            continue
        install_package(pkg, websocket, loop)

async def run_code(websocket):
    print(f"Client connected: {websocket.remote_address}")
    process = None
    
    # Helper to read output stream in a separate thread
    def read_stream(stream, loop):
        try:
            while True:
                # Read 1 byte/char at a time
                char = stream.read(1)
                if not char:
                    break
                asyncio.run_coroutine_threadsafe(
                    websocket.send(json.dumps({'type': 'stdout', 'data': char})), 
                    loop
                )
        except Exception:
            pass

    try:
        async for message in websocket:
            data = json.loads(message)
            
            if data.get('type') == 'run':
                code = data.get('code')
                language = data.get('language', 'python')
                
                # --- PYTHON HANDLING ---
                if language == 'python':
                    await websocket.send(json.dumps({'type': 'status', 'msg': 'Checking dependencies...'}))
                    # Run package check in executor to avoid blocking main loop
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, check_and_install_packages, code, websocket, loop)
                    
                    filename = "temp_script.py"
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(code)
                    
                    env = os.environ.copy()
                    env["PYTHONIOENCODING"] = "utf-8"

                    process = subprocess.Popen(
                        [sys.executable, "-u", filename], 
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, 
                        text=True, 
                        bufsize=0, 
                        encoding='utf-8', 
                        env=env
                    )
                    await websocket.send(json.dumps({'type': 'status', 'msg': 'Running Python...'}))

                # --- C HANDLING ---
                elif language == 'c':
                    filename = "temp_code.c"
                    executable = "./a.out" if platform.system() != "Windows" else "a.exe"
                    
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(code)
                    
                    await websocket.send(json.dumps({'type': 'status', 'msg': 'Compiling C...'}))
                    
                    compile_process = subprocess.run(
                        ["gcc", filename, "-o", executable],
                        capture_output=True,
                        text=True
                    )
                    
                    if compile_process.returncode != 0:
                        await websocket.send(json.dumps({'type': 'stdout', 'data': f"Compilation Error:\n{compile_process.stderr}"}))
                        continue 
                    
                    await websocket.send(json.dumps({'type': 'status', 'msg': 'Running C Binary...'}))
                    
                    process = subprocess.Popen(
                        [executable],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=0,
                        encoding='utf-8'
                    )

                # --- C++ HANDLING ---
                elif language == 'cpp':
                    filename = "temp_code.cpp"
                    executable = "./a.out" if platform.system() != "Windows" else "a.exe"
                    
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(code)
                    
                    await websocket.send(json.dumps({'type': 'status', 'msg': 'Compiling C++...'}))
                    
                    compile_process = subprocess.run(
                        ["g++", filename, "-o", executable],
                        capture_output=True,
                        text=True
                    )
                    
                    if compile_process.returncode != 0:
                        await websocket.send(json.dumps({'type': 'stdout', 'data': f"Compilation Error:\n{compile_process.stderr}"}))
                        continue
                    
                    await websocket.send(json.dumps({'type': 'status', 'msg': 'Running C++ Binary...'}))
                    
                    process = subprocess.Popen(
                        [executable],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=0,
                        encoding='utf-8'
                    )

                if process:
                    loop = asyncio.get_running_loop()
                    thread = threading.Thread(target=read_stream, args=(process.stdout, loop))
                    thread.daemon = True 
                    thread.start()

            elif data.get('type') == 'input':
                if process and process.poll() is None:
                    user_input = data.get('data')
                    try:
                        process.stdin.write(user_input)
                        process.stdin.flush()
                    except Exception:
                        pass

    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    except Exception as e:
        print(f"Server Error: {e}")
    finally:
        if process: process.kill()

async def health_check(path, request_headers):
    """
    Custom handler to intercept HTTP requests (like health checks) 
    before the WebSocket handshake.
    """
    # Render sends HTTP HEAD or GET requests to '/' or '/healthz' for health checks.
    # We must return a valid HTTP response to prevent the server from treating it as a failed handshake.
    if path == "/" or path == "/healthz":
        return http.HTTPStatus.OK, [], b"OK"
    # Returning None tells websockets to proceed with the standard handshake
    return None

async def main():
    # Use PORT env var for Render/Replit, default to 8765
    port = int(os.environ.get("PORT", 8765))
    print(f"Server started on port {port}...")
    
    # We pass 'process_request' to handle health checks
    async with websockets.serve(run_code, "0.0.0.0", port, process_request=health_check):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
