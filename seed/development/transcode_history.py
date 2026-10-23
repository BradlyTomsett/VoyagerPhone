#!/usr/bin/env python3
"""Offline copy-only history container migration. Requires the new codec-capable tools.

Never migrate a live directory in place. Publish a new directory only after verifying
every logical event byte, metadata, hot record, authority file and cold dependency.
"""
import argparse,copy,hashlib,importlib.util,json,os,pathlib,shutil,sys,tempfile
sys.dont_write_bytecode=True
P=pathlib.Path

def load(path):
    spec=importlib.util.spec_from_file_location('history_'+path.stem,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def transcode_copy(source,output,version):
    source=P(source).resolve();output=P(output).resolve()
    if output.exists() or source==output or source in output.parents or output in source.parents:
        raise ValueError('NEW_EXTERNAL_OUTPUT_REQUIRED')
    guard=load(source/'guard.py')
    with guard.guard_lock(source):
        for journal in ('native_commit_journal.json','consistency_repair_journal.json'):
            if (source/'.runtime'/journal).exists():raise ValueError('SOURCE_RECOVERY_REQUIRED')
        return _transcode_copy_locked(source,output,version)

def _transcode_copy_locked(source,output,version):
    source=P(source).resolve();output=P(output).resolve()
    if output.exists() or source==output or source in output.parents or output in source.parents:
        raise ValueError('NEW_EXTERNAL_OUTPUT_REQUIRED')
    os.environ['VOYAGER_ROOT']=str(source)
    api=load(source/'engine.py');guard=load(source/'guard.py')
    if api.HISTORY_EPOCH_CODEC!='lzma+xz+base64':raise ValueError('CODEC_CAPABLE_TOOLS_REQUIRED')
    old,errors=guard.validate_dir(source,strict=True)
    if errors or not old or not guard.development_intact(source,old):raise ValueError('SOURCE_NOT_INTACT:'+str(errors))
    original_manifest=(source/'manifest.json').read_bytes()
    if api.parse_version(version)<=api.parse_version(old['save_version']):raise ValueError('NEWER_SAVE_VERSION_REQUIRED')
    _,errors=guard.verify_cold_archives(source,old)
    if errors:raise ValueError('SOURCE_ARCHIVES_NOT_INTACT:'+str(errors))
    metadata,events,raws=api.read_history_raw(source/'events.jsonl')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=P(tempfile.mkdtemp(prefix='.'+output.name+'.history-',dir=output.parent))
    try:
        def ignore(path,names):
            skipped={n for n in names if n in ('.runtime','__pycache__','.game_engine.lock')}
            if P(path).resolve()==source:skipped.add('archives')
            return skipped
        # Construct the target dependency set directly. Old containers are never
        # copied into the target, so publication cannot retain an unbound second set.
        shutil.copytree(source,stage,dirs_exist_ok=True,ignore=ignore)
        manifest=copy.deepcopy(old);archives=manifest['cold_archives'];lines=[];changed=[]
        old_epochs={json.loads(line)['archive_ref']:json.loads(line) for line in (source/'events.jsonl').read_bytes().splitlines()
                    if json.loads(line).get('record_type')=='history_epoch' and json.loads(line).get('archive_ref')}
        for row in archives.values():
            epoch=old_epochs.get(row['path'])
            if epoch and epoch.get('codec')!=api.HISTORY_EPOCH_CODEC:continue
            dest=stage/row['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/row['path'],dest)
        for line in (source/'events.jsonl').read_bytes().splitlines(keepends=True):
            rec=json.loads(line)
            if rec.get('record_type')!='history_epoch' or rec.get('codec')==api.HISTORY_EPOCH_CODEC:
                lines.append(line);continue
            if not rec.get('archive_ref'):raise ValueError('EXTERNAL_HISTORY_REQUIRED')
            key=f"HISTORY_{rec['seq_start']:06d}_{rec['seq_end']:06d}"
            if key not in archives or archives[key]['path']!=rec['archive_ref']:raise ValueError('ARCHIVE_LOCATOR_NOT_BOUND')
            _,segment_raw=api._decode_history_epoch_record(rec,0,source)
            replacement=copy.deepcopy(rec);replacement.update(api._make_history_epoch_record(segment_raw,rec['epoch_index']))
            replacement,row=api._store_history_epoch_archive(stage,replacement)
            for field in ('seq_start','seq_end','event_count','events_sha256','uncompressed_sha256','uncompressed_bytes'):
                if replacement[field]!=rec[field]:raise ValueError('LOSSLESS_PROOF_FAILED:'+field)
            archives[key]=row
            lines.append(json.dumps(replacement,ensure_ascii=False,separators=(',',':')).encode()+b'\n')
            changed.append({'key':key,'old_path':rec['archive_ref'],'new_path':row['path'],
                            'old_bytes':(source/rec['archive_ref']).stat().st_size,'new_bytes':(stage/row['path']).stat().st_size,
                            'events_sha256':rec['events_sha256'],'event_count':rec['event_count']})
        (stage/'events.jsonl').write_bytes(b''.join(lines))
        manifest['migration_lineage']={'from_save_set_id':old['save_set_id'],
            'from_layout':'native_eight_component_v4_tiered_history','to_layout':'native_eight_component_v4_tiered_history',
            'game_time_advanced':False,'history_container_codec_upgrade':{'from':'zlib+base64' if changed else api.HISTORY_EPOCH_CODEC,'to':api.HISTORY_EPOCH_CODEC,
                'segments':len(changed),'logical_bytes_preserved':True,'new_logical_events':0}}
        (stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':'))+'\n')
        # The manifest is the commit point in this unpublished copy.
        referenced={r['path'] for r in archives.values()}
        actual={str(p.relative_to(stage)) for p in (stage/'archives').rglob('*') if p.is_file()}
        if actual!=referenced:raise ValueError('TARGET_ARCHIVE_FILESET_MISMATCH')
        check_meta,check_events,check_raws=api.read_history_raw(stage/'events.jsonl')
        if metadata!=check_meta or check_raws!=raws or check_events!=events:raise ValueError('HISTORY_LOGICAL_BYTES_CHANGED')
        for name in ('rules.json','catalog.json','state.json','tasks.json'):
            if (stage/name).read_bytes()!=(source/name).read_bytes():raise ValueError('GAME_AUTHORITY_CHANGED:'+name)
        api._component_write_manifest_native(stage,version,old['save_set_id'],manifest['migration_lineage'])
        current,errors=guard.validate_dir(stage,strict=True);_,archive_errors=guard.verify_cold_archives(stage,current or {})
        if errors or archive_errors or not current or not guard.development_intact(stage,current):
            raise ValueError('TARGET_NOT_INTACT:'+str(errors+archive_errors))
        if {str(p.relative_to(stage)) for p in (stage/'archives').rglob('*') if p.is_file()}!=referenced:
            raise ValueError('TARGET_ARCHIVE_FILESET_CHANGED_DURING_VALIDATION')
        closing,closing_errors=guard.validate_dir(source,strict=True)
        if closing_errors or closing!=old or (source/'manifest.json').read_bytes()!=original_manifest or not guard.development_intact(source,old):
            raise ValueError('SOURCE_CHANGED_DURING_MIGRATION')
        os.replace(stage,output)
        return {'schema':'VOYAGER_HISTORY_CODEC_UPGRADE_V1','status':'PASS','source_save_set_id':old['save_set_id'],
                'save_set_id':current['save_set_id'],'output':str(output),'logical_events':len(events),
                'logical_sha256':hashlib.sha256(b'\n'.join(raws)+b'\n').hexdigest(),'logical_bytes_exact':True,
                'metadata_exact':True,'new_logical_events':0,'game_authority_bytes_exact':True,'segments':changed,
                'cold_history_bytes_before':sum(r['old_bytes'] for r in changed),
                'cold_history_bytes_after':sum(r['new_bytes'] for r in changed)}
    finally:
        if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=P,required=True)
    parser.add_argument('--output',type=P,required=True);parser.add_argument('--version',required=True);args=parser.parse_args()
    try:print(json.dumps(transcode_copy(args.source,args.output,args.version),ensure_ascii=False))
    except Exception as ex:print(json.dumps({'status':'REFUSED','error':str(ex)},ensure_ascii=False));raise SystemExit(1)
