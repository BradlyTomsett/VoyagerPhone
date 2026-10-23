#!/usr/bin/env python3
"""Owner-operated password reset; run in the server terminal, then restart the game."""
import getpass
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from backend.auth import OwnerAuth, password_hash


def main():
    path = BASE / '.voyager-runtime' / 'data' / 'login.json'
    auth = OwnerAuth(path)
    password = getpass.getpass('新游戏密码（至少 16 个字符，不会显示）：')
    if not 16 <= len(password) <= 256:
        print('密码长度必须为 16–256 个字符。'); return 1
    if password != getpass.getpass('再次输入新密码：'):
        print('两次输入不一致，密码未修改。'); return 1
    salt = secrets.token_hex(16)
    value = {**auth.credentials, 'salt': salt, 'password_hash': password_hash(password, salt)}
    fd, staged = tempfile.mkstemp(prefix='.reset-login-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())
        os.replace(staged, path)
    finally:
        if os.path.exists(staged): os.unlink(staged)
    with auth.db() as db: db.execute('DELETE FROM sessions')
    print('密码已更新，旧登录会话已撤销。请停止后重新启动游戏服务。')
    return 0


if __name__ == '__main__': raise SystemExit(main())
