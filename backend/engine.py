"""Adapter around the unchanged V14.66 engine and exact host authorization."""
import copy
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from backend.setup_references import resolve_setup

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

SETUP_TYPES = {'scene_open', 'scene_phase', 'scene_focus_v2', 'scene_join',
               'life_place', 'life_profile', 'life_control', 'life_position'}

class SubmissionNotCommitted(Exception):
    """The guard recovered and verified the exact pre-submit save identity."""
    def __init__(self, code):
        self.code = code if re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}', str(code)) else 'NATIVE_SUBMIT_REJECTED'
        super().__init__(self.code)

class EngineBridge:
    def __init__(self, root, authorize, reviewer):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self.host = module(self.root / 'development/host_session.py', 'voyager_web_host').HostSession(
            self.root, 'web-owner', viewer='player', authorize=authorize, review_narrative=reviewer)

    def recover(self):
        proc = subprocess.run([sys.executable, str(self.root / 'guard.py'), '--resume'],
            env={**os.environ, 'VOYAGER_ROOT': str(self.root)}, capture_output=True,
            text=True, timeout=180)
        if proc.returncode:
            raise RuntimeError('GUARD_RECOVERY_FAILED')

    def identity(self):
        return {'save_set_id': json.loads((self.root / 'manifest.json').read_text())['save_set_id'],
                'manifest_sha256': hashlib.sha256((self.root / 'manifest.json').read_bytes()).hexdigest(),
                'engine_sha256': hashlib.sha256((self.root / 'engine.py').read_bytes()).hexdigest()}

    def context(self, intent='', scene_id=None, actor_id=None):
        with self.lock:
            a = self.host._engine()
            packet = self.host.context(player_intent=intent, scene_id=scene_id,
                                       actor_id=actor_id, budget_bytes=65536,
                                       topics=['五项余额', '活动任务', '舰队核心', '当前场景'])
            if packet.get('budget_exceeded') or packet.get('generation_blocked'):
                raise ValueError('CONTEXT_BUDGET_EXCEEDED')
            return copy.deepcopy(packet)

    def state(self):
        with self.lock:
            a = self.host._engine()
            with a.SnapshotContext(self.root):
                a.ensure_source_ready(self.root)
                # Engine's player projections only. Do not expose the raw state/GM packet.
                core = a.visible_query_packet(self.root, '舰队核心', audience='player')
                tasks = a.visible_query_packet(self.root, '活动任务', audience='player')
                accounts = a.visible_query_packet(self.root, '五项余额', audience='player')
                scenes = a.scene_index_packet(self.root)
                m = json.loads((self.root / 'manifest.json').read_text())
                return {'version': m['save_version'], 'save_set_id': m['save_set_id'],
                        'game_time': m['game_time'], 'core': core, 'tasks': tasks,
                        'accounts': accounts, 'scenes': scenes, 'source': 'verified_engine'}

    def setup_entities(self):
        state = json.loads((self.root / 'state.json').read_bytes())
        return {eid: row for eid, row in state.get('entity_registry', {}).get('entities', {}).items()
                if isinstance(row, dict) and row.get('visibility') not in ('gm', 'secret', 'hidden')}

    def contracts(self, kind):
        schema = json.loads((self.root / 'development/schemas/story_turn_v3.json').read_text())
        if kind == 'turn':
            return schema
        a = self.host._engine()
        return {'allowed_types': sorted(SETUP_TYPES),
            'existing_entities': [{'id': eid, 'name': row.get('canonical_name', eid), 'type': row.get('entity_type')}
                                  for eid, row in self.setup_entities().items()], 'notes': [
            'scene_open: scene_id, task_id(null allowed), family=conversation, title, location_ref(existing), participants, presence_mode(remote or present), visible_to',
            'scene_phase: scene_id, phase=open; scene_focus_v2: scene_id',
            'life_control: entity_id, operation=take, reason; only the selected actor',
            'life_place: location_ref, expected_revision=0, senses, conditions, visible_to, basis_refs',
            'life_profile: entity_id, expected_revision=0, record. record has important=true, background, voice, public_fields, voice_visible_to, daily_routine, basis_refs, source_kind=authored_consistent_extension',
            'Only author an uninitialized revision-0 profile. Do not replace established biographies.',
            'life_position: entity_id, location_ref, basis_refs, reason. Requires explicit relocation confirmation; prefer remote scene when physical position is unverified.',
            'Use state:entity_registry.entities.<entity_id> as basis for a consistent newly authored profile; never claim it establishes past experiences.',
            'When a location ID or actor is missing, return needs_information. Never invent IDs for already-existing entities.'],
            'background_fields': list(a.LIVING_BACKGROUND), 'voice_fields': list(a.LIVING_VOICE),
            'sense_fields': list(a.LIVING_SENSES), 'condition_fields': list(a.LIVING_CONDITIONS)}

    def normalize(self, plan, job, context):
        payload = json.loads(plan.get('payload_json', '{}'))
        if not isinstance(payload, dict):
            raise ValueError('PLAN_OBJECT_REQUIRED')
        actor = job['request']['actor_id']
        if plan['kind'] == 'turn':
            payload.update(schema='STORY_TURN_PROPOSAL_V3', turn_id=job['id'],
                base_identity=context['prepare']['base_identity'], actor_id=actor,
                viewer='player', player_intent=job['request']['intent'])
            if payload.get('scene_id') != context['prepare'].get('scene_id'):
                raise ValueError('PLAN_SCENE_MISMATCH')
        elif plan['kind'] == 'setup':
            actions = payload.get('actions')
            if set(payload) != {'actions'} or not isinstance(actions, list) or not 1 <= len(actions) <= 20:
                raise ValueError('SETUP_ACTIONS_INVALID')
            state = json.loads((self.root / 'state.json').read_text())
            profiles = state['engine_runtime']['living_world_v1']['profiles']
            entities = self.setup_entities()
            payload = resolve_setup(payload, actor, entities)
            actions = payload['actions']
            if entities.get(actor, {}).get('entity_type') != 'person':
                raise ValueError('SETUP_REFERENCE_UNAVAILABLE')
            for act in actions:
                if act.get('type') not in SETUP_TYPES:
                    raise ValueError('SETUP_TYPE_UNSUPPORTED')
                references = [act[k] for k in ('entity_id', 'location_ref') if k in act]
                if act['type'] == 'scene_open':
                    participants = act.get('participants')
                    if not isinstance(participants, list): raise ValueError('SETUP_REFERENCE_UNAVAILABLE')
                    references.extend(participants)
                if any(not isinstance(ref, str) or ref not in entities for ref in references):
                    raise ValueError('SETUP_REFERENCE_UNAVAILABLE')
                if act['type'] == 'scene_open' and entities.get(act.get('location_ref'), {}).get('entity_type') not in (
                        'location', 'independent_station', 'independent_planet', 'mining_site', 'independent_agricultural_planet'):
                    raise ValueError('STORY_LOCATION_REFERENCE_INVALID')
                if act['type'] == 'life_control' and (act.get('entity_id') != actor or act.get('operation') != 'take'):
                    raise ValueError('SETUP_CONTROL_SCOPE')
                if act['type'] == 'life_profile':
                    if profiles.get(act.get('entity_id'), {}).get('revision', 0) != 0 or act.get('expected_revision') != 0:
                        raise ValueError('SETUP_EXISTING_BIOGRAPHY_IMMUTABLE')
                    if act.get('record', {}).get('source_kind') != 'authored_consistent_extension':
                        raise ValueError('SETUP_NEW_PROFILE_MUST_BE_AUTHORED')
        else:
            raise ValueError('PLAN_KIND_INVALID')
        return payload

    def envelope(self, job, kind, payload):
        a = self.host._engine()
        command = {'schema': a.DOMAIN_COMMAND_SCHEMA, 'command_id': job['id'],
            'base_save_set_id': job['base_identity']['save_set_id'], 'kind': 'story_' + kind,
            'actor_id': job['request']['actor_id'], 'authorization': 'host_intent',
            'authorization_ref': 'WEB:' + job['id']}
        command.update({'proposal': payload} if kind == 'turn' else payload)
        with self.lock:
            cost = a._domain_authorization_cost(command)
            now = json.loads((self.root / 'manifest.json').read_text())['game_time']
            return {'schema': 'HOST_COMMAND_INTENT_V1', 'decision': 'approved',
                'subject_id': command['actor_id'], 'parent_save_set_id': command['base_save_set_id'],
                'instruction_text': job['request']['intent'], 'evidence_ref': 'web-confirmation:' + job['id'],
                'valid_from': now, 'valid_until': now, 'targets': a._domain_command_targets(command),
                'limits': {k: str(cost[k]) for k in ('uses', 'gold_units', 'grey_units', 'quantity')},
                'command': command}

    def validate(self, payload, verdict):
        a = self.host._engine()
        with self.lock, a.narrative_review_context(payload, lambda exact: verdict if exact == payload else None):
            return a.validate_proposal(self.root, payload)

    def submit(self, job):
        with self.lock:
            method = self.host.submit if job['kind'] == 'turn' else self.host.setup
            before = self.identity()
            try:
                return method(job['envelope'], job['next_version'])
            except Exception as error:
                try:
                    # A validation exception is not an uncertain commit if the
                    # guard verifies that every authoritative file still belongs
                    # to the exact original manifest. A changed/invalid save stays
                    # recoverable under the original command ID.
                    self.recover()
                    unchanged = self.identity() == before and before == job.get('base_identity')
                except Exception:
                    unchanged = False
                if unchanged:
                    raise SubmissionNotCommitted(getattr(error, 'code', str(error).split(':')[0])) from error
                raise

    def next_version(self):
        version = json.loads((self.root / 'manifest.json').read_text())['save_version']
        major, minor = version[1:].split('.')
        return 'V' + major + '.' + str(int(minor) + 1)
