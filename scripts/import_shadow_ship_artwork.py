"""Import built-in image_gen outputs; bind Shadow artwork to unchanged vessel IDs.

Usage: python scripts/import_shadow_ship_artwork.py generation-plan.json
The private plan supplies generated_path, prompt, slug, vessels and visual metadata.
"""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def vessel_length(vessel):
    if vessel.get('length_m'):
        return int(vessel['length_m'])
    match = re.search(r'(\d+)\s*m', vessel.get('type', ''), re.I)
    assert match, 'Vessel needs an explicit source length'
    return int(match[1])


def main(plan_path):
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8-sig'))
    vessels = json.loads((ROOT / 'seed/state.json').read_text(encoding='utf-8'))['shadow_fleet']['vessels']
    bindings = [vessel for entry in plan for vessel in entry['vessels']]
    assert len(plan) == 18 and len({entry['slug'] for entry in plan}) == 18
    assert len(bindings) == len(set(bindings)) == len(vessels) == 19
    assert set(bindings) == set(vessels), 'Every original named vessel must be covered exactly once'
    out = ROOT / 'browser/assets/ships/shadow'
    out.mkdir(parents=True, exist_ok=True)
    artworks, rows = [], []
    prompts = ['# 暗影舰队舰型插图生成提示词', '',
               '使用内置 image_gen。18 张独立原图覆盖19条单舰档案；暗鸦11号与12号共用舰型外观，按各舰实际长度显示。',
               '原图不作修改；WebP 仅缩小用于网页预览。图片是外观示意，不新增性能或装备。', '']
    digest = lambda data: hashlib.sha256(data).hexdigest()
    for entry in plan:
        assert re.fullmatch('[a-z0-9-]+', entry['slug'])
        assert entry['length'] == max(vessel_length(vessels[identity]) for identity in entry['vessels'])
        original = out / (entry['slug'] + '.png')
        raw = Path(entry['generated_path']).read_bytes()
        if original.exists():
            assert original.read_bytes() == raw, 'Refusing to replace existing artwork'
        else:
            shutil.copy2(entry['generated_path'], original)
        preview_path = out / (entry['slug'] + '.webp')
        with Image.open(original) as image:
            assert image.format == 'PNG'
            width, height = image.size
            assert 400 <= entry['frame_height'] <= height
            preview = image.convert('RGB')
            preview.thumbnail((1024, 683), Image.Resampling.LANCZOS)
            preview.save(preview_path, 'WEBP', quality=85, method=6)
        visual = {key: entry[key] for key in ('slug', 'role', 'features', 'frame_height')}
        visual.update(original='./assets/ships/shadow/' + original.name,
                      preview='./assets/ships/shadow/' + preview_path.name,
                      width=width, height=height)
        bound = []
        for identity in entry['vessels']:
            vessel = vessels[identity]
            row = dict(visual, id=identity, vessel_id=identity, name=vessel['name'],
                       length=vessel_length(vessel))
            rows.append(row)
            bound.append({key: row[key] for key in ('id', 'name', 'length')})
        artworks.append(dict(visual, name=entry['name'], vessels=bound,
                             original_sha256=digest(raw),
                             preview_sha256=digest(preview_path.read_bytes())))
        prompts.extend(['## ' + entry['name'], '',
                        '舰长：' + '、'.join(str(row['length']) + '米' for row in bound), '',
                        '[原图](' + original.name + ')', '', entry['prompt'], ''])
    (ROOT / 'browser/shadow-ship-image-data.js').write_bytes(
        ('// Vessel identities and exact lengths are checked against the unchanged save.\n'
         'export const shadowShipImages=' + json.dumps(rows, ensure_ascii=False, indent=1) + ';\n').encode('utf-8'))
    (out / 'artwork-manifest.json').write_bytes(json.dumps({
        'schema': 'VOYAGER_SHADOW_SHIP_ARTWORK_V1', 'generator': 'built-in image_gen',
        'basis': 'unchanged shadow_fleet vessel records and armament_audit_current; visual interpretation only',
        'artwork_count': len(artworks), 'vessel_count': len(rows), 'artworks': artworks,
    }, ensure_ascii=False, indent=2).encode('utf-8'))
    (out / 'prompts.md').write_bytes('\n'.join(prompts).encode('utf-8'))
    print(json.dumps({'artworks': len(artworks), 'vessels': len(rows),
                      'original_bytes': sum((out / (s['slug'] + '.png')).stat().st_size for s in artworks),
                      'preview_bytes': sum((out / (s['slug'] + '.webp')).stat().st_size for s in artworks)}))


if __name__ == '__main__':
    main(sys.argv[1])
