"""Submission classification, legacy repair and pre-confirmation identity checks."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest

# These fixture tests do not execute a native engine or exercise OS locks.
if sys.platform == 'win32' and 'fcntl' not in sys.modules:
    stub = types.ModuleType('fcntl')
    stub.LOCK_EX, stub.LOCK_NB, stub.LOCK_UN = 2, 4, 8
    stub.flock = lambda *args: None
    sys.modules['fcntl'] = stub

from backend.engine import EngineBridge, SubmissionNotCommitted, digest
from backend.app import GameService
from tests.test_backend import FixtureModel, FixtureBridge


class SubmissionWitnessTests(unittest.TestCase):
    def bridge(self, changed=False, recovery_fails=False, already_changed=False):
        bridge = EngineBridge.__new__(EngineBridge)
        bridge.lock = threading.RLock()
        base = {'save_set_id': 'SYNTHETIC-BEFORE', 'manifest_sha256': 'before', 'engine_sha256': 'engine'}
        current = dict(base)
        if already_changed: current['manifest_sha256'] = 'prior-commit'
        bridge.identity = lambda: dict(current)
        def recover():
            if recovery_fails: raise ValueError('GUARD_RECOVERY_FAILED')
        bridge.recover = recover
        def submit(*args):
            if changed: current['manifest_sha256'] = 'after-commit'
            raise ValueError('STORY_ENTITY_UNAVAILABLE')
        bridge.host = types.SimpleNamespace(setup=submit, submit=submit)
        return bridge, {'kind': 'setup', 'envelope': {}, 'next_version': 'V1.1', 'base_identity': base}

    def test_verified_unchanged_base_is_a_rejection(self):
        bridge, job = self.bridge()
        with self.assertRaises(SubmissionNotCommitted) as result: bridge.submit(job)
        self.assertEqual(result.exception.code, 'STORY_ENTITY_UNAVAILABLE')

    def test_response_loss_after_commit_is_never_reclassified(self):
        for options in ({'changed': True}, {'already_changed': True}, {'recovery_fails': True}):
            with self.subTest(options=options):
                bridge, job = self.bridge(**options)
                with self.assertRaises(ValueError): bridge.submit(job)


class JournalRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.game = GameService(self.temp.name, FixtureModel(), FixtureBridge, start=False)
        self.request = {'client_id': 'WEB-synthetic-recovery', 'intent': 'SYNTHETIC only',
                        'mode': 'action', 'actor_id': 'PER-SYNTHETIC', 'scene_id': None}
        self.game.create(self.request)
        self.game.process(self.game.store.get(self.request['client_id']))
        self.job = self.game.store.get(self.request['client_id'])

    def tearDown(self):
        self.game.process_lock.close()
        self.temp.cleanup()

    def test_verified_rejection_does_not_hold_active_turn_lock(self):
        self.game.confirm(self.job['id'], self.job['plan_hash'])
        def reject(job): raise SubmissionNotCommitted('STORY_ENTITY_UNAVAILABLE')
        self.game.bridge.submit = reject
        self.game.process(self.game.store.get(self.job['id']))
        failed = self.game.store.get(self.job['id'])
        self.assertEqual(failed['status'], 'BLOCKED')
        self.assertTrue(failed['uncommitted'])
        self.assertEqual(self.game.bridge.count, 0)
        self.game.create({**self.request, 'client_id': 'WEB-synthetic-new-request'})

    def test_only_known_unchanged_legacy_setup_is_released(self):
        self.job.update(status='RECOVERY_REQUIRED', error='STORY_ENTITY_UNAVAILABLE')
        self.game.store.save(self.job)
        self.game.bridge.recover()
        self.assertTrue(self.game.reject_unchanged_setup(self.job))
        self.assertEqual(self.game.store.get(self.job['id'])['status'], 'BLOCKED')
        for change in ({'base_identity': {'different': True}}, {'error': 'UNKNOWN_ERROR'}, {'kind': 'turn'}):
            job = {**self.job, 'status': 'RECOVERY_REQUIRED', **change}
            self.assertFalse(self.game.reject_unchanged_setup(job))
            self.assertEqual(job['status'], 'RECOVERY_REQUIRED')


class SetupReferenceTests(unittest.TestCase):
    def test_unknown_or_hidden_references_fail_before_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = EngineBridge.__new__(EngineBridge)
            bridge.root = Path(folder)
            state = {'entity_registry': {'entities': {
                'PER-A': {'entity_type': 'person', 'canonical_name': '测试人物'},
                'LOC-A': {'entity_type': 'location', 'canonical_name': '测试地点'},
                'PER-SECRET': {'entity_type': 'person', 'visibility': 'gm'},
            }}, 'engine_runtime': {'living_world_v1': {'profiles': {}}}}
            original = json.dumps(state).encode()
            (bridge.root / 'state.json').write_bytes(original)
            action = {'type': 'scene_open', 'location_ref': 'LOC-A', 'participants': ['PER-A']}
            plan = {'kind': 'setup', 'payload_json': json.dumps({'actions': [action]})}
            job = {'request': {'actor_id': 'PER-A'}}
            self.assertEqual(bridge.normalize(plan, job, {}), {'actions': [action]})
            for bad in ('PER-MISSING', 'PER-SECRET'):
                broken = copy.deepcopy(action); broken['participants'].append(bad)
                with self.assertRaisesRegex(ValueError, 'SETUP_REFERENCE_UNAVAILABLE'):
                    bridge.normalize({'kind': 'setup', 'payload_json': json.dumps({'actions': [broken]})}, job, {})
            self.assertEqual((bridge.root / 'state.json').read_bytes(), original)


if __name__ == '__main__': unittest.main()
