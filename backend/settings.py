"""Owner-only model configuration, outside Git and game exports."""
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

FIELDS = {'api_key', 'base_url', 'model_id', 'review_model_id', 'protocol'}

def load_settings(directory):
    file = Path(directory) / 'model-settings.json'
    if not file.exists():
        return {}
    value = json.loads(file.read_text())
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError('MODEL_SETTINGS_INVALID')
    return value

def validated_settings(value, previous):
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError('MODEL_SETTINGS_FIELDS_INVALID')
    if any(not isinstance(v, str) or len(v) > 2048 for v in value.values()):
        raise ValueError('MODEL_SETTINGS_VALUE_INVALID')
    result = {**previous, **{k: v.strip() for k, v in value.items()}}
    if not value.get('api_key', '').strip():
        result['api_key'] = previous.get('api_key', '')
    result.setdefault('base_url', 'https://api.openai.com/v1')
    result.setdefault('protocol', 'responses')
    result['base_url'] = result['base_url'].rstrip('/')
    url = urlsplit(result['base_url'])
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('MODEL_BASE_URL_REQUIRES_HTTPS')
    if (previous.get('api_key') and result['base_url'] != previous.get('base_url')
            and not value.get('api_key', '').strip()):
        raise ValueError('NEW_PROVIDER_REQUIRES_KEY')
    if not result.get('api_key') or not result.get('model_id'):
        raise ValueError('MODEL_KEY_AND_ID_REQUIRED')
    if any('\r' in v or '\n' in v for v in result.values()):
        raise ValueError('MODEL_SETTINGS_VALUE_INVALID')
    if result.get('protocol') not in ('responses', 'chat_completions'):
        raise ValueError('MODEL_PROTOCOL_UNSUPPORTED')
    return result

def save_settings(directory, value):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.model-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, ensure_ascii=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, directory / 'model-settings.json')
        parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(parent)
        finally: os.close(parent)
    finally:
        if os.path.exists(name): os.unlink(name)

def public_settings(value):
    return {k: v for k, v in value.items() if k != 'api_key'} | {'key_saved': bool(value.get('api_key'))}
