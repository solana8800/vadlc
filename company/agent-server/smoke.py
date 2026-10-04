"""No model/network requests: reject public destinations and verify local stdio RPC."""
import json
import os
import pathlib
import queue
import subprocess
import sys
import tempfile
import threading

binary = str(pathlib.Path(sys.argv[1]).resolve())
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
