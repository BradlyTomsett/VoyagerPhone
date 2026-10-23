#!/usr/bin/env python3
"""Start a single owner game host and print its private, token-bearing launch URL."""
import fcntl
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = Path(__file__).resolve().parents[1]

def write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600); stream.write(text)

def healthy(token):
    request = urllib.request.Request('http://127.0.0.1:8000/api/status',
        headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response).get('web_version') == '0.2.0'
    except (OSError, ValueError):
        return False

def launch_url(token):
    name = os.environ.get('CODESPACE_NAME')
    domain = os.environ.get('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'app.github.dev')
    if name:
        if not all(c.isalnum() or c == '-' for c in name): raise ValueError('CODESPACE_NAME_INVALID')
        if not all(c.isalnum() or c in '.-' for c in domain): raise ValueError('FORWARDING_DOMAIN_INVALID')
        origin = f'https://{name}-8000.{domain}'
    else:
        origin = 'http://127.0.0.1:8000'
    return origin, origin + '/#access=' + token

def main():
    runtime = BASE / '.voyager-runtime'
    runtime.mkdir(mode=0o700, exist_ok=True); os.chmod(runtime, 0o700)
    with (runtime / 'startup.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        token_path = runtime / 'access-token'
        token = token_path.read_text().strip() if token_path.exists() else secrets.token_urlsafe(32)
        if len(token) < 32: raise ValueError('ACCESS_TOKEN_INVALID')
        write_private(token_path, token)
        origin, url = launch_url(token)
        if not healthy(token):
            if os.environ.get('CODESPACE_NAME'):
                # New forwarded ports default to private. Some Codespaces tokens cannot
                # manage port visibility; the application's separate owner token still
                # protects all data and settings if this management call is unavailable.
                try:
                    result = subprocess.run(['gh','codespace','ports','visibility','8000:private',
                        '-c',os.environ['CODESPACE_NAME']], capture_output=True, text=True, timeout=15)
                    if result.returncode:
                        print('端口可见性未自动核验，请保留 Ports 面板默认的 Private 设置。')
                except (OSError, subprocess.TimeoutExpired):
                    print('端口可见性未自动核验，请保留 Ports 面板默认的 Private 设置。')
            env = {**os.environ, 'VOYAGER_ACCESS_TOKEN': token,
                   'VOYAGER_DATA_DIR': str(runtime / 'data'), 'VOYAGER_ALLOWED_ORIGINS': origin}
            log_path = runtime / 'server.log'
            fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'a') as log:
                child = subprocess.Popen([sys.executable,'-m','gunicorn','--bind','0.0.0.0:8000',
                    '--workers','1','--threads','8','--timeout','240','backend.app:application'],
                    cwd=BASE, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    start_new_session=True)
            for _ in range(20):
                if healthy(token): break
                if child.poll() is not None:
                    print('游戏启动失败，请检查 .voyager-runtime/server.log。'); return 1
                time.sleep(0.5)
            else:
                print('后端仍在恢复存档，请稍后重新运行本命令。'); return 1
        write_private(runtime / 'game-url.txt', url + '\n')
        print('\n远航游戏已启动。点击下面的私人链接，填写模型 API 后即可进入：\n')
        print(url)
        print('\n此链接包含游戏访问口令，仅供本人使用。API 密钥不会提交到 GitHub。\n')
    return 0

if __name__ == '__main__': raise SystemExit(main())
