"""Copy generated class artwork and make small web previews, without changing saves.

Usage: python scripts/import_ship_artwork.py path/to/generation-plan.json
The plan contains one built-in image_gen output path and prompt for each class.
"""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main(plan_path):
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8'))
    catalog = json.loads((ROOT / 'seed/catalog.json').read_text(encoding='utf-8'))
    classes = {k: v for k, v in catalog['catalog_registry']['entities'].items()
               if v.get('entity_type') == 'ship_class'}
    assert {s['id'] for s in plan} == set(classes), 'All twelve fleet classes are required'
    assert len(plan) == len(classes), 'Duplicate ship class'
    out = ROOT / 'browser/assets/ships'
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    prompts = ['# 远航者舰队舰型插图生成提示词', '',
               '使用内置 image_gen，每个舰级独立生成一张；原图保持不变，WebP 仅作缩略显示。', '']
    digest = lambda data: hashlib.sha256(data).hexdigest()
    for entry in plan:
        model = classes[entry['id']]
        assert entry['name'] == model['name']
        assert str(entry['length']) + 'm' == model['immutable_specs']['length']
        assert re.fullmatch('[a-z]+', entry['slug'])
        raw = Path(entry['generated_path']).read_bytes()
        original = out / (entry['slug'] + '.png')
        if original.exists():
            assert original.read_bytes() == raw, 'Refusing to overwrite existing artwork'
        else:
            shutil.copy2(entry['generated_path'], original)
        with Image.open(original) as image:
            assert image.format == 'PNG'
            width, height = image.size
            preview = image.convert('RGB')
            preview.thumbnail((1024, 683), Image.Resampling.LANCZOS)
            preview.save(out / (entry['slug'] + '.webp'), 'WEBP', quality=85, method=6)
        row = {k: entry[k] for k in ('id', 'slug', 'name', 'length', 'role', 'features', 'frame_height')}
        row.update(original='./assets/ships/' + original.name,
                   preview='./assets/ships/' + entry['slug'] + '.webp',
                   width=width, height=height,
                   original_sha256=digest(raw),
                   preview_sha256=digest((out / (entry['slug'] + '.webp')).read_bytes()))
        rows.append(row)
        prompts.extend(['## ' + entry['name'] + ' · ' + str(entry['length']) + '米', '',
                        entry['prompt'], ''])
    public = [{k: v for k, v in s.items() if not k.endswith('_sha256')} for s in rows]
    (ROOT / 'browser/ship-image-data.js').write_bytes(
        ('// Class identities and lengths are checked against the unchanged catalog.\n'
         'export const shipImages=' + json.dumps(public, ensure_ascii=False, indent=1) + ';\n').encode('utf-8'))
    (out / 'artwork-manifest.json').write_bytes(json.dumps({
        'schema': 'VOYAGER_SHIP_ARTWORK_V1', 'generator': 'built-in image_gen',
        'basis': 'catalog ship classes and fixed armament; visual interpretation only',
        'max_length_m': max(s['length'] for s in rows), 'classes': rows,
    }, ensure_ascii=False, indent=2).encode('utf-8'))
    (out / 'prompts.md').write_bytes('\n'.join(prompts).encode('utf-8'))
    print(json.dumps({'classes': len(rows), 'original_bytes': sum((out / (s['slug'] + '.png')).stat().st_size for s in rows),
                      'preview_bytes': sum((out / (s['slug'] + '.webp')).stat().st_size for s in rows)}))


if __name__ == '__main__':
    main(sys.argv[1])
