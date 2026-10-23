import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('codespaces_start',ROOT/'scripts/start_codespaces.py')
startup=importlib.util.module_from_spec(spec);spec.loader.exec_module(startup)

class StartupTests(unittest.TestCase):
    def test_password_login_url_has_no_credential(self):
        with patch.dict(os.environ,{'CODESPACE_NAME':'synthetic-safe-name','GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN':'app.github.dev'}):
            origin,url=startup.launch_url()
        self.assertEqual(url,origin+'/')
        self.assertNotIn('#',url)
    def test_private_file_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'token';startup.write_private(p,'SYNTHETIC_TOKEN')
            self.assertEqual(p.stat().st_mode&0o777,0o600)
    def test_invalid_forwarding_domain_rejected(self):
        with patch.dict(os.environ,{'CODESPACE_NAME':'synthetic-safe-name','GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN':'example.com/path'}):
            with self.assertRaises(ValueError):startup.launch_url()
