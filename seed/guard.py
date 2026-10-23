#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voyager native component launcher / restore guard v2.23.0 with lossless XZ history verification."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,zipfile,shutil,re,tempfile,fcntl,gzip,uuid,threading,datetime,base64,zlib,lzma
from contextlib import contextmanager
GUARD_VERSION='2.23.0'
GUARD_PROTOCOL='4'
GUARD_MAGIC='VOYAGER_FLEET_SAVE_GUARD'
SCHEMAS={'VOYAGER_COMPONENT_SET_V2','VOYAGER_COMPONENT_SET_V1'}
COMPONENTS=('rules.json','catalog.json','state.json','tasks.json','events.jsonl','engine.py','guard.py')
DATA_COMPONENTS=('rules.json','catalog.json','state.json','tasks.json','events.jsonl')
COMMIT_JOURNAL='native_commit_journal.json'

def cold_archives(m):
    raw=m.get('cold_archives') or {}
    if not isinstance(raw,dict):return {}
    out={}
    for key,rec in raw.items():
        if not isinstance(rec,dict):continue
        path=str(rec.get('path') or '').strip().replace('\\','/')
        if not path or path.startswith('/') or '..' in Path(path).parts:continue
        out[path]=rec
    return out

def verify_cold_archives(root:Path,m:dict):
    errs=[];verified=[]
    for rel,rec in cold_archives(m).items():
        fp=root/rel
        if not fp.is_file():errs.append('COLD_ARCHIVE_MISSING:'+rel);continue
        expected=str(rec.get('file_sha256') or '')
        actual=sha_file(fp)
        if not expected or actual!=expected:errs.append('COLD_ARCHIVE_HASH:'+rel);continue
        try:
            with gzip.open(fp,'rt',encoding='utf-8') as f:obj=json.load(f)
            payload=obj.get('payload')
            ph=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            declared=str(rec.get('payload_sha256') or '')
            if declared and ph!=declared:errs.append('COLD_ARCHIVE_PAYLOAD_HASH:'+rel);continue
            if str(obj.get('payload_sha256') or '')!=ph:errs.append('COLD_ARCHIVE_WRAPPER_PAYLOAD_HASH:'+rel);continue
            if 'seq_start' in rec:_verify_history_payload(payload,rec)
            verified.append({'path':rel,'file_sha256':actual,'payload_sha256':ph})
        except Exception as e:errs.append('COLD_ARCHIVE_PARSE:'+rel+':'+type(e).__name__+':'+str(e))
    return verified,errs

def _verify_history_payload(payload,rec):
    """Independently verify old zlib and new XZ history without importing game code."""
    codec=payload.get('codec','zlib+base64')
    schemas={'zlib+base64':'VOYAGER_HISTORY_PAYLOAD_V1','lzma+xz+base64':'VOYAGER_HISTORY_PAYLOAD_V2'}
    if codec not in schemas or payload.get('schema')!=schemas[codec] or rec.get('codec','zlib+base64')!=codec:
        raise ValueError('HISTORY_ARCHIVE_CODEC')
    for key in ('seq_start','seq_end','event_count','compressed_sha256'):
        if payload.get(key)!=rec.get(key):raise ValueError('HISTORY_ARCHIVE_BINDING:'+key)
    comp=base64.b64decode(payload['payload_b64'],validate=True)
    if hashlib.sha256(comp).hexdigest()!=rec['compressed_sha256']:raise ValueError('HISTORY_COMPRESSED_HASH')
    decoder=(lzma.LZMADecompressor(format=lzma.FORMAT_XZ,memlimit=64*1024*1024)
             if codec=='lzma+xz+base64' else zlib.decompressobj())
    raw=decoder.decompress(comp,128*1024*1024+1)
    if len(raw)>128*1024*1024:raise ValueError('HISTORY_DECODED_TOO_LARGE')
    if not decoder.eof or decoder.unused_data:raise ValueError('HISTORY_TRUNCATED_OR_TRAILING_STREAM')
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=rec['events_sha256']:raise ValueError('HISTORY_EVENTS_HASH')
    if codec=='lzma+xz+base64':
        for key,value in (('compressed_bytes',len(comp)),('uncompressed_bytes',len(raw)),('uncompressed_sha256',digest),('events_sha256',digest)):
            if payload.get(key)!=value or rec.get(key)!=value:raise ValueError('HISTORY_SIZE_OR_HASH:'+key)
    events=[json.loads(line) for line in raw.splitlines() if line.strip()]
    if len(events)!=rec['event_count'] or not events:raise ValueError('HISTORY_EVENT_COUNT')
    if [event.get('seq') for event in events]!=list(range(rec['seq_start'],rec['seq_end']+1)):
        raise ValueError('HISTORY_SEQUENCE')

def sha_file(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def sha_zip_member(z,n):
    h=hashlib.sha256()
    with z.open(n,'r') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def bundle(h):return hashlib.sha256(''.join(f'{k}\t{h[k]}\n' for k in sorted(h)).encode()).hexdigest()

def manifest_fingerprint(m):
    # The authority SID alone does not identify development, archives or policies.
    return hashlib.sha256(json.dumps(m,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

@contextmanager
def guard_lock(base:Path):
    runtime=base/'.runtime';runtime.mkdir(parents=True,exist_ok=True)
    fd=os.open(base/'.game_engine.lock',os.O_CREAT|os.O_RDWR,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX);yield
    finally:
        try:fcntl.flock(fd,fcntl.LOCK_UN)
        finally:os.close(fd)

def validate_dir(root:Path,strict=True,allow_historical_guard=False):
    p=root/'manifest.json'
    if not p.is_file():return None,['MANIFEST_MISSING']
    try:m=json.loads(p.read_text('utf-8'))
    except Exception as e:return None,[f'MANIFEST_PARSE:{type(e).__name__}:{e}']
    errs=[]
    if m.get('schema') not in SCHEMAS:errs.append('MANIFEST_SCHEMA')
    comps=m.get('components') or {}
    for rel,rec in cold_archives(m).items():
        fp=root/rel
        if not fp.is_file():errs.append('COLD_ARCHIVE_MISSING:'+rel);continue
        expected=str(rec.get('file_sha256') or '')
        if not expected or sha_file(fp)!=expected:errs.append('COLD_ARCHIVE_HASH:'+rel)
    for fn in COMPONENTS:
        fp=root/fn
        if not fp.is_file():errs.append('MISSING:'+fn);continue
        if comps.get(fn)!=sha_file(fp):errs.append('HASH:'+fn)
    if m.get('schema')=='VOYAGER_COMPONENT_SET_V2':
        dh={fn:sha_file(root/fn) for fn in DATA_COMPONENTS if (root/fn).is_file()}
        th={fn:sha_file(root/fn) for fn in ('engine.py','guard.py') if (root/fn).is_file()}
        if m.get('authority_components')!=dh:errs.append('AUTHORITY_HASH_SET')
        if m.get('tool_bindings')!=th:errs.append('TOOL_BINDINGS')
        if len(dh)==len(DATA_COMPONENTS):
            ab=bundle(dh);tb=bundle({**dh,**th})
            if m.get('authority_bundle_sha256')!=ab:errs.append('AUTHORITY_BUNDLE')
            if m.get('component_bundle_sha256')!=tb:errs.append('COMPONENT_BUNDLE')
            if m.get('save_set_id')!=f"SAVESET-{m.get('save_version')}-{ab[:16]}":errs.append('SAVESET_ID')
        if 'legacy_runtime_view' in (m.get('runtime') or {}):errs.append('LEGACY_RUNTIME_VIEW_FLAG_FORBIDDEN')
        if 'legacy_compat' in json.dumps(m,ensure_ascii=False):errs.append('LEGACY_COMPAT_CURRENT_FLAG_FORBIDDEN')
    if strict:
        expected=set(COMPONENTS)|{'manifest.json'}
        extra=[x.name for x in root.iterdir() if x.is_file() and x.name not in expected and not x.name.startswith('VOYAGER_SOURCE_') and not x.name.startswith('.')]
        if extra:errs.append('UNEXPECTED_TOPLEVEL:'+','.join(sorted(extra)))
    if (root/'.runtime'/'legacy_compat').exists():errs.append('LEGACY_COMPAT_DIRECTORY_PRESENT')
    try:compile((root/'engine.py').read_bytes(),str(root/'engine.py'),'exec')
    except Exception as e:errs.append('ENGINE_COMPILE:'+str(e))
    try:compile((root/'guard.py').read_bytes(),str(root/'guard.py'),'exec')
    except Exception as e:errs.append('GUARD_COMPILE:'+str(e))
    # Runtime protocol/version binding is a hard gate, not merely a file-hash check.
    if not errs:
        try:
            env=os.environ.copy();env['VOYAGER_ROOT']=str(root)
            cp=subprocess.run([sys.executable,str(root/'engine.py'),'--version-info'],env=env,text=True,capture_output=True,timeout=20)
            info=json.loads(cp.stdout) if cp.returncode==0 else {}
            if cp.returncode!=0:errs.append('ENGINE_VERSION_INFO_EXEC:'+str(cp.returncode))
            if str(info.get('engine_protocol'))!=str(m.get('engine_protocol')):errs.append('ENGINE_PROTOCOL_BINDING')
            if str(info.get('engine_version'))!=str(m.get('engine_version')):errs.append('ENGINE_VERSION_BINDING')
            if str(m.get('guard_protocol'))!=GUARD_PROTOCOL:errs.append('GUARD_PROTOCOL_BINDING')
            if str(m.get('guard_version'))!=GUARD_VERSION:
                old_text=(root/'guard.py').read_text('utf-8')
                match=re.search(r"^GUARD_VERSION\s*=\s*['\"]([^'\"]+)['\"]",old_text,re.M)
                if not allow_historical_guard or not match or match.group(1)!=str(m.get('guard_version')):
                    errs.append('GUARD_VERSION_BINDING')
        except Exception as e:errs.append('RUNTIME_BINDING:'+type(e).__name__+':'+str(e))
    return (m if not errs else None),errs

def development_sources(manifest):
    rec=manifest.get('development_sources') or {}
    if not rec:return {}
    files=rec.get('files')
    if rec.get('schema')!='VOYAGER_DEV_SOURCES_V1' or not isinstance(files,dict) or not files:
        raise ValueError('DEVELOPMENT_SOURCES_SCHEMA')
    for name,digest in files.items():
        if not isinstance(name,str) or not name.startswith('development/') or name.endswith('/') or '..' in Path(name).parts or not re.fullmatch(r'[0-9a-f]{64}',str(digest)):
            raise ValueError('DEVELOPMENT_SOURCE_ENTRY_INVALID')
    return files

def development_intact(root,manifest):
    for rel,digest in development_sources(manifest).items():
        p=root/rel
        if not p.is_file() or p.is_symlink() or sha_file(p)!=digest:return False
    return True

def inspect_transport(pack:Path):
    try:
        with zipfile.ZipFile(pack,'r') as z:
            names=z.namelist()
            if len(names)!=len(set(names)) or 'manifest.json' not in names:return None,'SOURCE_ZIP_FILESET'
            m=json.loads(z.read('manifest.json').decode('utf-8'))
            if m.get('schema') not in SCHEMAS:return None,'SOURCE_ZIP_SCHEMA'
            archives=cold_archives(m);dev=development_sources(m);expected={'manifest.json',*COMPONENTS,*archives.keys(),*dev.keys()}
            if set(names)!=expected:return None,'SOURCE_ZIP_FILESET'
            # Routine inspection hashes only live authority/tool members. Cold archives are
            # deliberately not decompressed or parsed during normal boot.
            actual={n:hashlib.sha256(z.read(n)).hexdigest() for n in COMPONENTS}
            if m.get('components')!=actual:return None,'SOURCE_ZIP_COMPONENT_HASHES'
            for rel,archive_rec in archives.items():
                expected_hash=str(archive_rec.get('file_sha256') or '')
                if not expected_hash or sha_zip_member(z,rel)!=expected_hash:return None,'SOURCE_ZIP_COLD_ARCHIVE_HASH:'+rel
            for rel,digest in dev.items():
                if sha_zip_member(z,rel)!=digest:return None,'SOURCE_ZIP_DEVELOPMENT_HASH:'+rel
            data={n:actual[n] for n in DATA_COMPONENTS};tools={n:actual[n] for n in ('engine.py','guard.py')}
            if m.get('authority_components')!=data or m.get('tool_bindings')!=tools:return None,'SOURCE_ZIP_BINDINGS'
            authority_bundle=bundle(data);transport_bundle=bundle(actual)
            if m.get('authority_bundle_sha256')!=authority_bundle or m.get('component_bundle_sha256')!=transport_bundle:return None,'SOURCE_ZIP_BUNDLE'
        sv=str(m.get('save_version') or '');vm=re.fullmatch(r'V(\d+)\.(\d+)',sv)
        if not vm:return None,'SOURCE_ZIP_VERSION'
        if m.get('save_set_id')!=f'SAVESET-{sv}-{authority_bundle[:16]}':return None,'SOURCE_ZIP_SAVESET_ID'
        return {'path':pack,'manifest':m,'version':(int(vm.group(1)),int(vm.group(2))),'mtime':pack.stat().st_mtime},None
    except Exception as e:return None,f'{type(e).__name__}:{e}'

def find_transport(base:Path):
    packs=sorted(p for p in base.glob('VOYAGER_SOURCE_V*.zip') if p.is_file())
    valid=[];invalid=[]
    for p in packs:
        rec,err=inspect_transport(p)
        if rec:valid.append(rec)
        else:invalid.append({'name':p.name,'error':err})
    if not valid:raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_ZIP_NONE_VALID','count':len(packs),'invalid':invalid},ensure_ascii=False))
    highest=max(x['version'] for x in valid);top=[x for x in valid if x['version']==highest]
    sids={str(x['manifest'].get('save_set_id') or '') for x in top}
    if len(sids)!=1:raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_ZIP_FORK','version':f'V{highest[0]}.{highest[1]}','save_set_ids':sorted(sids)},ensure_ascii=False))
    if len({x['manifest'].get('component_bundle_sha256') for x in top})!=1:
        raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_ZIP_COMPONENT_FORK','save_set_id':next(iter(sids))},ensure_ascii=False))
    if len({manifest_fingerprint(x['manifest']) for x in top})!=1:
        raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_ZIP_MANIFEST_FORK','save_set_id':next(iter(sids))},ensure_ascii=False))
    return sorted(top,key=lambda x:x['path'].name)[0]['path']

def extract_transport(pack:Path,base:Path,inspected=None):
    inspect_error=None
    if inspected is None:inspected,inspect_error=inspect_transport(pack)
    if not inspected:raise SystemExit(json.dumps({'status':'FAIL','error':inspect_error},ensure_ascii=False))
    with zipfile.ZipFile(pack,'r') as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or 'manifest.json' not in names:raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_ZIP_FILESET','names':names},ensure_ascii=False))
        m=json.loads(z.read('manifest.json').decode('utf-8'))
        if manifest_fingerprint(m)!=manifest_fingerprint(inspected['manifest']):
            raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_CHANGED_SINCE_INSPECTION'},ensure_ascii=False))
        archives=cold_archives(m);dev=development_sources(m);expected={'manifest.json',*COMPONENTS,*archives.keys(),*dev.keys()}
        if set(names)!=expected:raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_ZIP_FILESET','names':names},ensure_ascii=False))
        sid=str(m.get('save_set_id') or 'unknown')
        target=base/'.runtime'/'component_sources'/re.sub(r'[^A-Za-z0-9._-]','_',sid);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            old,_=validate_dir(target,strict=True)
            if old and old.get('save_set_id')!=m.get('save_set_id'):
                raise SystemExit(json.dumps({'status':'FAIL','error':'CACHED_SOURCE_DIVERGED','cached_save_set_id':old.get('save_set_id'),'requested_save_set_id':m.get('save_set_id'),'preserved_root':str(target)},ensure_ascii=False))
            if old and old.get('save_set_id')==m.get('save_set_id') and manifest_fingerprint(old)==manifest_fingerprint(m) and development_intact(target,m):return target,old
        tmp=Path(tempfile.mkdtemp(prefix=target.name+'.tmp.',dir=target.parent))
        try:
            for n in names:
                dest=tmp/n;dest.parent.mkdir(parents=True,exist_ok=True)
                if n in archives:
                    # Stream the already-compressed archive member; do not parse the inner gzip/JSON.
                    with z.open(n,'r') as src,dest.open('wb') as dst:shutil.copyfileobj(src,dst,1024*1024)
                else:dest.write_bytes(z.read(n))
            mm,errs=validate_dir(tmp,strict=True)
            if not mm:raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_COMPONENT_INVALID','errors':errs},ensure_ascii=False))
            if not development_intact(tmp,mm):raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_DEVELOPMENT_INVALID'},ensure_ascii=False))
            if target.exists():
                old,_=validate_dir(target,strict=True)
                if old and old.get('save_set_id')!=mm.get('save_set_id'):
                    raise SystemExit(json.dumps({'status':'FAIL','error':'CACHED_SOURCE_DIVERGED','cached_save_set_id':old.get('save_set_id'),'requested_save_set_id':mm.get('save_set_id'),'preserved_root':str(target)},ensure_ascii=False))
                if old and old.get('save_set_id')==mm.get('save_set_id') and manifest_fingerprint(old)==manifest_fingerprint(mm) and development_intact(target,mm):return target,old
                quarantine=target.with_name(target.name+'.invalid.'+uuid.uuid4().hex)
                os.replace(target,quarantine)
            os.replace(tmp,target)
            return target,mm
        finally:
            if tmp.exists():shutil.rmtree(tmp,ignore_errors=True)

def _recovery_trace(base,event,**fields):
    path=base/'.runtime'/'recovery_trace.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
    row={'event':event,'pid':os.getpid(),'thread':threading.get_ident(),'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**fields}
    with path.open('ab') as stream:
        stream.write((json.dumps(row,sort_keys=True)+'\n').encode());stream.flush();os.fsync(stream.fileno())


def _classify_components(base,parent,target,names):
    classes={}
    for name in sorted(names):
        path=base/name
        if not path.is_file() or path.is_symlink():raise ValueError('UNKNOWN_MODIFICATION:'+name)
        digest=sha_file(path)
        if digest not in {parent[name],target[name]}:raise ValueError('UNKNOWN_MODIFICATION:'+name)
        classes[name]='BOTH' if parent[name]==target[name] else 'PARENT' if digest==parent[name] else 'TARGET'
    return classes


def _journal_digest(j):
    return hashlib.sha256(json.dumps(j,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def finalized_journal_state(base,j):
    """A resurrected name is inert only with an exact durable final proof.
    No metadata-only exemption: every current component must equal one recorded
    completed byte set, and a later set must have a recorded lineage chain.
    """
    token=j.get('transaction_id');tomb=base/'.runtime'/'finalized_transactions'/str(token)
    if not tomb.is_file() or tomb.is_symlink():return False
    row=json.loads(tomb.read_text())
    if row.get('journal_digest')!=_journal_digest(j):raise ValueError('FINALIZED_JOURNAL_CONTENT_CHANGED')
    names={'manifest.json',*COMPONENTS}
    records=[row]
    for path in tomb.parent.iterdir():
        if path.is_file() and not path.is_symlink() and path!=tomb:
            try:records.append(json.loads(path.read_text()))
            except Exception:continue
    actual={n:sha_file(base/n) if (base/n).is_file() and not (base/n).is_symlink() else None for n in names}
    matching=next((r for r in records if r.get('final_hashes')==actual),None)
    if matching is None:raise ValueError('FINALIZED_JOURNAL_UNKNOWN_CURRENT_BYTES')
    ancestor=row.get('final_save_set_id');cursor=matching.get('final_save_set_id');seen=set()
    parents={r.get('final_save_set_id'):r.get('parent_save_set_id') for r in records}
    while cursor!=ancestor and cursor not in seen:
        seen.add(cursor);cursor=parents.get(cursor)
        if cursor is None:raise ValueError('FINALIZED_JOURNAL_UNPROVEN_LINEAGE')
    if cursor!=ancestor:raise ValueError('FINALIZED_JOURNAL_LINEAGE_CYCLE')
    return True


def active_journal(base,name):
    path=base/'.runtime'/name
    if not path.exists():return False
    if path.is_symlink():raise ValueError('JOURNAL_SYMLINK')
    j=json.loads(path.read_text())
    return not finalized_journal_state(base,j)


def _finish_journal(base,path,j,outcome):
    # Keep finalized identity before deleting the active name. Late writes through
    # either engine or Guard are rejected against this durable tombstone.
    token=j.get('transaction_id')
    if token:
        tomb=base/'.runtime'/'finalized_transactions'/token
        tomb.parent.mkdir(parents=True,exist_ok=True)
        data=(json.dumps({'transaction_id':token,'outcome':outcome,'journal_sha256':sha_file(path),'journal_digest':_journal_digest(j),'parent_save_set_id':j.get('parent_save_set_id'),'final_save_set_id':json.loads((base/'manifest.json').read_text()).get('save_set_id'),'final_hashes':{n:sha_file(base/n) for n in ['manifest.json',*COMPONENTS]}})+'\n').encode()
        _repair_replace_bytes(tomb,data)
    expected=hashlib.sha256(json.dumps(j,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    current=json.loads(path.read_text())
    if hashlib.sha256(json.dumps(current,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=expected:raise ValueError('JOURNAL_CHANGED_BEFORE_CLEANUP')
    ident=path.stat().st_ino;_recovery_trace(base,'FINALIZED',transaction_id=token,outcome=outcome,journal_inode=ident)
    path.unlink();_sync_dir(path.parent)


def write_journal(base,path,j):
    token=j.get('transaction_id')
    if not isinstance(token,str) or not re.fullmatch(r'[0-9a-f]{32}|[0-9a-f]{64}',token):raise ValueError('TRANSACTION_ID_REQUIRED')
    if (base/'.runtime'/'finalized_transactions'/token).exists():raise ValueError('FINALIZED_TRANSACTION_REPLAY_REFUSED')
    if path.exists():
        old=json.loads(path.read_text())
        if old.get('transaction_id')==token and old==j:return
        if not finalized_journal_state(base,old):raise ValueError('ACTIVE_JOURNAL_OVERWRITE_REFUSED')
        parked=base/'.runtime'/'finalized_transactions'/(old['transaction_id']+'.journal')
        os.replace(path,parked);_sync_dir(path.parent)
        _recovery_trace(base,'STALE_FINALIZED_JOURNAL_PARKED',transaction_id=old['transaction_id'],journal_sha256=sha_file(parked))
    _repair_replace_bytes(path,(json.dumps(j,ensure_ascii=False,sort_keys=True)+'\n').encode())
    _recovery_trace(base,'PREPARED',transaction_id=token,journal_inode=path.stat().st_ino,journal_sha256=sha_file(path),caller='write_journal')


def recover_interrupted_commit(base:Path):
    base=Path(base).resolve();journal=base/'.runtime'/COMMIT_JOURNAL
    if not journal.is_file():return None,['COMMIT_JOURNAL_MISSING']
    try:
        if journal.is_symlink():raise ValueError('JOURNAL_SYMLINK')
        j=json.loads(journal.read_text('utf-8'))
        if finalized_journal_state(base,j):
            _recovery_trace(base,'STALE_FINALIZED_JOURNAL_OBSERVED',transaction_id=j.get('transaction_id'),journal_inode=journal.stat().st_ino)
            return json.loads((base/'manifest.json').read_text()),[]
        if j.get('schema')!='VOYAGER_NATIVE_COMMIT_JOURNAL_V2':
            # V1 did not freeze target fingerprints. A mixed set cannot be safely
            # distinguished from a third-party write; retain evidence for diagnosis.
            raise ValueError('LEGACY_JOURNAL_TARGET_PROOF_MISSING')
        if j.get('root')!=str(base):raise ValueError('JOURNAL_ROOT_MISMATCH')
        token=j.get('transaction_id')
        if not isinstance(token,str) or not re.fullmatch(r'[0-9a-f]{32}',token):raise ValueError('JOURNAL_ID_INVALID')
        names={'manifest.json',*COMPONENTS};snaps={};manifests={}
        for label in ('parent','target'):
            path=(base/str(j.get(label+'_snapshot') or '')).resolve()
            if not path.is_relative_to(base/'.runtime') or path==base/'.runtime':raise ValueError('SNAPSHOT_PATH_INVALID')
            hashes=j.get(label+'_hashes')
            if not isinstance(hashes,dict) or set(hashes)!=names:raise ValueError('SNAPSHOT_HASH_SET')
            if any(not (path/n).is_file() or (path/n).is_symlink() or sha_file(path/n)!=h for n,h in hashes.items()):raise ValueError('SNAPSHOT_BYTES:'+label)
            manifest,errs=validate_dir(path,strict=True,allow_historical_guard=True)
            if errs or not manifest:raise ValueError('SNAPSHOT_BINDING:'+label+':'+','.join(errs))
            _,errs=verify_cold_archives(path,manifest)
            if errs:raise ValueError('SNAPSHOT_ARCHIVES:'+label+':'+','.join(errs))
            if manifest.get('save_set_id')!=j[label+'_save_set_id']:raise ValueError('SNAPSHOT_SAVESET:'+label)
            if (path/'development').exists() and not development_intact(path,manifest):raise ValueError('SNAPSHOT_DEVELOPMENT:'+label)
            snaps[label]=path;manifests[label]=manifest
        if manifests['target'].get('parent_save_set_id')!=j['parent_save_set_id']:raise ValueError('TARGET_PARENT_BINDING')
        classes=_classify_components(base,j['parent_hashes'],j['target_hashes'],names)
        label='target' if sha_file(base/'manifest.json')==j['target_hashes']['manifest.json'] else 'parent'
        # Cold/development dependencies can be shared or versioned; classify their
        # actual bytes too, before writing any component.
        all_dependencies=set(cold_archives(manifests['parent']))|set(cold_archives(manifests['target']))
        if (base/'development').exists():all_dependencies|=set(development_sources(manifests['parent']))|set(development_sources(manifests['target']))
        for rel in sorted(all_dependencies):
            values=[]
            for key in ('parent','target'):
                m=manifests[key];values.append((cold_archives(m).get(rel) or {}).get('file_sha256') or development_sources(m).get(rel))
            current=base/rel
            actual=sha_file(current) if current.is_file() and not current.is_symlink() else None
            if current.is_symlink() or (actual is None and (current.exists() or None not in values)) or actual not in values:raise ValueError('UNKNOWN_MODIFICATION:'+rel)
        _recovery_trace(base,'CLASSIFIED',transaction_id=token,outcome=label,components=classes)
        for name in sorted(names-{'manifest.json'}):_durable_copy(snaps[label]/name,base/name)
        for rel in sorted(all_dependencies):
            source=snaps[label]/rel;dest=base/rel
            wanted=(cold_archives(manifests[label]).get(rel) or {}).get('file_sha256') or development_sources(manifests[label]).get(rel)
            if wanted:
                if not source.is_file() or sha_file(source)!=wanted:raise ValueError('FROZEN_DEPENDENCY_MISSING:'+rel)
                dest.parent.mkdir(parents=True,exist_ok=True);_durable_copy(source,dest)
            elif dest.is_file():dest.unlink();_sync_dir(dest.parent)
        _durable_copy(snaps[label]/'manifest.json',base/'manifest.json')
        verified,errs=validate_dir(base,strict=True,allow_historical_guard=True)
        if errs or not verified:raise ValueError('RESTORE_VERIFY:'+','.join(errs))
        _finish_journal(base,journal,j,label)
        return verified,[]
    except Exception as ex:
        _recovery_trace(base,'RECOVERY_REFUSED',error=str(ex))
        return None,[str(ex)]


def _sync_dir(path):
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:os.fsync(fd)
    finally:os.close(fd)

def _durable_copy(src,dest):
    tmp=dest.with_name('.'+dest.name+'.restore.'+str(os.getpid())+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with src.open('rb') as a,tmp.open('wb') as b:
            shutil.copyfileobj(a,b,1024*1024);b.flush();os.fsync(b.fileno())
        os.replace(tmp,dest);_sync_dir(dest.parent)
    finally:tmp.unlink(missing_ok=True)

def _version(m):
    match=re.fullmatch(r'V(\d+)\.(\d+)',str(m.get('save_version') or ''))
    if not match:raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_VERSION_INVALID'},ensure_ascii=False))
    return tuple(map(int,match.groups()))

def select_source(base:Path,explicit=None):
    """Select only complete, verified sources; file mtime never orders SAVESETs."""
    if explicit:
        p=Path(explicit).resolve();rec,err=inspect_transport(p)
        if not rec:raise SystemExit(json.dumps({'status':'FAIL','error':err},ensure_ascii=False))
        target=base/'.runtime'/'component_sources'/str(rec['manifest']['save_set_id'])
        cached=target.is_dir()
        root,m=extract_transport(p,base,rec)
        return root,m,{'kind':'zip','path':str(p),'local_sync':'cached_extraction' if cached else 'extracted_new'}
    direct=None;errs=[]
    if (base/'manifest.json').is_file():
        direct,errs=validate_dir(base,strict=True,allow_historical_guard=True)
        if direct and (base/'development').exists() and not development_intact(base,direct):
            direct=None;errs.append('DEVELOPMENT_BINDING')
        if direct and (base/'.runtime'/COMMIT_JOURNAL).is_file():
            recovered,recovery_errs=recover_interrupted_commit(base)
            if not recovered or recovered.get('save_set_id')!=direct.get('save_set_id'):
                raise SystemExit(json.dumps({'status':'FAIL','error':'COMMIT_JOURNAL_TARGET_MISMATCH','errors':recovery_errs},ensure_ascii=False))
            direct=recovered
        if not direct:
            direct,recovery_errs=recover_interrupted_commit(base)
            errs+=recovery_errs
    else:
        direct,recovery_errs=recover_interrupted_commit(base)
        errs+=recovery_errs
    valid=[];invalid=[]
    for p in base.glob('VOYAGER_SOURCE_V*.zip'):
        if not p.is_file():continue
        rec,err=inspect_transport(p)
        if rec:valid.append(rec)
        else:invalid.append({'name':p.name,'error':err})
    if not direct and not valid:
        raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_NONE_VALID','directory_errors':errs,'invalid_zips':invalid},ensure_ascii=False))
    records=[{'manifest':direct,'version':_version(direct),'path':None}] if direct else []
    records.extend(valid)
    highest=max(x['version'] for x in records);top=[x for x in records if x['version']==highest]
    sids={x['manifest'].get('save_set_id') for x in top}
    if len(sids)>1:
        raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_FORK','version':f'V{highest[0]}.{highest[1]}','save_set_ids':sorted(sids)},ensure_ascii=False))
    bundles={x['manifest'].get('component_bundle_sha256') for x in top}
    if len(bundles)>1:
        raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_COMPONENT_FORK','save_set_id':next(iter(sids))},ensure_ascii=False))
    if len({manifest_fingerprint(x['manifest']) for x in top})!=1:
        raise SystemExit(json.dumps({'status':'FAIL','error':'SOURCE_MANIFEST_FORK','save_set_id':next(iter(sids))},ensure_ascii=False))
    if direct and _version(direct)==highest:
        return base,direct,{'kind':'directory','path':str(base),'local_sync':'current_directory'}
    chosen=sorted((x for x in top if x.get('path')),key=lambda x:x['path'].name)[0]
    p=chosen['path'];target=base/'.runtime'/'component_sources'/str(chosen['manifest']['save_set_id']);cached=target.is_dir()
    root,m=extract_transport(p,base,chosen)
    return root,m,{'kind':'zip','path':str(p),'local_sync':'cached_extraction' if cached else 'extracted_new'}

def _verified_receipt(root,m,selection):
    names=['manifest.json',*COMPONENTS,*cold_archives(m)]
    return {'root':str(root.resolve()),'save_set_id':m['save_set_id'],'manifest_sha256':sha_file(root/'manifest.json'),
            'stats':{name:[(root/name).stat().st_size,(root/name).stat().st_mtime_ns,(root/name).stat().st_ino] for name in names},
            'selected_source':selection,'guard_validated':True,'coverage':'integrity_only','checks':['component_hashes','protocol_binding','cold_file_hashes'],'validator_version':GUARD_VERSION,'authority_digest':m.get('authority_bundle_sha256')}

def _repair_replace_bytes(path,data):
    tmp=path.with_name('.'+path.name+'.repair.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('xb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path);_sync_dir(path.parent)
    finally:tmp.unlink(missing_ok=True)


REPAIR_JOURNAL='consistency_repair_journal.json'

def recover_consistency_repair(base:Path):
    """Recover exact verified snapshots; this never invents or executes a repair."""
    base=Path(base).resolve();journal=base/'.runtime'/REPAIR_JOURNAL
    if not journal.is_file():return None
    j=json.loads(journal.read_text('utf-8'))
    if finalized_journal_state(base,j):return {'status':'FINALIZED_STALE','transaction_id':j.get('transaction_id'),'save_set_id':json.loads((base/'manifest.json').read_text()).get('save_set_id')}
    if j.get('schema')!='VOYAGER_CONSISTENCY_REPAIR_JOURNAL_V1':raise ValueError('REPAIR_JOURNAL_SCHEMA')
    token=j.get('transaction_id')
    if not isinstance(token,str) or not re.fullmatch(r'[0-9a-f]{64}',token):raise ValueError('REPAIR_JOURNAL_ID')
    if j.get('root')!=str(base):raise ValueError('REPAIR_JOURNAL_ROOT')
    home=base/'.runtime'/'consistency_repairs'/token
    if home.is_symlink() or not home.resolve().is_relative_to((base/'.runtime').resolve()):raise ValueError('REPAIR_SNAPSHOT_PATH')
    expected_names=set(COMPONENTS)|{'manifest.json'}
    snapshots={}
    for label in ('parent','target'):
        path=home/label
        if path.is_symlink():raise ValueError('REPAIR_SNAPSHOT_SYMLINK')
        declared=j.get(label+'_hashes')
        if not isinstance(declared,dict) or set(declared)!=expected_names:raise ValueError('REPAIR_SNAPSHOT_FILESET')
        if any(not (path/n).is_file() or (path/n).is_symlink() or sha_file(path/n)!=h for n,h in declared.items()):raise ValueError('REPAIR_SNAPSHOT_HASH:'+label)
        m,errs=validate_dir(path,strict=True)
        if errs:raise ValueError('REPAIR_SNAPSHOT_BINDING:'+label+':'+','.join(errs))
        _,errs=verify_cold_archives(path,m)
        if errs:raise ValueError('REPAIR_SNAPSHOT_ARCHIVES:'+label+':'+','.join(errs))
        materialized=j.get('development_materialized')
        if type(materialized) is not bool:raise ValueError('REPAIR_DEVELOPMENT_SCOPE_MISSING')
        if materialized:
            if not development_intact(path,m):raise ValueError('REPAIR_SNAPSHOT_DEVELOPMENT:'+label)
        elif (path/'development').exists():raise ValueError('REPAIR_SNAPSHOT_DEVELOPMENT_SCOPE_CHANGED')
        if sha_file(path/'guard.py')!=sha_file(Path(__file__).resolve()):raise ValueError('REPAIR_GUARD_BINDING')
        snapshots[label]=path
    parent=j['parent_hashes'];target=j['target_hashes']
    # Unknown third-party writes are not overwritten with a guessed recovery.
    _classify_components(base,parent,target,expected_names)
    manifest_hash=sha_file(base/'manifest.json')
    label='target' if manifest_hash==target['manifest.json'] else 'parent'
    # Frozen dependencies remain identical through this metadata/reference repair.
    manifest=json.loads((snapshots[label]/'manifest.json').read_text('utf-8'))
    for rel,rec in cold_archives(manifest).items():
        if not (base/rel).is_file() or sha_file(base/rel)!=rec['file_sha256']:raise ValueError('REPAIR_RECOVERY_COLD_SOURCE_CHANGED:'+rel)
    if j['development_materialized']:
        if not development_intact(base,manifest):raise ValueError('REPAIR_RECOVERY_DEVELOPMENT_CHANGED')
    elif (base/'development').exists():raise ValueError('REPAIR_RECOVERY_DEVELOPMENT_SCOPE_CHANGED')
    for name in sorted(expected_names-{'manifest.json'}):_durable_copy(snapshots[label]/name,base/name)
    _durable_copy(snapshots[label]/'manifest.json',base/'manifest.json')
    # Retain an inspectable receipt and both snapshots; only clear the active journal.
    receipt=home/'recovery_receipt.json'
    _repair_replace_bytes(receipt,(json.dumps({'schema':'VOYAGER_REPAIR_RECOVERY_V1','transaction_id':token,'outcome':label,
                                     'save_set_id':manifest.get('save_set_id')},ensure_ascii=False)+'\n').encode())
    _finish_journal(base,journal,j,label)
    return {'status':'RECOVERED','outcome':label,'transaction_id':token,'save_set_id':manifest.get('save_set_id')}


def verify_project_visual_assets(root: Path, resolve_label=None, source_dir=None):
    """Check bundled image index only on boot; resolve original artwork from external ZIPs on demand."""
    gate=root/'development'/'visual_assets'/'舰队图片来源闸门.py'
    if not gate.is_file():return False,{'status':'BLOCK','error':'IMAGE_GATE_MISSING'}
    cmd=[sys.executable,str(gate)]
    if source_dir:cmd.extend(['--root',str(source_dir)])
    cmd.extend(['resolve',resolve_label] if resolve_label else ['index-check'])
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=80)
        payload=json.loads(proc.stdout) if proc.stdout.strip() else {'error':proc.stderr.strip()}
        return proc.returncode==0 and payload.get('status')=='PASS',payload
    except Exception as e:return False,{'status':'BLOCK','error':str(e)}

def main(argv=None):
    ap=argparse.ArgumentParser(prog='guard.py');ap.add_argument('--resume',action='store_true');ap.add_argument('--check',action='store_true');ap.add_argument('--source');ap.add_argument('--image-resolve',metavar='NAME');ap.add_argument('--image-source-dir',metavar='DIR');args=ap.parse_args(argv)
    base=Path(os.environ.get('VOYAGER_ROOT',str(Path(__file__).resolve().parent))).resolve()
    with guard_lock(base):
        try:recover_consistency_repair(base)
        except Exception as ex:
            print(json.dumps({'status':'FAIL','error':'REPAIR_RECOVERY_FAILED','detail':str(ex)},ensure_ascii=False));return 1
        if (base/'.runtime'/COMMIT_JOURNAL).is_file():
            recovered,errs=recover_interrupted_commit(base)
            if errs:
                print(json.dumps({'status':'FAIL','error':'COMMIT_RECOVERY_FAILED','errors':errs}));return 1
        root,m,selection=select_source(base,args.source)
    images_ok,image_report=verify_project_visual_assets(root,args.image_resolve if args.image_resolve else None,args.image_source_dir)
    if not images_ok:
        print(json.dumps({'status':'FAIL','error':'ORIGINAL_IMAGE_GATE_FAILED','detail':image_report},ensure_ascii=False));return 1
    if args.image_resolve:
        print(json.dumps({'status':'PASS','save_set_id':m.get('save_set_id'),'image':image_report},ensure_ascii=False));return 0
    if args.check:
        verified,aerrs=verify_cold_archives(root,m)
        if aerrs:
            print(json.dumps({'status':'FAIL','error':'COLD_ARCHIVE_VERIFY_FAILED','errors':aerrs,'save_set_id':m.get('save_set_id')},ensure_ascii=False));return 1
        env=os.environ.copy();env['VOYAGER_ROOT']=str(root)
        cp=subprocess.run([sys.executable,str(root/'engine.py'),'readiness'],env=env,text=True,capture_output=True)
        try:readiness=json.loads(cp.stdout)
        except Exception:readiness={'status':'BLOCKED','errors':['ENGINE_READINESS_UNAVAILABLE']}
        print(json.dumps({'status':'PASS','coverage':'integrity_only','readiness':readiness,'guard_version':GUARD_VERSION,'guard_protocol':GUARD_PROTOCOL,'save_set_id':m.get('save_set_id'),'save_version':m.get('save_version'),'schema':m.get('schema'),'native_eight_component':True,'indexed_external_images':image_report.get('index_records'),'original_images_embedded':0,'root':str(root),'selected_source':selection,'cold_archives_verified':verified},ensure_ascii=False));return 0
    env=os.environ.copy();env['VOYAGER_ROOT']=str(root);env['VOYAGER_DELIVERY_ROOT']=str(base)
    if selection['kind']=='zip':env['VOYAGER_TRANSPORT_PATH']=selection['path']
    receipt=_verified_receipt(root,m,selection);read_fd,write_fd=os.pipe()
    try:
        os.write(write_fd,json.dumps(receipt,ensure_ascii=False,separators=(',',':')).encode());os.close(write_fd)
        env['VOYAGER_GUARD_RECEIPT_FD']=str(read_fd)
        cp=subprocess.run([sys.executable,str(root/'engine.py'),'boot'],env=env,text=True,capture_output=True,pass_fds=(read_fd,))
    finally:
        os.close(read_fd)
    if cp.stdout:sys.stdout.write(cp.stdout)
    if cp.stderr:sys.stderr.write(cp.stderr)
    return cp.returncode
if __name__=='__main__':raise SystemExit(main())
