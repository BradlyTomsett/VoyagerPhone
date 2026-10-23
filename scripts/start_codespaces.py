#!/usr/bin/env python3
"""Start the owner's game and optionally expose its password-protected port."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from backend.auth import create_credentials


def write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600); stream.write(text)


def healthy():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5) as response:
            value = json.load(response)
        return value.get('web_version') == '0.3.0' and value.get('login_required') is True
    except (OSError, ValueError):
        return False


def launch_url():
    name = os.environ.get('CODESPACE_NAME')
    domain = os.environ.get('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'app.github.dev')
    if name:
        if not all(c.isalnum() or c == '-' for c in name): raise ValueError('CODESPACE_NAME_INVALID')
        if not all(c.isalnum() or c in '.-' for c in domain): raise ValueError('FORWARDING_DOMAIN_INVALID')
        origin = f'https://{name}-8000.{domain}'
    else:
        origin = 'http://127.0.0.1:8000'
    return origin, origin + '/'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--public', action='store_true',
                        default=os.environ.get('VOYAGER_PORT_VISIBILITY') == 'public')
    args = parser.parse_args()
    runtime = BASE / '.voyager-runtime'
    runtime.mkdir(mode=0o700, exist_ok=True); os.chmod(runtime, 0o700)
    with (runtime / 'startup.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = runtime / 'data'
        auth_file = data / 'login.json'
        initial_password = create_credentials(auth_file)
        if initial_password:
            print('用户名：commander', flush=True)
            print('初始密码（仅显示这一次）：' + initial_password, flush=True)
            print('请自行妥善保存。服务器仅保存密码散列，不保存明文密码。', flush=True)
        origin, url = launch_url()
        if not healthy():
            env = {**os.environ, 'VOYAGER_AUTH_FILE': str(auth_file), 'VOYAGER_REQUIRE_LOGIN': '1',
                   'VOYAGER_DATA_DIR': str(data), 'VOYAGER_ALLOWED_ORIGINS': origin}
            env.pop('VOYAGER_ACCESS_TOKEN', None)
            log_path = runtime / 'server.log'
            fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'a') as log:
                child = subprocess.Popen([sys.executable,'-m','gunicorn','--bind','0.0.0.0:8000',
                    '--workers','1','--threads','8','--timeout','240','backend.app:application'],
                    cwd=BASE, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    start_new_session=True)
            write_private(runtime / 'server.pid', str(child.pid))
            for _ in range(40):
                if healthy(): break
                if child.poll() is not None:
                    print('游戏启动失败，请检查 .voyager-runtime/server.log。'); return 1
                time.sleep(0.5)
            else:
                print('后端仍在恢复存档，请稍后重新运行本命令。'); return 1
        # Never expose the service until its password authentication is verified.
        if args.public and os.environ.get('CODESPACE_NAME'):
            try:
                result = subprocess.run(['gh','codespace','ports','visibility','8000:public',
                    '-c',os.environ['CODESPACE_NAME']], capture_output=True, text=True, timeout=15)
                if result.returncode:
                    print('游戏登录已启用。请在 Ports 面板将 8000 的可见性设为 Public。')
            except (OSError, subprocess.TimeoutExpired):
                print('游戏登录已启用。请在 Ports 面板将 8000 的可见性设为 Public。')
        write_private(runtime / 'game-url.txt', url + '\n')
        print('\n远航游戏已启动。打开下面的地址，使用游戏账号登录：\n')
        print(url)
        print('\n用户名：commander')
        if not initial_password:
            print('使用你已保存的游戏密码。')
        print('登录后在设置中填写模型 API Key。游戏和模型密钥不会提交到 GitHub。\n')
    return 0


if __name__ == '__main__': raise SystemExit(main())
