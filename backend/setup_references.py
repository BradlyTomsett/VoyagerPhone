"""Resolve public names exactly; stage identities already present in the save.

This module never writes world state, creates biographies, moves people or grants
knowledge. Identity registration remains part of the reviewed, confirmed setup.
"""
import copy
import hashlib
import re
import unicodedata

LOCATION_TYPES = {'location', 'independent_station', 'independent_planet', 'mining_site', 'independent_agricultural_planet'}


def name_key(value):
    return re.sub(r'[\s·•・]', '', unicodedata.normalize('NFKC', str(value)).casefold())


class SetupReferenceError(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__('SETUP_REFERENCE_UNAVAILABLE')


def source_people(state):
    """Only the explicit current shop staff and named four companions, no scans."""
    cover = state.get('world_state_overrides', {}).get('freeport_xilu9_current', {}).get('hawke_commercial_cover', {})
    root = 'state:world_state_overrides.freeport_xilu9_current.hawke_commercial_cover.'
    candidates = []
    for name in cover.get('shadow_people', {}).get('aliases', {}).get('members', []):
        if re.fullmatch(r'Q[2-5]', str(name)):
            candidates.append((name, '霍克同行人员，公开身份为退役游商', root + 'shadow_people.aliases.members'))
    for index, row in enumerate(cover.get('local_employees', [])):
        if isinstance(row, dict) and isinstance(row.get('name'), str) and row['name'].strip():
            candidates.append((row['name'], '余火咖啡正式员工；' + str(row.get('role', '')), root + 'local_employees.' + str(index)))
    guard = cover.get('reto_guard_contract_live')
    if isinstance(guard, dict) and guard.get('occupation') == '余火民用安保':
        candidates.append(('雷托', guard['occupation'], root + 'reto_guard_contract_live'))
    registry = state.get('entity_registry', {}).get('entities', {})
    result = {}
    for name, role, basis in candidates:
        matches = [(eid, row) for eid, row in registry.items() if isinstance(row, dict)
                   and name_key(name) in {name_key(n) for n in [row.get('canonical_name', ''), *row.get('aliases', [])]}]
        # Existing public identities are reused through the normal registry;
        # hidden identities and ambiguous aliases never become new choices.
        if matches:
            continue
        identity = 'PER-WEB-SOURCE-' + hashlib.sha256(name_key(name).encode()).hexdigest()[:16].upper()
        if identity in registry:
            continue
        result[identity] = {'canonical_name': name, 'entity_type': 'person',
                            'aliases': [], 'role': role[:300], 'basis_ref': basis}
    return result


def resolve_setup(payload, actor, entities):
    normalized = copy.deepcopy(payload)
    issues = []
    index = {}
    for eid, row in entities.items():
        names = [row.get('canonical_name', ''), *row.get('aliases', [])]
        full = row.get('canonical_name', '')
        if row.get('entity_type') == 'person' and '·' in full and len(full.split('·')[0]) >= 2:
            names.append(full.split('·')[0])
        for name in names:
            if name: index.setdefault(name_key(name), set()).add(eid)

    def resolve(value, kind):
        candidates = {value} if isinstance(value, str) and value in entities else index.get(name_key(value), set()) if isinstance(value, str) else set()
        expected = LOCATION_TYPES if kind == 'place' else {'person'}
        valid = [eid for eid in candidates if entities[eid].get('entity_type') in expected]
        if len(valid) == 1 and len(candidates) == 1:
            return valid[0]
        row = entities.get(value, {}) if isinstance(value, str) else {}
        name = row.get('canonical_name') or value
        if not isinstance(name, str) or re.match(r'^(?:PER|LOC|ORG|PLACE|STA|SYS|REG|NPC)-', name) or len(name) > 80:
            name = {'actor': '当前视角人物', 'person': '草案中一位人物', 'place': '草案中的地点'}[kind]
        issues.append({'kind': kind, 'name': name, 'reason': 'ambiguous' if len(candidates) > 1 else 'wrong_type' if candidates else 'missing'})
        return value

    # The selected actor must be an exact host-supplied identity, not model text.
    if entities.get(actor, {}).get('entity_type') != 'person':
        resolve(actor, 'actor')
        if not issues: issues.append({'kind': 'actor', 'name': '当前视角人物', 'reason': 'missing'})
    for action in normalized.get('actions', []):
        if not isinstance(action, dict): continue
        if 'entity_id' in action: action['entity_id'] = resolve(action['entity_id'], 'person')
        if 'location_ref' in action: action['location_ref'] = resolve(action['location_ref'], 'place')
        if action.get('type') == 'scene_open' and isinstance(action.get('participants'), list):
            action['participants'] = [resolve(value, 'person') for value in action['participants']]
    if issues: raise SetupReferenceError(issues)
    return normalized
