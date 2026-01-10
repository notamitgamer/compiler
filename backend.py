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

# ==================================================================================
# THREADED COMPILER SERVER (Auto-Install + UTF-8)
# ==================================================================================

def install_package(package_name):
    """Attempt to install a package via pip."""
    try:
        # Check if already installed to save time
        if importlib.util.find_spec(package_name) is not None:
            return

        print(f"Installing missing package: {package_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
    except Exception as e:
        print(f"Failed to install {package_name}: {e}")

def check_and_install_packages(code):
    """Scan code for imports and install them if missing."""
    # Regex to find 'import x' or 'from x import y'
    imports = re.findall(r'^\s*import\s+(\w+)', code, re.MULTILINE)
    from_imports = re.findall(r'^\s*from\s+(\w+)', code, re.MULTILINE)
    
    unique_packages = set(imports + from_imports)
    
    # Filter out standard library modules (approximate list or just let pip handle it)
    # Ideally, we just try to install. Pip is smart enough to skip if satisfied.
    for pkg in unique_packages:
        # Skip common standard libs to save time (add more if needed)
        if pkg in ['os', 'sys', 'time', 'random', 'math', 'json', 'asyncio', 'threading', 'platform', 'subprocess', 're']:
            continue
        install_package(pkg)

async def run_code(websocket):
    print(f"Client connected: {websocket.remote_address}")
    process = None
    
    def read_stream(stream, loop):
        try:
            while True:
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
                
                # 1. AUTO-INSTALL PACKAGES
                await websocket.send(json.dumps({'type': 'status', 'msg': 'Checking dependencies...'}))
                # Run in executor to avoid blocking the event loop
                await asyncio.get_running_loop().run_in_executor(None, check_and_install_packages, code)
                
                # 2. WRITE FILE
                filename = "temp_script.py"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(code)
                
                # 3. RUN CODE
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
                
                await websocket.send(json.dumps({'type': 'status', 'msg': 'Running...'}))

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

async def main():
    print("Server started on port 8765...")
    async with websockets.serve(run_code, "0.0.0.0", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())