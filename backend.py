import asyncio
import aiohttp
from aiohttp import web
import json
import subprocess
import os
import sys
import threading
import re
import importlib.util
import platform 

# ==================================================================================
# CLOUD COMPILER SERVER (AIOHTTP) - RENDER COMPATIBLE
# ==================================================================================

# Get API Key from Environment
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

def install_package(package_name, ws=None, loop=None):
    """Attempt to install a python package via pip."""
    try:
        if importlib.util.find_spec(package_name) is not None:
            return
        
        msg = f"Installing missing package: {package_name}..."
        print(msg)
        if ws and loop:
             asyncio.run_coroutine_threadsafe(
                ws.send_json({'type': 'status', 'msg': msg}), 
                loop
            )

        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
    except Exception as e:
        error_msg = f"Failed to install {package_name}: {e}"
        print(error_msg)
        if ws and loop: 
             asyncio.run_coroutine_threadsafe(
                ws.send_json({'type': 'stdout', 'data': f"\n[Error] {error_msg}\n"}), 
                loop
            )

def check_and_install_packages(code, ws=None, loop=None):
    """Scan Python code for imports and install them if missing."""
    imports = re.findall(r'^\s*import\s+(\w+)', code, re.MULTILINE)
    from_imports = re.findall(r'^\s*from\s+(\w+)', code, re.MULTILINE)
    unique_packages = set(imports + from_imports)
    for pkg in unique_packages:
        if pkg in ['os', 'sys', 'time', 'random', 'math', 'json', 'asyncio', 'threading', 'platform', 'subprocess', 're', 'aiohttp']:
            continue
        install_package(pkg, ws, loop)

async def handle_client(request):
    # --- HEALTH CHECK HANDLING ---
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return web.Response(text="OK")

    # --- WEBSOCKET HANDLING ---
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    print(f"Client connected: {request.remote}")
    process = None
    
    # Helper to read output stream in a separate thread
    def read_stream(stream, loop):
        try:
            while True:
                char = stream.read(1)
                if not char:
                    break
                asyncio.run_coroutine_threadsafe(
                    ws.send_json({'type': 'stdout', 'data': char}), 
                    loop
                )
            
            asyncio.run_coroutine_threadsafe(
                ws. send_json({'type': 'status', 'msg': 'Program finished'}), 
                loop
            )
        except Exception: 
            pass

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                
                if data. get('type') == 'run': 
                    code = data.get('code')
                    language = data.get('language', 'python')
                    
                    # --- PYTHON HANDLING ---
                    if language == 'python':
                        await ws.send_json({'type': 'status', 'msg': 'Checking dependencies...'})
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(None, check_and_install_packages, code, ws, loop)
                        
                        filename = "temp_script.py"
                        with open(filename, "w", encoding="utf-8") as f:
                            f.write(code)
                        
                        # 🔒 SECURITY FIX: Use sanitized environment (no API keys or secrets)
                        safe_env = {
                            "PYTHONIOENCODING": "utf-8",
                            "PATH": os.environ.get("PATH", ""),
                            "PYTHONPATH": os.environ. get("PYTHONPATH", ""),
                            "HOME": os.environ.get("HOME", ""),
                            "USER": os.environ.get("USER", ""),
                            "LANG":  os.environ.get("LANG", "en_US.UTF-8"),
                        }

                        process = subprocess.Popen(
                            [sys. executable, "-u", filename], 
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess. STDOUT, 
                            text=True, 
                            bufsize=0, 
                            encoding='utf-8', 
                            env=safe_env  # ✅ Use sanitized environment
                        )
                        await ws.send_json({'type':  'status', 'msg':  'Running Python.. .'})

                    # --- C HANDLING ---
                    elif language == 'c': 
                        filename = "temp_code.c"
                        executable = "./a.out" if platform. system() != "Windows" else "a.exe"
                        
                        with open(filename, "w", encoding="utf-8") as f:
                            f. write(code)
                        
                        await ws.send_json({'type':  'status', 'msg':  'Compiling C...'})
                        
                        # 🔒 SECURITY:  Sanitized environment for compilation
                        safe_env = {
                            "PATH": os.environ. get("PATH", ""),
                            "HOME": os.environ. get("HOME", ""),
                            "USER": os.environ. get("USER", ""),
                            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
                            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
                        }
                        
                        compile_process = subprocess.run(
                            ["gcc", filename, "-o", executable],
                            capture_output=True,
                            text=True,
                            env=safe_env  # ✅ Sanitized env for compilation
                        )
                        
                        if compile_process.returncode != 0:
                            await ws. send_json({'type': 'stdout', 'data': f"Compilation Error:\n{compile_process.stderr}"})
                            await ws.send_json({'type': 'status', 'msg': 'Compilation Failed'})
                            continue 
                        
                        await ws.send_json({'type': 'status', 'msg': 'Running C Binary...'})
                        
                        process = subprocess.Popen(
                            [executable],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=0,
                            encoding='utf-8',
                            env=safe_env  # ✅ Sanitized env for execution
                        )

                    # --- C++ HANDLING ---
                    elif language == 'cpp':
                        filename = "temp_code.cpp"
                        executable = "./a.out" if platform.system() != "Windows" else "a.exe"
                        
                        with open(filename, "w", encoding="utf-8") as f:
                            f.write(code)
                        
                        await ws.send_json({'type': 'status', 'msg': 'Compiling C++...'})
                        
                        # 🔒 SECURITY:  Sanitized environment for compilation
                        safe_env = {
                            "PATH": os.environ. get("PATH", ""),
                            "HOME": os.environ. get("HOME", ""),
                            "USER": os.environ. get("USER", ""),
                            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
                            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
                        }
                        
                        compile_process = subprocess.run(
                            ["g++", filename, "-o", executable],
                            capture_output=True,
                            text=True,
                            env=safe_env  # ✅ Sanitized env for compilation
                        )
                        
                        if compile_process.returncode != 0:
                            await ws.send_json({'type': 'stdout', 'data': f"Compilation Error:\n{compile_process.stderr}"})
                            await ws.send_json({'type': 'status', 'msg': 'Compilation Failed'})
                            continue
                        
                        await ws. send_json({'type': 'status', 'msg': 'Running C++ Binary...'})
                        
                        process = subprocess.Popen(
                            [executable],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=0,
                            encoding='utf-8',
                            env=safe_env  # ✅ Sanitized env for execution
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
                            process.stdin. flush()
                        except Exception: 
                            pass

                # --- AI FIX HANDLER (with secure API call) ---
                elif data.get('type') == 'ai_fix':
                    code = data.get('code')
                    error_log = data.get('error')
                    language = data.get('language', 'c')
                    
                    if not GEMINI_API_KEY: 
                        await ws.send_json({'type': 'ai_error', 'msg': 'Server Error:  GEMINI_API_KEY not configured.'})
                        continue

                    # Construct Prompt
                    json_format = '{\n    "explanation": "Brief explanation of the bug (max 2 sentences)",\n    "fixed_code": "The full corrected code"\n}'
                    
                    prompt = (
                        f"You are an expert {language. upper()} programming debugger.\n"
                        f"CODE:\n{code}\n"
                        f"ERROR OUTPUT:\n{error_log}\n"
                        "TASK:\n"
                        "1. Analyze the error.\n"
                        "2. Provide a concise explanation.\n"
                        "3. Provide the COMPLETE corrected code.\n"
                        "RESPONSE FORMAT:\n"
                        "Return ONLY a valid JSON object with no markdown formatting or backticks:\n"
                        f"{json_format}"
                    )

                    try:
                        # 🔒 SECURITY FIX: Use stable model with header-based authentication
                        api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
                        
                        async with aiohttp.ClientSession() as session:
                            async with session.post(
                                api_url,
                                headers={
                                    "x-goog-api-key":  GEMINI_API_KEY,  # ✅ Secure:  API key in header
                                    "Content-Type": "application/json"
                                },
                                json={
                                    "contents": [{"parts": [{"text": prompt}]}],
                                    "generationConfig": {
                                        "temperature": 0.2,
                                        "responseMimeType": "application/json"
                                    }
                                }
                            ) as resp:
                                if resp.status != 200:
                                    error_body = await resp.text()
                                    print(f"Gemini API Error {resp.status}: {error_body}")
                                    await ws. send_json({'type': 'ai_error', 'msg':  f"AI API Error (Status {resp.status})"})
                                else:
                                    result = await resp.json()
                                    # Extract text from Gemini response structure
                                    try:
                                        content_text = result['candidates'][0]['content']['parts'][0]['text']
                                        parsed_response = json.loads(content_text)
                                        
                                        # Send back to client
                                        await ws.send_json({
                                            'type': 'ai_response', 
                                            'data': parsed_response
                                        })
                                    except (KeyError, IndexError, json.JSONDecodeError) as parse_error:
                                        print(f"Response parsing error: {parse_error}")
                                        print(f"Raw response: {result}")
                                        await ws. send_json({'type': 'ai_error', 'msg': "Failed to parse AI response"})
                                    
                    except Exception as e:
                        print(f"AI Error: {e}")
                        await ws.send_json({'type':  'ai_error', 'msg': "Server processing error occurred"})

            elif msg.type == web.WSMsgType.ERROR:
                print(f'ws connection closed with exception {ws.exception()}')

    finally:
        if process:
            try:
                process.kill()
            except:
                pass
        print("Client disconnected")

    return ws

async def main():
    port = int(os.environ.get("PORT", 8765))
    app = web.Application()
    app.add_routes([web.get('/', handle_client)])
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    print(f"AIOHTTP Server started on port {port}...")
    await site.start()
    
    # Keep the server running
    await asyncio.Event().wait()

if __name__ == "__main__": 
    asyncio.run(main())
