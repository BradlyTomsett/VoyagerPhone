"""Public-site authentication boundaries; synthetic credentials only."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from backend import app
from backend.auth import create_credentials, OwnerAuth


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'login.json'
        self.password = 'SYNTHETIC-PASSWORD-ONLY-123'
        create_credentials(self.path, 'commander', self.password)
        self.env = patch.dict(os.environ, {'VOYAGER_AUTH_FILE':str(self.path),
            'VOYAGER_REQUIRE_LOGIN':'1', 'VOYAGER_ACCESS_TOKEN':'old-'+'x'*40,
            'VOYAGER_ALLOWED_ORIGINS':'https://game.example.com'})
        self.env.start()
        self.game = SimpleNamespace(model=SimpleNamespace(configured=False,model=''),
            bridge=SimpleNamespace(state=lambda:{'synthetic':True}),
            store=SimpleNamespace(list=lambda:[]))
        self.stub = patch.object(app, '_service', self.game); self.stub.start()

    def tearDown(self):
        self.stub.stop(); self.env.stop(); self.temp.cleanup()

    def request(self, path, method='GET', data=None, cookie='', csrf=True,
                origin='https://game.example.com', bearer=''):
        body = json.dumps(data).encode() if data is not None else b''
        env = {'PATH_INFO':path,'REQUEST_METHOD':method,'wsgi.url_scheme':'http',
               'HTTP_HOST':'game.example.com','HTTP_ORIGIN':origin,
               'HTTP_COOKIE':cookie,'HTTP_AUTHORIZATION':'Bearer '+bearer,
               'CONTENT_LENGTH':str(len(body)),'CONTENT_TYPE':'application/json',
               'wsgi.input':io.BytesIO(body)}
        if csrf: env['HTTP_X_VOYAGER_REQUEST'] = '1'
        result = {}
        def start(status, headers): result.update(status=int(status[:3]), headers=dict(headers))
        result['body'] = b''.join(app.application(env, start))
        return result

    def login(self):
        result = self.request('/api/auth/login','POST',{'username':'commander','password':self.password})
        self.assertEqual(result['status'], 200)
        return result['headers']['Set-Cookie'].split(';')[0]

    def test_unauthenticated_navigation_shows_login_but_cannot_read_game(self):
        result = self.request('/')
        self.assertEqual(result['status'],200)
        self.assertIn('登录指挥台'.encode(), result['body'])
        for path in ('/api/status','/api/state','/api/turns','/api/model-settings','/api/export','/snapshot.json'):
            self.assertEqual(self.request(path)['status'],401,path)
        for path in ('/data/login.json','/.voyager-runtime/data/login.json','/seed/state.json'):
            self.assertEqual(self.request(path)['status'],404,path)

    def test_password_is_hashed_and_initializer_never_changes_existing_account(self):
        self.assertNotIn(self.password,self.path.read_text())
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        before = self.path.read_bytes()
        self.assertIsNone(create_credentials(self.path))
        self.assertEqual(before,self.path.read_bytes())

    def test_login_cookie_authenticates_after_process_restart_without_exposing_secrets(self):
        cookie = self.login()
        self.assertEqual(self.request('/api/state',cookie=cookie)['status'],200)
        self.assertIn(b'Command deck',self.request('/',cookie=cookie)['body'])
        result = self.request('/api/auth/status',cookie=cookie)
        self.assertEqual(json.loads(result['body'])['username'],'commander')
        with patch.object(app,'_owner_auth_path',None):
            self.assertEqual(self.request('/api/state',cookie=cookie)['status'],200)
        auth = OwnerAuth(self.path)
        with auth.db() as db:
            stored = db.execute('SELECT digest FROM sessions').fetchone()[0]
        self.assertNotEqual(stored,cookie.split('=')[1])

    def test_cookie_has_transport_protections_even_behind_http_proxy(self):
        result = self.request('/api/auth/login','POST',{'username':'commander','password':self.password})
        value = result['headers']['Set-Cookie']
        for flag in ('HttpOnly','Secure','SameSite=Lax','Path=/'): self.assertIn(flag,value)
        self.assertNotIn(self.password,result['body'].decode())
        self.assertNotIn('voyager_session',result['body'].decode())

    def test_wrong_username_and_password_fail_without_enumerating_accounts(self):
        errors=[]
        for username,password in (('commander','wrong'),('unknown',self.password)):
            result=self.request('/api/auth/login','POST',{'username':username,'password':password})
            self.assertEqual(result['status'],401); errors.append(result['body'])
            self.assertNotIn('Set-Cookie',result['headers'])
        self.assertEqual(errors[0],errors[1])

    def test_legacy_bearer_cannot_bypass_password_login(self):
        self.assertEqual(self.request('/api/state',bearer='old-'+'x'*40)['status'],401)

    def test_cross_site_and_missing_csrf_cannot_login_or_mutate(self):
        login={'username':'commander','password':self.password}
        self.assertEqual(self.request('/api/auth/login','POST',login,csrf=False)['status'],403)
        self.assertEqual(self.request('/api/auth/login','POST',login,origin='https://evil.example')['status'],403)
        cookie=self.login()
        self.assertEqual(self.request('/api/model-settings','POST',{},cookie=cookie,csrf=False)['status'],403)
        self.assertEqual(self.request('/api/auth/logout','POST',{},cookie=cookie,csrf=False)['status'],403)
        self.assertEqual(self.request('/api/state',cookie=cookie)['status'],200)

    def test_logout_revokes_copied_cookie(self):
        cookie=self.login()
        result=self.request('/api/auth/logout','POST',{},cookie=cookie)
        self.assertEqual(result['status'],200);self.assertIn('Max-Age=0',result['headers']['Set-Cookie'])
        self.assertEqual(self.request('/api/state',cookie=cookie)['status'],401)

    def test_expired_or_forged_session_is_rejected(self):
        cookie=self.login();auth=OwnerAuth(self.path)
        with auth.db() as db: db.execute('UPDATE sessions SET expires=?',(time.time()-1,))
        self.assertEqual(self.request('/api/state',cookie=cookie)['status'],401)
        self.assertEqual(self.request('/api/state',cookie='voyager_session='+'x'*43)['status'],401)

    def test_repeated_failed_logins_are_limited_and_attempts_are_persisted(self):
        for _ in range(20):
            self.assertEqual(self.request('/api/auth/login','POST',{'username':'different','password':'wrong'})['status'],401)
        result=self.request('/api/auth/login','POST',{'username':'commander','password':self.password})
        self.assertEqual(result['status'],429);self.assertEqual(result['headers']['Retry-After'],'300')

    def test_missing_required_login_never_falls_back_to_old_token(self):
        self.path.unlink()
        self.assertEqual(self.request('/api/state',bearer='old-'+'x'*40)['status'],503)

    def test_owner_password_replacement_is_picked_up_without_accepting_old_password(self):
        from backend.auth import password_hash
        old_cookie=self.login()
        value=json.loads(self.path.read_text())
        value['password_hash']=password_hash('NEW-SYNTHETIC-PASSWORD-ONLY',value['salt'])
        updated=self.path.with_suffix('.new');updated.write_text(json.dumps(value));updated.replace(self.path)
        auth=OwnerAuth(self.path)
        with auth.db() as db:db.execute('DELETE FROM sessions')
        self.assertEqual(self.request('/api/state',cookie=old_cookie)['status'],401)
        result=self.request('/api/auth/login','POST',{'username':'commander','password':self.password})
        self.assertEqual(result['status'],401)
        self.password='NEW-SYNTHETIC-PASSWORD-ONLY'
        self.login()


if __name__ == '__main__': unittest.main()
