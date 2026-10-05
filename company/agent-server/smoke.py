"""No model/network requests: reject public destinations and verify local stdio RPC."""
import json
import os
import pathlib
import queue
import subprocess
import sys
import tempfile
import threading

# Smoke the fixed build output for this native runner; never execute a CLI-supplied path.
import platform
if sys.platform == 'darwin' and platform.machine() == 'arm64': target, name = 'aarch64-apple-darwin', 'v-adlc-agent-server'
elif sys.platform == 'linux' and platform.machine() == 'x86_64': target, name = 'x86_64-unknown-linux-gnu', 'v-adlc-agent-server'
elif sys.platform == 'win32' and platform.machine().lower() in {'amd64', 'x86_64'}: target, name = 'x86_64-pc-windows-msvc', 'v-adlc-agent-server.exe'
else: raise RuntimeError('unsupported native smoke platform')
root = pathlib.Path(__file__).resolve().parents[2] / 'codex-rs' / 'target'
binary_path = root / target / 'adlc-release' / name
if not binary_path.exists(): binary_path = root / 'adlc-release' / name
if binary_path.is_symlink() or not binary_path.is_file(): raise RuntimeError('private release binary missing')
binary = str(binary_path)
for args in [['--remote-control'], ['--private-model-endpoint', 'https://api.openai.com/v1']]:
    result = subprocess.run([binary, *args], capture_output=True, timeout=30)
    if result.returncode == 0: raise RuntimeError('private policy rejection failed')
with tempfile.TemporaryDirectory() as home:
    env = dict(os.environ, CODEX_HOME=home)
    process = subprocess.Popen([binary, '--listen', 'stdio://'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
    received = queue.Queue()
    def read():
        for line in process.stdout:
            received.put(json.loads(line))
    threading.Thread(target=read, daemon=True).start()
    try:
        process.stdin.write(json.dumps({'id':1,'method':'initialize','params':{'clientInfo':{'name':'adlc-release-smoke','version':'1'},'capabilities':{'experimentalApi':True}}}) + '\n'); process.stdin.flush()
        response = received.get(timeout=30)
        if response.get('id') != 1 or 'result' not in response: raise RuntimeError('initialize failed')
    finally:
        process.kill(); process.wait(timeout=10)
print('Private policy and initialize PASS')
