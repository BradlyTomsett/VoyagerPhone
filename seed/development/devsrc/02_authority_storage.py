# === VOYAGER_DEV_MODULE: authority_storage ===
def parse_index_manifest(text: str) -> Optional[dict]:
    def exactly_one(pattern:str):
        ms=list(re.finditer(pattern,text,re.M))
        return ms[0] if len(ms)==1 else None
    def optional_one(pattern:str):
        ms=list(re.finditer(pattern,text,re.M))
        if len(ms)>1: raise ValueError("duplicate INDEX manifest field")
        return ms[0] if ms else None
    try:
        hashes: Dict[str, str] = {}
        for fn in SRC_ORDER:
            m=exactly_one(rf"^- `{re.escape(fn)}`：`([0-9a-f]{{64}})`$")
            if not m:return None
            hashes[fn]=m.group(1)
        mb=exactly_one(r"^- `bundle_sha256`：`([0-9a-f]{64})`$")
        ms=exactly_one(r"^- `save_set_id`：`([^`]+)`$")
        mv=exactly_one(r"^> \*\*当前存档版本\*\*：V(\d+)\.(\d+)$")
        if not (mb and ms and mv):return None
        out={"hashes":hashes,"bundle":mb.group(1),"save_set_id":ms.group(1),"version":(int(mv.group(1)),int(mv.group(2)))}
        fields={
            "engine_version":r"^- `game_engine_version`：`([^`]+)`$",
            "engine_sha256":r"^- `game_engine_sha256`：`([0-9a-f]{64})`$",
            "save_guard_sha256":r"^- `save_guard_sha256`：`([0-9a-f]{64})`$",
            "parent_save_set_id":r"^- `parent_save_set_id`：`([^`]+)`$",
            "commit_format":r"^- `commit_format`：`([^`]+)`$",
            "save_storage_format":r"^- `save_storage_format`：`([^`]+)`$",
            "active_slot":r"^- `active_slot`：`([AB])`$",
            "active_pointer_format":r"^- `active_pointer_format`：`([^`]+)`$",
        }
        for k,pat in fields.items():
            m=optional_one(pat)
            if m:out[k]=m.group(1)
        return out
    except (ValueError,TypeError):
        return None


def read_commit(path: Path) -> Optional[dict]:
    p = path / "COMMIT.json"
    if not p.is_file():
        return None
    try:
        x = strict_json_load(p)
        return x if isinstance(x, dict) else None
    except Exception:
        return None


def _v130_layer_validate_authority_set_01(base: Path) -> Optional[dict]:
    """Validate the five authority files using INDEX's manifest only; directory name/COMMIT are irrelevant."""
    if any(not (base / fn).is_file() for fn in AUTH_FILES):
        return None
    try:
        index_bytes = (base / "INDEX.md").read_bytes()
        parsed = parse_index_manifest(index_bytes.decode("utf-8"))
        if not parsed:
            return None
        actual = {fn: sha256_file(base / fn) for fn in SRC_ORDER}
        b = bundle_hash(actual)
        sid = f"SAVESET-{version_text(parsed['version'])}-{b[:16]}"
        if actual != parsed["hashes"] or b != parsed["bundle"] or parsed["save_set_id"] != sid:
            return None
        return {
            "base": base, "version": parsed["version"], "bundle": b, "save_set_id": sid,
            "manifest": actual, "index": parsed, "index_sha256": sha256_bytes(index_bytes),
        }
    except Exception:
        return None



def _ab_pointer_path(root:Path=ROOT)->Path:
    return root/AB_ACTIVE_FILE


def _ab_slot_path(root:Path,slot:str)->Path:
    if slot not in AB_SLOT_FILES:raise EngineError(f"AB_SLOT_INVALID:{slot}")
    return root/AB_SLOT_FILES[slot]


def _ab_index_for_slot(index_text:str,slot:str)->str:
    if slot not in AB_SLOT_FILES:raise EngineError(f"AB_SLOT_INVALID:{slot}")
    index_text=_replace_or_insert(index_text,r"^- `save_storage_format`：`[^`]+`$",f"- `save_storage_format`：`{AB_SLOT_FORMAT}`")
    index_text=_replace_or_insert(index_text,r"^- `active_slot`：`[AB]`$",f"- `active_slot`：`{slot}`")
    index_text=_replace_or_insert(index_text,r"^- `active_pointer_format`：`[^`]+`$",f"- `active_pointer_format`：`{AB_ACTIVE_FORMAT}`")
    return index_text


def _ab_validate_slot_file(path:Path,expected_slot:Optional[str]=None)->Optional[dict]:
    """Validate a self-contained A/B slot without making runtime slot identity an INDEX fact.

    Legacy slots may still contain the three historical INDEX A/B fields; when present they
    must agree with SLOT.json.  New slots carry slot identity only in SLOT.json / SAVE_ACTIVE.json.
    """
    if not path.is_file():return None
    try:
        with zipfile.ZipFile(path,'r') as z:
            names=z.namelist()
            if len(names)!=len(set(names)) or set(names)!=set(AB_REQUIRED_MEMBERS):return None
            raw={name:z.read(name) for name in AB_REQUIRED_MEMBERS}
        sm=strict_json_loads(raw['SLOT.json'].decode('utf-8'))
        if not isinstance(sm,dict) or sm.get('format')!=AB_SLOT_FORMAT:return None
        slot=str(sm.get('slot') or '')
        if slot not in AB_SLOT_FILES or (expected_slot is not None and slot!=expected_slot):return None
        idx_text=raw['INDEX.md'].decode('utf-8');idx=parse_index_manifest(idx_text)
        if not idx:return None
        # Backward compatibility only: tolerate old INDEX runtime fields but never require them.
        if idx.get('save_storage_format') not in (None,AB_SLOT_FORMAT):return None
        if idx.get('active_slot') not in (None,slot):return None
        if idx.get('active_pointer_format') not in (None,AB_ACTIVE_FORMAT):return None
        actual={fn:sha256_bytes(raw[fn]) for fn in SRC_ORDER};b=bundle_hash(actual);sid=f"SAVESET-{version_text(idx['version'])}-{b[:16]}"
        if actual!=idx.get('hashes') or b!=idx.get('bundle') or sid!=idx.get('save_set_id'):return None
        if sm.get('version')!=version_text(idx['version']) or sm.get('save_set_id')!=sid or sm.get('bundle_sha256')!=b:return None
        if sm.get('index_sha256')!=sha256_bytes(raw['INDEX.md']) or sm.get('source_sha256')!=actual:return None
        return {'slot':slot,'path':path,'version':idx['version'],'save_set_id':sid,'bundle':b,'index':idx,'index_sha256':sm['index_sha256'],'manifest':actual,'raw':raw,'slot_sha256':sha256_file(path),'slot_manifest':sm}
    except Exception:
        return None


def _ab_read_pointer(root:Path=ROOT)->Optional[dict]:
    p=_ab_pointer_path(root)
    if not p.is_file():return None
    try:
        x=strict_json_load(p)
        if not isinstance(x,dict) or x.get('format')!=AB_ACTIVE_FORMAT:return None
        slot=str(x.get('active_slot') or '')
        if slot not in AB_SLOT_FILES:return None
        rec=_ab_validate_slot_file(_ab_slot_path(root,slot),slot)
        if rec is None:return None
        if x.get('slot_file')!=rec['path'].name or x.get('slot_sha256')!=rec['slot_sha256']:return None
        if x.get('save_set_id')!=rec['save_set_id'] or x.get('bundle_sha256')!=rec['bundle'] or x.get('index_sha256')!=rec['index_sha256'] or x.get('version')!=version_text(rec['version']):return None
        out=dict(x);out['slot_record']=rec;return out
    except Exception:
        return None


def _ab_active_slot(root:Path=ROOT)->Optional[dict]:
    p=_ab_read_pointer(root)
    return (p or {}).get('slot_record') if p else None


def _ab_storage_present(root:Path=ROOT)->bool:
    return _ab_pointer_path(root).exists() or any(_ab_slot_path(root,s).exists() for s in AB_SLOT_FILES)


def _ab_resolve_active(root:Path=ROOT,repair_pointer:bool=False)->Optional[dict]:
    """Resolve committed slot fail-closed; optionally repair a missing pointer from a matching root cache."""
    pp=_ab_pointer_path(root)
    if pp.exists():
        rec=_ab_active_slot(root)
        if rec is None:raise EngineError('AB_ACTIVE_POINTER_OR_SLOT_CORRUPT')
        return rec
    present=[s for s in AB_SLOT_FILES if _ab_slot_path(root,s).exists()]
    if not present:return None
    root_auth=validate_authority_set(root);matches=[]
    if root_auth is not None:
        for s in present:
            r=_ab_validate_slot_file(_ab_slot_path(root,s),s)
            if r is not None and r.get('save_set_id')==root_auth.get('save_set_id'):matches.append(r)
    if len(matches)==1 and repair_pointer:
        _ab_write_pointer(root,matches[0]);return matches[0]
    raise EngineError('AB_STORAGE_PRESENT_WITHOUT_VALID_POINTER')


def _ab_write_slot_from_source(source:Path,root:Path,slot:str)->dict:
    """Write one complete inactive slot, fsync/rename it, then validate exact bytes."""
    if slot not in AB_SLOT_FILES:raise EngineError(f"AB_SLOT_INVALID:{slot}")
    # Slot identity is runtime infrastructure.  Preserve the authority INDEX byte-for-byte;
    # SLOT.json and SAVE_ACTIVE.json are the only A/B slot authorities.
    raw={fn:(source/fn).read_bytes() for fn in AUTH_FILES}
    idx_text=raw['INDEX.md'].decode('utf-8');idx=parse_index_manifest(idx_text)
    if not idx:raise EngineError('AB_SLOT_SOURCE_INDEX_INVALID')
    actual={fn:sha256_bytes(raw[fn]) for fn in SRC_ORDER};b=bundle_hash(actual);sid=f"SAVESET-{version_text(idx['version'])}-{b[:16]}"
    if actual!=idx.get('hashes') or b!=idx.get('bundle') or sid!=idx.get('save_set_id'):
        raise EngineError('AB_SLOT_SOURCE_MANIFEST_MISMATCH')
    sm={'format':AB_SLOT_FORMAT,'slot':slot,'version':version_text(idx['version']),'save_set_id':sid,'bundle_sha256':b,'index_sha256':sha256_bytes(raw['INDEX.md']),'source_sha256':actual,'parent_save_set_id':idx.get('parent_save_set_id'),'created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    target=_ab_slot_path(root,slot);tmp=root/f".{target.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
            for fn in AUTH_FILES:z.writestr(fn,raw[fn])
            z.writestr('SLOT.json',json.dumps(sm,ensure_ascii=False,separators=(',',':'))+'\n')
        # fsync file before atomic rename where supported.
        try:
            with tmp.open('rb') as f:os.fsync(f.fileno())
        except OSError:pass
        os.replace(tmp,target)
    finally:
        try:tmp.unlink(missing_ok=True)
        except OSError:pass
    rec=_ab_validate_slot_file(target,slot)
    if rec is None or rec['save_set_id']!=sid:raise EngineError('AB_SLOT_POSTWRITE_VERIFY_FAILED')
    return rec


def _ab_write_pointer(root:Path,slot_rec:dict)->dict:
    payload={'format':AB_ACTIVE_FORMAT,'active_slot':slot_rec['slot'],'slot_file':slot_rec['path'].name,'slot_sha256':slot_rec['slot_sha256'],'save_set_id':slot_rec['save_set_id'],'bundle_sha256':slot_rec['bundle'],'index_sha256':slot_rec['index_sha256'],'version':version_text(slot_rec['version']),'committed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    p=_ab_pointer_path(root);tmp=root/f".{AB_ACTIVE_FILE}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    tmp.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    try:
        with tmp.open('rb') as f:os.fsync(f.fileno())
    except OSError:pass
    os.replace(tmp,p)
    try:
        fd=os.open(str(root),os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    except OSError:pass
    chk=_ab_read_pointer(root)
    if chk is None or chk.get('save_set_id')!=slot_rec['save_set_id']:raise EngineError('AB_POINTER_POSTWRITE_VERIFY_FAILED')
    return chk


def _ab_materialize_root(root:Path,slot_rec:dict)->dict:
    """Restore mutable compatibility caches from the committed slot; INDEX is written last."""
    raw=slot_rec['raw'];stage=Path(tempfile.mkdtemp(prefix='.ab_materialize_',dir=str(root)))
    try:
        for fn in AUTH_FILES:(stage/fn).write_bytes(raw[fn])
        if validate_authority_set(stage) is None:raise EngineError('AB_MATERIALIZE_STAGE_INVALID')
        for fn in [x for x in AUTH_FILES if x!='INDEX.md']+['INDEX.md']:
            target=root/fn
            try:
                if target.exists():target.chmod(0o644)
            except OSError:pass
            os.replace(stage/fn,target)
        auth=validate_authority_set(root)
        if auth is None or auth.get('save_set_id')!=slot_rec['save_set_id']:raise EngineError('AB_MATERIALIZE_POSTVERIFY_FAILED')
        for fn in AUTH_FILES:
            try:(root/fn).chmod(0o444)
            except OSError:pass
        return {'status':'RESTORED','save_set_id':slot_rec['save_set_id'],'slot':slot_rec['slot']}
    finally:
        shutil.rmtree(stage,ignore_errors=True)


def _ab_seed_from_snapshot(root:Path,snapshot:dict)->dict:
    """One-time legacy migration seed: parent becomes slot A and active pointer A."""
    cur=_ab_active_slot(root)
    if cur is not None:return cur
    # A malformed pointer with existing slot files is ambiguous: never guess.
    if _ab_pointer_path(root).exists() or any(_ab_slot_path(root,s).exists() for s in AB_SLOT_FILES):
        raise EngineError('AB_STORAGE_PARTIAL_OR_POINTER_INVALID')
    rec=_ab_write_slot_from_source(Path(snapshot['dir']),root,'A');_ab_write_pointer(root,rec);_ab_materialize_root(root,rec)
    return rec


def _ab_opposite(slot:str)->str:
    return 'B' if slot=='A' else 'A'

def _parse_parent_version_from_sid(sid: Optional[str]) -> Optional[str]:
    if not sid:
        return None
    m = re.fullmatch(r"SAVESET-(V\d+\.\d+)-[0-9a-f]{16}", str(sid))
    return m.group(1) if m else None


def _write_recovery_commit(snapshot_dir: Path, authority: dict, root: Path, recovery_anchor: bool,
                           parent_snapshot: Optional[dict] = None) -> dict:
    idx = authority["index"]
    parent_sid = idx.get("parent_save_set_id")
    if parent_snapshot is not None:
        parent_sid = parent_snapshot["save_set_id"]
        parent_version = version_text(parent_snapshot["version"])
        parent_bundle = parent_snapshot["bundle"]
    else:
        parent_version = _parse_parent_version_from_sid(parent_sid)
        parent_bundle = None
    def exact_bound_tool(paths: Iterable[Path], expected_hash: Optional[str]) -> Optional[Path]:
        candidates=[];seen=set()
        for q in paths:
            try:
                key=str(q.resolve())
                if key in seen:continue
                seen.add(key)
                if q.is_file() and (not expected_hash or sha256_file(q)==expected_hash):candidates.append(q)
            except OSError:continue
        return candidates[0] if candidates else None
    engine_expected=idx.get("engine_sha256")
    guard_expected=idx.get("save_guard_sha256")
    engine_paths=[root/".game_engine.py"]+sorted(root.glob("GAME_ENGINE_v*.py"),reverse=True)+[Path(__file__).resolve()]
    guard_paths=[root/".save_guard.py"]+sorted(root.glob("SAVE_GUARD_v*.py"),reverse=True)
    engine=exact_bound_tool(engine_paths,engine_expected)
    guard=exact_bound_tool(guard_paths,guard_expected)
    # Preserve the authority INDEX's historical tool binding when reconstructing a snapshot.
    # Recovery may be performed by a newer engine; that must not rewrite what the recovered save originally declared.
    tools = {
        "game_engine_version": idx.get("engine_version") or ENGINE_VERSION,
        "game_engine_sha256": idx.get("engine_sha256") or (sha256_file(engine) if engine and engine.is_file() else None),
        "save_guard_sha256": idx.get("save_guard_sha256") or (sha256_file(guard) if guard and guard.is_file() else None),
    }
    c = {
        "format": COMMIT_FORMAT,
        "version": version_text(authority["version"]),
        "save_set_id": authority["save_set_id"],
        "bundle_sha256": authority["bundle"],
        "index_sha256": authority["index_sha256"],
        "source_sha256": authority["manifest"],
        "parent_save_set_id": parent_sid,
        "parent_version": parent_version,
        "parent_bundle_sha256": parent_bundle,
        "recovery_anchor": bool(recovery_anchor),
        "recovery_note": "Reconstructed from self-validating authority files; no game facts changed.",
        "tools": tools,
    }
    (snapshot_dir / "COMMIT.json").write_text(json.dumps(c, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    tdir = snapshot_dir / "_tools"
    tdir.mkdir(exist_ok=True)
    if engine and engine.is_file(): shutil.copy2(engine, tdir / "game_engine.py")
    if guard and guard.is_file(): shutil.copy2(guard, tdir / "save_guard.py")
    return c


def _bootstrap_snapshot_from_authority(root: Path, source: Path, recovery_anchor: bool = True,
                                       parent_snapshot: Optional[dict] = None) -> dict:
    authority = validate_authority_set(source)
    if authority is None:
        raise EngineError(f"BOOTSTRAP_AUTHORITY_INVALID: {source}")
    semantic = run_checks(source, full=False, require_manifest=True, parent_snapshot=parent_snapshot)
    if semantic.get("status") != "PASS":
        raise EngineError("BOOTSTRAP_SEMANTIC_CHECK_FAILED: " + "; ".join(semantic.get("errors", [])))
    version = version_text(authority["version"])
    snap_dir = root / f"{version}_SAVESET_{authority['bundle'][:16]}"
    if snap_dir.exists():
        writable_tree(snap_dir)
        q = root / f".quarantine_{snap_dir.name}_{int(time.time())}"
        os.replace(snap_dir, q)
    tmp = root / f".{snap_dir.name}.bootstrap.{os.getpid()}.tmp"
    if tmp.exists(): shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    for fn in AUTH_FILES: shutil.copy2(source / fn, tmp / fn)
    _write_recovery_commit(tmp, authority, root, recovery_anchor=recovery_anchor, parent_snapshot=parent_snapshot)
    os.replace(tmp, snap_dir)
    readonly_tree(snap_dir)
    v = validate_game_snapshot_available(snap_dir, root) if not recovery_anchor else validate_game_snapshot(snap_dir, verify_parent=False, root=root)
    if v is None:
        raise EngineError("BOOTSTRAP_SNAPSHOT_VERIFY_FAILED")
    return v

def _tool_status(path: Path, index: dict, commit: Optional[dict]) -> dict:
    expected_engine = None
    expected_guard = None
    expected_version = index.get("engine_version")
    if commit:
        expected_engine = (commit.get("tools") or {}).get("game_engine_sha256")
        expected_guard = (commit.get("tools") or {}).get("save_guard_sha256")
        expected_version = (commit.get("tools") or {}).get("game_engine_version", expected_version)
    expected_engine = expected_engine or index.get("engine_sha256")
    expected_guard = expected_guard or index.get("save_guard_sha256")
    ep = path / "_tools" / "game_engine.py"
    gp = path / "_tools" / "save_guard.py"
    def one(p: Path, expected: Optional[str]) -> dict:
        if not expected:
            return {"expected": None, "present": p.is_file(), "match": None}
        if not p.is_file():
            return {"expected": expected, "present": False, "match": False}
        actual = sha256_file(p)
        return {"expected": expected, "actual": actual, "present": True, "match": actual == expected}
    e = one(ep, expected_engine)
    g = one(gp, expected_guard)
    return {
        "engine_version": expected_version,
        "engine": e,
        "guard": g,
        "ok": (e["match"] in (True, None)) and (g["match"] in (True, None)),
    }


def validate_game_snapshot(path: Path, verify_parent: bool = False, root: Optional[Path] = None,
                           _visited: Optional[set] = None) -> Optional[dict]:
    """Validate game-state integrity and, when requested, the complete parent lineage. Tool loss never invalidates game state."""
    m = SNAP_RE.match(path.name)
    if not m or not path.is_dir():
        return None
    authority = validate_authority_set(path)
    if authority is None:
        return None
    parsed = authority["index"]
    ver = authority["version"]
    b = authority["bundle"]
    sid = authority["save_set_id"]
    if (int(m.group(1)), int(m.group(2))) != ver or m.group(3) != b[:16]:
        return None

    commit = read_commit(path)
    if commit is None and parsed.get("commit_format") == COMMIT_FORMAT:
        return None
    legacy = commit is None
    parent_sid = parsed.get("parent_save_set_id")
    recovery_anchor = False
    if commit is not None:
        if commit.get("format") != COMMIT_FORMAT:
            return None
        if commit.get("version") != version_text(ver) or commit.get("save_set_id") != sid:
            return None
        if commit.get("bundle_sha256") != b or commit.get("source_sha256") != authority["manifest"]:
            return None
        if commit.get("index_sha256") != authority["index_sha256"]:
            return None
        parent_sid = commit.get("parent_save_set_id")
        recovery_anchor = bool(commit.get("recovery_anchor"))
        if parent_sid:
            sid_parent_version = _parse_parent_version_from_sid(parent_sid)
            if commit.get("parent_version") != sid_parent_version:
                return None
            if not recovery_anchor and not re.fullmatch(r"[0-9a-f]{64}", str(commit.get("parent_bundle_sha256") or "")):
                return None
        if parsed.get("commit_format") != COMMIT_FORMAT:
            return None
        if parsed.get("parent_save_set_id") != parent_sid:
            return None
        ctools=commit.get("tools") or {}
        if parsed.get("engine_version") != ctools.get("game_engine_version"):
            return None
        if parsed.get("engine_sha256") != ctools.get("game_engine_sha256"):
            return None
        if parsed.get("save_guard_sha256") != ctools.get("save_guard_sha256"):
            return None

        if verify_parent and parent_sid and not recovery_anchor:
            root = root or path.parent
            visited = set(_visited or set())
            if sid in visited:
                return None
            visited.add(sid)
            pp = snapshot_path_from_sid(root, parent_sid)
            if pp is None:
                return None
            pv = validate_game_snapshot(pp, verify_parent=True, root=root, _visited=visited)
            if pv is None or pv["save_set_id"] != parent_sid or pv["version"] >= ver:
                return None
            if commit.get("parent_version") != version_text(pv["version"]):
                return None
            if commit.get("parent_bundle_sha256") != pv["bundle"]:
                return None
        elif verify_parent and recovery_anchor:
            # A cold-recovery anchor is intentionally a new trust root; declared historical parent is informational only.
            pass

    return {
        "dir": path, "version": ver, "bundle": b, "save_set_id": sid,
        "manifest": authority["manifest"], "index": parsed, "index_sha256": authority["index_sha256"],
        "commit": commit, "legacy": legacy, "recovery_anchor": recovery_anchor,
        "parent_save_set_id": parent_sid, "tools": _tool_status(path, parsed, commit),
    }

def snapshot_path_from_sid(root: Path, sid: str) -> Optional[Path]:
    m = re.fullmatch(r"SAVESET-(V\d+\.\d+)-([0-9a-f]{16})", str(sid))
    if not m:
        return None
    p = root / f"{m.group(1)}_SAVESET_{m.group(2)}"
    return p if p.is_dir() else None


def _make_writable_tree_for_quarantine(path: Path) -> None:
    try:
        for p in path.rglob("*"):
            try: p.chmod(0o755 if p.is_dir() else 0o644)
            except OSError: pass
        try: path.chmod(0o755)
        except OSError: pass
    except OSError:
        pass


def _quarantine_partial_dir(root: Path, path: Path, reason: str = "partial_upload") -> Path:
    _make_writable_tree_for_quarantine(path)
    base = root / f".quarantine_{path.name}_{reason}"
    q = base; i = 1
    while q.exists():
        q = root / f"{base.name}_{i}"; i += 1
    os.replace(path, q)
    return q


def quarantine_obvious_partial_artifacts(root: Path = ROOT) -> List[dict]:
    """Hide unmistakable external-sync fragments without masking real corruption.

    Safety boundary:
    - SAVESET with COMMIT.json: never auto-quarantine; it can be genuinely corrupt.
    - complete legacy SAVESET without COMMIT: keep for backward compatibility.
    - SAVESET without COMMIT and missing authority files: external partial artifact.
    - PROJECT_SOURCE must be a complete seven-file handoff; incomplete directories
      are delivery artifacts, not authority candidates, and may be quarantined.
    """
    moved: List[dict] = []
    if not root.is_dir(): return moved
    for p in list(root.iterdir()):
        if not p.is_dir(): continue
        if SNAP_RE.match(p.name):
            if (p / "COMMIT.json").is_file(): continue
            missing = [fn for fn in AUTH_FILES if not (p / fn).is_file()]
            if missing:
                q = _quarantine_partial_dir(root, p)
                moved.append({"kind":"saveset","from":p.name,"to":q.name,"missing":missing})
        elif PROJECT_SOURCE_RE.match(p.name):
            missing = [fn for fn in AUTH_FILES if not (p / fn).is_file()]
            engines = [x for x in p.glob("GAME_ENGINE_v*.py") if x.is_file()]
            guards = [x for x in p.glob("SAVE_GUARD_v*.py") if x.is_file()]
            if missing or len(engines) != 1 or len(guards) != 1:
                q = _quarantine_partial_dir(root, p)
                moved.append({"kind":"project_source","from":p.name,"to":q.name,"missing":missing,"engine_count":len(engines),"guard_count":len(guards)})
    return moved


def snapshot_dirs_by_version(root: Path, quarantine_partial: bool = True) -> Dict[Tuple[int, int], List[Path]]:
    groups: Dict[Tuple[int, int], List[Path]] = {}
    if not root.is_dir():
        return groups
    if quarantine_partial:
        quarantine_obvious_partial_artifacts(root)
    for p in root.iterdir():
        m = SNAP_RE.match(p.name)
        if p.is_dir() and m:
            groups.setdefault((int(m.group(1)), int(m.group(2))), []).append(p)
    return groups


def _verify_available_lineage(snapshot: dict, root: Path, visited: Optional[set] = None) -> dict:
    """Verify locally available lineage, tolerating a pruned/missing ancestor.

    Project/mobile persistence does not guarantee that every historical SAVESET is
    materialized in the current session. Missing lineage is therefore reported, not
    conflated with corruption. If an expected parent directory is present but invalid,
    validation still fails closed.
    """
    sid = snapshot.get("save_set_id"); commit = snapshot.get("commit") or {}
    parent_sid = snapshot.get("parent_save_set_id")
    if not parent_sid or snapshot.get("recovery_anchor"):
        return {"status":"COMPLETE" if not parent_sid else "RECOVERY_ANCHOR","verified_depth":1,"missing_parent_save_set_id":None}
    seen = set(visited or set())
    if sid in seen:
        return {"status":"INVALID","error":"LINEAGE_CYCLE","verified_depth":0}
    seen.add(sid)
    pp = snapshot_path_from_sid(root, parent_sid)
    if pp is None:
        return {"status":"TRUNCATED_PARENT_UNAVAILABLE","verified_depth":1,"missing_parent_save_set_id":parent_sid}
    pv = validate_game_snapshot(pp, verify_parent=False, root=root)
    if pv is None:
        return {"status":"INVALID","error":f"PARENT_PRESENT_BUT_INVALID:{parent_sid}","verified_depth":1}
    if pv.get("save_set_id") != parent_sid or pv.get("version") >= snapshot.get("version"):
        return {"status":"INVALID","error":f"PARENT_ID_OR_VERSION_MISMATCH:{parent_sid}","verified_depth":1}
    if commit.get("parent_version") and commit.get("parent_version") != version_text(pv["version"]):
        return {"status":"INVALID","error":f"PARENT_VERSION_BINDING_MISMATCH:{parent_sid}","verified_depth":1}
    if commit.get("parent_bundle_sha256") and commit.get("parent_bundle_sha256") != pv.get("bundle"):
        return {"status":"INVALID","error":f"PARENT_BUNDLE_BINDING_MISMATCH:{parent_sid}","verified_depth":1}
    tail = _verify_available_lineage(pv, root, seen)
    if tail.get("status") == "INVALID":
        tail["verified_depth"] = int(tail.get("verified_depth") or 0) + 1
        return tail
    return {"status":tail.get("status"),"verified_depth":int(tail.get("verified_depth") or 0)+1,"missing_parent_save_set_id":tail.get("missing_parent_save_set_id")}


def validate_game_snapshot_available(path: Path, root: Path) -> Optional[dict]:
    snap = validate_game_snapshot(path, verify_parent=False, root=root)
    if snap is None: return None
    lineage = _verify_available_lineage(snap, root)
    if lineage.get("status") == "INVALID": return None
    snap["lineage"] = lineage
    return snap


def _v130_layer_latest_valid_snapshot_01(root: Path = ROOT, verify_parent: bool = True) -> dict:
    """Select the highest committed version without silent rollback.

    Obvious uncommitted partial-upload directories are quarantined before ranking.
    A missing historical parent is a truncated lineage condition; an available but
    invalid parent remains hard corruption. Invalid committed siblings at the highest
    version also remain fail-closed.
    """
    ab=_ab_resolve_active(root,repair_pointer=False)
    if ab is not None:
        pp=snapshot_path_from_sid(root,ab['save_set_id'])
        if pp is None:raise EngineError(f"AB_ACTIVE_SNAPSHOT_MISSING:{ab['save_set_id']}")
        v=validate_game_snapshot_available(pp,root) if verify_parent else validate_game_snapshot(pp,verify_parent=False,root=root)
        if v is None or v.get('save_set_id')!=ab['save_set_id']:raise EngineError(f"AB_ACTIVE_SNAPSHOT_INVALID:{ab['save_set_id']}")
        v['ab_active_slot']=ab['slot'];v['invalid_higher_candidates']=[];return v
    groups = snapshot_dirs_by_version(root, quarantine_partial=True)
    if not groups:
        raise EngineError("NO_COMMITTED_SNAPSHOT")
    ver = max(groups)
    valid: List[dict] = []
    invalid: List[str] = []
    for p in groups[ver]:
        v = validate_game_snapshot_available(p, root) if verify_parent else validate_game_snapshot(p, verify_parent=False, root=root)
        if v: valid.append(v)
        else: invalid.append(p.name)
    if len(valid) > 1:
        raise ForkError(f"FORK_DETECTED {version_text(ver)}: {[x['save_set_id'] for x in valid]}")
    if len(valid) == 1 and not invalid:
        valid[0]["invalid_higher_candidates"] = []
        return valid[0]
    if len(valid) == 1 and invalid:
        raise CorruptedLatestError(version_text(ver), invalid + [valid[0]["dir"].name])
    raise CorruptedLatestError(version_text(ver), [p.name for p in groups[ver]])

def files_match(a: Path, b: Path, files: Iterable[str] = AUTH_FILES) -> bool:
    try:
        return all((a / f).is_file() and (b / f).is_file() and sha256_file(a / f) == sha256_file(b / f) for f in files)
    except OSError:
        return False


def atomic_copy_set(src: Path, dst: Path, files: Iterable[str]) -> None:
    files = list(files)
    dst.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".engine_copy_", dir=str(dst)))
    try:
        for f in files:
            shutil.copy2(src / f, stage / f)
        for f in files:
            if sha256_file(stage / f) != sha256_file(src / f):
                raise EngineError(f"staging verification failed: {f}")
        for f in files:
            target = dst / f
            try:
                if target.exists():
                    target.chmod(0o644)
            except OSError:
                pass
            os.replace(stage / f, target)
        for f in files:
            if sha256_file(dst / f) != sha256_file(src / f):
                raise EngineError(f"post-copy verification failed: {f}")
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _find_tool_candidate(root: Path, snap: dict, kind: str, expected: Optional[str]) -> Optional[Path]:
    if not expected:
        return None
    candidates: List[Path] = []
    if kind == "engine":
        candidates += [snap["dir"] / "_tools" / "game_engine.py", root / ".game_engine.py"]
        candidates += sorted(root.glob("GAME_ENGINE_v*.py"), reverse=True)
        leaf = "game_engine.py"
    else:
        candidates += [snap["dir"] / "_tools" / "save_guard.py", root / ".save_guard.py"]
        candidates += sorted(root.glob("SAVE_GUARD_v*.py"), reverse=True)
        leaf = "save_guard.py"
    # Historical tool copies are fallback only; game snapshot selection never depends on them.
    for p in sorted(root.glob("V*_SAVESET_*/_tools/" + leaf), reverse=True):
        candidates.append(p)
    seen = set()
    for p in candidates:
        try:
            rp = str(p.resolve())
        except Exception as ex:
            rp = str(p)
        if rp in seen:
            continue
        seen.add(rp)
        try:
            if p.is_file() and sha256_file(p) == expected:
                return p
        except OSError:
            continue
    return None


def _guard_protocol(path: Path) -> Optional[str]:
    try:
        text=path.read_text(encoding="utf-8",errors="strict")[:16000]
        m=re.search(r"^GUARD_PROTOCOL\s*=\s*['\"]([^'\"]+)['\"]",text,re.M)
        return m.group(1) if m else None
    except Exception:return None

def _guard_source_version(path:Path)->Tuple[int,int,int]:
    try:
        txt=path.read_text(encoding="utf-8")[:12000]
        if not re.search(r'^GUARD_MAGIC\s*=\s*["\']VOYAGER_FLEET_SAVE_GUARD["\']',txt,re.M):return (-1,-1,-1)
        m=re.search(r'^GUARD_VERSION\s*=\s*["\'](\d+)\.(\d+)(?:\.(\d+))?["\']',txt,re.M)
        return (int(m.group(1)),int(m.group(2)),int(m.group(3) or 0)) if m else (-1,-1,-1)
    except Exception:return (-1,-1,-1)


def restore_tools(root: Path, snap: dict) -> dict:
    commit = snap.get("commit") or {};tools = commit.get("tools") or {}
    e_expected = tools.get("game_engine_sha256") or snap["index"].get("engine_sha256")
    g_expected = tools.get("save_guard_sha256") or snap["index"].get("save_guard_sha256")
    expected_version = tools.get("game_engine_version") or snap["index"].get("engine_version")
    results={}

    # Never downgrade a newer compatible engine that is already executing. Snapshot tool hashes are archival bindings,
    # not a mandate to replace newer infrastructure. The next save will bind the newer tool explicitly.
    running=Path(__file__).resolve(); dst=root/".game_engine.py"
    rv=semver_tuple(ENGINE_VERSION);bv=semver_tuple(expected_version);running_hash=sha256_file(running) if running.is_file() else None
    running_acceptable = rv>bv or (rv==bv and (not e_expected or running_hash==e_expected))
    if running_acceptable:
        try:
            if running.is_file():
                if not dst.is_file() or sha256_file(dst)!=running_hash:
                    tmp=root/f".game_engine.upgrade.{os.getpid()}.tmp";shutil.copy2(running,tmp);os.replace(tmp,dst);dst.chmod(0o755)
                results["engine"]={"status":"NEWER_OK" if rv>bv else "OK_BOUND","path":str(dst),"running_version":ENGINE_VERSION,"snapshot_bound_version":expected_version,"running_sha256":running_hash}
            else:raise OSError("running engine unavailable")
        except Exception as e:
            results["engine"]={"status":"WORKCOPY_UPDATE_FAILED","detail":str(e)}
    else:
        src=_find_tool_candidate(root,snap,"engine",e_expected) if e_expected else None
        if src is None:results["engine"]={"status":"MISSING","expected_sha256":e_expected,"running_version":ENGINE_VERSION,"running_sha256":running_hash}
        else:
            tmp=root/f".game_engine.restore.{os.getpid()}.tmp";shutil.copy2(src,tmp);os.replace(tmp,dst);dst.chmod(0o755);results["engine"]={"status":"RESTORED","from":str(src),"path":str(dst)}

    # Guard launcher may be upgraded independently; prefer the highest versioned Project copy, else exact bound hash.
    gdst=root/".save_guard.py"
    def guard_file_ver(p:Path):
        m=re.fullmatch(r"SAVE_GUARD_v(\d+)\.(\d+)(?:\.(\d+))?\.py",p.name)
        return (int(m.group(1)),int(m.group(2)),int(m.group(3) or 0)) if m else (-1,-1,-1)
    project_guards=[]
    for gp in root.glob("SAVE_GUARD_v*.py"):
        try:
            if gp.is_file() and _guard_protocol(gp)==GUARD_PROTOCOL and sha256_file(gp)==BUNDLED_GUARD_SHA256:project_guards.append((_guard_source_version(gp),gp))
        except Exception:pass
    project_guards.sort(key=lambda z:z[0],reverse=True)
    gsrc=project_guards[0][1] if project_guards else _find_tool_candidate(root,snap,"guard",g_expected)
    try:
        if gsrc and gsrc.is_file():
            if not gdst.is_file() or sha256_file(gdst)!=sha256_file(gsrc):
                tmp=root/f".save_guard.upgrade.{os.getpid()}.tmp";shutil.copy2(gsrc,tmp);os.replace(tmp,gdst);gdst.chmod(0o755)
            results["guard"]={"status":"OK_OR_NEWER","path":str(gdst),"from":str(gsrc)}
        elif g_expected and gdst.is_file() and sha256_file(gdst)==g_expected:
            results["guard"]={"status":"OK","path":str(gdst)}
        else:results["guard"]={"status":"MISSING","expected_sha256":g_expected}
    except Exception as e:results["guard"]={"status":"RESTORE_FAILED","detail":str(e)}
    results["ok"]=results["engine"].get("status") not in {"MISSING","WORKCOPY_UPDATE_FAILED"} and results["guard"].get("status") not in {"MISSING","RESTORE_FAILED"}
    return results

def _find_recovery_source(root: Path, target_ver: Tuple[int,int]) -> Optional[Path]:
    candidates: List[Path] = [root]
    for p in root.iterdir() if root.is_dir() else []:
        m = EXPORT_RE.match(p.name)
        if p.is_dir() and m and (int(m.group(1)), int(m.group(2))) == target_ver:
            candidates.append(p)
    valid = []
    for p in candidates:
        a = validate_authority_set(p)
        if a and a["version"] == target_ver:
            valid.append((a["save_set_id"], p, a))
    uniq = {}
    for sid,p,a in valid: uniq.setdefault(sid, []).append((p,a))
    if len(uniq) > 1:
        raise ForkError(f"RECOVERY_SOURCE_FORK {version_text(target_ver)}: {list(uniq)}")
    if not uniq:
        return None
    sid = next(iter(uniq))
    return uniq[sid][0][0]


def _repair_corrupted_latest(root: Path, ver: Tuple[int,int]) -> Optional[dict]:
    source = _find_recovery_source(root, ver)
    if source is None:
        return None
    a = validate_authority_set(source)
    parent = None
    psid = (a or {}).get("index",{}).get("parent_save_set_id") if a else None
    if psid:
        pp = snapshot_path_from_sid(root, psid)
        if pp is None:
            return None
        parent = validate_game_snapshot_available(pp, root)
        if parent is None:
            return None
    # Quarantine every official directory at the damaged highest version. Leaving an invalid sibling
    # would make the next guard ambiguous even after successful same-version reconstruction.
    for old in snapshot_dirs_by_version(root).get(ver, []):
        writable_tree(old)
        q = root / f".quarantine_{old.name}_{int(time.time()*1000)}"
        while q.exists(): q = root / (q.name + "x")
        os.replace(old, q)
    return _bootstrap_snapshot_from_authority(root, source, recovery_anchor=False if parent else True, parent_snapshot=parent)


def _quarantine_superseded_engine_sources(root:Path,bound_version:str)->List[str]:
    """Move only older versioned Engine source files out of the strict runtime root."""
    root=Path(root).resolve();cur=semver_tuple(str(bound_version or "0"));moved=[];qdir=root/".runtime"/"work"/"retired_engines"
    for p in sorted(root.glob("GAME_ENGINE_v*.py")):
        m=re.fullmatch(r"GAME_ENGINE_v(\d+\.\d+\.\d+)\.py",p.name)
        if not m:continue
        try:v=semver_tuple(m.group(1))
        except Exception:continue
        if v>=cur:continue
        try:
            qdir.mkdir(parents=True,exist_ok=True);dst=qdir/(p.name+f".superseded_{int(time.time()*1000)}")
            while dst.exists():dst=dst.with_name(dst.name+"x")
            os.replace(p,dst);moved.append(p.name)
        except OSError:pass
    return moved

def _v130_layer_guard_01(root: Path = ROOT, restore: bool = True, restore_tool_files: bool = True) -> dict:
    """Select newest trustworthy authority; A/B pointer is authoritative once activated."""
    with engine_lock(root, exclusive=True):
        quarantined_partials=quarantine_obvious_partial_artifacts(root)
        ab=_ab_resolve_active(root,repair_pointer=True);bootstrapped=False;imported_project_source=False;repaired_snapshot=False;restored=False
        if ab is not None:
            root_auth=validate_authority_set(root)
            if _select_root_import(root_auth,ab):
                if not restore:raise EngineError('PROJECT_SOURCE_NEWER_THAN_AB_ACTIVE')
                pp=snapshot_path_from_sid(root,ab['save_set_id'])
                parent=validate_game_snapshot_available(pp,root) if pp is not None else None
                if parent is None:raise EngineError('PROJECT_SOURCE_ACTIVE_PARENT_UNAVAILABLE')
                # root_auth already verified the uploaded manifest. Full semantic
                # checks must not demand that this import already be the active cache.
                check=run_checks(root,full=True,require_manifest=False,parent_snapshot=parent)
                if check.get('status')!='PASS':raise EngineError('PROJECT_SOURCE_IMPORT_SEMANTIC_CHECK_FAILED:'+str(check.get('errors')))
                imported=_bootstrap_snapshot_from_authority(root,root,recovery_anchor=False,parent_snapshot=parent)
                inactive='B' if ab['slot']=='A' else 'A'
                slot=_ab_write_slot_from_source(Path(imported['dir']),root,inactive)
                _ab_write_pointer(root,slot);ab=slot;imported_project_source=True
            if root_auth is None or root_auth.get('save_set_id')!=ab['save_set_id']:
                if not restore:raise EngineError('AB_ROOT_CACHE_MISMATCH')
                _ab_materialize_root(root,ab);restored=True
            pp=snapshot_path_from_sid(root,ab['save_set_id']);snap=validate_game_snapshot_available(pp,root) if pp is not None else None
            if snap is None:
                if not restore:raise EngineError(f"AB_ACTIVE_SNAPSHOT_UNAVAILABLE:{ab['save_set_id']}")
                snap=_bootstrap_snapshot_from_authority(root,root,recovery_anchor=True,parent_snapshot=None);bootstrapped=True
            if snap.get('save_set_id')!=ab['save_set_id']:raise EngineError('AB_ACTIVE_SNAPSHOT_IDENTITY_MISMATCH')
        else:
            groups=snapshot_dirs_by_version(root,quarantine_partial=False);root_auth=validate_authority_set(root)
            if not groups:
                if not restore:raise EngineError("NO_COMMITTED_SNAPSHOT")
                if root_auth is None:raise EngineError("NO_COMMITTED_SNAPSHOT_AND_ROOT_AUTHORITY_INVALID")
                snap=_bootstrap_snapshot_from_authority(root,root,recovery_anchor=True,parent_snapshot=None);bootstrapped=True;imported_project_source=True
            else:
                highest=max(groups)
                if root_auth is not None and root_auth["version"]>highest:
                    if not restore:raise EngineError(f"PROJECT_SOURCE_NEWER_THAN_LOCAL_SNAPSHOT: root={version_text(root_auth['version'])} local={version_text(highest)}")
                    parent=None;psid=(root_auth.get("index") or {}).get("parent_save_set_id")
                    if psid:
                        pp=snapshot_path_from_sid(root,psid)
                        if pp is not None:
                            parent=validate_game_snapshot_available(pp,root)
                            if parent is None:raise EngineError(f"PROJECT_SOURCE_DECLARED_PARENT_INVALID: {psid}")
                    semantic=run_checks(root,full=False,require_manifest=False,parent_snapshot=parent)
                    if semantic.get("status")!="PASS":raise EngineError("PROJECT_SOURCE_IMPORT_SEMANTIC_CHECK_FAILED: "+"; ".join(semantic.get("errors",[])))
                    snap=_bootstrap_snapshot_from_authority(root,root,recovery_anchor=(parent is None),parent_snapshot=parent);bootstrapped=True;imported_project_source=True
                else:
                    try:snap=latest_valid_snapshot(root,verify_parent=True)
                    except CorruptedLatestError:
                        if not restore:raise
                        snap=_repair_corrupted_latest(root,highest)
                        if snap is None:raise EngineError(f"CORRUPTED_LATEST_SNAPSHOT_FAIL_CLOSED {version_text(highest)}; automatic downgrade forbidden")
                        repaired_snapshot=True
                    if root_auth is not None and root_auth["version"]==snap["version"] and root_auth["save_set_id"]!=snap["save_set_id"]:
                        raise ForkError(f"PROJECT_SOURCE_SAME_VERSION_FORK: root={root_auth['save_set_id']} local={snap['save_set_id']}")
            # Legacy authority becomes A/B only at formal save. Guard never mutates storage format merely by reading.

        semantic=_semantic_snapshot_check(snap,root)
        if semantic.get("status")!="PASS":raise EngineError("LATEST_SNAPSHOT_SEMANTIC_CHECK_FAILED: "+"; ".join(semantic.get("errors",[])))
        root_matches=files_match(root,snap["dir"])
        # In A/B mode, root INDEX may contain slot annotations absent from a legacy-reconstructed snapshot.
        ab=_ab_active_slot(root)
        if ab is not None:
            root_auth=validate_authority_set(root);root_matches=bool(root_auth and root_auth.get('save_set_id')==ab['save_set_id'])
            if not root_matches and restore:_ab_materialize_root(root,ab);restored=True;root_matches=True
        elif not root_matches and restore:
            atomic_copy_set(snap["dir"],root,AUTH_FILES)
            for f in AUTH_FILES:
                try:(root/f).chmod(0o444)
                except OSError:pass
            restored=True;root_matches=files_match(root,snap["dir"])
            if not root_matches:raise EngineError("SAVE_GUARD_POST_RESTORE_MISMATCH")
        tools=restore_tools(root,snap) if restore_tool_files else snap["tools"]
        bound_version=str(((snap.get("index") or {}).get("engine_version") or ((snap.get("commit") or {}).get("tools") or {}).get("game_engine_version") or ENGINE_VERSION))
        retired_engine_sources=_quarantine_superseded_engine_sources(root,bound_version) if restore_tool_files else []
        return {"status":"PASS" if root_matches else "MISMATCH","latest":snap["save_set_id"],"version":version_text(snap["version"]),"root_matches":root_matches,"restored":restored,"bootstrapped_cold":bootstrapped,"imported_project_source":imported_project_source,"repaired_latest_snapshot":repaired_snapshot,"snapshot_dir":str(snap["dir"]),"legacy_snapshot":snap["legacy"],"ab_storage":bool(ab),"active_slot":ab.get('slot') if ab else None,"recovery_anchor":snap.get("recovery_anchor",False),"parent_save_set_id":snap.get("parent_save_set_id"),"tools":tools,"invalid_higher_candidates":[],"lineage":snap.get("lineage"),"quarantined_partial_artifacts":quarantined_partials,"quarantined_superseded_engine_files":retired_engine_sources}


def _v1403_previous_read_json(path: Path) -> Any:
    return strict_json_load(path)


HISTORY_EPOCH_SCHEMA="HISTORY_EPOCH_V1"
HISTORY_EPOCH_CODEC="lzma+xz+base64"
HISTORY_EPOCH_LEGACY_CODEC="zlib+base64"
HISTORY_EPOCH_SUPPORTED_CODECS=frozenset((HISTORY_EPOCH_CODEC,HISTORY_EPOCH_LEGACY_CODEC))
HISTORY_EPOCH_MAX_DECODED_BYTES=128*1024*1024
HISTORY_EPOCH_LZMA_MEMORY_LIMIT=64*1024*1024
HISTORY_EPOCH_KEEP_RECENT=800
HISTORY_EPOCH_RECENT_BYTE_BUDGET=768*1024
HISTORY_EPOCH_MIN_RECENT=8
HISTORY_EPOCH_CHUNK_EVENTS=1000
HISTORY_EPOCH_CHUNK_UNCOMPRESSED_BYTES=4*1024*1024

def _history_epoch_search_record(event:dict)->dict:
    return {k:copy.deepcopy(event[k]) for k in ('seq','event_id','game_time','type','source_task_id','source','summary','details','entities','locations','tags') if k in event}

def _history_epoch_decompress(comp:bytes,codec:str,lineno:int=0)->bytes:
    """Decode one bounded stream. Never silently accept a truncated or trailing stream."""
    if codec not in HISTORY_EPOCH_SUPPORTED_CODECS:
        raise EngineError(f"HISTORY epoch codec invalid at line {lineno}")
    try:
        decoder=(lzma.LZMADecompressor(format=lzma.FORMAT_XZ,memlimit=HISTORY_EPOCH_LZMA_MEMORY_LIMIT)
                 if codec==HISTORY_EPOCH_CODEC else zlib.decompressobj())
        raw=decoder.decompress(comp,HISTORY_EPOCH_MAX_DECODED_BYTES+1)
        if len(raw)>HISTORY_EPOCH_MAX_DECODED_BYTES:
            raise EngineError(f"HISTORY epoch decoded payload too large at line {lineno}")
        if not decoder.eof or decoder.unused_data:
            raise EngineError(f"HISTORY epoch truncated or trailing stream at line {lineno}")
        return raw
    except EngineError:raise
    except Exception as ex:
        raise EngineError(f"HISTORY epoch decompress failed at line {lineno}: {ex}") from ex

def _decode_history_epoch_record(rec:dict,lineno:int=0,base:Optional[Path]=None,_archive_bytes:Optional[bytes]=None)->Tuple[List[dict],List[bytes]]:
    if rec.get("record_type")!="history_epoch" or rec.get("schema")!=HISTORY_EPOCH_SCHEMA:
        raise EngineError(f"HISTORY epoch record invalid at line {lineno}")
    if rec.get("codec") not in HISTORY_EPOCH_SUPPORTED_CODECS:
        raise EngineError(f"HISTORY epoch codec invalid at line {lineno}")
    encoded=rec.get('payload_b64')
    if rec.get('archive_ref'):
        rel=str(rec['archive_ref'])
        if base is None or rel.startswith('/') or '..' in Path(rel).parts or encoded is not None:
            raise EngineError('HISTORY_ARCHIVE_REFERENCE_INVALID:'+rel)
        archive=Path(base)/rel
        if not archive.is_file():raise EngineError('HISTORY_ARCHIVE_MISSING:'+rel)
        try:
            archive_bytes=archive.read_bytes() if _archive_bytes is None else _archive_bytes
            wrapper=json.loads(gzip.decompress(archive_bytes).decode('utf-8'))
            payload=wrapper['payload'];encoded=payload['payload_b64']
            ph=sha256_bytes(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
            if wrapper.get('schema')!='VOYAGER_COLD_ARCHIVE_V1' or wrapper.get('payload_sha256')!=ph:
                raise EngineError('HISTORY_ARCHIVE_PAYLOAD_HASH_MISMATCH:'+rel)
            expected_schema=('VOYAGER_HISTORY_PAYLOAD_V2' if rec['codec']==HISTORY_EPOCH_CODEC else 'VOYAGER_HISTORY_PAYLOAD_V1')
            if payload.get('schema')!=expected_schema or payload.get('codec',HISTORY_EPOCH_LEGACY_CODEC)!=rec['codec']:
                raise EngineError('HISTORY_ARCHIVE_CODEC_MISMATCH:'+rel)
            if payload['seq_start']!=rec['seq_start'] or payload['seq_end']!=rec['seq_end'] or payload['event_count']!=rec['event_count']:
                raise EngineError('HISTORY_ARCHIVE_RANGE_MISMATCH:'+rel)
            if payload['compressed_sha256']!=rec['compressed_sha256']:
                raise EngineError('HISTORY_ARCHIVE_DIGEST_MISMATCH:'+rel)
            if rec['codec']==HISTORY_EPOCH_CODEC:
                for key in ('compressed_bytes','uncompressed_sha256','uncompressed_bytes','events_sha256'):
                    if payload.get(key)!=rec.get(key):raise EngineError('HISTORY_ARCHIVE_BINDING_MISMATCH:'+key+':'+rel)
        except EngineError:raise
        except Exception as ex:raise EngineError('HISTORY_ARCHIVE_READ_FAILED:'+rel+':'+str(ex)) from ex
    try:
        comp=base64.b64decode(str(encoded or ""),validate=True)
    except Exception as e:
        raise EngineError(f"HISTORY epoch base64 invalid at line {lineno}: {e}")
    if sha256_bytes(comp)!=str(rec.get("compressed_sha256") or ""):
        raise EngineError(f"HISTORY epoch compressed hash mismatch at line {lineno}")
    if type(rec.get('compressed_bytes')) is not int or len(comp)!=rec['compressed_bytes']:
        raise EngineError(f"HISTORY epoch compressed size mismatch at line {lineno}")
    raw=_history_epoch_decompress(comp,rec['codec'],lineno)
    if type(rec.get('uncompressed_bytes')) is not int or len(raw)!=rec['uncompressed_bytes']:
        raise EngineError(f"HISTORY epoch uncompressed size mismatch at line {lineno}")
    if sha256_bytes(raw)!=str(rec.get("uncompressed_sha256") or ""):
        raise EngineError(f"HISTORY epoch uncompressed hash mismatch at line {lineno}")
    raws=[x for x in raw.splitlines() if x.strip()];events=[]
    for i,eraw in enumerate(raws,1):
        try:e=strict_json_loads(eraw.decode("utf-8"))
        except Exception as exc:raise EngineError(f"HISTORY epoch event JSON invalid line={lineno} item={i}: {exc}")
        if "seq" not in e:raise EngineError(f"HISTORY epoch event missing seq line={lineno} item={i}")
        events.append(e)
    if len(events)!=int(rec.get("event_count") or -1):raise EngineError(f"HISTORY epoch event_count mismatch at line {lineno}")
    if events:
        if int(events[0].get("seq") or 0)!=int(rec.get("seq_start") or 0) or int(events[-1].get("seq") or 0)!=int(rec.get("seq_end") or 0):
            raise EngineError(f"HISTORY epoch seq range mismatch at line {lineno}")
        digest=sha256_bytes(b"\n".join(raws)+b"\n")
        if digest!=str(rec.get("events_sha256") or ""):raise EngineError(f"HISTORY epoch events hash mismatch at line {lineno}")
    if 'search_index' in rec and rec['search_index']!=[_history_epoch_search_record(e) for e in events]:
        raise EngineError(f"HISTORY epoch search index mismatch at line {lineno}")
    return events,raws

def _make_history_epoch_record(raws:List[bytes],epoch_index:int)->dict:
    if not raws:raise EngineError("HISTORY_EPOCH_EMPTY")
    events=[strict_json_loads(x.decode("utf-8")) for x in raws]
    payload=b"\n".join(raws)+b"\n";comp=lzma.compress(payload,format=lzma.FORMAT_XZ,preset=6)
    s0=int(events[0].get("seq") or 0);s1=int(events[-1].get("seq") or 0)
    return {
        "record_type":"history_epoch","schema":HISTORY_EPOCH_SCHEMA,"epoch_index":int(epoch_index),
        "seq_start":s0,"seq_end":s1,"event_count":len(events),"codec":HISTORY_EPOCH_CODEC,
        "events_sha256":sha256_bytes(payload),"uncompressed_sha256":sha256_bytes(payload),
        "compressed_sha256":sha256_bytes(comp),"uncompressed_bytes":len(payload),"compressed_bytes":len(comp),
        "payload_b64":base64.b64encode(comp).decode("ascii")
    }

def _history_read_verified(path: Path, validate_metadata: bool = True, _raw_bytes: Optional[bytes] = None, _archive_bytes_by_ref: Optional[dict] = None) -> Tuple[dict, List[dict], List[bytes]]:
    lines = (path.read_bytes() if _raw_bytes is None else _raw_bytes).splitlines()
    meta = None
    events: List[dict] = []
    event_raw: List[bytes] = []
    expected_seq=1
    for lineno, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            rec = strict_json_loads(raw.decode("utf-8"))
        except Exception as e:
            raise EngineError(f"HISTORY invalid JSON at line {lineno}: {e}")
        if rec.get("record_type") == "metadata" and meta is None:
            meta = rec
        elif rec.get("record_type")=="history_epoch":
            ee,rr=_decode_history_epoch_record(rec,lineno,path.parent,_archive_bytes=(_archive_bytes_by_ref or {}).get(rec.get('archive_ref')))
            for e,eraw in zip(ee,rr):
                if type(e.get("seq")) is not int or e["seq"]!=expected_seq:raise EngineError(f"HISTORY seq discontinuity expected={expected_seq} actual={e.get('seq')}")
                events.append(e);event_raw.append(eraw);expected_seq+=1
        elif "seq" in rec:
            if type(rec.get("seq")) is not int or rec["seq"]!=expected_seq:raise EngineError(f"HISTORY seq discontinuity expected={expected_seq} actual={rec.get('seq')}")
            events.append(rec);event_raw.append(raw);expected_seq+=1
        else:
            raise EngineError(f"HISTORY unknown record at line {lineno}")
    if meta is None:
        raise EngineError("HISTORY metadata missing")
    if validate_metadata and (type(meta.get("next_seq")) is not int or meta["next_seq"]!=expected_seq):
        raise EngineError(f"HISTORY metadata next_seq mismatch expected={expected_seq} actual={meta.get('next_seq')}")
    return meta, events, event_raw


def read_history_raw(path: Path) -> Tuple[dict, List[dict], List[bytes]]:
    return _history_read_verified(path, validate_metadata=True)


def _history_expected_next_seq(events: List[dict]) -> int:
    # Empty history starts at one under the existing protocol. Never count epochs.
    expected = 1
    for event in events:
        if type(event.get('seq')) is not int or event['seq'] != expected:
            raise EngineError('HISTORY_SEQ_NOT_PROVEN_CONTIGUOUS')
        expected = event['seq'] + 1
    return expected


def _history_replace_metadata_bytes(data: bytes, metadata: dict, append_raws=()) -> bytes:
    # Preserve every pre-existing event/epoch/blank line and its line ending.
    rows = data.splitlines(keepends=True); found = False
    for i, raw in enumerate(rows):
        if not raw.strip(): continue
        record = strict_json_loads(raw.decode('utf-8'))
        if record.get('record_type') == 'metadata':
            if found: raise EngineError('HISTORY_DUPLICATE_METADATA')
            ending = b'\r\n' if raw.endswith(b'\r\n') else b'\n' if raw.endswith(b'\n') else b''
            rows[i] = json.dumps(metadata, ensure_ascii=False, separators=(',', ':')).encode('utf-8') + ending
            found = True
    if not found: raise EngineError('HISTORY_METADATA_MISSING')
    result = b''.join(rows)
    if append_raws:
        if result and not result.endswith((b'\n', b'\r')): result += b'\n'
        result += b''.join(raw + b'\n' for raw in append_raws)
    return result


def _history_physical_nonmeta_lines(path:Path)->List[bytes]:
    out=[];seen_meta=False
    for lineno,raw in enumerate(path.read_bytes().splitlines(),1):
        if not raw.strip():continue
        rec=strict_json_loads(raw.decode("utf-8"))
        if rec.get("record_type")=="metadata" and not seen_meta:
            seen_meta=True;continue
        out.append(raw)
    if not seen_meta:raise EngineError("HISTORY metadata missing")
    return out


# v2.16 validation layer: one check/save invocation may reuse an already validated
# parent HISTORY parse and parse only newly appended physical records from staging.
# The cache is caller-owned and in-memory only; no authority or runtime sidecar is trusted.
def _history_validation_cache_key(path:Path)->tuple:
    p=path.resolve()
    return (str(p),sha256_file(p))

def _history_cached_full(path:Path,cache:Optional[dict]=None)->Tuple[dict,List[dict],List[bytes]]:
    if cache is None:return read_history_view(path)
    k=("full",)+_history_validation_cache_key(path)
    row=cache.get(k)
    if row is None:
        row=read_history_view(path);cache[k]=row
    return row

def _history_nonblank_lines_cached(path:Path,cache:Optional[dict]=None)->List[bytes]:
    k=("lines",)+_history_validation_cache_key(path)
    if cache is not None and k in cache:return cache[k]
    rows=[x for x in path.read_bytes().splitlines() if x.strip()]
    if cache is not None:cache[k]=rows
    return rows

def _history_metadata_first(rows:List[bytes])->Optional[dict]:
    if not rows:return None
    try:rec=strict_json_loads(rows[0].decode("utf-8"))
    except Exception:return None
    return rec if isinstance(rec,dict) and rec.get("record_type")=="metadata" else None

def _history_parse_tail_records(rows:List[bytes],expected_seq:int,line_offset:int=0,base:Optional[Path]=None)->Tuple[List[dict],List[bytes],int]:
    events=[];raws=[]
    for j,raw in enumerate(rows,1):
        lineno=line_offset+j
        try:rec=strict_json_loads(raw.decode("utf-8"))
        except Exception as e:raise EngineError(f"HISTORY invalid JSON at line {lineno}: {e}")
        if rec.get("record_type")=="history_epoch":
            ee,rr=_decode_history_epoch_record(rec,lineno,base)
            for e,eraw in zip(ee,rr):
                if type(e.get("seq")) is not int or e["seq"]!=expected_seq:raise EngineError(f"HISTORY seq discontinuity expected={expected_seq} actual={e.get('seq')}")
                events.append(e);raws.append(eraw);expected_seq+=1
        elif rec.get("record_type")=="metadata":
            raise EngineError(f"HISTORY duplicate metadata at line {lineno}")
        elif "seq" in rec:
            if type(rec.get("seq")) is not int or rec["seq"]!=expected_seq:raise EngineError(f"HISTORY seq discontinuity expected={expected_seq} actual={rec.get('seq')}")
            events.append(rec);raws.append(raw);expected_seq+=1
        else:
            raise EngineError(f"HISTORY unknown record at line {lineno}")
    return events,raws,expected_seq

def _history_read_pair_incremental(parent_path:Path,current_path:Path,cache:Optional[dict]=None)->dict:
    """Read parent once and validate a normal append-only child by parsing only its tail.

    Exact physical-prefix equality is the fast-path proof. Epoch compaction or approved
    text migration automatically falls back to the legacy full parser, preserving every
    existing exception and fail-closed rule.
    """
    pmeta,pevents,praw=_history_cached_full(parent_path,cache)
    prows=_history_nonblank_lines_cached(parent_path,cache);crows=_history_nonblank_lines_cached(current_path,cache)
    pm0=_history_metadata_first(prows);cm0=_history_metadata_first(crows)
    if pm0 is not None and cm0 is not None:
        pphys=prows[1:];cphys=crows[1:]
        if len(cphys)>=len(pphys) and cphys[:len(pphys)]==pphys:
            tail_phys=cphys[len(pphys):]
            tail_events,tail_raw,expected=_history_parse_tail_records(tail_phys,len(pevents)+1,line_offset=1+len(pphys),base=current_path.parent)
            if int(cm0.get("next_seq") or expected)!=expected:
                raise EngineError(f"HISTORY metadata next_seq mismatch expected={expected} actual={cm0.get('next_seq')}")
            current=(cm0,pevents+tail_events,praw+tail_raw)
            return {"mode":"tail_incremental","parent":(pmeta,pevents,praw),"current":current,"parent_physical":pphys,"current_physical":cphys,"tail_event_count":len(tail_events)}
    cmeta,cevents,craw=_history_cached_full(current_path,cache)
    return {"mode":"full_fallback","parent":(pmeta,pevents,praw),"current":(cmeta,cevents,craw),"parent_physical":None,"current_physical":None,"tail_event_count":max(0,len(cevents)-len(pevents))}


def _v130_layer_get_by_path_01(obj: Any, path: str) -> Any:
    raw = path
    if path.startswith(("STATE.","state:")):
        path = path[6:]
    if path.startswith("/"):
        parts = [p for p in path.split("/") if p]
    else:
        parts = [p for p in path.split(".") if p]
    cur = obj
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        elif isinstance(cur, list) and p.isdigit() and int(p) < len(cur):
            cur = cur[int(p)]
        else:
            raise KeyError(raw)
    return cur


def _legacy_calder_552_portfolio_path(state: dict) -> str:
    """Resolve the retired Calder 552 label to the single current industry account."""
    path="world_state_overrides.multinational_industry_current"
    obj=get_by_path(state,path)
    if not isinstance(obj,dict):raise KeyError("ref:"+CALDER_552_COMPONENT_REF)
    return path

def _calder_552_component(state: dict) -> Tuple[dict,dict,str]:
    """Backward-compatible query redirect; no synthetic legacy item/profile is exposed."""
    path=_legacy_calder_552_portfolio_path(state)
    component=get_by_path(state,path)
    return component,component,path

def _v130_layer_resolve_state_ref_01(state: dict, path: str) -> str:
    """Resolve stable TASK/Engine state references without exposing versioned paths.

    Paths beginning with ``ref:`` are looked up in
    STATE.engine_runtime.state_refs.  Plain paths remain fully backward compatible.
    """
    raw=str(path or "").strip()
    if not raw.startswith("ref:"):
        return raw[6:] if raw.startswith(("STATE.","state:")) else raw
    key=raw[4:].strip()
    refs=(((state.get("engine_runtime") or {}).get("state_refs") or {}))
    mapped=refs.get(key)
    if not isinstance(mapped,str) or not mapped.strip():
        if key==CALDER_552_COMPONENT_REF:
            return _legacy_calder_552_portfolio_path(state)
        raise KeyError(raw)
    mapped=mapped.strip()
    return mapped[6:] if mapped.startswith(("STATE.","state:")) else mapped


def get_state_path(state: dict, path: str) -> Any:
    return get_by_path(state,resolve_state_ref(state,path))


def _task_machine_state_paths(task: dict) -> List[Tuple[str,str]]:
    """Return machine-consumed STATE paths embedded in one task.

    Retrieval routes are validated elsewhere.  This covers paths that deterministic
    resolvers and task runtime metadata actually dereference, so stale versioned
    current pointers cannot survive merely because the human-facing retrieval route is valid.
    """
    out: List[Tuple[str,str]]=[]
    td=task.get("task_data") or {}
    def walk_task_data(obj: Any, prefix: str="task_data") -> None:
        if isinstance(obj,dict):
            for k,v in obj.items():
                q=f"{prefix}.{k}"
                if isinstance(v,str) and str(k).lower().endswith("path") and (v.startswith(("STATE.","state:")) or v.startswith("ref:") or v.startswith("world_state_overrides.") or v.startswith("voyager_fleet.") or v.startswith("jinchuan_fleet.") or v.startswith("shadow_fleet.") or v.startswith("inventories.") or v.startswith("engine_runtime.")):
                    out.append((q,v))
                walk_task_data(v,q)
        elif isinstance(obj,list):
            for i,v in enumerate(obj):walk_task_data(v,f"{prefix}[{i}]")
    walk_task_data(td)
    rp=task.get("runtime_policy") or {}
    def walk_runtime(obj: Any, prefix: str="runtime_policy") -> None:
        if isinstance(obj,dict):
            for k,v in obj.items():
                q=f"{prefix}.{k}"
                if isinstance(v,str) and (v.startswith(("STATE.","state:")) or v.startswith("ref:")):
                    out.append((q,v))
                walk_runtime(v,q)
        elif isinstance(obj,list):
            for i,v in enumerate(obj):walk_runtime(v,f"{prefix}[{i}]")
    walk_runtime(rp)
    # Stable order + de-duplication keeps validation deterministic.
    seen=set();dedup=[]
    for q,v in out:
        key=(q,v)
        if key not in seen:seen.add(key);dedup.append(key)
    return dedup


ACTIVE_RUNTIME_VERSIONED_PATH_MIN_VERSION=(9,50)
ACTIVE_RUNTIME_VERSIONED_STATE_PATH_RE=re.compile(r'(?i)(?:^|\.)[^.]+_v\d+(?=\.|$)')

def _active_runtime_versioned_state_path_report(tasks:dict)->dict:
    """Reject version-pinned STATE paths in active/queued task machine contracts.

    Version labels may remain in task IDs, schema names, historical phases, and HISTORY.
    This only inspects declared STATE retrieval/machine paths, where version pinning causes
    current tasks to silently follow obsolete objects after schema migrations.
    """
    hits=[]
    for bucket in ('active_tasks','queued_tasks'):
        rows=tasks.get(bucket) or [] if isinstance(tasks,dict) else []
        if not isinstance(rows,list):continue
        for i,t in enumerate(rows):
            if not isinstance(t,dict):continue
            tid=str(t.get('task_id') or f'{bucket}[{i}]')
            declared=[]
            rr=t.get('retrieval_route') or {}
            for j,v in enumerate(rr.get('state_paths') or []):
                if isinstance(v,str):declared.append((f'retrieval_route.state_paths[{j}]',v))
            declared.extend(_task_machine_state_paths(t))
            seen=set()
            for fp,raw in declared:
                key=(fp,raw)
                if key in seen:continue
                seen.add(key)
                z=str(raw or '').strip()
                if z.startswith('ref:'):continue
                if z.startswith(('STATE.','state:')):z=z[6:]
                if ACTIVE_RUNTIME_VERSIONED_STATE_PATH_RE.search(z):
                    hits.append({'bucket':bucket,'index':i,'task_id':tid,'field':fp,'path':raw})
    try:ver=parse_version(str(tasks.get('save_version') or ('V99.99' if tasks.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=ACTIVE_RUNTIME_VERSIONED_PATH_MIN_VERSION
    return {'required':required,'minimum_version':version_text(ACTIVE_RUNTIME_VERSIONED_PATH_MIN_VERSION),'save_version':tasks.get('save_version') if isinstance(tasks,dict) else None,'count':len(hits),'hits':hits[:100]}


def _v130_layer_current_index_version_01(base: Path) -> Optional[str]:
    try:
        txt = (base / "INDEX.md").read_text(encoding="utf-8")
    except Exception:
        return None
    m = re.search(r"^> \*\*当前存档版本\*\*：(V\d+\.\d+)$", txt, re.M)
    return m.group(1) if m else None


def sum_numeric_values(x: Any) -> float:
    if isinstance(x, dict):
        return sum(sum_numeric_values(v) for v in x.values())
    if isinstance(x, list):
        return sum(sum_numeric_values(v) for v in x)
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    return 0.0


def _walk_numbers(x: Any, prefix: str = ""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _walk_numbers(v, f"{prefix}/{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _walk_numbers(v, f"{prefix}/{i}")
    elif isinstance(x, (int, float)) and not isinstance(x, bool):
        yield prefix, float(x)


def _reference_corpus(base: Path, state: dict) -> str:
    world = _authority_world_text(base) if (base / "rules.json").is_file() and (base / "catalog.json").is_file() else ""
    # STATE serialization contains current IDs. HISTORY is intentionally excluded for current-reference integrity.
    return world + "\n" + json.dumps(state, ensure_ascii=False)


def _parse_world_medical_expected(world_text: str) -> Tuple[Dict[str,int], List[str]]:
    """Derive medical capacities from WORLD itself; no mutable game values are hard-coded in the engine."""
    class_name_to_id: Dict[str,str] = {}
    for line in world_text.splitlines():
        m = re.match(r"\|\s*(CLS-[A-Z0-9-]+)\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            class_name_to_id[m.group(2).strip()] = m.group(1)
    sec = extract_rule_section(world_text, "RULE-PLAYER-FLEET-MEDICAL-01", max_chars=7000) or ""
    by_name: Dict[str,int] = {}
    for line in sec.splitlines():
        m = re.match(r"\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|", line)
        if m and m.group(1).strip() not in {"舰级"}:
            by_name[m.group(1).strip()] = int(m.group(2))
    expected: Dict[str,int] = {}
    unresolved=[]
    for name,val in by_name.items():
        cid = class_name_to_id.get(name)
        if cid: expected[cid]=val
        else: unresolved.append(name)
    return expected, unresolved


def _derive_naming_prefix_from_class_name(class_name: Any) -> Optional[str]:
    if not isinstance(class_name,str): return None
    x=re.sub(r"[`*_~]","",class_name).strip()
    if not x: return None
    if "级" in x:
        p=x.split("级",1)[0].strip(); return p or None
    if "号旗舰" in x:
        p=x.split("号旗舰",1)[0].strip(); return p or None
    if x.endswith("号") and len(x)>1:
        return x[:-1].strip() or None
    return None


def _validate_voyager_vessel_naming(vf: dict) -> List[str]:
    """Validate RULE-PLAYER-VESSEL-NAMING-01 and bind names to registered class names."""
    bad: List[str] = []
    rule=vf.get("vessel_naming"); roster=vf.get("vessel_roster")
    if not isinstance(rule,dict): return ["voyager_fleet.vessel_naming missing/not dict"]
    if rule.get("rule_id")!="RULE-PLAYER-VESSEL-NAMING-01": bad.append(f"unexpected naming rule_id={rule.get('rule_id')!r}")
    if rule.get("format")!="{prefix}{serial}号": bad.append(f"unexpected naming format={rule.get('format')!r}")
    vv=rule.get("validation_version",1)
    if not isinstance(vv,int) or isinstance(vv,bool) or vv<1: bad.append(f"invalid naming validation_version={vv!r}"); vv=1
    if not isinstance(roster,list): return bad+["voyager_fleet.vessel_roster missing/not list"]
    cc=vf.get("class_counts",[])
    if not isinstance(cc,list): return bad+["voyager_fleet.class_counts not list"]
    expected={}; seen=set()
    for rec in cc:
        if not isinstance(rec,dict): bad.append("class_counts contains non-dict record"); continue
        cid,count,prefix,cname=rec.get("class_id"),rec.get("count"),rec.get("naming_prefix"),rec.get("name")
        if not isinstance(cid,str) or not cid: bad.append(f"invalid class_id in {rec!r}"); continue
        if cid in seen: bad.append(f"duplicate class_id {cid}")
        seen.add(cid)
        if not isinstance(count,int) or isinstance(count,bool) or count<0: bad.append(f"invalid count for {cid}: {count!r}"); continue
        if not isinstance(prefix,str) or not prefix.strip(): bad.append(f"missing naming_prefix for {cid}"); continue
        prefix=prefix.strip()
        if vv>=2:
            d=_derive_naming_prefix_from_class_name(cname)
            if d is None: bad.append(f"cannot derive naming prefix from class name {cid}: {cname!r}")
            elif prefix!=d: bad.append(f"{cid} naming_prefix={prefix!r} does not match class name prefix={d!r}")
        expected[cid]=(count,prefix)
    if vv>=2:
        em={cid:p for cid,(_,p) in expected.items()}
        if rule.get("standard_class_prefixes")!=em: bad.append(f"standard_class_prefixes mismatch: {rule.get('standard_class_prefixes')!r} != {em!r}")
    ids=set(); names=set(); by_class={cid:[] for cid in expected}; external=[]
    for i,rec in enumerate(roster):
        if not isinstance(rec,dict): bad.append(f"roster[{i}] non-dict"); continue
        vid,name,cid=rec.get("vessel_id"),rec.get("name"),rec.get("class_id"); serial,prefix,ext=rec.get("serial"),rec.get("naming_prefix"),rec.get("external_owned",False)
        if not isinstance(vid,str) or not vid: bad.append(f"roster[{i}] invalid vessel_id"); continue
        if vid in ids: bad.append(f"duplicate vessel_id {vid}")
        ids.add(vid)
        if not isinstance(name,str) or not name: bad.append(f"{vid} invalid name"); continue
        if name in names: bad.append(f"duplicate vessel name {name}")
        names.add(name)
        if not isinstance(serial,int) or isinstance(serial,bool) or serial<=0: bad.append(f"{vid} invalid serial={serial!r}"); continue
        if not isinstance(prefix,str) or not prefix: bad.append(f"{vid} invalid naming_prefix={prefix!r}"); continue
        if name!=f"{prefix}{serial}号": bad.append(f"{vid} name mismatch: {name!r} != {prefix}{serial}号")
        if cid in expected and not ext: by_class[cid].append(rec)
        elif ext:
            if vv>=2:
                rc=rec.get("registered_class_name"); d=_derive_naming_prefix_from_class_name(rc)
                if d is None: bad.append(f"{vid} external owned vessel missing/invalid registered_class_name={rc!r}")
                elif prefix!=d: bad.append(f"{vid} prefix={prefix!r} does not match registered class prefix={d!r}")
            external.append(rec)
        else: bad.append(f"{vid} class_id not in standard classes and not external_owned: {cid!r}")
    for cid,(count,prefix) in expected.items():
        rows=by_class.get(cid,[])
        if len(rows)!=count: bad.append(f"{cid} roster count={len(rows)} expected={count}")
        serials=sorted(r.get("serial") for r in rows if isinstance(r.get("serial"),int) and not isinstance(r.get("serial"),bool))
        if serials!=list(range(1,count+1)): bad.append(f"{cid} serials={serials} expected={list(range(1,count+1))}")
        for r in rows:
            if r.get("naming_prefix")!=prefix: bad.append(f"{r.get('vessel_id')} prefix={r.get('naming_prefix')!r} expected={prefix!r}")
    ee=vf.get("external_owned_ship_count")
    if isinstance(ee,int) and not isinstance(ee,bool) and len(external)!=ee: bad.append(f"external roster count={len(external)} expected={ee}")
    if vv>=2:
        ed=rule.get("current_external_classes")
        if not isinstance(ed,dict): bad.append("current_external_classes missing/not dict")
        else:
            eby={r.get("vessel_id"):r for r in external if isinstance(r,dict)}
            if set(ed)!=set(eby): bad.append(f"current_external_classes ids mismatch: {sorted(ed)} != {sorted(eby)}")
            for vid,d in ed.items():
                r=eby.get(vid)
                if not r or not isinstance(d,dict): continue
                vals={"registered_class_name":r.get("registered_class_name"),"naming_prefix":r.get("naming_prefix"),"serial":r.get("serial"),"formal_name":r.get("name")}
                for fld,val in vals.items():
                    if d.get(fld)!=val: bad.append(f"{vid} external class registry {fld}={d.get(fld)!r} != roster {val!r}")
    sc=vf.get("ship_count")
    if isinstance(sc,int) and not isinstance(sc,bool) and len(roster)!=sc: bad.append(f"total roster count={len(roster)} expected ship_count={sc}")
    named=vf.get("named_vessels",{})
    if isinstance(named,dict):
        rby={r.get("vessel_id"):r for r in roster if isinstance(r,dict) and isinstance(r.get("vessel_id"),str)}
        for vid,rec in named.items():
            rr=rby.get(vid)
            if rr is None: bad.append(f"named_vessels id missing from vessel_roster: {vid}")
            elif isinstance(rec,dict) and rec.get("name")!=rr.get("name"): bad.append(f"named_vessels name mismatch {vid}: {rec.get('name')!r} != {rr.get('name')!r}")
    else: bad.append("named_vessels not dict")
    return bad

def _strip_save_metadata(obj: Any) -> Any:
    x = copy.deepcopy(obj)
    if isinstance(x, dict):
        for k in ["save_version", "sync_scope"]:
            x.pop(k, None)
    return x


def _substantive_parent_change(parent_base: Path, base: Path) -> dict:
    pstate=read_json(parent_base/"state.json"); cstate=read_json(base/"state.json")
    ptasks=read_json(parent_base/"tasks.json"); ctasks=read_json(base/"tasks.json")
    pr=read_json(parent_base/"rules.json");cr=read_json(base/"rules.json")
    pc=read_json(parent_base/"catalog.json");cc=read_json(base/"catalog.json")
    return {
        "rules.json": _strip_save_metadata(pr) != _strip_save_metadata(cr),
        "catalog.json": _strip_save_metadata(pc) != _strip_save_metadata(cc),
        "state.json": _strip_save_metadata(pstate) != _strip_save_metadata(cstate),
        "tasks.json": _strip_save_metadata(ptasks) != _strip_save_metadata(ctasks),
    }



def _v10_authority_surface_report(state:dict,tasks:dict)->dict:
    try:ver=parse_version(str(state.get("save_version") or tasks.get("save_version") or ('V99.99' if state.get('manifest_ref') or tasks.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=(10,0) or ((tasks.get("task_object_schema") or {}).get("revision")==TASK_OBJECT_SCHEMA)
    rows=[]
    er=state.get("engine_runtime") or {}
    for p,v in (("STATE.engine_runtime.engine_maintenance",er.get("engine_maintenance")),("STATE.engine_runtime.automation",er.get("automation"))):
        if v is not None:rows.append({"path":p,"reason":"runtime_tool_metadata_not_game_fact"})
    rec=er.get("recovery") or {}
    if isinstance(rec,dict) and rec.get("current_checkpoint") is not None:rows.append({"path":"STATE.engine_runtime.recovery.current_checkpoint","reason":"derived_cold_start_cache"})
    tr=tasks.get("recovery") or {}
    if isinstance(tr,dict) and tr.get("current_checkpoint") is not None:rows.append({"path":"TASKS.recovery.current_checkpoint","reason":"derived_cold_start_cache"})
    auto=tasks.get("automation_schema") or {}
    if isinstance(auto,dict) and auto.get("engine_version") is not None:rows.append({"path":"TASKS.automation_schema.engine_version","reason":"runtime_build_identity_belongs_to_INDEX_COMMIT"})
    audits=state.get("audits") or {}
    if isinstance(audits,dict):
        if audits.get("archive"):rows.append({"path":"STATE.audits.archive","reason":"terminal_audits_belong_to_HISTORY","count":len(audits.get("archive") or [])})
        extra=[k for k in audits if k not in {"schema","active","archive"}]
        for k in extra:rows.append({"path":"STATE.audits."+str(k),"reason":"legacy_audit_snapshot_belongs_to_HISTORY"})
    cr=state.get("commander_runtime_rules")
    if isinstance(cr,dict):
        allowed={"_structure","parameters","overrides"};extra=[k for k in cr if k not in allowed]
        for k in extra:rows.append({"path":"STATE.commander_runtime_rules."+str(k),"reason":"stable_rule_reference_belongs_to_WORLD_INDEX"})
        st=(cr.get("_structure") or {})
        if required and st.get("revision")!="COMMANDER_RUNTIME_RULES_V3":rows.append({"path":"STATE.commander_runtime_rules._structure.revision","reason":"expected_COMMANDER_RUNTIME_RULES_V3"})
    return {"required":required,"minimum_version":"V10.0","count":len(rows),"rows":rows[:100]}


def _infer_parent_for_check(base: Path) -> Optional[dict]:
    try:
        root = base.parent if SNAP_RE.match(base.name) else ROOT
        if SNAP_RE.match(base.name):
            cur = validate_game_snapshot(base, verify_parent=False, root=root)
        elif base.resolve() == ROOT.resolve():
            cur = latest_valid_snapshot(ROOT, verify_parent=True)
            if not files_match(ROOT, cur["dir"]): return None
        else:
            return None
        if not cur or not cur.get("parent_save_set_id") or cur.get("recovery_anchor"):
            return None
        pp = snapshot_path_from_sid(root, cur["parent_save_set_id"])
        return validate_game_snapshot(pp, verify_parent=True, root=root) if pp else None
    except Exception:
        return None


def _v130_layer__event_change_target_prefixes_01(events: List[dict]) -> set:
    out=set()
    def one(ch):
        if isinstance(ch,dict):
            t=ch.get("target")
            if isinstance(t,str) and t.strip(): out.add(re.split(r"[./]",t.strip(),maxsplit=1)[0].upper())
    for e in events:
        changes=e.get("changes") if isinstance(e,dict) else None
        if isinstance(changes,list):
            for ch in changes: one(ch)
        elif isinstance(changes,dict): one(changes)
    return out


def _v130_layer__event_targets_by_domain_01(events: List[dict]) -> Dict[str,List[str]]:
    out={"WORLD":[],"STATE":[],"TASKS":[]}
    def one(ch):
        if not isinstance(ch,dict): return
        t=ch.get("target")
        if not isinstance(t,str) or not t.strip(): return
        raw=t.strip(); first=re.split(r"[./]",raw,maxsplit=1)[0].upper()
        if first not in out: return
        rest=raw[len(re.split(r"[./]",raw,maxsplit=1)[0]):].lstrip("./").replace(".","/")
        out[first].append("/"+rest if rest else "")
    for e in events:
        changes=e.get("changes") if isinstance(e,dict) else None
        if isinstance(changes,list):
            for ch in changes: one(ch)
        elif isinstance(changes,dict): one(changes)
    return out


def _changed_structured_paths(parent_base: Path, base: Path, fn: str, limit: int = 10000) -> Tuple[List[str],bool]:
    a=_strip_save_metadata(read_json(parent_base/fn)); b=_strip_save_metadata(read_json(base/fn))
    rows,tr=json_diff_paths(a,b,limit=limit)
    paths=[]
    for row in rows:
        p=row.split(":",1)[0]
        if p: paths.append(p)
    return paths,tr


def _target_covers_path(target: str, changed: str) -> bool:
    if not target: return False
    t=target.rstrip("/"); c=changed.rstrip("/")
    return c==t or c.startswith(t+"/") or t.startswith(c+"/")


def _event_authority_files(events: List[dict]) -> Tuple[set,List[str]]:
    allowed={"rules.json","catalog.json","state.json","tasks.json"}; out=set(); bad=[]
    for e in events:
        if not isinstance(e,dict) or "authority_files" not in e: continue
        af=e.get("authority_files")
        if not isinstance(af,list) or not all(isinstance(x,str) and x in allowed for x in af) or len(af)!=len(set(af)):
            bad.append(f"seq={e.get('seq')} invalid authority_files={af!r}")
        else: out.update(af)
    return out,bad


def _audit_registry_items(audits: Any) -> Tuple[List[dict], str]:
    """Return audit records from either the legacy list or the V2 active/archive registry."""
    if isinstance(audits, list):
        return audits, "legacy_list"
    if isinstance(audits, dict):
        active = audits.get("active")
        archive = audits.get("archive")
        if isinstance(active, list) and isinstance(archive, list):
            return active + archive, str(audits.get("schema") or "registry_missing_schema")
    return [], "invalid"


def _audit_registry_errors(audits: Any) -> List[str]:
    """Validate the audit registry while retaining read compatibility with legacy snapshots."""
    if isinstance(audits, list):
        items = audits
    elif isinstance(audits, dict):
        if audits.get("schema") != AUDIT_REGISTRY_SCHEMA:
            return [f"schema must be {AUDIT_REGISTRY_SCHEMA}"]
        active = audits.get("active")
        archive = audits.get("archive")
        if not isinstance(active, list) or not isinstance(archive, list):
            return ["active and archive must both be lists"]
        items = active + archive
        errors = []
        archived_statuses = {"archived_known_gap", "archived_unrecoverable", "closed_known_gap"}
        for a in active:
            if not isinstance(a, dict):
                errors.append("active contains non-object record")
                continue
            st = str(a.get("status") or "").strip().lower()
            if st.startswith("resolved") or st in archived_statuses:
                errors.append(f"active contains terminal audit {a.get('audit_id') or a.get('id') or '<unnamed>'}")
        for a in archive:
            if not isinstance(a, dict):
                errors.append("archive contains non-object record")
                continue
            st = str(a.get("status") or "").strip().lower()
            if not (st.startswith("resolved") or st in archived_statuses):
                errors.append(f"archive contains nonterminal audit {a.get('audit_id') or a.get('id') or '<unnamed>'}")
        if errors:
            return errors
    else:
        return ["audits must be a legacy list or V2 registry object"]

    seen = set()
    dup = []
    for a in items:
        if not isinstance(a, dict):
            return ["audit registry contains non-object record"]
        aid = str(a.get("audit_id") or a.get("id") or "").strip()
        if not aid:
            return ["audit record missing audit_id/id"]
        if aid in seen:
            dup.append(aid)
        seen.add(aid)
    return [f"duplicate audit ids: {sorted(set(dup))}"] if dup else []


def _audit_summary(audits: Any) -> dict:
    """Classify audit records by operational meaning instead of counting every retained record as a warning."""
    items, registry_format = _audit_registry_items(audits)
    buckets = {
        "open_reconcilable": [],
        "open_blocking_other": [],
        "open_nonblocking": [],
        "archived_known_gap": [],
        "resolved": [],
    }
    for a in items:
        if not isinstance(a, dict):
            buckets["open_blocking_other"].append("<malformed>")
            continue
        aid = str(a.get("audit_id") or a.get("id") or "<unnamed>")
        st = str(a.get("status") or "").strip().lower()
        if st.startswith("resolved"):
            buckets["resolved"].append(aid)
        elif st in {"archived_known_gap", "archived_unrecoverable", "closed_known_gap"}:
            buckets["archived_known_gap"].append(aid)
        elif st in {"open_nonblocking", "nonblocking"}:
            buckets["open_nonblocking"].append(aid)
        elif st in {"open_reconcilable", "reconcilable", "audit_scheduled"}:
            buckets["open_reconcilable"].append(aid)
        else:
            # Legacy/missing status remains blocking until explicitly classified.
            buckets["open_blocking_other"].append(aid)
    open_blocking = len(buckets["open_reconcilable"]) + len(buckets["open_blocking_other"])
    return {
        "registry_format": registry_format,
        "total_records": len(items),
        "open_blocking": open_blocking,
        "open_reconcilable": len(buckets["open_reconcilable"]),
        "open_blocking_other": len(buckets["open_blocking_other"]),
        "open_nonblocking": len(buckets["open_nonblocking"]),
        "archived_known_gap": len(buckets["archived_known_gap"]),
        "resolved": len(buckets["resolved"]),
        "ids": buckets,
        "policy": "Only open blocking audits are warnings; V2 separates active and archive records while legacy list snapshots remain readable for recovery.",
    }



def _shadow_active_mobile_vessels(state: dict) -> Dict[str, dict]:
    sf=state.get("shadow_fleet") or {}; vessels=sf.get("vessels") or {}; out={}
    if not isinstance(vessels,dict): return out
    for vid,rec in vessels.items():
        if not isinstance(rec,dict): continue
        if vid=="VES-PRISON1" or rec.get("propulsion")=="none" or rec.get("status")=="active_shadow_service_nonpropelled": continue
        if rec.get("active_service") is True or str(rec.get("status") or "").startswith("active_"): out[str(vid)]=rec
    return out


def _robot_model_map_from_vessel(rec: dict) -> Tuple[Optional[int],Dict[str,int],str]:
    """Resolve current combat-robot count/model split without trusting derived fleet snapshots.

    Quantity authority is current_combat_robot_count when present. Exact current_embarked_assets
    (or an explicit current loadout map) may provide the model split. Older plan/refit structures
    may identify a single model family, but their quantities never override the current count.
    """
    models=("fortress5","fortress6")
    raw_count=rec.get("current_combat_robot_count")
    count=raw_count if isinstance(raw_count,int) and not isinstance(raw_count,bool) and raw_count>=0 else None
    for field in ("current_embarked_assets","loadout"):
        m=rec.get(field)
        if not isinstance(m,dict): continue
        exact={k:int(m[k]) for k in models if isinstance(m.get(k),int) and not isinstance(m.get(k),bool) and int(m[k])>=0}
        if not exact: continue
        sm=sum(exact.values())
        if count is None: return sm,exact,field
        if sm==count: return count,exact,field
        if field=="current_embarked_assets": return count,exact,"current_embarked_assets_mismatch"
    types=set()
    def walk(obj: Any, path: str="") -> None:
        if isinstance(obj,dict):
            for k,v in obj.items():
                if k in {"ground_power_snapshot","mobile_combat_assets_current","combat_power_current"}: continue
                if k in models and isinstance(v,int) and not isinstance(v,bool): types.add(k)
                else: walk(v,path+"/"+str(k))
        elif isinstance(obj,list):
            for x in obj: walk(x,path)
    walk(rec)
    if count is not None and len(types)==1: return count,{next(iter(types)):count},"current_count_plus_model_identity"
    return count,{},"current_count_only" if count is not None else "unknown"


def _snapshot_robot_count(rec: dict) -> Optional[int]:
    if not isinstance(rec,dict): return None
    text=str(rec.get("loadout") or "")
    nums=[int(x) for x in re.findall(r"堡垒-[56]×(\d+)",text)]
    return sum(nums) if nums else 0


def _asset_count_map(obj: Any, ignored: Optional[set]=None) -> Dict[str,int]:
    ignored=ignored or {"total"}
    if not isinstance(obj,dict): return {}
    return {str(k):int(v) for k,v in obj.items() if k not in ignored and isinstance(v,int) and not isinstance(v,bool) and v>=0}


def shadow_shipboard_asset_crosspath_report(state: dict) -> dict:
    """Fast deterministic cross-path audit for current Shadow Fleet embarked assets.

    Current per-vessel manifests/counts are authoritative. Fleet aggregate is a required
    derived projection. ``ground_power_snapshot`` is an optional rebuildable report cache:
    when present it must agree with current manifests, but its absence must never block a save
    or force AI to preserve stale combat-power numbers.
    """
    sf=state.get("shadow_fleet") or {}; vessels=_shadow_active_mobile_vessels(state); bad=[]; model_totals={"fortress5":0,"fortress6":0}; total=0
    snap_raw=sf.get("ground_power_snapshot")
    snapshot_present=isinstance(snap_raw,dict) and bool(snap_raw)
    snap=snap_raw if snapshot_present else {}
    snapships=snap.get("ships") or {}; by_vid={}
    if snapshot_present and isinstance(snapships,dict):
        for _,sr in snapships.items():
            if isinstance(sr,dict) and isinstance(sr.get("vessel_id"),str): by_vid[sr["vessel_id"]]=sr
    newest_asset_time=None
    for vid,rec in vessels.items():
        name=str(rec.get("name") or vid); count,models,source=_robot_model_map_from_vessel(rec)
        cea=rec.get("current_embarked_assets") or {}
        if isinstance(cea,dict):
            gt=parse_iso(cea.get("as_of"))
            if gt and (newest_asset_time is None or gt>newest_asset_time): newest_asset_time=gt
            exact={k:int(cea[k]) for k in ("fortress5","fortress6") if isinstance(cea.get(k),int) and not isinstance(cea.get(k),bool)}
            if exact and count is not None and sum(exact.values())!=count:
                bad.append({"kind":"current_manifest_robot_count","vessel_id":vid,"name":name,"current_combat_robot_count":count,"current_embarked_robot_sum":sum(exact.values()),"source":source})
        cav=rec.get("current_armored_vehicles") or {}
        if isinstance(cav,dict):
            gt=parse_iso(cav.get("as_of"))
            if gt and (newest_asset_time is None or gt>newest_asset_time): newest_asset_time=gt
        if count is None:
            bad.append({"kind":"current_robot_count_missing","vessel_id":vid,"name":name}); continue
        total+=count
        if models:
            if sum(models.values())!=count:
                bad.append({"kind":"current_robot_model_split","vessel_id":vid,"name":name,"count":count,"models":models,"source":source})
            else:
                for k,n in models.items(): model_totals[k]=model_totals.get(k,0)+int(n)
        else: bad.append({"kind":"current_robot_model_unresolved","vessel_id":vid,"name":name,"count":count})
        if snapshot_present:
            sr=by_vid.get(vid)
            if sr is None: bad.append({"kind":"ground_snapshot_vessel_missing","vessel_id":vid,"name":name})
            else:
                sc=_snapshot_robot_count(sr)
                if sc!=count: bad.append({"kind":"ground_snapshot_robot_count","vessel_id":vid,"name":name,"current":count,"snapshot":sc})
                if isinstance(cav,dict) and cav:
                    sa=sr.get("armored_vehicles") or {}
                    cur_total=cav.get("total"); snap_total=sa.get("total") if isinstance(sa,dict) else None
                    if isinstance(cur_total,int) and not isinstance(cur_total,bool) and cur_total!=snap_total:
                        bad.append({"kind":"ground_snapshot_armored_total","vessel_id":vid,"name":name,"current":cur_total,"snapshot":snap_total})
                    cur_models=_asset_count_map(cav,{"total"}); snap_models=_asset_count_map(sa,{"total"})
                    cur_models={k:v for k,v in cur_models.items() if not k.endswith("_G") and k not in {"added_ground_G"}}
                    snap_models={k:v for k,v in snap_models.items() if not k.endswith("_G") and k not in {"added_ground_G"}}
                    if cur_models!=snap_models:
                        bad.append({"kind":"ground_snapshot_armored_models","vessel_id":vid,"name":name,"current":cur_models,"snapshot":snap_models})
    agg=((sf.get("mobile_combat_assets_current") or {}).get("shipboard_combat_robots") or {})
    if isinstance(agg,dict):
        if agg.get("total")!=total: bad.append({"kind":"fleet_robot_total","current_manifest_total":total,"aggregate":agg.get("total")})
        am=agg.get("models_exact_current") or {}
        if isinstance(am,dict):
            actual={k:int(am.get(k,0) or 0) for k in model_totals}
            if actual!=model_totals: bad.append({"kind":"fleet_robot_models","current_manifest_models":model_totals,"aggregate":actual})
        else: bad.append({"kind":"fleet_robot_models_missing"})
    else: bad.append({"kind":"fleet_robot_aggregate_missing"})
    if snapshot_present:
        sat=parse_iso(snap.get("as_of"))
        if newest_asset_time and (sat is None or sat<newest_asset_time):
            bad.append({"kind":"derived_snapshot_stale","ground_power_snapshot_as_of":snap.get("as_of"),"newest_current_asset_as_of":newest_asset_time.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"status":"PASS" if not bad else "FAIL","errors":bad,"active_mobile_vessels":len(vessels),"current_robot_total":total,"current_robot_models":model_totals,"snapshot_present":snapshot_present,"snapshot_role":"optional_rebuildable_derived_cache_non_authoritative"}


def _run_checks_impl(base: Path, full: bool = False, expected_version: Optional[str] = None,
               require_manifest: bool = True, parent_snapshot: Optional[dict] = None, validation_cache: Optional[dict]=None) -> dict:
    errors: List[str] = []; warnings: List[str] = []; passed: List[str] = []
    def ok(name): passed.append(name)
    def fail(name,detail): errors.append(f"{name}: {detail}")
    def warn(name,detail): warnings.append(f"{name}: {detail}")

    for fn in AUTH_FILES:
        if not (base/fn).is_file(): fail("FILES", f"missing {fn}")
    if errors: return _check_result(base,full,passed,errors,warnings,0,0,0)
    history_pair=None
    try:
        state=read_json(base/"state.json"); tasks=read_json(base/"tasks.json")
        if parent_snapshot is not None:
            history_pair=_history_read_pair_incremental(Path(parent_snapshot["dir"])/"events.jsonl",base/"events.jsonl",validation_cache)
            meta,events,event_raw=history_pair["current"]
        else:
            meta,events,event_raw=_history_cached_full(base/"events.jsonl",validation_cache)
        world_text=_authority_world_text(base); index_text=_manifest_protocol_text(base); ok("PARSE")
        if history_pair is not None and history_pair.get("mode")=="tail_incremental":ok(f"HISTORY_TAIL_INCREMENTAL[{history_pair.get('tail_event_count',0)}]")
    except Exception as e:
        fail("PARSE",str(e)); return _check_result(base,full,passed,errors,warnings,0,0,0)

    if text_policy_active(world_text):
        text_bad=authority_text_policy_report(base)
        if not text_bad:ok("TEXT_CHARSET_POLICY")
        else:fail("TEXT_CHARSET_POLICY",json.dumps(text_bad,ensure_ascii=False))
        name_bad=name_symbol_policy_report(base)
        if not name_bad:ok("TEXT_NAME_SYMBOL_POLICY")
        else:fail("TEXT_NAME_SYMBOL_POLICY",json.dumps(name_bad,ensure_ascii=False))

    schemas={"STATE":state.get("schema_version"),"TASKS":tasks.get("schema_version"),"HISTORY":meta.get("schema_version")}
    if len(set(schemas.values()))==1 and next(iter(set(schemas.values())), None) in SUPPORTED_SCHEMA_VERSIONS: ok("SCHEMA")
    else: fail("SCHEMA",f"unsupported/mismatched schemas={schemas}; supported={sorted(SUPPORTED_SCHEMA_VERSIONS)}")

    iv=current_index_version(base)
    # Native eight-component protocol: manifest.json is the sole current save/version authority.
    forbidden_versions={"state":state.get("save_version"),"tasks":tasks.get("save_version"),"events_metadata":meta.get("save_version")}
    declared={k:v for k,v in forbidden_versions.items() if v is not None}
    if declared:
        fail("VERSION_AUTHORITY",f"current version duplicates forbidden outside manifest: {declared}")
    elif expected_version and iv!=expected_version:
        fail("VERSION",f"manifest expected {expected_version}; actual={iv}")
    elif not iv:
        fail("VERSION","manifest save_version missing")
    else:
        ok("VERSION")

    ph=_protocol_symbol_hygiene_report(state,world_text,index_text)
    if (not ph.get("required")) or int(ph.get("count",0) or 0)==0:ok("PROTOCOL_SYMBOL_HYGIENE" if ph.get("required") else "PROTOCOL_SYMBOL_HYGIENE_UPGRADE_COMPAT")
    else:fail("PROTOCOL_SYMBOL_HYGIENE",json.dumps(ph,ensure_ascii=False))

    stale_current=_stale_current_semantic_report(state,tasks,index_text)
    if (not stale_current.get('required')) or int(stale_current.get('count',0) or 0)==0:ok('STALE_CURRENT_SEMANTIC_CHECK' if stale_current.get('required') else 'STALE_CURRENT_SEMANTIC_CHECK_UPGRADE_COMPAT')
    else:fail('STALE_CURRENT_SEMANTIC_CHECK',json.dumps(stale_current,ensure_ascii=False))

    if require_manifest:
        wr=_world_revision_from_text(world_text); ir=_index_world_revision_from_text(index_text)
        if wr and ir and wr==ir: ok("WORLD_REVISION_SYNC")
        elif wr or ir: fail("WORLD_REVISION_SYNC",f"INDEX={ir} WORLD={wr}")

    wreg=_world_rule_registry_integrity_report(world_text)
    if int(wreg.get("count",0) or 0)==0:ok("WORLD_RULE_REGISTRY_INTEGRITY")
    else:fail("WORLD_RULE_REGISTRY_INTEGRITY",json.dumps(wreg,ensure_ascii=False))

    st=state.get("game_time"); tt=tasks.get("game_time")
    if st and st==tt and parse_iso(st): ok("GAME_TIME")
    else: fail("GAME_TIME",f"STATE={st}, TASKS={tt}")

    seqs=[e.get("seq") for e in events]
    seq_types=all(isinstance(x,int) and not isinstance(x,bool) for x in seqs)
    if seq_types and seqs==list(range(1,len(seqs)+1)):ok("HISTORY_SEQ")
    else:fail("HISTORY_SEQ",f"count={len(seqs)} last={seqs[-1] if seqs else None}; strict_int={seq_types}")
    next_seq=_history_expected_next_seq(events) if seq_types and seqs==list(range(1,len(seqs)+1)) else None
    if isinstance(meta.get("next_seq"),int) and not isinstance(meta.get("next_seq"),bool) and meta.get("next_seq")==next_seq:ok("HISTORY_NEXT_SEQ")
    else:fail("HISTORY_NEXT_SEQ",f"metadata={meta.get('next_seq')} expected={next_seq}")
    event_ids=[e.get("event_id") for e in events]
    if all(isinstance(x,str) and x.strip() for x in event_ids) and len(event_ids)==len(set(event_ids)):ok("EVENT_ID_UNIQUE")
    else:fail("EVENT_ID_UNIQUE","missing/non-string/duplicate event_id")
    current_dt=parse_iso(st); future=[]
    if current_dt:
        for e in events:
            edt=parse_iso(e.get("game_time"))
            if edt and edt>current_dt:future.append((e.get("seq"),e.get("game_time")))
    if not future:ok("HISTORY_TIME_BOUND")
    else:fail("HISTORY_TIME_BOUND",str(future[:10]))

    _asset_ledger_bad=_validate_active_asset_ledger(state)
    if _asset_ledger_bad is None:
        if isinstance(state.get('asset_ledger_v1'),dict):ok("ASSET_LEDGER_INTEGRITY")
    else:fail("ASSET_LEDGER_INTEGRITY",_asset_ledger_bad)

    summary=state.get("summary",{}); vf=state.get("voyager_fleet",{}); jf=state.get("jinchuan_fleet",{})
    ships=summary.get("ships",{}); pers=summary.get("personnel",{}); funds=summary.get("funds",{})
    if ships.get("voyager")==vf.get("ship_count") and ships.get("jinchuan")==jf.get("ship_count") and ships.get("total")==ships.get("voyager",0)+ships.get("jinchuan",0):ok("SHIP_COUNTS")
    else:fail("SHIP_COUNTS",f"summary={ships}")
    class_sum=sum(int(x.get("count",0)) for x in vf.get("class_counts",[]))
    if class_sum==vf.get("standard_class_ship_count") and vf.get("ship_count")==class_sum+int(vf.get("external_owned_ship_count",0)):ok("VOYAGER_CLASS_COUNTS")
    else:fail("VOYAGER_CLASS_COUNTS",f"class_sum={class_sum}")
    if "RULE-PLAYER-VESSEL-NAMING-01" in world_text:
        vessel_name_bad=_validate_voyager_vessel_naming(vf)
        if not vessel_name_bad:ok("VOYAGER_VESSEL_NAMING")
        else:fail("VOYAGER_VESSEL_NAMING",json.dumps(vessel_name_bad[:60],ensure_ascii=False))
    vloc=_player_vessel_location_hygiene_report(state)
    if (not vloc.get('required')) or int(vloc.get('count',0) or 0)==0:ok("PLAYER_VESSEL_LOCATION_AUTHORITY")
    else:fail("PLAYER_VESSEL_LOCATION_AUTHORITY",json.dumps(vloc,ensure_ascii=False))
    vmcur=_voyager_named_mission_current_hygiene_report(state)
    if (not vmcur.get('required')) or int(vmcur.get('count',0) or 0)==0:ok("VOYAGER_MISSION_CURRENT_HYGIENE")
    else:fail("VOYAGER_MISSION_CURRENT_HYGIENE",json.dumps(vmcur,ensure_ascii=False))
    tmir=_active_task_temporal_mirror_report(state,tasks)
    if (not tmir.get('required')) or int(tmir.get('count',0) or 0)==0:ok("ACTIVE_TASK_TEMPORAL_MIRROR_HYGIENE")
    else:fail("ACTIVE_TASK_TEMPORAL_MIRROR_HYGIENE",json.dumps(tmir,ensure_ascii=False))
    dcur=_dated_current_alias_report(state)
    if (not dcur.get('required')) or int(dcur.get('count',0) or 0)==0:ok("DATED_CURRENT_ALIAS_HYGIENE")
    else:fail("DATED_CURRENT_ALIAS_HYGIENE",json.dumps(dcur,ensure_ascii=False))
    ctmp=_current_state_temporal_hygiene_report(state)
    if (not ctmp.get('required')) or int(ctmp.get('count',0) or 0)==0:ok("CURRENT_STATE_TEMPORAL_HYGIENE")
    else:fail("CURRENT_STATE_TEMPORAL_HYGIENE",json.dumps(ctmp,ensure_ascii=False))
    ronly=_routing_only_fact_hygiene_report(state)
    if (not ronly.get('required')) or int(ronly.get('count',0) or 0)==0:ok("ROUTING_ONLY_FACT_HYGIENE")
    else:fail("ROUTING_ONLY_FACT_HYGIENE",json.dumps(ronly,ensure_ascii=False))
    scoh=_current_settlement_record_coherence_report(state)
    if (not scoh.get('required')) or int(scoh.get('count',0) or 0)==0:ok("CURRENT_SETTLEMENT_RECORD_COHERENCE")
    else:fail("CURRENT_SETTLEMENT_RECORD_COHERENCE",json.dumps(scoh,ensure_ascii=False))
    elife=_entity_lifecycle_integrity_report(state,tasks)
    if (not elife.get('required')) or int(elife.get('count',0) or 0)==0:ok("ENTITY_LIFECYCLE_INTEGRITY")
    else:fail("ENTITY_LIFECYCLE_INTEGRITY",json.dumps(elife,ensure_ascii=False))
    ereg=_entity_registry_integrity_report(state)
    if (not ereg.get('required')) or int(ereg.get('count',0) or 0)==0:ok("ENTITY_REGISTRY_INTEGRITY" if ereg.get('required') else "ENTITY_REGISTRY_INTEGRITY_UPGRADE_COMPAT")
    else:fail("ENTITY_REGISTRY_INTEGRITY",json.dumps(ereg,ensure_ascii=False))
    if pers.get("voyager")==vf.get("current_personnel") and pers.get("jinchuan")==jf.get("personnel_total") and pers.get("total")==pers.get("voyager",0)+pers.get("jinchuan",0):ok("PERSONNEL_COUNTS")
    else:fail("PERSONNEL_COUNTS",f"summary={pers}")

    sf=state.get("shadow_fleet",{})
    fleet_cross_bad=[]
    if ships.get("shadow_active")!=sf.get("ship_count_active"):fleet_cross_bad.append(("shadow_ships",ships.get("shadow_active"),sf.get("ship_count_active")))
    if pers.get("shadow")!=sf.get("personnel_total"):fleet_cross_bad.append(("shadow_personnel",pers.get("shadow"),sf.get("personnel_total")))
    if ships.get("total_player_active")!=sum(int(x or 0) for x in [ships.get("voyager"),ships.get("jinchuan"),ships.get("shadow_active")]):fleet_cross_bad.append(("total_player_active",ships.get("total_player_active")))
    if pers.get("total_player_active")!=sum(int(x or 0) for x in [pers.get("voyager"),pers.get("jinchuan"),pers.get("shadow")]):fleet_cross_bad.append(("personnel_total_player_active",pers.get("total_player_active")))
    if not fleet_cross_bad:ok("FLEET_CORE_CROSSPATH")
    else:fail("FLEET_CORE_CROSSPATH",json.dumps(fleet_cross_bad,ensure_ascii=False))

    if SHIPBOARD_ASSET_CROSSPATH_RULE_ID in world_text:
        asset_cross=shadow_shipboard_asset_crosspath_report(state)
        if asset_cross.get("status")=="PASS":ok("SHIPBOARD_ASSET_CROSSPATH")
        else:fail("SHIPBOARD_ASSET_CROSSPATH",json.dumps(asset_cross.get("errors",[])[:80],ensure_ascii=False))

    if state.get("schema_version")=="V7.0":
        loc=sf.get("current_location") or {};loc_bad=[]
        base_rec=loc.get("at_shadow_base") or {};deploy=loc.get("deployments") or {};transit=loc.get("transit") or {}
        bships=int(base_rec.get("ships",0) or 0)
        dships=sum(int((v or {}).get("ships",0) or 0) for v in deploy.values() if isinstance(v,dict)) if isinstance(deploy,dict) else 0
        tships=int(transit.get("ships",0) or 0) if isinstance(transit,dict) else 0
        if bships+dships+tships!=int(sf.get("ship_count_active",0) or 0):loc_bad.append(("partition",bships,dships,tships,sf.get("ship_count_active")))
        if loc.get("as_of")!=state.get("game_time") and not _location_coverage_valid(state):loc_bad.append(("time_coverage",loc.get("as_of"),state.get("game_time")))
        vessels=sf.get("vessels") or {};active_mobile=[]
        if isinstance(vessels,dict):
            for vid,rec in vessels.items():
                if not isinstance(rec,dict):continue
                if vid=="VES-PRISON1" or rec.get("propulsion")=="none" or rec.get("status")=="active_shadow_service_nonpropelled":continue
                if rec.get("active_service") is True or str(rec.get("status","")).startswith("active_"):active_mobile.append(vid)
        if len(active_mobile)!=int(sf.get("ship_count_active",0) or 0):loc_bad.append(("active_vessel_registry",len(active_mobile),sf.get("ship_count_active")))
        if not loc_bad:ok("SHADOW_LOCATION_PARTITION")
        else:fail("SHADOW_LOCATION_PARTITION",json.dumps(loc_bad,ensure_ascii=False))
        base_ids=list(base_rec.get("vessels") or []) if isinstance(base_rec,dict) else []
        seen_loc=[]
        if len(base_ids)!=bships:seen_loc.append(("base_vessel_count",len(base_ids),bships))
        if len(base_ids)!=len(set(base_ids)):seen_loc.append(("base_vessel_duplicate",True))
        active_set=set(active_mobile)
        if set(base_ids)!=active_set and bships==int(sf.get("ship_count_active",0) or 0):seen_loc.append(("base_vessel_set",len(set(base_ids)),len(active_set)))
        home_id=loc.get("homeport")
        for vid in base_ids:
            rec=(vessels or {}).get(vid) if isinstance(vessels,dict) else None
            if not isinstance(rec,dict):seen_loc.append(("base_vessel_missing",vid));continue
            if rec.get("location_id")!=home_id:seen_loc.append(("vessel_location",vid,rec.get("location_id"),home_id))
        if not seen_loc:ok("SHADOW_VESSEL_LOCATION_CROSSPATH")
        else:fail("SHADOW_VESSEL_LOCATION_CROSSPATH",json.dumps(seen_loc[:20],ensure_ascii=False))
        deprecated=[k for k in ["recovery_bridges","current_reconstruction_v6672","recovery_stage_v6671","current_orders_83620811_1220","calder_income_ledger_v6827"] if k in (state.get("world_state_overrides") or {})]
        stale_refs=[]
        def _scan_stale(x,path="STATE"):
            if len(stale_refs)>=20:return
            if isinstance(x,dict):
                for k,v in x.items():
                    if re.fullmatch(r"current_checkpoint_v\d+",str(k)):stale_refs.append(path+"."+str(k))
                    _scan_stale(v,path+"."+str(k))
            elif isinstance(x,list):
                for i,v in enumerate(x):_scan_stale(v,f"{path}[{i}]")
            elif isinstance(x,str) and "STATE.world_state_overrides.current_checkpoint_v" in x:stale_refs.append(path+"=>"+x[:140])
        _scan_stale(state)
        enforce_current_only=False
        try:enforce_current_only=parse_version(str(state.get("save_version") or ('V99.99' if state.get('manifest_ref') else 'V0.0'))) >= (7,2)
        except Exception:enforce_current_only=False
        if not deprecated and not stale_refs:ok("STATE_CURRENT_ONLY_POLICY")
        elif enforce_current_only:fail("STATE_CURRENT_ONLY_POLICY",json.dumps({"deprecated_keys":deprecated,"stale_checkpoint_refs":stale_refs},ensure_ascii=False))
        else:ok("STATE_CURRENT_ONLY_POLICY_UPGRADE_PENDING")

    vc_zero=_versioned_current_zero_policy_report(state)
    if vc_zero.get('required'):
        if int(vc_zero.get('count',0) or 0)==0:ok('VERSIONED_CURRENT_ZERO_POLICY')
        else:fail('VERSIONED_CURRENT_ZERO_POLICY',json.dumps(vc_zero,ensure_ascii=False))
    else:
        ok('VERSIONED_CURRENT_ZERO_POLICY_UPGRADE_COMPAT')

    semantic_hygiene=_current_semantic_hygiene_report(state,tasks)
    if semantic_hygiene.get('required'):
        if int(semantic_hygiene.get('count',0) or 0)==0:ok('CURRENT_SEMANTIC_HYGIENE')
        else:fail('CURRENT_SEMANTIC_HYGIENE',json.dumps(semantic_hygiene,ensure_ascii=False))
    else:
        ok('CURRENT_SEMANTIC_HYGIENE_UPGRADE_COMPAT')

    v10surface=_v10_authority_surface_report(state,tasks)
    if (not v10surface.get("required")) or int(v10surface.get("count",0) or 0)==0:ok("V10_AUTHORITY_SURFACE_HYGIENE")
    else:fail("V10_AUTHORITY_SURFACE_HYGIENE",json.dumps(v10surface,ensure_ascii=False))

    if state.get("schema_version")=="V7.0":
        try:
            account=get_by_path(state,"world_state_overrides.multinational_industry_current");rb=[]
            if not isinstance(account,dict):rb.append(("account","not_object"))
            else:
                if account.get("schema")!="MULTINATIONAL_INDUSTRY_CURRENT_V2":rb.append(("schema",account.get("schema")))
                if not isinstance(account.get("asset_count"),int) or account.get("asset_count",0)<0:rb.append(("asset_count",account.get("asset_count")))
                for fld in ("daily_net_income_gold","daily_net_income_grey","last_settlement_gold","last_settlement_grey"):
                    val=account.get(fld)
                    if not isinstance(val,(int,float)) or isinstance(val,bool) or not math.isfinite(float(val)) or float(val)<0:rb.append((fld,val))
                if not isinstance(account.get("history_archive_ref"),str) or not account.get("history_archive_ref"):rb.append(("history_archive_ref",account.get("history_archive_ref")))
                if "composition" in account:rb.append(("composition","must_be_archived"))
            if not rb:ok("MULTINATIONAL_INDUSTRY_CURRENT_V2_INTEGRITY")
            else:fail("MULTINATIONAL_INDUSTRY_CURRENT_V2_INTEGRITY",json.dumps(rb[:12],ensure_ascii=False))
        except KeyError:
            warn("MULTINATIONAL_INDUSTRY_CURRENT_V2_INTEGRITY","current industry account absent")
        except Exception as exc:
            fail("MULTINATIONAL_INDUSTRY_CURRENT_V2_INTEGRITY",str(exc))

    calder_sched=_calder_legacy_schedule_hygiene_report(state)
    if (not calder_sched.get('required')) or int(calder_sched.get('count',0) or 0)==0:ok("CALDER_LEGACY_SCHEDULE_HYGIENE")
    else:fail("CALDER_LEGACY_SCHEDULE_HYGIENE",json.dumps(calder_sched,ensure_ascii=False))

    nonneg=[]
    for name,val in [("gold",funds.get("gold")),("grey",funds.get("grey")),("voyager_personnel",vf.get("current_personnel")),("jinchuan_personnel",jf.get("personnel_total")),("voyager_ships",vf.get("ship_count")),("jinchuan_ships",jf.get("ship_count"))]:
        if not isinstance(val,(int,float)) or isinstance(val,bool) or not math.isfinite(float(val)) or val<0:nonneg.append((name,val))
    if not nonneg:ok("NONNEGATIVE_CORE")
    else:fail("NONNEGATIVE_CORE",str(nonneg))
    _fin=_finance_integrity_report(state)
    if _fin.get('active') and _fin.get('status')=='PASS':ok('FIXED_POINT_FINANCE_INTEGRITY')
    elif _fin.get('active'):fail('FIXED_POINT_FINANCE_INTEGRITY',json.dumps(_fin,ensure_ascii=False))
    else:warn('FIXED_POINT_FINANCE_INTEGRITY','legacy finance runtime not activated')
    _dci=_domain_runtime_integrity_report(state)
    if _dci.get('active') and _dci.get('status')=='PASS':ok('DOMAIN_COMMAND_RUNTIME_INTEGRITY')
    elif _dci.get('active'):fail('DOMAIN_COMMAND_RUNTIME_INTEGRITY',json.dumps(_dci,ensure_ascii=False))
    else:warn('DOMAIN_COMMAND_RUNTIME_INTEGRITY','legacy domain command runtime not activated')
    if "RULE-SUPPLY-INVENTORY-01" in world_text:
        if "supplies" not in summary: ok("LEGACY_SUPPLY_DAYS_REMOVED")
        else: fail("LEGACY_SUPPLY_DAYS_REMOVED","STATE.summary.supplies must be removed under RULE-SUPPLY-INVENTORY-01")
        supply_inv=(state.get("inventories") or {}).get("supply_inventory")
        expected_supply={
            "food":"包",
            "water":"桶",
            "maintenance_parts":"箱",
            "compressed_air":"罐",
            "fuel":"罐",
            "medical_kits":"包",
        }
        supply_bad=[]
        if not isinstance(supply_inv,dict):
            supply_bad.append(("/inventories/supply_inventory","missing_or_not_object"))
        else:
            if supply_inv.get("rule_id")!="RULE-SUPPLY-INVENTORY-01": supply_bad.append(("/inventories/supply_inventory/rule_id",supply_inv.get("rule_id")))
            fleets=supply_inv.get("fleets")
            if not isinstance(fleets,dict):
                supply_bad.append(("/inventories/supply_inventory/fleets","missing_or_not_object"))
            else:
                if set(fleets)!={"voyager","jinchuan"}: supply_bad.append(("/inventories/supply_inventory/fleets/keys",sorted(fleets)))
                for fleet_name in ("voyager","jinchuan"):
                    goods=fleets.get(fleet_name)
                    if not isinstance(goods,dict):
                        supply_bad.append((f"/inventories/supply_inventory/fleets/{fleet_name}","missing_or_not_object"));continue
                    if set(goods)!=set(expected_supply): supply_bad.append((f"/inventories/supply_inventory/fleets/{fleet_name}/keys",sorted(goods)))
                    for key,unit in expected_supply.items():
                        rec=goods.get(key)
                        if not isinstance(rec,dict):
                            supply_bad.append((f"/inventories/supply_inventory/fleets/{fleet_name}/{key}","missing_or_not_object"));continue
                        val=rec.get("value")
                        if not isinstance(val,int) or isinstance(val,bool) or val<0: supply_bad.append((f"/inventories/supply_inventory/fleets/{fleet_name}/{key}/value",val))
                        if rec.get("unit")!=unit: supply_bad.append((f"/inventories/supply_inventory/fleets/{fleet_name}/{key}/unit",rec.get("unit")))
        if not supply_bad: ok("SUPPLY_INVENTORY_SCHEMA")
        else: fail("SUPPLY_INVENTORY_SCHEMA",json.dumps(supply_bad[:30],ensure_ascii=False))
    vd=state.get("voyage_day")
    if isinstance(vd,int) and not isinstance(vd,bool) and vd>=0:ok("VOYAGE_DAY_TYPE")
    else:fail("VOYAGE_DAY_TYPE",repr(vd))
    invneg=[(p,v) for p,v in _walk_numbers(state.get("inventories",{}),"/inventories") if (not math.isfinite(v)) or v<0]
    if not invneg:ok("NONNEGATIVE_INVENTORY")
    else:fail("NONNEGATIVE_INVENTORY",str(invneg[:20]))

    active=tasks.get("active_tasks",[]);queued=tasks.get("queued_tasks",[]);ids=[t.get("task_id") for t in active+queued]
    if all(ids) and len(ids)==len(set(ids)):ok("TASK_ID_UNIQUE")
    else:fail("TASK_ID_UNIQUE","missing/duplicate task_id")

    task_object_meta=tasks.get("task_object_schema")
    task_revision=(task_object_meta or {}).get("revision") if isinstance(task_object_meta,dict) else None
    structured_revisions={"TASK_OBJECT_V2","TASK_OBJECT_V3",TASK_OBJECT_SCHEMA}
    task_object_structured=task_revision in structured_revisions
    task_object_v4=task_revision==TASK_OBJECT_SCHEMA
    task_schema_errors=[]
    if task_object_meta is not None:
        if not isinstance(task_object_meta,dict):
            task_schema_errors.append("task_object_schema must be an object when present")
        elif task_revision not in structured_revisions:
            task_schema_errors.append(f"unsupported task object schema revision: {task_revision!r}")
        else:
            expected_task_meta={"lifecycle_field":"status","phase_field":"phase","task_specific_container":"task_data"}
            for mk,mv in expected_task_meta.items():
                if task_object_meta.get(mk)!=mv:task_schema_errors.append(f"task_object_schema.{mk} must be {mv!r}")
            if task_object_v4 and task_object_meta.get("view_rule_schema")!=DERIVED_VIEW_RULE_SCHEMA:
                task_schema_errors.append(f"task_object_schema.view_rule_schema must be {DERIVED_VIEW_RULE_SCHEMA!r}")
    if not task_schema_errors:ok("TASK_OBJECT_SCHEMA")
    else:fail("TASK_OBJECT_SCHEMA","; ".join(task_schema_errors))

    legacy_ar={"task_id","type","priority","title","status","owner_ids","location_ids","current_status","resource_locks","retrieval_route","next_trigger","report_policy","decision_gate"}
    v4_ar={"task_id","type","priority","title","status","owner_ids","location_ids","resource_locks","retrieval_route","report_policy","decision_gate","phase","task_data","view_rule"}
    legacy_qr={"task_id","type","priority","title","status","owner_ids","location_ids","known_value","activation_condition","retrieval_route"}
    v4_qr={"task_id","type","priority","title","status","owner_ids","location_ids","retrieval_route","phase","task_data","view_rule"}
    ar=v4_ar if task_object_v4 else legacy_ar; qr=v4_qr if task_object_v4 else legacy_qr
    if task_object_structured and not task_object_v4:
        ar=ar|{"phase","task_data"}; qr=qr|{"phase","task_data"}
    miss=[]
    for t in active:
        x=sorted(ar-set(t));
        if x:miss.append((t.get("task_id"),x))
    for t in queued:
        x=sorted(qr-set(t));
        if x:miss.append((t.get("task_id"),x))
    if not miss:ok("TASK_REQUIRED_FIELDS")
    else:fail("TASK_REQUIRED_FIELDS",str(miss[:20]))
    type_bad=[]
    for t in active+queued:
        tid=t.get("task_id")
        for fld in ["task_id","type","priority","title","status"]:
            if not isinstance(t.get(fld),str) or not t.get(fld).strip(): type_bad.append((tid,fld,type(t.get(fld)).__name__))
        if task_object_structured:
            if not isinstance(t.get("phase"),str) or not t.get("phase").strip():type_bad.append((tid,"phase","expected non-empty str"))
            if not isinstance(t.get("task_data"),dict):type_bad.append((tid,"task_data","expected dict"))
        if task_object_v4:
            vr=t.get("view_rule")
            if not isinstance(vr,dict) or vr.get("schema")!=DERIVED_VIEW_RULE_SCHEMA:type_bad.append((tid,"view_rule",DERIVED_VIEW_RULE_SCHEMA))
            else:
                ss=vr.get("status_sources",[])
                if not isinstance(ss,list) or not all(isinstance(x,str) and x for x in ss):type_bad.append((tid,"view_rule.status_sources","expected list[str]"))
            if "current_status" in t or "next_trigger" in t:type_bad.append((tid,"legacy_view_mirror","TASK_OBJECT_V4 forbids current_status/next_trigger"))
        for fld in ["owner_ids","location_ids"]:
            if not isinstance(t.get(fld),list) or not all(isinstance(x,str) and x for x in t.get(fld,[])): type_bad.append((tid,fld,"expected list[str]"))
        rr=t.get("retrieval_route")
        if not isinstance(rr,dict): type_bad.append((tid,"retrieval_route","expected dict"))
        else:
            for fld in ["state_paths","world_rules","history_tags"]:
                if fld in rr and (not isinstance(rr.get(fld),list) or not all(isinstance(x,str) for x in rr.get(fld,[]))): type_bad.append((tid,f"retrieval_route.{fld}","expected list[str]"))
        if t in active and not isinstance(t.get("resource_locks"),list): type_bad.append((tid,"resource_locks","expected list"))
    if not type_bad:ok("TASK_FIELD_TYPES")
    else:fail("TASK_FIELD_TYPES",str(type_bad[:30]))
    bad=[]
    for t in active:
        st=str(t.get("status","")).lower()
        if task_object_structured:
            if st!="active":bad.append((t.get("task_id"),t.get("status")))
        elif st in {"completed","complete","closed","cancelled","canceled","queued"}:bad.append((t.get("task_id"),t.get("status")))
    for t in queued:
        if str(t.get("status","")).lower()!="queued":bad.append((t.get("task_id"),t.get("status")))
    if not bad:ok("TASK_LIFECYCLE")
    else:fail("TASK_LIFECYCLE",str(bad))

    runtime_rules=load_runtime_rules(base)
    runtime_errors=[];expected_ranks={"routine":0,"notable":1,"important":2,"critical":3}
    try:
        _cat=read_json(base/"catalog.json")["static_catalog"];_sv=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')));_cat_required=_sv>=(12,32)
        if _cat:
            _counts=_cat.get('model_counts') or {};_combat=_cat.get('combat') or {}
            if _cat.get('schema')!=STATIC_CATALOG_SCHEMA or not isinstance(_combat,dict) or not isinstance(_counts,dict):raise EngineError('catalog structure invalid')
            ok('WORLD_STATIC_CATALOG_INTEGRITY')
        elif _cat_required:fail('WORLD_STATIC_CATALOG_INTEGRITY','V12.32+ requires distinct static catalog block')
        else:ok('WORLD_STATIC_CATALOG_LEGACY_COMPAT')
    except Exception as _ce:
        fail('WORLD_STATIC_CATALOG_INTEGRITY',str(_ce))
    if "RULE-LONG-HORIZON-RISK-01" in world_text and not runtime_rules:runtime_errors.append("WORLD runtime rules block missing")
    if runtime_rules:
        sevmap=runtime_rules.get("event_severity")
        if not isinstance(sevmap,dict) or set(sevmap)!=set(expected_ranks):runtime_errors.append("WORLD event_severity map invalid")
        else:
            for sk,sr in sevmap.items():
                if not isinstance(sr,dict) or sr.get("rank")!=expected_ranks[sk] or not isinstance(sr.get("event_mode_interrupt"),bool) or not isinstance(sr.get("hard_endpoint_interrupt"),bool):runtime_errors.append(f"WORLD event_severity {sk} invalid")
        profiles=runtime_rules.get("hazard_profiles")
        if not isinstance(profiles,dict):runtime_errors.append("WORLD hazard_profiles invalid")
        else:
            for pid,pr in profiles.items():
                if not isinstance(pr,dict):runtime_errors.append(f"WORLD hazard profile {pid} invalid");continue
                if pr.get("severity","notable") not in expected_ranks:runtime_errors.append(f"WORLD hazard profile {pid} severity invalid")
                cd=pr.get("cooldown_days",0)
                if not isinstance(cd,(int,float)) or isinstance(cd,bool) or not math.isfinite(float(cd)) or cd<0:runtime_errors.append(f"WORLD hazard profile {pid} cooldown invalid")
                rate=pr.get("annual_rate");rr=pr.get("annual_rate_range");prob=pr.get("annual_probability_per_entity");count=pr.get("entity_count",1)
                rate_modes=sum([rate is not None,rr is not None,prob is not None])
                if rate_modes!=1:runtime_errors.append(f"WORLD hazard profile {pid} requires exactly one rate model")
                if rate is not None and (not isinstance(rate,(int,float)) or isinstance(rate,bool) or not math.isfinite(float(rate)) or float(rate)<0):runtime_errors.append(f"WORLD hazard profile {pid} annual_rate invalid")
                if rr is not None:
                    if not isinstance(rr,list) or len(rr)!=2 or any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(float(x)) or float(x)<0 for x in rr):runtime_errors.append(f"WORLD hazard profile {pid} annual_rate_range invalid")
                if prob is not None:
                    if not isinstance(prob,(int,float)) or isinstance(prob,bool) or not math.isfinite(float(prob)) or not 0<=float(prob)<1:runtime_errors.append(f"WORLD hazard profile {pid} annual_probability_per_entity invalid")
                    if not isinstance(count,(int,float)) or isinstance(count,bool) or not math.isfinite(float(count)) or float(count)<0:runtime_errors.append(f"WORLD hazard profile {pid} entity_count invalid")
        rf=runtime_rules.get("random_event_framework")
        if rf is not None:
            if not isinstance(rf,dict):runtime_errors.append("WORLD random_event_framework invalid")
            else:
                activated=rf.get("activated_at")
                if activated is not None and parse_iso(activated) is None:runtime_errors.append("WORLD random_event_framework activated_at invalid")
                if rf.get("no_retroactive_rolls") not in {None,True}:runtime_errors.append("WORLD random_event_framework no_retroactive_rolls must be true")
                operational=rf.get("operational_hazard_families")
                if operational is not None:
                    if not isinstance(operational,list) or any(not isinstance(x,str) or not x.strip() for x in operational) or len(set(operational))!=len(operational):runtime_errors.append("WORLD operational_hazard_families invalid")
                    elif isinstance(profiles,dict):
                        missing=[x for x in operational if x not in profiles]
                        if missing:runtime_errors.append(f"WORLD operational_hazard_families profile missing: {missing}")
                disabled=rf.get("disabled_random_families")
                if disabled is not None:
                    if not isinstance(disabled,list) or any(not isinstance(x,str) or not x.strip() for x in disabled) or len(set(disabled))!=len(disabled):runtime_errors.append("WORLD disabled_random_families invalid")
                    elif isinstance(operational,list):
                        overlap=sorted(set(disabled)&set(operational))
                        if overlap:runtime_errors.append(f"WORLD disabled_random_families overlaps operational_hazard_families: {overlap}")
                contact=rf.get("contact_sensor_initiative")
                if contact is not None:
                    if not isinstance(contact,dict):runtime_errors.append("WORLD contact_sensor_initiative config invalid")
                    else:
                        for key in ("pirate_civilian_regular_mercenary_player_first_unaware_probability","regular_military_research_low_emission_player_first_unaware_probability","external_top_stealth_recon_player_first_unaware_probability"):
                            val=contact.get(key)
                            if not isinstance(val,(int,float)) or isinstance(val,bool) or not math.isfinite(float(val)) or not 0<=float(val)<=1:runtime_errors.append(f"WORLD contact_sensor_initiative {key} invalid")
                        if contact.get("requires_player_sensor_operational") not in {None,True}:runtime_errors.append("WORLD contact_sensor_initiative requires_player_sensor_operational must be true")
                        if contact.get("identity_requires_available_signature_or_intelligence") not in {None,True}:runtime_errors.append("WORLD contact_sensor_initiative identity_requires_available_signature_or_intelligence must be true")
                scfg=rf.get("secondhand_hidden_issue")
                if scfg is not None:
                    if not isinstance(scfg,dict):runtime_errors.append("WORLD secondhand_hidden_issue config invalid")
                    else:
                        prob=scfg.get("probability");cap=scfg.get("hard_probability_cap_exclusive")
                        if not isinstance(prob,(int,float)) or isinstance(prob,bool) or not math.isfinite(float(prob)) or float(prob)<0:runtime_errors.append("WORLD secondhand_hidden_issue probability invalid")
                        if not isinstance(cap,(int,float)) or isinstance(cap,bool) or not math.isfinite(float(cap)) or not 0<float(cap)<1:runtime_errors.append("WORLD secondhand_hidden_issue hard cap invalid")
                        if isinstance(prob,(int,float)) and not isinstance(prob,bool) and isinstance(cap,(int,float)) and not isinstance(cap,bool) and math.isfinite(float(prob)) and math.isfinite(float(cap)) and float(prob)>=float(cap):runtime_errors.append("WORLD secondhand_hidden_issue probability must be below hard cap")
                        if scfg.get("random_key") not in {None,"immutable_transaction_id"}:runtime_errors.append("WORLD secondhand_hidden_issue random_key must be immutable_transaction_id")
                        if scfg.get("one_check_per_transaction") not in {None,True}:runtime_errors.append("WORLD secondhand_hidden_issue one_check_per_transaction must be true")
    combat_cfg=runtime_rules.get("combat_evaluation") if isinstance(runtime_rules,dict) else None
    # Backward-compatible read: pre-v2.2.7 snapshots may not yet expose machine-readable combat parameters.
    # Once the block exists, validate it strictly; combatcalc itself refuses to run without it.
    if combat_cfg is not None:
        runtime_errors.extend(_validate_combat_runtime_config(combat_cfg))
    er=state.get("engine_runtime")
    if er is not None:
        if not isinstance(er,dict) or er.get("schema")!=RUNTIME_SCHEMA:runtime_errors.append("STATE.engine_runtime schema invalid")
        else:
            if not isinstance(er.get("seed_anchor"),str) or not er.get("seed_anchor"):runtime_errors.append("STATE.engine_runtime.seed_anchor missing")
            gate_errors=_validate_secondhand_gate_ledger(state,runtime_rules) if isinstance(runtime_rules,dict) else []
            runtime_errors.extend(f"secondhand hidden issue gate {x}" for x in gate_errors)
            state_time=parse_iso(state.get("game_time"));runtime_time=parse_iso(er.get("last_evaluated_game_time"));init_time=parse_iso(er.get("initialized_at_game_time"))
            if state_time is None or runtime_time!=state_time:runtime_errors.append("STATE.engine_runtime.last_evaluated_game_time must equal STATE.game_time")
            if init_time is None or (state_time and init_time>state_time):runtime_errors.append("STATE.engine_runtime.initialized_at_game_time invalid")
            lh=er.get("long_horizon") or {};clocks=lh.get("hazard_clocks") if isinstance(lh,dict) else None
            if not isinstance(clocks,dict):runtime_errors.append("STATE.engine_runtime.long_horizon.hazard_clocks must be object")
            else:
                profiles=runtime_rules.get("hazard_profiles",{}) if isinstance(runtime_rules,dict) else {}
                profile_clock_map={}
                for cid,c in clocks.items():
                    if not isinstance(c,dict):runtime_errors.append(f"hazard clock {cid} invalid");continue
                    profile_id=c.get("profile_id")
                    if profile_id not in profiles:runtime_errors.append(f"hazard clock {cid} profile missing: {profile_id}")
                    elif profile_id in profile_clock_map:runtime_errors.append(f"hazard profile {profile_id} mapped by duplicate clocks: {profile_clock_map[profile_id]}, {cid}")
                    else:profile_clock_map[profile_id]=cid
                    if not isinstance(c.get("cycle"),int) or isinstance(c.get("cycle"),bool) or c.get("cycle",0)<0:runtime_errors.append(f"hazard clock {cid} cycle invalid")
                    ch=c.get("cumulative_hazard");num=c.get("cumulative_hazard_numerator")
                    if not isinstance(ch,(int,float)) or isinstance(ch,bool) or not math.isfinite(float(ch)) or ch<0:runtime_errors.append(f"hazard clock {cid} exposure invalid")
                    if not isinstance(num,int) or isinstance(num,bool) or num<0:runtime_errors.append(f"hazard clock {cid} numerator invalid")
                    elif isinstance(ch,(int,float)) and math.isfinite(float(ch)) and round(float(ch),12)!=round(_exposure_float(num),12):runtime_errors.append(f"hazard clock {cid} exposure/numerator mismatch")
                    rm=c.get("risk_multiplier",1.0)
                    if not isinstance(rm,(int,float)) or isinstance(rm,bool) or not math.isfinite(float(rm)) or rm<0:runtime_errors.append(f"hazard clock {cid} risk_multiplier invalid")
                    ce=parse_iso(c.get("last_evaluated"))
                    if ce is None:runtime_errors.append(f"hazard clock {cid} last_evaluated invalid")
                    elif state_time and ce!=state_time and not _risk_clock_gap_valid(state,cid,c):runtime_errors.append(f"hazard clock {cid} uncovered interval before STATE.game_time")
                    if c.get("cooldown_until") is not None:
                        cooldown_at=parse_iso(c.get("cooldown_until"))
                        if cooldown_at is None:runtime_errors.append(f"hazard clock {cid} cooldown_until invalid")
                        elif state_time and cooldown_at<=state_time:runtime_errors.append(f"hazard clock {cid} cooldown_until stale/past; canonical state requires null")
                if isinstance(profiles,dict):
                    missing_profile_clocks=sorted(set(profiles)-set(profile_clock_map))
                    if missing_profile_clocks:runtime_errors.append(f"hazard profiles missing persistent clocks: {missing_profile_clocks}")
            latent=lh.get("latent_processes") if isinstance(lh,dict) else None
            if not isinstance(latent,list):runtime_errors.append("STATE.engine_runtime.long_horizon.latent_processes must be list")
            else:
                seen_proc=set()
                for proc in latent:
                    if not isinstance(proc,dict):runtime_errors.append("latent_process entry invalid");continue
                    pid=proc.get("process_id")
                    if not isinstance(pid,str) or not pid.strip() or pid in seen_proc:runtime_errors.append(f"latent_process process_id invalid/duplicate: {pid}")
                    else:seen_proc.add(pid)
                    if not isinstance(proc.get("family"),str) or not proc.get("family","").strip():runtime_errors.append(f"latent_process {pid} family missing")
                    status=str(proc.get("status","active")).lower()
                    if status not in {"active","latent","monitoring","paused","resolved","closed"}:runtime_errors.append(f"latent_process {pid} status invalid")
                    if proc.get("severity","notable") not in expected_ranks:runtime_errors.append(f"latent_process {pid} severity invalid")
                    started=parse_iso(proc.get("started_at")) if proc.get("started_at") is not None else None
                    if proc.get("started_at") is not None and (started is None or (state_time and started>state_time)):runtime_errors.append(f"latent_process {pid} started_at invalid")
                    ne=parse_iso(proc.get("next_evaluation")) if proc.get("next_evaluation") is not None else None
                    if status in {"active","latent","monitoring"} and ne is None:runtime_errors.append(f"latent_process {pid} active process requires next_evaluation")
                    elif ne and state_time and ne<state_time:runtime_errors.append(f"latent_process {pid} next_evaluation before STATE.game_time")
            kl=er.get("knowledge_layer") or {}
            if not isinstance(kl,dict) or kl.get("schema") not in {None,"KNOWLEDGE_V1"} or not isinstance(kl.get("claims",[]),list) or not isinstance(kl.get("source_groups",{}),dict):runtime_errors.append("STATE.engine_runtime.knowledge_layer invalid")
            else:
                claim_ids=set();groups=kl.get("source_groups",{})
                for claim in kl.get("claims",[]):
                    if not isinstance(claim,dict):runtime_errors.append("knowledge claim invalid");continue
                    cid=claim.get("claim_id")
                    if not isinstance(cid,str) or not cid.strip() or cid in claim_ids:runtime_errors.append(f"knowledge claim_id invalid/duplicate: {cid}")
                    else:claim_ids.add(cid)
                    rel=claim.get("reliability")
                    if rel is not None and (not isinstance(rel,(int,float)) or isinstance(rel,bool) or not math.isfinite(float(rel)) or not 0<=float(rel)<=1):runtime_errors.append(f"knowledge claim {cid} reliability invalid")
                    obs=parse_iso(claim.get("observed_at")) if claim.get("observed_at") is not None else None;rec=parse_iso(claim.get("received_at")) if claim.get("received_at") is not None else None
                    if claim.get("observed_at") is not None and obs is None:runtime_errors.append(f"knowledge claim {cid} observed_at invalid")
                    if claim.get("received_at") is not None and rec is None:runtime_errors.append(f"knowledge claim {cid} received_at invalid")
                    if obs and rec and rec<obs:runtime_errors.append(f"knowledge claim {cid} received_at before observed_at")
                    gid=claim.get("independence_group") or claim.get("source_group_id")
                    if gid is not None and (not isinstance(gid,str) or gid not in groups):runtime_errors.append(f"knowledge claim {cid} source group missing: {gid}")
    if tasks.get("runtime_schema") is not None:
        trs=tasks.get("runtime_schema")
        if trs not in {"TASK_RUNTIME_V1","TASK_RUNTIME_V2","TASK_RUNTIME_V3"}:runtime_errors.append("TASKS.runtime_schema invalid")
        runtime_profiles=tasks.get("runtime_profiles") or {}
        if trs in {"TASK_RUNTIME_V2","TASK_RUNTIME_V3"}:
            required_profiles={"autonomous_standard","supervised_standard","queued_standard"}
            if not isinstance(runtime_profiles,dict) or not required_profiles.issubset(runtime_profiles):runtime_errors.append("TASKS.runtime_profiles missing standard profiles")
            else:
                for pn,pv in runtime_profiles.items():
                    if not isinstance(pv,dict):runtime_errors.append(f"runtime profile {pn} invalid");continue
                    for fld in ["execution_mode","minimum_interrupt_severity","hard_interrupt_severity","scheduled_event_severity"]:
                        if fld not in pv:runtime_errors.append(f"runtime profile {pn} missing {fld}")
        for t in active+queued:
            rp=t.get("runtime_policy");tid=t.get("task_id")
            if not isinstance(rp,dict):runtime_errors.append(f"{tid} runtime_policy missing");continue
            schema=rp.get("schema")
            if schema=="TASK_POLICY_V2":
                profile=rp.get("profile")
                if not isinstance(profile,str) or profile not in runtime_profiles:runtime_errors.append(f"{tid} runtime profile invalid: {profile}")
                eff=effective_runtime_policy(tasks,t);mon=rp.get("monitor")
                if not isinstance(mon,dict):runtime_errors.append(f"{tid} monitor missing")
                else:
                    mode=mon.get("mode")
                    if mode not in MONITOR_MODES:runtime_errors.append(f"{tid} monitor mode invalid")
                    if not isinstance(mon.get("requires_ai_review"),bool):runtime_errors.append(f"{tid} monitor requires_ai_review invalid")
                    if not isinstance(mon.get("review_on_time_advance"),bool):runtime_errors.append(f"{tid} monitor review_on_time_advance invalid")
                    resolver=str(mon.get("resolver") or "")
                    event_driven=mon.get("event_driven",False)
                    if "event_driven" in mon and not isinstance(event_driven,bool):runtime_errors.append(f"{tid} monitor event_driven invalid")
                    wc=mon.get("watch_condition")
                    if wc is not None:
                        if not isinstance(wc,dict) or wc.get("schema")!=WATCH_CONDITION_SCHEMA:runtime_errors.append(f"{tid} watch_condition schema invalid")
                        else:
                            src=wc.get("sources");op=str(wc.get("operator") or "fingerprint_changed");bd=str(wc.get("baseline_digest") or "")
                            if op!="fingerprint_changed":runtime_errors.append(f"{tid} watch_condition operator invalid: {op}")
                            if not isinstance(src,list) or not src or len(src)>16 or any(not isinstance(x,str) or not x.strip() for x in src):runtime_errors.append(f"{tid} watch_condition sources invalid")
                            if not re.fullmatch(r"[0-9a-f]{64}",bd):runtime_errors.append(f"{tid} watch_condition baseline_digest invalid")
                            if mon.get("requires_ai_review") is not True:runtime_errors.append(f"{tid} watch_condition requires_ai_review=true")
                            if mode not in {"on_advance","external_wait","continuous"}:runtime_errors.append(f"{tid} watch_condition mode invalid: {mode}")
                    if resolver and resolver not in DETERMINISTIC_RESOLVERS:runtime_errors.append(f"{tid} monitor resolver invalid: {resolver}")
                    if t in active and mode in {"scheduled","on_advance","external_wait","continuous"} and mon.get("requires_ai_review") is False and resolver not in DETERMINISTIC_RESOLVERS:
                        runtime_errors.append(f"{tid} automatic non-AI monitor requires a registered deterministic resolver")
                    if mode in {"continuous","external_wait"} and mon.get("requires_ai_review") is False and resolver=="passive_event_v1" and event_driven is not True:
                        runtime_errors.append(f"{tid} passive_event_v1 must be event_driven=true")
                    tclass=rp.get("task_class")
                    if tclass is not None and tclass not in {"job","schedule","watcher"}:runtime_errors.append(f"{tid} task_class invalid: {tclass}")
                    _progress_contract_enforced=_continuous_progress_contract_enabled(tasks)
                    for err in _continuous_progress_contract_errors(t,_progress_contract_enforced):runtime_errors.append(f"{tid} {err}")
                    if resolver=="settlement_rule_v1":
                        srule=rp.get("settlement_rule") or (t.get("task_data") or {}).get("settlement_rule")
                        if not isinstance(srule,dict) or srule.get("schema")!=SETTLEMENT_RULE_SCHEMA:runtime_errors.append(f"{tid} settlement_rule_v1 requires SETTLEMENT_RULE_V1")
                    elif resolver=="world_process_rule_v1":
                        wrule=rp.get("world_process_rule") or (t.get("task_data") or {}).get("world_process_rule")
                        for err in _validate_world_process_rule(wrule):runtime_errors.append(f"{tid} {err}")
                    elif resolver=="progress_rule_v1":
                        prule=rp.get("progress_rule") or (t.get("task_data") or {}).get("progress_rule")
                        for err in _validate_progress_rule(prule):runtime_errors.append(f"{tid} {err}")
                    elif resolver=="business_daily_settlement_v1":
                        try:_business_rule(t)
                        except Exception as ex:runtime_errors.append(f"{tid} {ex}")
                    elif resolver in DETERMINISTIC_RESOLVERS-{"passive_event_v1","jinchuan_daily_settlement_v1","research_sales_daily_v1","settlement_rule_v1","world_process_rule_v1","progress_rule_v1","business_daily_settlement_v1"}:
                        arule=rp.get("automation") or (t.get("task_data") or {}).get("automation")
                        if not isinstance(arule,dict) or arule.get("schema")!=AUTOMATION_RULE_SCHEMA:runtime_errors.append(f"{tid} automation resolver requires AUTOMATION_RULE_V1")
                    lr=parse_iso(mon.get("last_reviewed_at")) if mon.get("last_reviewed_at") is not None else None
                    if mon.get("last_reviewed_at") is not None and (lr is None or (parse_iso(tasks.get("game_time")) and lr>parse_iso(tasks.get("game_time")))):runtime_errors.append(f"{tid} monitor last_reviewed_at invalid")
                    nr=parse_iso(mon.get("next_review_at")) if mon.get("next_review_at") is not None else None
                    if mon.get("next_review_at") is not None and nr is None:runtime_errors.append(f"{tid} monitor next_review_at invalid")
                    hd=parse_iso(mon.get("hard_deadline")) if mon.get("hard_deadline") is not None else None
                    if mon.get("hard_deadline") is not None and hd is None:runtime_errors.append(f"{tid} monitor hard_deadline invalid")
            elif schema=="TASK_POLICY_V1":
                eff=rp
            else:
                runtime_errors.append(f"{tid} runtime_policy schema invalid");continue
            if not isinstance(eff.get("execution_mode"),str) or not eff.get("execution_mode","").strip():runtime_errors.append(f"{tid} execution_mode invalid")
            minsev=eff.get("minimum_interrupt_severity");hardsev=eff.get("hard_interrupt_severity");schedsev=eff.get("scheduled_event_severity")
            if minsev not in expected_ranks:runtime_errors.append(f"{tid} minimum_interrupt_severity invalid")
            if hardsev not in expected_ranks:runtime_errors.append(f"{tid} hard_interrupt_severity invalid")
            if schedsev not in expected_ranks:runtime_errors.append(f"{tid} scheduled_event_severity invalid")
            if minsev in expected_ranks and hardsev in expected_ranks and expected_ranks[hardsev]<expected_ranks[minsev]:runtime_errors.append(f"{tid} hard_interrupt_severity must be >= minimum_interrupt_severity")
            if schema=="TASK_POLICY_V2":
                profile=str(rp.get("profile") or "")
                if t in active and (profile=="queued_standard" or eff.get("execution_mode")=="queued_until_activation"):
                    runtime_errors.append(f"{tid} active task cannot use queued runtime profile")
                if t in queued and (profile!="queued_standard" or eff.get("execution_mode")!="queued_until_activation"):
                    runtime_errors.append(f"{tid} queued task must use queued_standard runtime profile")
            defer=eff.get("defer_severities")
            if not isinstance(defer,list) or len(defer)!=len(set(defer)) or any(x not in expected_ranks for x in defer):runtime_errors.append(f"{tid} defer_severities invalid")
            if not isinstance(eff.get("decision_conditions"),list):runtime_errors.append(f"{tid} decision_conditions invalid")
        # Time-advance precommit barrier: semantic monitor reviews cannot be skipped.
        if trs=="TASK_RUNTIME_V2" and parent_snapshot and isinstance(parent_snapshot,dict) and parent_snapshot.get("dir"):
            try:
                pt=read_json(Path(parent_snapshot["dir"])/"tasks.json");old_time=parse_iso(pt.get("game_time"));new_time=parse_iso(tasks.get("game_time"))
                if old_time and new_time and new_time>old_time:
                    for t in active:
                        rp=t.get("runtime_policy") or {};mon=rp.get("monitor") or {}
                        if rp.get("schema")!="TASK_POLICY_V2":continue
                        nr=parse_iso(mon.get("next_review_at")) if mon.get("next_review_at") else None;lr=parse_iso(mon.get("last_reviewed_at")) if mon.get("last_reviewed_at") else None
                        due=bool(mon.get("review_on_time_advance")) or bool(nr and nr<=new_time)
                        if due and lr!=new_time:runtime_errors.append(f"{t.get('task_id')} monitor review required at advanced game_time")
            except Exception as exc:runtime_errors.append(f"TASK_MONITOR_PARENT_CHECK_FAILED:{exc}")
    if not runtime_errors:ok("RUNTIME_ARCHITECTURE")
    else:fail("RUNTIME_ARCHITECTURE",str(runtime_errors[:60]))

    corpus=_reference_corpus(base,state);badrefs=[]
    entity_ids=set(re.findall(r"(?:PER|LOC)-[A-Z0-9]+(?:-[A-Z0-9]+)*", corpus))
    for t in active+queued:
        owners=t.get("owner_ids") or []; locations=t.get("location_ids") or []
        if not isinstance(owners,list) or not isinstance(locations,list):
            badrefs.append((t.get("task_id"),"owner_ids/location_ids must be lists")); continue
        for ident in owners+locations:
            if not isinstance(ident,str) or ident not in entity_ids:badrefs.append((t.get("task_id"),ident))
    if not badrefs:ok("TASK_ENTITY_REFS")
    else:fail("TASK_ENTITY_REFS",str(badrefs[:20]))
    badsp=[];badwr=[]
    for t in active+queued:
        rr=t.get("retrieval_route") or {}
        for p in rr.get("state_paths",[]) or []:
            try:get_state_path(state,p)
            except KeyError:badsp.append((t.get("task_id"),p))
        for rid in rr.get("world_rules",[]) or []:
            if extract_rule_section(world_text,rid) is None:badwr.append((t.get("task_id"),rid))
    if not badsp:ok("RETRIEVAL_STATE_PATHS")
    else:fail("RETRIEVAL_STATE_PATHS",str(badsp[:20]))
    if not badwr:ok("RETRIEVAL_WORLD_RULES")
    else:fail("RETRIEVAL_WORLD_RULES",str(badwr[:20]))
    route_gaps=[]
    for t in active:
        rr=t.get("retrieval_route") or {}
        if "state_requirement" not in rr:continue
        req=rr.get("state_requirement","required")
        if req not in {"required","optional","none"}:route_gaps.append((t.get("task_id"),"invalid_state_requirement"))
        elif req=="required" and not (rr.get("state_paths") or []):route_gaps.append((t.get("task_id"),"required_state_paths_empty"))
    if not route_gaps:ok("RETRIEVAL_ROUTE_COVERAGE")
    else:fail("RETRIEVAL_ROUTE_COVERAGE",str(route_gaps[:20]))

    runtime_path_bad=[]
    for t in active+queued:
        for field_path,state_path in _task_machine_state_paths(t):
            try:get_state_path(state,state_path)
            except KeyError:runtime_path_bad.append((t.get("task_id"),field_path,state_path))
    runtime_path_contract_active=((tasks.get("task_object_schema") or {}).get("revision")==TASK_OBJECT_SCHEMA) or parse_version(str(tasks.get("save_version") or ('V99.99' if tasks.get('manifest_ref') else 'V0.0')))>=(10,0)
    if not runtime_path_bad or not runtime_path_contract_active:ok("RUNTIME_STATE_PATHS")
    else:fail("RUNTIME_STATE_PATHS",str(runtime_path_bad[:30]))

    runtime_versioned=_active_runtime_versioned_state_path_report(tasks)
    if not runtime_versioned.get('required') or int(runtime_versioned.get('count',0) or 0)==0:ok("ACTIVE_RUNTIME_VERSIONED_STATE_PATHS")
    else:fail("ACTIVE_RUNTIME_VERSIONED_STATE_PATHS",json.dumps(runtime_versioned,ensure_ascii=False))

    badres=[]
    for t in active+queued:
        locks=t.get("resource_locks",[])
        if isinstance(locks,list):
            for ref in locks:
                if isinstance(ref,str) and ref.startswith(("STATE.","state:")):
                    try:get_by_path(state,ref)
                    except KeyError:badres.append((t.get("task_id"),ref))
    if not badres:ok("STATE_RESOURCE_REFS")
    else:fail("STATE_RESOURCE_REFS",str(badres[:20]))

    inv_errors=[];checked_inv=0
    def inv_walk(x,path=""):
        nonlocal checked_inv
        if isinstance(x,dict):
            if isinstance(x.get("available"),(int,float)) and (isinstance(x.get("total_owned"),(int,float)) or isinstance(x.get("original"),(int,float))):
                total=x.get("total_owned",x.get("original"));alloc=sum_numeric_values(x.get("allocated",{}));reserved=sum_numeric_values(x.get("reserved",0));checked_inv+=1
                if abs(float(total)-(float(x["available"])+alloc+reserved))>1e-9:inv_errors.append((path,total,alloc,reserved,x["available"]))
            for k,v in x.items():inv_walk(v,f"{path}/{k}")
        elif isinstance(x,list):
            for i,v in enumerate(x):inv_walk(v,f"{path}/{i}")
    inv_walk(state.get("inventories",{}),"/inventories")
    if not inv_errors:ok(f"INVENTORY_BALANCE[{checked_inv}]")
    else:fail("INVENTORY_BALANCE",str(inv_errors[:20]))

    expected_med,unresolved_names=_parse_world_medical_expected(world_text); med=(vf.get("medical_capacity") or {}).get("by_class",{})
    if not expected_med or unresolved_names:
        fail("MEDICAL_RULE_PARSE",f"expected={expected_med} unresolved={unresolved_names}")
    else:
        med_bad={k:{"actual":med.get(k),"expected":v} for k,v in expected_med.items() if med.get(k)!=v}; extra=sorted(set(med)-set(expected_med))
        if not med_bad and not extra:ok("MEDICAL_CAPACITY_VALUES")
        else:fail("MEDICAL_CAPACITY_VALUES",json.dumps({"mismatch":med_bad,"extra":extra},ensure_ascii=False))

    stale=[]
    def find_stale(x,path=""):
        if isinstance(x,dict):
            status=str(x.get("status","")).lower()
            if any(k in status for k in ["purchased","accepted_and_purchased","成交"]):
                for k in x:
                    if "auto_buy" in k.lower() and x.get(k) not in (None,False,0,"closed","inactive"):stale.append((path,k,x.get(k),x.get("status")))
            for k,v in x.items():find_stale(v,f"{path}/{k}")
        elif isinstance(x,list):
            for i,v in enumerate(x):find_stale(v,f"{path}/{i}")
    find_stale(tasks,"/TASKS");stale=[x for x in stale if "package_quotes" not in x[0]]
    if not stale:ok("NO_STALE_PURCHASE_AUTH")
    else:fail("NO_STALE_PURCHASE_AUTH",str(stale[:20]))

    if full and parent_snapshot is None:
        parent_snapshot=_infer_parent_for_check(base)
    if parent_snapshot is not None:
        try:
            pbase=parent_snapshot["dir"];pstate=read_json(pbase/"state.json")
            if history_pair is None:
                history_pair=_history_read_pair_incremental(pbase/"events.jsonl",base/"events.jsonl",validation_cache)
            pmeta,pevents,praw=history_pair["parent"];craw=event_raw
            migration_ok=_history_text_migration_allowed(pbase,base,praw,craw,events,len(pevents),world_text)
            epoch_ok=_history_epoch_compaction_allowed(pbase/"events.jsonl",base/"events.jsonl",praw,craw,events,len(pevents))
            pphys=history_pair.get("parent_physical") or _history_physical_event_lines(pbase/"events.jsonl"); cphys=history_pair.get("current_physical") or _history_physical_event_lines(base/"events.jsonl")
            physical_append_only=(len(cphys)>=len(pphys) and cphys[:len(pphys)]==pphys)
            if len(craw)<len(praw):
                fail("HISTORY_APPEND_ONLY","prior events removed")
            elif craw[:len(praw)]==praw:
                ok("HISTORY_APPEND_ONLY")
                if physical_append_only:
                    ok("HISTORY_PHYSICAL_APPEND_ONLY")
                elif epoch_ok:
                    ok("HISTORY_EPOCH_PHYSICAL_COMPACTION")
                else:
                    fail("HISTORY_PHYSICAL_APPEND_ONLY","physical prior records changed without verified HISTORY_EPOCH_V1 compaction proof")
            elif migration_ok:
                ok("HISTORY_CANONICAL_TEXT_MIGRATION")
            else:
                fail("HISTORY_APPEND_ONLY","prior event bytes changed outside approved canonical text migration")
            allowed={"save_version","next_seq","game_time_current","manifest_ref"}
            schema_upgrade=(pmeta.get("schema_version")=="V6.0" and meta.get("schema_version")=="V7.0")
            if schema_upgrade:allowed.add("schema_version")
            pc={k:v for k,v in pmeta.items() if k not in allowed};cc={k:v for k,v in meta.items() if k not in allowed}
            if pc==cc:
                ok("HISTORY_METADATA_STABLE" if not schema_upgrade else "HISTORY_METADATA_SCHEMA_UPGRADE")
            elif migration_ok and canonicalize_game_obj(pc)==cc:
                ok("HISTORY_METADATA_CANONICAL_TEXT_MIGRATION")
            else:
                fail("HISTORY_METADATA_STABLE","metadata changed outside save_version/next_seq/schema-upgrade or approved canonical text migration")
            pdt=parse_iso(pstate.get("game_time"));cdt=parse_iso(state.get("game_time"))
            if pdt and cdt and cdt>=pdt and tasks.get("game_time")==state.get("game_time"):ok("TIME_MONOTONIC")
            else:fail("TIME_MONOTONIC",f"parent={pstate.get('game_time')} current={state.get('game_time')}")
            pseed=str(((pstate.get("engine_runtime") or {}).get("seed_anchor") or "")); cseed=str(((state.get("engine_runtime") or {}).get("seed_anchor") or ""))
            if pseed and cseed==pseed:ok("ENGINE_SEED_ANCHOR_IMMUTABLE")
            else:fail("ENGINE_SEED_ANCHOR_IMMUTABLE",f"parent={pseed!r} current={cseed!r}")
            pled=_secondhand_gate_ledger(pstate);cled=_secondhand_gate_ledger(state);gate_mut=[]
            for tid,prec in pled.items():
                if tid not in cled:gate_mut.append(f"removed:{tid}")
                elif cled.get(tid)!=prec:gate_mut.append(f"changed:{tid}")
            if not gate_mut:ok("SECONDHAND_GATE_LEDGER_APPEND_ONLY")
            else:fail("SECONDHAND_GATE_LEDGER_APPEND_ONLY",str(gate_mut[:20]))
            newevents=events[len(pevents):];badnew=[];req={"seq","event_id","game_time","type","summary","changes","source"}
            for i,e in enumerate(newevents,start=len(pevents)+1):
                missing=sorted(req-set(e))
                if missing:badnew.append((i,"missing",missing));continue
                if not isinstance(e.get("seq"),int) or isinstance(e.get("seq"),bool) or e.get("seq")!=i:badnew.append((i,"seq",e.get("seq")))
                if not isinstance(e.get("event_id"),str) or not e.get("event_id").strip():badnew.append((i,"event_id",e.get("event_id")))
                edt=parse_iso(e.get("game_time"))
                if edt is None:badnew.append((i,"invalid_game_time",e.get("game_time")))
                if not isinstance(e.get("type"),str) or not e.get("type").strip():badnew.append((i,"type",e.get("type")))
                if not isinstance(e.get("summary"),str) or not e.get("summary").strip():badnew.append((i,"summary",e.get("summary")))
                if not isinstance(e.get("source"),str) or not e.get("source").strip():badnew.append((i,"source",e.get("source")))
                if not isinstance(e.get("changes"),(dict,list)):badnew.append((i,"changes_type",type(e.get("changes")).__name__))
                if "authority_files" in e:
                    af=e.get("authority_files"); allowed_af={"rules.json","catalog.json","state.json","tasks.json"}
                    if not isinstance(af,list) or not all(isinstance(x,str) and x in allowed_af for x in af) or len(af)!=len(set(af)):badnew.append((i,"authority_files",af))
                if edt and pdt and edt<pdt:badnew.append((i,"event_time_before_parent",e.get("game_time")))
                if edt and cdt and edt>cdt:badnew.append((i,"event_time_after_state",e.get("game_time")))
            if not badnew:ok("NEW_EVENT_SCHEMA_BOUNDS")
            else:fail("NEW_EVENT_SCHEMA_BOUNDS",str(badnew[:20]))
            hz_cov=_hazard_cycle_history_coverage_errors(pstate,state,newevents,world_text,runtime_rules)
            if not hz_cov:ok("HAZARD_CYCLE_HISTORY_COVERAGE")
            else:fail("HAZARD_CYCLE_HISTORY_COVERAGE",str(hz_cov[:40]))
            if state.get("schema_version")=="V7.0":
                pfun=(pstate.get("summary") or {}).get("funds") or {};cfun=(state.get("summary") or {}).get("funds") or {}
                pfr=_finance_runtime(pstate,create=False);cfr=_finance_runtime(state,create=False)
                if pfr is not None and cfr is not None:
                    actual_gold_units=int(cfr['funds_units']['gold'])-int(pfr['funds_units']['gold']);actual_grey_units=int(cfr['funds_units']['grey'])-int(pfr['funds_units']['grey'])
                else:
                    actual_gold_units=_money_units_currency(cfun.get("gold",0) or 0,'gold')-_money_units_currency(pfun.get("gold",0) or 0,'gold');actual_grey_units=_money_units_currency(cfun.get("grey",0) or 0,'grey')-_money_units_currency(pfun.get("grey",0) or 0,'grey')
                ledger_gold_units=0;ledger_grey_units=0;finance_bad=[]
                for e in newevents:
                    fin=e.get("finance")
                    if fin is None:continue
                    items=fin if isinstance(fin,list) else [fin]
                    if not all(isinstance(x,dict) for x in items):finance_bad.append((e.get("event_id"),"finance_type"));continue
                    for x in items:
                        try:ledger_gold_units+=_money_units_currency(x.get("gold",0) or 0,'gold');ledger_grey_units+=_money_units_currency(x.get("grey",0) or 0,'grey')
                        except Exception:finance_bad.append((e.get("event_id"),"finance_numeric"))
                        if not isinstance(x.get("account"),str) or not x.get("account"):finance_bad.append((e.get("event_id"),"finance_account"))
                if actual_gold_units!=ledger_gold_units or actual_grey_units!=ledger_grey_units:finance_bad.append(("delta_mismatch_units",actual_gold_units,ledger_gold_units,actual_grey_units,ledger_grey_units))
                if not finance_bad:ok("FINANCE_LEDGER_COVERAGE")
                else:fail("FINANCE_LEDGER_COVERAGE",json.dumps(finance_bad[:20],ensure_ascii=False))
            substantive=_substantive_parent_change(pbase,base)
            if any(substantive.values()):
                if not newevents:
                    fail("STATE_CHANGE_REQUIRES_HISTORY",str(substantive))
                elif not any(isinstance(e.get("changes"),(dict,list)) and len(e.get("changes"))>0 for e in newevents):
                    fail("STATE_CHANGE_REQUIRES_HISTORY","substantive state/task/world change requires at least one non-empty structured event.changes payload")
                else:
                    coverage_rule="RULE-HISTORY-AUTHORITY-COVERAGE-01"
                    try: parent_world=_authority_world_text(pbase)
                    except Exception: parent_world=""
                    coverage_active=(coverage_rule in world_text) or (coverage_rule in parent_world)
                    if coverage_active:
                        changed={fn for fn,yes in substantive.items() if yes}
                        af,badaf=_event_authority_files(newevents); target_prefixes=_event_change_target_prefixes(newevents); targets=_event_targets_by_domain(newevents)
                        prefix_map={"rules.json":"WORLD","catalog.json":"WORLD","state.json":"STATE","tasks.json":"TASKS"}
                        missing_targets=sorted(fn for fn in changed if prefix_map[fn] not in target_prefixes)
                        uncovered=[]; diff_truncated=[]
                        for fn,domain in (("state.json","STATE"),("tasks.json","TASKS")):
                            if fn not in changed: continue
                            paths,tr=_changed_structured_paths(pbase,base,fn)
                            if tr: diff_truncated.append(fn)
                            for cp in paths:
                                if not any(_target_covers_path(t,cp) for t in targets.get(domain,[])): uncovered.append((fn,cp))
                        schema_migration_event=any(isinstance(e,dict) and e.get("type")=="architecture_migration" and isinstance(e.get("migration_archive"),dict) for e in newevents)
                        if badaf or af!=changed or missing_targets or uncovered or (diff_truncated and not schema_migration_event):
                            fail("AUTHORITY_CHANGE_EVENT_COVERAGE",f"changed={sorted(changed)} authority_files={sorted(af)} missing_targets={missing_targets} uncovered={uncovered[:30]} diff_truncated={diff_truncated} schema_migration_event={schema_migration_event} bad={badaf}")
                        else:
                            ok("STATE_CHANGE_REQUIRES_HISTORY");ok("AUTHORITY_CHANGE_EVENT_COVERAGE")
                    else: ok("STATE_CHANGE_REQUIRES_HISTORY")
            else:ok("STATE_CHANGE_REQUIRES_HISTORY")
        except Exception as e:fail("PARENT_INVARIANTS",str(e))

    if require_manifest:
        a=validate_authority_set(base)
        if a:ok("MANIFEST")
        else:fail("MANIFEST","INDEX/source manifest mismatch")
        if full:
            if SNAP_RE.match(base.name):
                v=validate_game_snapshot(base,verify_parent=True,root=base.parent)
                if v:ok("COMMIT_OR_LEGACY_ENVELOPE")
                else:fail("COMMIT_OR_LEGACY_ENVELOPE","snapshot envelope/lineage invalid")
            elif base.resolve()==ROOT.resolve():
                try:
                    latest=latest_valid_snapshot(ROOT,verify_parent=True)
                    if files_match(ROOT,latest["dir"]):ok("ROOT_BOUND_TO_COMMIT")
                    else:fail("ROOT_BOUND_TO_COMMIT","root does not match latest committed snapshot")
                except Exception as e:
                    # A seven-file Project source is a valid cold-start root before
                    # SAVE_GUARD has imported it into a local committed SAVESET.
                    try:
                        ps=project_source_check(base,strict_fileset=True)
                        if ps.get("status")=="PASS":ok("ROOT_PROJECT_SOURCE_COLD")
                        else:fail("ROOT_BOUND_TO_COMMIT",f"{e}; project_source={ps.get('errors')}")
                    except Exception as pe:fail("ROOT_BOUND_TO_COMMIT",f"{e}; project_source_check={pe}")

    audits=state.get("audits",[])
    audit_registry_errors=_audit_registry_errors(audits)
    if audit_registry_errors:
        fail("AUDIT_REGISTRY_SCHEMA", "; ".join(audit_registry_errors))
    else:
        ok("AUDIT_REGISTRY_SCHEMA")
    audit_summary=_audit_summary(audits)
    if full and audit_summary.get("open_blocking",0):
        warn("AUDITS_OPEN",f"{audit_summary['open_blocking']} blocking audit item(s) remain: {audit_summary['open_reconcilable']} reconcilable, {audit_summary['open_blocking_other']} other; resolved/archived records are retained but not warnings")
    return _check_result(base,full,passed,errors,warnings,len(events),len(active),len(queued),audit_summary=audit_summary)

def _check_result(base:Path,full:bool,passed:List[str],errors:List[str],warnings:List[str],history_count:int,active_count:int,queued_count:int,audit_summary:Optional[dict]=None)->dict:
    return {
        "status":"FAIL" if errors else "PASS",
        "mode":"full" if full else "quick",
        "base":str(base),
        "passed_count":len(passed),"error_count":len(errors),"warning_count":len(warnings),
        "passed":passed,"errors":errors,"warnings":warnings,
        "history_last_seq":history_count if history_count else 0,
        "history_next_seq":history_count+1,
        "active_tasks":active_count,"queued_tasks":queued_count,
        "audit_summary": audit_summary or {"total_records":0,"open_blocking":0,"open_reconcilable":0,"open_blocking_other":0,"open_nonblocking":0,"archived_known_gap":0,"resolved":0,"ids":{}},
    }




PROTOCOL_SYMBOL_HYGIENE_MIN_VERSION=(10,2)

def _protocol_symbol_hygiene_report(state:dict,world_text:str,index_text:str)->dict:
    try:ver=parse_version(str(state.get("save_version") or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=PROTOCOL_SYMBOL_HYGIENE_MIN_VERSION;rows=[]
    stale=[
        ("WORLD.md","权威任务对象使用`TASK_OBJECT_V3`","TASK_OBJECT_V4"),
        ("WORLD.md","`COLD_START_PACKET_V2`、stable refs","COLD_START_PACKET_V5"),
    ]
    for fn,needle,expected in stale:
        text=world_text if fn=="WORLD.md" else index_text
        if needle in text:rows.append({"file":fn,"needle":needle,"expected":expected})
    # INDEX/save-version coherence is already enforced by VERSION+manifest gates.
    # Do not duplicate it here because engineupgrade staging intentionally syncs
    # the future INDEX title before atomic_save rewrites STATE/TASKS save_version.
    return {"required":required,"minimum_version":version_text(PROTOCOL_SYMBOL_HYGIENE_MIN_VERSION),"count":len(rows),"rows":rows}



STALE_CURRENT_SEMANTIC_MIN_VERSION=(10,280)

def _stale_current_semantic_report(state:dict,tasks:dict,index_text:str)->dict:
    """Detect legal-but-stale CURRENT mirrors that hashes/manifest cannot catch.

    This gate intentionally activates only for V10.280+ so the candidate engine can
    read the V10.279 parent during a controlled migration.  INDEX is a router/manifest,
    not a current-state snapshot; current gameplay facts must come from STATE/TASKS.
    """
    try:ver=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=STALE_CURRENT_SEMANTIC_MIN_VERSION;rows=[]
    wso=state.get('world_state_overrides') or {}
    if isinstance(wso,dict) and 'current_continuity_checkpoint' in wso:
        cp=wso.get('current_continuity_checkpoint') or {}
        rows.append({'kind':'state_current_checkpoint','path':'STATE.world_state_overrides.current_continuity_checkpoint','game_time':cp.get('game_time') if isinstance(cp,dict) else None,'save_version':cp.get('save_version') if isinstance(cp,dict) else None})
    # Runtime/recovery CURRENT mirrors are never authority in the post-V10.280 contract.
    for root_name,obj in (('STATE',state),('TASKS',tasks)):
        def walk(x,path):
            if isinstance(x,dict):
                for k,v in x.items():
                    p=f'{path}.{k}'
                    lk=str(k).lower()
                    if lk in {'current_checkpoint','continuation_checkpoint','current_bridge'} or lk.startswith('continuation_checkpoint_v') or lk.startswith('current_bridge_v'):
                        rows.append({'kind':'recovery_current_mirror','path':p})
                    walk(v,p)
            elif isinstance(x,list):
                for i,v in enumerate(x):walk(v,f'{path}[{i}]')
        walk(obj,root_name)
    banned_index_patterns=[
        (r'^- `active_pointer_format`：', 'runtime_ab_pointer'),
        (r'^- `active_slot`：', 'runtime_ab_slot'),
        (r'^> \*\*当前游戏时间\*\*：', 'derived_game_time'),
        (r'^## 2\. 当前冷启动关键路由', 'dynamic_cold_start_section'),
        (r'完整连续性检查点', 'continuity_checkpoint_text'),
        (r'^## 3\. 当前恢复与封存注意事项', 'dynamic_recovery_section'),
    ]
    for pat,kind in banned_index_patterns:
        if re.search(pat,index_text,re.M):rows.append({'kind':'index_dynamic_current','pattern':kind})
    return {'required':required,'minimum_version':version_text(STALE_CURRENT_SEMANTIC_MIN_VERSION),'count':len(rows),'rows':rows[:100]}

def _v130_layer_run_checks_01(base: Path, full: bool = False, expected_version: Optional[str] = None,
               require_manifest: bool = True, parent_snapshot: Optional[dict] = None, validation_cache: Optional[dict]=None) -> dict:
    """Never leak malformed-save exceptions to callers; malformed data becomes a deterministic FAIL."""
    try:
        result=_run_checks_impl(base, full=full, expected_version=expected_version, require_manifest=require_manifest, parent_snapshot=parent_snapshot, validation_cache=validation_cache)
        # In component-authority mode the externally authoritative root is the
        # eight-component source, not the legacy A/B runtime directory. After a
        # successful legacy transaction is synchronized back, a freshly
        # materialized compatibility view may no longer be byte-identical to
        # the old A/B root envelope (notably INDEX metadata). Treat the component
        # source itself as the binding proof, but only when both source and
        # materialized legacy authority validate to the same gameplay save-set.
        if COMPONENT_MODE and full and base.resolve()==ROOT.resolve() and result.get('status')=='FAIL':
            errs=list(result.get('errors') or [])
            root_bind=[e for e in errs if str(e).startswith('ROOT_BOUND_TO_COMMIT:')]
            if root_bind:
                try:
                    cs=component_source_check(COMPONENT_ROOT,strict_fileset=False)
                    la=validate_authority_set(ROOT)
                    cm=_component_manifest_read(COMPONENT_ROOT)
                    if cs.get('status')=='PASS' and la and la.get('save_set_id')==cm.get('save_set_id'):
                        errs=[e for e in errs if not str(e).startswith('ROOT_BOUND_TO_COMMIT:')]
                        result['errors']=errs
                        result['error_count']=len(errs)
                        result.setdefault('passed',[]).append('COMPONENT_ROOT_BOUND_TO_SOURCE')
                        result['passed_count']=len(result.get('passed') or [])
                        if not errs:result['status']='PASS'
                except Exception:
                    pass
        if result.get('status')=='PASS':
            bad=_mobile_contract_errors(base,read_json(base/'state.json'),read_json(base/'tasks.json'),parent_snapshot)
            if bad:result['status']='FAIL';result.setdefault('errors',[]).extend(bad);result['error_count']=len(result.get('errors') or [])
        return result
    except Exception as e:
        return _check_result(base, full, [], [f"CHECK_INTERNAL_EXCEPTION: {type(e).__name__}: {e}"], [], 0, 0, 0)


def _semantic_snapshot_check(snap: dict, root: Path) -> dict:
    parent=None
    if snap.get("parent_save_set_id") and not snap.get("recovery_anchor"):
        pp=snapshot_path_from_sid(root,snap["parent_save_set_id"])
        if pp is not None:
            parent=validate_game_snapshot(pp,verify_parent=True,root=root)
    return run_checks(snap["dir"],full=False,require_manifest=True,parent_snapshot=parent)




def parse_world_static_catalog(world_text:str)->dict:
    pat=re.compile(r"<!--\s*"+re.escape(STATIC_CATALOG_MARKER)+r"\s*(\{.*?\})\s*"+re.escape(STATIC_CATALOG_MARKER)+r"_END\s*-->",re.S)
    m=pat.search(world_text)
    if not m:return {}
    obj=strict_json_loads(m.group(1))
    if not isinstance(obj,dict) or obj.get('schema')!=STATIC_CATALOG_SCHEMA:raise EngineError('WORLD_STATIC_CATALOG_INVALID')
    return obj

def _merge_runtime_static_catalog(rules:dict,catalog:dict)->dict:
    if not catalog:return rules
    out=copy.deepcopy(rules);combat=(catalog.get('combat') or {}) if isinstance(catalog,dict) else {};ce=out.setdefault('combat_evaluation',{})
    for section in ('ship','ground','air_ground'):
        src=combat.get(section) or {}
        if not isinstance(src,dict):continue
        dst=ce.setdefault(section,{})
        for k,v in src.items():
            if k not in dst:dst[k]=copy.deepcopy(v)
            elif isinstance(dst.get(k),dict) and isinstance(v,dict):
                for kk,vv in v.items():dst[k].setdefault(kk,copy.deepcopy(vv))
    if 'reconnaissance_equipment' in catalog and 'reconnaissance_equipment' not in out:
        out['reconnaissance_equipment']=copy.deepcopy(catalog.get('reconnaissance_equipment'))
    return out

def parse_world_runtime_rules(world_text: str) -> dict:
    """Legacy WORLD migration reader only; current commands use load_runtime_rules.

    WORLD remains one authority file for the mobile seven-file protocol, but deterministic
    rules and stable model templates are stored in distinct machine blocks. The merge is a
    read-time compatibility view, not a second writable authority.
    """
    pat = re.compile(r"<!--\s*" + re.escape(RUNTIME_RULES_MARKER) + r"\s*(\{.*?\})\s*" + re.escape(RUNTIME_RULES_MARKER) + r"_END\s*-->", re.S)
    m = pat.search(world_text)
    if not m:return {}
    obj = strict_json_loads(m.group(1))
    if not isinstance(obj, dict):raise EngineError("WORLD_RUNTIME_RULES_NOT_OBJECT")
    return _merge_runtime_static_catalog(obj,parse_world_static_catalog(world_text))

def resolve_rule_registry(base:Path, rule_id:Optional[str]=None)->dict:
    """Resolve lifecycle and machine bindings from the one editable rule registry.

    The resolver never chooses between conflicting active rules by file order.
    """
    source=read_json(Path(base)/'rules.json');reg=source.get('rule_registry') or {}
    if reg.get('schema')!='RULE_REGISTRY_V4':raise EngineError('RULE_REGISTRY_SCHEMA_REQUIRED:V4')
    rows=reg.get('rules') or {};errors=[];resolved={};visiting=set()
    lifecycle={'draft','active','superseded','revoked'}
    implementations={'semantic_only','partially_executable','fully_executable'}
    def walk(rid):
        if rid in resolved:return resolved[rid]
        if rid in visiting:errors.append('RULE_SUPERSESSION_CYCLE:'+rid);return rid
        rec=rows.get(rid)
        if not isinstance(rec,dict):errors.append('RULE_REFERENCE_MISSING:'+rid);return rid
        visiting.add(rid)
        successors=rec.get('superseded_by') or []
        if len(successors)>1:errors.append('RULE_MULTIPLE_SUCCESSORS:'+rid)
        targets=[walk(str(nxt)) for nxt in successors]
        visiting.remove(rid)
        resolved[rid]=targets[0] if targets and str(successors[0]) in rows else rid
        return resolved[rid]
    for rid,rec in rows.items():
        if not isinstance(rec,dict):errors.append('RULE_RECORD_INVALID:'+rid);continue
        if rec.get('rule_id')!=rid:errors.append('RULE_ID_KEY_MISMATCH:'+rid)
        if rec.get('lifecycle_status') not in lifecycle:errors.append('RULE_LIFECYCLE_INVALID:'+rid)
        if rec.get('implementation_status') not in implementations:errors.append('RULE_IMPLEMENTATION_INVALID:'+rid)
        if not isinstance(rec.get('version'),int) or rec.get('version',0)<1:errors.append('RULE_VERSION_INVALID:'+rid)
        if not rec.get('scope') or not rec.get('source_ref'):errors.append('RULE_PROVENANCE_MISSING:'+rid)
        if rec.get('lifecycle_status')=='superseded' and not rec.get('superseded_by'):errors.append('RULE_SUCCESSOR_REQUIRED:'+rid)
        if rec.get('lifecycle_status')=='active' and rec.get('superseded_by'):errors.append('RULE_ACTIVE_HAS_SUCCESSOR:'+rid)
        for old in rec.get('supersedes') or []:
            if old not in rows:errors.append('RULE_SUPERSEDES_MISSING:'+rid+'->'+str(old))
            elif rid not in (rows[old].get('superseded_by') or []):errors.append('RULE_SUPERSESSION_ASYMMETRIC:'+rid+'->'+old)
        for name,spec in (rec.get('parameter_bindings') or {}).items():
            path=spec.get('path','')
            if not path.startswith('runtime_rules.'):errors.append('RULE_PARAMETER_PATH_INVALID:'+rid+':'+name);continue
            try:
                value=get_by_path(source,path)
            except (KeyError,TypeError):
                if spec.get('required'):errors.append('RULE_PARAMETER_MISSING:'+rid+':'+name)
                continue
            kind=spec.get('type')
            valid={'integer':isinstance(value,int) and not isinstance(value,bool),'number':isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(float(value)),'boolean':isinstance(value,bool),'list[string]':isinstance(value,list) and all(isinstance(x,str) for x in value),'object':isinstance(value,dict)}.get(kind,False)
            if not valid or not spec.get('unit'):errors.append('RULE_PARAMETER_TYPE_OR_UNIT:'+rid+':'+name)
            if kind in ('integer','number') and valid and value<spec.get('minimum',value):errors.append('RULE_PARAMETER_RANGE:'+rid+':'+name)
            if name=='money_decimal_places' and value!=MONEY_DECIMAL_PLACES:errors.append('RULE_FINANCE_PRECISION_BINDING:'+rid)
        if rec.get('implementation_status')=='fully_executable' and not rec.get('parameter_bindings') and not rec.get('effects'):errors.append('RULE_EXECUTION_UNBOUND:'+rid)
    for rid in rows:resolved[rid]=walk(rid)
    groups={}
    for rid,rec in rows.items():
        if rec.get('lifecycle_status')=='active' and rec.get('conflict_group'):
            key=(rec['conflict_group'],rec.get('scope'))
            groups.setdefault(key,[]).append(rid)
    for key,ids in groups.items():
        if len(ids)>1:errors.append('RULE_ACTIVE_CONFLICT:'+str(key)+':'+','.join(sorted(ids)))
    if errors:raise EngineError(';'.join(sorted(set(errors))))
    if rule_id is not None:
        if rule_id not in rows:raise EngineError('RULE_UNKNOWN:'+rule_id)
        target=resolved[rule_id];rec=copy.deepcopy(rows[target])
        if rec['lifecycle_status']!='active':raise EngineError('RULE_NOT_ACTIVE:'+rule_id+':'+rec['lifecycle_status'])
        rec['resolved_from']=rule_id;rec['effective_rule_id']=target
        rec['resolved_parameters']={name:copy.deepcopy(get_by_path(source,spec['path'])) for name,spec in (rec.get('parameter_bindings') or {}).items() if spec.get('path','').startswith('runtime_rules.')}
        return rec
    return {'rules':rows,'resolved_ids':resolved,'count':len(rows),'lifecycle_counts':dict(collections.Counter(r['lifecycle_status'] for r in rows.values())),'implementation_counts':dict(collections.Counter(r['implementation_status'] for r in rows.values()))}

def load_runtime_rules(base:Path)->dict:
    resolve_rule_registry(base)
    rules=read_json(Path(base)/'rules.json')['runtime_rules']
    catalog=read_json(Path(base)/'catalog.json')['static_catalog']
    return _merge_runtime_static_catalog(copy.deepcopy(rules),catalog)


def _compact_value(v: Any, max_chars: int = 1800) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        if isinstance(v, str) and len(v) > max_chars:
            return v[:max_chars] + "...[truncated]"
        return v
    raw = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    if len(raw) <= max_chars:
        return v
    if isinstance(v, dict):
        if v.get("format")==ROW_REGISTRY_FORMAT and isinstance(v.get("rows"),list):
            return {"format":ROW_REGISTRY_FORMAT,"row_count":len(v.get("rows") or []),"columns":v.get("columns"),"defaults":v.get("defaults"),"note":"row data omitted in compact mode; query asset id/name or use --detail full"}
        out = {}
        for k, x in v.items():
            if len(json.dumps(out, ensure_ascii=False)) > max_chars:
                break
            out[k] = _compact_value(x, max(240, max_chars // 3))
        out["_truncated"] = True
        return out
    if isinstance(v, list):
        out = [_compact_value(x, max(180, max_chars // 4)) for x in v[:8]]
        if len(v) > len(out): out.append({"_truncated_items": len(v)-len(out)})
        return out
    return str(v)[:max_chars]



def _task_uses_derived_view(task: dict) -> bool:
    rule=task.get("view_rule") if isinstance(task,dict) else None
    return isinstance(rule,dict) and rule.get("schema")==DERIVED_VIEW_RULE_SCHEMA


def _task_derived_view(task: dict, state: Optional[dict] = None, max_chars: int = 1800) -> dict:
    """Build the non-authoritative task presentation from canonical runtime/state.

    TASK_OBJECT_V4 deliberately stops persisting mutable ``current_status`` and
    ``next_trigger`` display mirrors.  This function is the single rendering path used
    by query/turn/cold-start surfaces.  Semantic context may remain in TASKS because it
    is not mechanically derivable; numeric/current facts come from referenced STATE.
    """
    if not isinstance(task,dict):return {}
    rule=task.get("view_rule") or {}
    mon=((task.get("runtime_policy") or {}).get("monitor") or {})
    out={
        "schema":DERIVED_VIEW_RULE_SCHEMA,
        "phase":task.get("phase"),
        "next_review_at":mon.get("next_review_at"),
        "resolver":mon.get("resolver"),
        "requires_ai_review":bool(mon.get("requires_ai_review",False)),
    }
    if task.get("semantic_context") not in (None,""):
        out["semantic_context"]=_compact_value(task.get("semantic_context"),max(320,max_chars//2))
    if task.get("trigger_condition") not in (None,""):
        out["trigger_condition"]=_compact_value(task.get("trigger_condition"),max(240,max_chars//3))
    sources=rule.get("status_sources")
    if not isinstance(sources,list):
        sources=list(((task.get("retrieval_route") or {}).get("state_paths") or []))[:2]
    resolved=[]
    if isinstance(state,dict):
        for src in sources[:4]:
            if not isinstance(src,str) or not src:continue
            try:
                rp=resolve_state_ref(state,src);val=get_by_path(state,rp)
                resolved.append({"source":src,"path":rp,"value":_compact_value(val,max(260,max_chars//max(1,min(4,len(sources)))) )})
            except Exception as exc:
                resolved.append({"source":src,"unresolved":type(exc).__name__})
    if resolved:out["status_sources"]=resolved
    return out


def _task_surface(task: dict, state: Optional[dict] = None, full: bool = False) -> dict:
    """Canonical query/report task surface with V2/V3 read compatibility."""
    if not isinstance(task,dict):return {}
    if full:
        out=copy.deepcopy(task)
        if _task_uses_derived_view(task):out["derived_view"]=_task_derived_view(task,state,4800)
        return out
    out={k:_compact_value(task.get(k),900) for k in ("task_id","type","priority","title","status","phase") if task.get(k) is not None}
    if task.get("decision_gate") not in (None,""):out["decision_gate"]=_compact_value(task.get("decision_gate"),520)
    if task.get("autonomy") not in (None,""):out["autonomy"]=_compact_value(task.get("autonomy"),520)
    if _task_uses_derived_view(task):
        out["derived_view"]=_task_derived_view(task,state,1800)
    else:
        if task.get("current_status") is not None:out["current_status"]=_compact_value(task.get("current_status"),700)
        if task.get("next_trigger") is not None:out["next_trigger"]=_compact_value(task.get("next_trigger"),320)
        if task.get("known_value") is not None:out["known_value"]=_compact_value(task.get("known_value"),700)
        if task.get("activation_condition") is not None:out["activation_condition"]=_compact_value(task.get("activation_condition"),320)
    return out


def _expand_row_registry_v2(reg: dict, row: list, row_index: Optional[int] = None) -> dict:
    """Expand a compact ROW_REGISTRY_V2 row without losing explicit-null vs absent fields.

    V7.1 registries may carry ``presence_masks``.  Each bit corresponds to a
    column and records whether that key existed in the pre-compaction object.
    This lets the compact representation reconstruct legacy row dictionaries
    exactly, including explicit ``null`` values.  Older V7.0 registries remain
    readable: without a mask we preserve the original V7.0 behavior.
    """
    cols=list(reg.get("columns") or []); defaults=dict(reg.get("defaults") or {})
    obj=dict(defaults)
    masks=reg.get("presence_masks")
    mask=None
    if isinstance(row_index,int) and isinstance(masks,list) and 0 <= row_index < len(masks):
        raw=masks[row_index]
        try:
            mask=int(raw,16) if isinstance(raw,str) else int(raw)
        except Exception:
            mask=None
    for i,k in enumerate(cols):
        if i >= len(row):
            continue
        if mask is not None:
            if mask & (1 << i):
                obj[k]=row[i]
        elif row[i] is not None:
            obj[k]=row[i]
    return obj

def _expanded_row_registry_v2_rows(reg: dict) -> List[dict]:
    rows=reg.get("rows") or []
    return [_expand_row_registry_v2(reg,row,i) for i,row in enumerate(rows) if isinstance(row,list)]

def _row_registry_expanded_sha256(reg: dict) -> str:
    payload=json.dumps(_expanded_row_registry_v2_rows(reg),ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
    return sha256_bytes(payload)

def _search_obj_hits(obj: Any, q: str, prefix: str = "", limit: int = 12, max_chars: int = 1400) -> List[dict]:
    hits: List[dict] = []
    nq = _normalize_search_text(q)
    def rec(x: Any, path: str, depth: int = 0):
        if len(hits) >= limit or depth > 9:
            return
        if isinstance(x, dict):
            if x.get("format")==ROW_REGISTRY_FORMAT and isinstance(x.get("rows"),list):
                for row_index,row in enumerate(x.get("rows") or []):
                    if len(hits)>=limit:break
                    if not isinstance(row,list):continue
                    robj=_expand_row_registry_v2(x,row,row_index)
                    blob=_normalize_search_text(" ".join(str(v) for v in robj.values() if v is not None))
                    if nq and nq in blob:
                        rid=robj.get("asset_id") or robj.get("id") or "?"
                        hits.append({"path":f"{path}.rows[{rid}]","value":_compact_value(robj,max_chars)})
                return
            for k, v in x.items():
                if len(hits) >= limit: break
                kp = f"{path}.{k}" if path else str(k)
                key_blob = _normalize_search_text(str(k))
                if nq and nq in key_blob:
                    hits.append({"path": kp, "value": _compact_value(v, max_chars)})
                    continue
                if isinstance(v, (str, int, float, bool)) or v is None:
                    if nq and nq in _normalize_search_text(str(v)):
                        hits.append({"path": kp, "value": _compact_value(v, max_chars)})
                else:
                    rec(v, kp, depth + 1)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                if len(hits) >= limit: break
                rec(v, f"{path}[{i}]", depth + 1)
    rec(obj, prefix)
    return hits


def _authority_fingerprint(base: Path) -> str:
    h = hashlib.sha256()
    for fn in AUTH_FILES:
        p = base / fn
        h.update(fn.encode("utf-8") + b"\0")
        h.update(bytes.fromhex(sha256_file(p)))
    return h.hexdigest()


# runtime-cache implementation is defined once in the v2.6 performance layer below.

def _ensure_source_ready_v251(base: Path, allow_cache: bool = True) -> dict:
    """Fast read barrier.

    Root reads first verify the INDEX manifest and current snapshot identity. If
    the authority fingerprint was already semantically checked by this engine,
    repeated query/turn calls skip redundant full semantic validation. Any byte
    change invalidates the cache automatically.
    """
    base = base.resolve()
    if base != ROOT.resolve():
        is_stage=base.name.startswith(".stage_") and (base/".PARENT.json").is_file()
        if not is_stage and validate_authority_set(base) is None:
            raise EngineError("SOURCE_CHECK_FAILED: AUTHORITY_MANIFEST_INVALID")
        qc = run_checks(base, full=False, require_manifest=False)
        if qc.get("status") != "PASS":
            raise EngineError("SOURCE_CHECK_FAILED: " + "; ".join(qc.get("errors", [])))
        return {"status":"PASS","cached":False,"mode":"staging_check" if is_stage else "nonroot_authority_check"}

    auth = validate_authority_set(ROOT)
    if auth is None:
        guard(ROOT, restore=True, restore_tool_files=False)
        auth = validate_authority_set(ROOT)
        if auth is None: raise EngineError("ROOT_AUTHORITY_INVALID_AFTER_GUARD")
    groups = snapshot_dirs_by_version(ROOT)
    need_guard = False
    if not groups:
        need_guard = True
    else:
        highest = max(groups)
        if highest != auth["version"]: need_guard = True
        same = groups.get(auth["version"], [])
        expected_name = f"{version_text(auth['version'])}_SAVESET_{auth['bundle'][:16]}"
        if same and not any(x.name == expected_name for x in same): need_guard = True
        if len(same) > 1: need_guard = True
    if need_guard:
        guard(ROOT, restore=True, restore_tool_files=False)
        auth = validate_authority_set(ROOT)
        if auth is None: raise EngineError("ROOT_AUTHORITY_INVALID_AFTER_RESTORE")

    running_binding=_running_engine_binding_status(ROOT)
    fp = _authority_fingerprint(ROOT)
    if allow_cache:
        cp = _runtime_cache_path(ROOT)
        try:
            c = strict_json_load(cp)
            if _runtime_session_cache_intact(c) and c.get("format") == RUNTIME_SCHEMA and c.get("engine_version") == ENGINE_VERSION and c.get("engine_sha256") == sha256_file(Path(__file__).resolve()) and c.get("authority_fingerprint") == fp and c.get("save_set_id") == auth.get("save_set_id"):
                return {"status":"PASS","cached":True,"mode":"fingerprint","save_set_id":auth.get("save_set_id"),"engine_binding":running_binding}
        except Exception:
            pass
    qc = run_checks(ROOT, full=False, require_manifest=True)
    if qc.get("status") != "PASS":
        raise EngineError("SOURCE_CHECK_FAILED: " + "; ".join(qc.get("errors", [])))
    _write_runtime_cache(ROOT, qc)
    return {"status":"PASS","cached":False,"mode":"semantic_check","save_set_id":auth.get("save_set_id"),"engine_binding":running_binding}


def _running_engine_binding_status(base: Path) -> dict:
    """Bind same-version engine bytes to INDEX while allowing explicit newer upgrades.

    Reusing an ENGINE_VERSION with different bytes is forbidden: it defeats Guard and
    session-cache trust. A strictly newer engine may read an older save during a
    controlled upgrade, but the next formal save must bind the new version/hash.
    """
    auth=validate_authority_set(base)
    if auth is None: raise EngineError("RUNNING_ENGINE_BINDING_AUTHORITY_INVALID")
    idx=auth.get("index") or {};expected_version=str(idx.get("engine_version") or "").strip();expected_hash=idx.get("engine_sha256")
    if not expected_version or not expected_hash:
        raise EngineError("RUNNING_ENGINE_BINDING_MISSING_IN_INDEX")
    actual_version=semver_tuple(ENGINE_VERSION);bound_version=semver_tuple(expected_version);actual_hash=sha256_file(Path(__file__).resolve())
    if actual_version < bound_version:
        raise EngineError(f"RUNNING_ENGINE_OLDER_THAN_SAVE: running={ENGINE_VERSION} bound={expected_version}")
    if actual_version == bound_version and actual_hash != expected_hash:
        raise EngineError(f"RUNNING_ENGINE_SAME_VERSION_HASH_MISMATCH: version={ENGINE_VERSION} expected={expected_hash} actual={actual_hash}")
    return {"status":"BOUND" if actual_version==bound_version else "NEWER_UPGRADE","running_version":ENGINE_VERSION,"running_sha256":actual_hash,"bound_version":expected_version,"bound_sha256":expected_hash}


# ---------------------------------------------------------------------------
# v2.6 performance layer: stat-fast validation, SQLite cache, compact authority
# serialization, cold boot packets and transactional turn sessions.
# ---------------------------------------------------------------------------

def _authority_json_bytes(obj: Any) -> bytes:
    return (json.dumps(obj,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8")

def _write_authority_json(path: Path, obj: Any) -> None:
    if path.name=='state.json' and isinstance(obj,dict) and _mobile_contract(obj):
        if _finance_runtime(obj,create=False) is not None:
            rep=_finance_integrity_report(obj)
            if rep.get('status')!='PASS':raise EngineError('FINANCE_COMPATIBILITY_VIEW_DIVERGED:'+json.dumps(rep,ensure_ascii=False))
        else:
            for k in ('gold','grey'):
                if k in (obj.get('summary') or {}).get('funds',{}):obj['summary']['funds'][k]=_money_currency(obj['summary']['funds'][k],k)
    _atomic_replace_bytes(path,_authority_json_bytes(obj))

def _stat_record(p: Path) -> dict:
    st=p.stat()
    return {"ino":int(getattr(st,"st_ino",0)),"size":int(st.st_size),"mtime_ns":int(st.st_mtime_ns),"ctime_ns":int(st.st_ctime_ns)}

def _authority_stat_signature(base: Path) -> dict:
    return {fn:_stat_record(base/fn) for fn in AUTH_FILES + ([AB_ACTIVE_FILE] if (base/AB_ACTIVE_FILE).exists() else [])}

def _runtime_session_integrity(obj: dict) -> str:
    """Self-check the non-authoritative source-ready session cache.

    Runtime caches are performance hints only. Corruption must never alter SAVESET
    identity or allow a false stat-fast result, so every trusted read verifies this
    digest before consuming cache metadata.
    """
    payload=copy.deepcopy(obj);payload.pop("integrity_sha256",None)
    return sha256_bytes(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8"))

def _runtime_session_cache_intact(obj: Any) -> bool:
    return isinstance(obj,dict) and isinstance(obj.get("integrity_sha256"),str) and obj.get("integrity_sha256")==_runtime_session_integrity(obj)

def _runtime_cache_path(root: Path = ROOT) -> Path:
    """Engine-specific disposable cache name; authentication is in cache validation.

    Naming never rehashes all authority files. Exact candidate bytes have a distinct
    slot, including candidates with the same advertised semantic version.
    """
    digest=sha256_file(Path(__file__).resolve())[:16]
    return root.resolve()/'.runtime'/f'engine_session_{ENGINE_VERSION}_{digest}.json'

def _latest_pointer_path(root: Path=ROOT)->Path:
    return root/".runtime"/"LATEST.json"

def _write_latest_pointer(snapshot: dict, root: Path=ROOT) -> None:
    try:
        d=root/".runtime";d.mkdir(parents=True,exist_ok=True)
        payload={"format":"VOYAGER_LATEST_V1","save_set_id":snapshot.get("save_set_id"),"version":version_text(snapshot.get("version")),"snapshot_dir":Path(snapshot.get("dir")).name,"bundle_sha256":snapshot.get("bundle"),"verified_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
        tmp=d/f".LATEST.{os.getpid()}.tmp";tmp.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8");os.replace(tmp,_latest_pointer_path(root))
    except Exception: pass

def _write_runtime_cache(base: Path, check: dict) -> None:
    if base.resolve()!=ROOT.resolve() or check.get("status")!="PASS":return
    try:
        d=_runtime_cache_path(ROOT).parent;d.mkdir(parents=True,exist_ok=True)
        auth=validate_authority_set(base)
        payload={"format":RUNTIME_SCHEMA,"engine_version":ENGINE_VERSION,"engine_sha256":sha256_file(Path(__file__).resolve()),"authority_fingerprint":_authority_fingerprint(base),"authority_stats":_authority_stat_signature(base),"save_set_id":(auth or {}).get("save_set_id"),"game_time":read_json(base/"state.json").get("game_time"),"checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
        payload["integrity_sha256"]=_runtime_session_integrity(payload)
        tmp=d/f".session.{os.getpid()}.tmp";tmp.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8");os.replace(tmp,_runtime_cache_path(ROOT))
    except Exception:pass

def _v130_layer_ensure_source_ready_01(base: Path, allow_cache: bool=True)->dict:
    base=base.resolve()
    if base!=ROOT.resolve():return _ensure_source_ready_v251(base,allow_cache=False)
    if allow_cache:
        try:
            c=strict_json_load(_runtime_cache_path(ROOT))
            if _runtime_session_cache_intact(c) and c.get("format")==RUNTIME_SCHEMA and c.get("engine_version")==ENGINE_VERSION and c.get("engine_sha256")==sha256_file(Path(__file__).resolve()) and c.get("authority_stats")==_authority_stat_signature(ROOT):
                return {"status":"PASS","cached":True,"mode":"stat-fast","save_set_id":c.get("save_set_id"),"engine_binding":{"status":"BOUND_FAST"}}
        except Exception:pass
    # The compatibility path already performs one semantic run_checks and seeds the
    # runtime fingerprint. Repeating it here doubled cold/no-cache validation cost.
    return _ensure_source_ready_v251(base,allow_cache=False)

def _reset_runtime_sqlite_files(p:Path)->None:
    """Delete a corrupt non-authoritative SQLite cache and its transient sidecars."""
    for q in (p,Path(str(p)+"-wal"),Path(str(p)+"-shm")):
        try:q.unlink(missing_ok=True)
        except Exception:pass

def _cache_db_path(root:Path=ROOT)->Path:return root/".runtime"/"cache.db"

def _cache_connect(root:Path=ROOT):
    p=_cache_db_path(root);p.parent.mkdir(parents=True,exist_ok=True)
    last=None
    for attempt in range(2):
        con=None
        try:
            con=sqlite3.connect(str(p));con.execute("PRAGMA journal_mode=WAL");con.execute("PRAGMA synchronous=NORMAL");return con
        except sqlite3.DatabaseError as ex:
            last=ex
            try:
                if con is not None:con.close()
            except Exception:pass
            if attempt==0:
                _reset_runtime_sqlite_files(p);continue
            raise
    raise last if last is not None else EngineError("RUNTIME_CACHE_DB_OPEN_FAILED")

def rebuild_runtime_cache_db(base:Path=ROOT)->dict:
    base=Path(base).resolve();ensure_source_ready(base);state=read_json(base/"state.json");world=_authority_world_text(base);con=_cache_connect(base)
    try:
        con.executescript("DROP TABLE IF EXISTS meta;DROP TABLE IF EXISTS state_alias;DROP TABLE IF EXISTS history_offset;DROP TABLE IF EXISTS world_rule;CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT);CREATE TABLE state_alias(alias TEXT PRIMARY KEY,path TEXT,value_json TEXT);CREATE TABLE history_offset(seq INTEGER PRIMARY KEY,event_id TEXT,game_time TEXT,type TEXT,offset INTEGER,length INTEGER);CREATE INDEX idx_hist_event ON history_offset(event_id);CREATE INDEX idx_hist_time ON history_offset(game_time);CREATE TABLE world_rule(rule_id TEXT PRIMARY KEY,start INTEGER,end INTEGER);")
        aliases={"game_time":"game_time","gold":"summary.funds.gold","grey":"summary.funds.grey","voyager_ships":"summary.ships.voyager","jinchuan_ships":"summary.ships.jinchuan","shadow_ships":"summary.ships.shadow_active","voyager_personnel":"summary.personnel.voyager","jinchuan_personnel":"summary.personnel.jinchuan","shadow_personnel":"summary.personnel.shadow","jinchuan_resource_network":"world_state_overrides.mining_and_industry.jinchuan_resource_network_current","jinchuan_latest_settlement":"jinchuan_fleet.latest_daily_financial_settlement"}
        for a,p in aliases.items():
            try:v=get_by_path(state,p)
            except Exception:continue
            con.execute("INSERT INTO state_alias VALUES(?,?,?)",(a,p,json.dumps(v,ensure_ascii=False,separators=(",",":"))))
        # HISTORY may contain physical HISTORY_EPOCH_V1 containers.  Cache the
        # logical event stream rather than physical byte lines so cache counts,
        # event ids, and times remain invariant before/after epoch compaction.
        _,logical_events,_=read_history_view(base/"events.jsonl")
        for seq0,r in enumerate(logical_events,1):
            seq=int(r.get("seq") or seq0)
            con.execute("INSERT OR REPLACE INTO history_offset VALUES(?,?,?,?,?,?)",(seq,str(r.get("event_id") or ""),str(r.get("game_time") or ""),str(r.get("type") or ""),-1,0))
        matches=list(re.finditer(r'(?m)^###?\s+.*?(RULE-[A-Z0-9-]+).*$',world))
        for i,m in enumerate(matches):con.execute("INSERT OR REPLACE INTO world_rule VALUES(?,?,?)",(m.group(1),m.start(),matches[i+1].start() if i+1<len(matches) else len(world)))
        auth=validate_authority_set(base) or {};con.executemany("INSERT INTO meta VALUES(?,?)",[("save_set_id",str(auth.get("save_set_id") or "")),("engine_version",ENGINE_VERSION),("built_at",dt.datetime.now(dt.timezone.utc).isoformat())]);con.commit()
        return {"status":"READY","db":str(_cache_db_path(base)),"history_rows":con.execute("SELECT count(*) FROM history_offset").fetchone()[0],"aliases":con.execute("SELECT count(*) FROM state_alias").fetchone()[0],"world_rules":con.execute("SELECT count(*) FROM world_rule").fetchone()[0]}
    finally:con.close()

VESSEL_LOCATION_AUTHORITY_MIN_VERSION=(9,54)

def _player_vessel_location_index(state:dict)->dict:
    out={}
    vf=state.get('voyager_fleet') or {}; roster=vf.get('vessel_roster') or []; part=vf.get('current_location_partition') or {}
    dep_by_vid={}
    for did,d in (part.get('deployments') or {}).items():
        if not isinstance(d,dict):continue
        for vid in d.get('vessels') or []:
            if isinstance(vid,str):dep_by_vid[vid]=(did,d)
    tr=part.get('transit') or {}; tr_ids=set(tr.get('vessels') or []) if isinstance(tr,dict) else set()
    for r in roster:
        if not isinstance(r,dict):continue
        vid=str(r.get('vessel_id') or '');name=str(r.get('name') or '')
        if not vid or not name:continue
        if vid in dep_by_vid:
            did,d=dep_by_vid[vid];loc=str(d.get('location_name') or d.get('location') or did)
            out[name]={'fleet_id':'voyager','vessel_id':vid,'name':name,'location_name':loc,'location_id':d.get('location_id'),'status':d.get('status'),'authority_path':f'STATE.voyager_fleet.current_location_partition.deployments.{did}'}
        elif vid in tr_ids:
            out[name]={'fleet_id':'voyager','vessel_id':vid,'name':name,'location_name':'在途','location_id':None,'status':tr.get('status'),'authority_path':'STATE.voyager_fleet.current_location_partition.transit'}
        else:
            out[name]={'fleet_id':'voyager','vessel_id':vid,'name':name,'location_name':'远航者基地','location_id':None,'status':(part.get('at_voyager_base') or {}).get('status'),'authority_path':'STATE.voyager_fleet.current_location_partition.at_voyager_base'}
    sf=state.get('shadow_fleet') or {}; spart=sf.get('current_location') or {}; sv=sf.get('vessels') or {}; sbase=spart.get('at_shadow_base') or {}; shome=spart.get('homeport')
    sdep={}
    for did,d in (spart.get('deployments') or {}).items():
        if not isinstance(d,dict):continue
        for vid in d.get('vessels') or []:
            if isinstance(vid,str):sdep[vid]=(did,d)
    strans=spart.get('transit') or {}; strans_ids=set(strans.get('vessels') or []) if isinstance(strans,dict) else set(); sbase_ids=set(sbase.get('vessels') or []) if isinstance(sbase,dict) else set()
    for vid,r in sv.items():
        if not isinstance(r,dict):continue
        name=str(r.get('name') or vid)
        if vid in sdep:
            did,d=sdep[vid];out[name]={'fleet_id':'shadow','vessel_id':vid,'name':name,'location_name':str(d.get('location_name') or d.get('location') or did),'location_id':d.get('location_id'),'status':d.get('status'),'authority_path':f'STATE.shadow_fleet.current_location.deployments.{did}'}
        elif vid in strans_ids:
            out[name]={'fleet_id':'shadow','vessel_id':vid,'name':name,'location_name':'在途','location_id':None,'status':strans.get('status'),'authority_path':'STATE.shadow_fleet.current_location.transit'}
        elif vid in sbase_ids:
            out[name]={'fleet_id':'shadow','vessel_id':vid,'name':name,'location_name':'S-B5暗影基地','location_id':shome,'status':sbase.get('status'),'authority_path':'STATE.shadow_fleet.current_location.at_shadow_base'}
        else:
            loc=r.get('current_location') or r.get('location');out[name]={'fleet_id':'shadow','vessel_id':vid,'name':name,'location_name':loc,'location_id':r.get('location_id'),'status':r.get('status'),'authority_path':f'STATE.shadow_fleet.vessels.{vid}'}
    jf=state.get('jinchuan_fleet') or {}
    for vid,r in (jf.get('vessels') or {}).items():
        if not isinstance(r,dict):continue
        name=str(r.get('name') or vid);loc=r.get('current_location') or r.get('location')
        if isinstance(loc,dict):loc=loc.get('name') or loc.get('status') or loc.get('location_id')
        out[name]={'fleet_id':'jinchuan','vessel_id':vid,'name':name,'location_name':loc,'location_id':r.get('location_id') or ((r.get('location') or {}).get('location_id') if isinstance(r.get('location'),dict) else None),'status':r.get('status'),'authority_path':f'STATE.jinchuan_fleet.vessels.{vid}'}
    return out

def _player_vessel_location_hygiene_report(state:dict)->dict:
    errs=[]
    try:ver=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=VESSEL_LOCATION_AUTHORITY_MIN_VERSION
    vf=state.get('voyager_fleet') or {};roster=vf.get('vessel_roster') or [];rids={str(r.get('vessel_id')) for r in roster if isinstance(r,dict) and r.get('vessel_id')};part=vf.get('current_location_partition') or {};deps=part.get('deployments') or {};tr=part.get('transit') or {};dep_ids=[]
    for did,d in deps.items():
        if not isinstance(d,dict):continue
        ids=[x for x in d.get('vessels') or [] if isinstance(x,str)];dep_ids+=ids
        if int(d.get('ships',len(ids)) or 0)!=len(ids):errs.append({'kind':'voyager_deployment_count','deployment':did})
        for vid in ids:
            if vid not in rids:errs.append({'kind':'voyager_deployment_unknown_vessel','deployment':did,'vessel_id':vid})
    tr_ids=[x for x in (tr.get('vessels') or []) if isinstance(x,str)] if isinstance(tr,dict) else []
    if set(dep_ids)&set(tr_ids):errs.append({'kind':'voyager_location_overlap','vessels':sorted(set(dep_ids)&set(tr_ids))})
    base_expected=len(rids)-len(set(dep_ids))-len(set(tr_ids));base_recorded=int(((part.get('at_voyager_base') or {}).get('ships') or 0))
    if base_expected!=base_recorded:errs.append({'kind':'voyager_base_count','expected':base_expected,'recorded':base_recorded})
    redundant=[]
    for vid,r in (vf.get('named_vessels') or {}).items():
        if not isinstance(r,dict):continue
        for k in ('location_id','location_name','location','current_location','current_location_status'):
            if k in r:redundant.append({'vessel_id':vid,'key':k,'value':r.get(k)})
        if isinstance(r.get('status'),str) and r.get('status').startswith('at_'):redundant.append({'vessel_id':vid,'key':'status','value':r.get('status')})
    if required and redundant:errs.append({'kind':'voyager_named_location_mirror_forbidden','count':len(redundant),'samples':redundant[:30]})
    retired_aliases=[k for k in ('main_fleet_location','ship_count_note','personnel_note') if k in vf]
    if required and retired_aliases:errs.append({'kind':'voyager_retired_location_or_personnel_alias','keys':retired_aliases})
    if required and isinstance(vf.get('fleet_activity_status'),dict):errs.append({'kind':'voyager_retired_fleet_activity_status','path':'STATE.voyager_fleet.fleet_activity_status'})
    sf=state.get('shadow_fleet') or {};sp=sf.get('current_location') or {};base=sp.get('at_shadow_base') or {};base_ids=[x for x in base.get('vessels') or [] if isinstance(x,str)];home=sp.get('homeport')
    if int(base.get('ships',len(base_ids)) or 0)!=len(base_ids):errs.append({'kind':'shadow_base_count'})
    total=len(base_ids)+sum(int((d or {}).get('ships',0) or 0) for d in (sp.get('deployments') or {}).values() if isinstance(d,dict))+int((sp.get('transit') or {}).get('ships',0) or 0)
    if int(sf.get('ship_count_active',total) or 0)!=total:errs.append({'kind':'shadow_partition_total','partition':total,'active':sf.get('ship_count_active')})
    for vid in base_ids:
        r=(sf.get('vessels') or {}).get(vid) or {}
        if home and r.get('location_id') not in (None,home):errs.append({'kind':'shadow_homeport_location_id','vessel_id':vid})
        for k in ('location','current_location'):
            if isinstance(r.get(k),str) and 'S-B5' not in r.get(k):errs.append({'kind':'shadow_homeport_location_text','vessel_id':vid,'key':k,'value':r.get(k)})
    return {'required':required,'minimum_version':version_text(VESSEL_LOCATION_AUTHORITY_MIN_VERSION),'errors':errs,'count':len(errs),'voyager_redundant_location_mirrors':redundant[:100]}

def _voyager_named_mission_current_hygiene_report(state:dict)->dict:
    """Reject historical named-vessel mission snapshots that still claim current authority."""
    try:ver=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=VESSEL_LOCATION_AUTHORITY_MIN_VERSION;rows=[]
    vf=state.get('voyager_fleet') or {};named=vf.get('named_vessels') or {}
    terminal_prefixes=('completed','closed','cancelled','canceled','failed','aborted','resolved','returned','retired')
    no_current_tokens=('无当前外派任务','无当前任务','已返航','no current assignment','no current mission','returned to')
    for vid,rec in named.items():
        if not isinstance(rec,dict):continue
        canonical=str(rec.get('current_mission') or '')
        no_assignment=rec.get('current_assignment_task_id') in (None,'')
        canonical_declares_none=any(tok.lower() in canonical.lower() for tok in no_current_tokens)
        for key,payload in rec.items():
            if not (isinstance(key,str) and key.endswith('_current') and isinstance(payload,dict)):continue
            status=str(payload.get('status') or '').strip().lower()
            if status.startswith(terminal_prefixes):
                rows.append({'vessel_id':vid,'key':key,'kind':'terminal_named_vessel_snapshot_named_current','status':payload.get('status')})
            elif key.endswith('_mission_current') and no_assignment and canonical_declares_none and status.startswith('active'):
                rows.append({'vessel_id':vid,'key':key,'kind':'active_mission_snapshot_conflicts_with_canonical_no_assignment','status':payload.get('status'),'current_mission':canonical[:240]})
    return {'required':required,'minimum_version':version_text(VESSEL_LOCATION_AUTHORITY_MIN_VERSION),'count':len(rows),'rows':rows[:100]}

def _active_task_temporal_mirror_report(state:dict,tasks:dict)->dict:
    try:ver=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=VESSEL_LOCATION_AUTHORITY_MIN_VERSION;now=parse_iso(state.get('game_time'));bad=[]
    if now:
        for bucket in ('active_tasks','queued_tasks'):
            for i,t in enumerate(tasks.get(bucket) or []):
                if not isinstance(t,dict):continue
                mon=((t.get('runtime_policy') or {}).get('monitor') or {});mn=parse_iso(mon.get('next_review_at'));td=t.get('task_data') or {}
                if not isinstance(td,dict):continue
                for k,v in td.items():
                    if not str(k).startswith('next_') or not isinstance(v,str):continue
                    d=parse_iso(v)
                    if d and d<now and mn and mn>=now:bad.append({'task_id':t.get('task_id'),'path':f'TASKS.{bucket}[{i}].task_data.{k}','value':v,'runtime_next_review_at':mon.get('next_review_at')})
    return {'required':required,'minimum_version':version_text(VESSEL_LOCATION_AUTHORITY_MIN_VERSION),'count':len(bad),'rows':bad[:100]}

def _exact_vessel_location_query(base:Path,topic:str)->Optional[dict]:
    q=_normalize_search_text(topic)
    if not any(x in q for x in ('在哪','位置','当前地点','现在地点','驻地')):return None
    ensure_source_ready(base);st=read_json(base/'state.json');idx=_player_vessel_location_index(st);matches=[]
    for name,row in idx.items():
        nn=_normalize_search_text(name)
        if nn and nn in q:matches.append((len(nn),name,row))
    if not matches:return None
    _,name,row=sorted(matches,reverse=True,key=lambda x:x[0])[0]
    return {'packet':'VESSEL_LOCATION_QUERY_V1','status':'COMPLETE','engine_version':ENGINE_VERSION,'topic':topic,'game_time':st.get('game_time'),'vessel':row,'path':row.get('authority_path'),'source':'state.json','resolved_state_paths':[str(row.get('authority_path') or '').removeprefix('STATE.')],'save_set_id':(validate_authority_set(base) or {}).get('save_set_id')}

ENTITY_LIFECYCLE_SCHEMA="ENTITY_LIFECYCLE_V1"
ENTITY_LIFECYCLE_MIN_VERSION=(10,133)
ENTITY_LIFECYCLE_STATUSES={"active","merged","retired","dissolved","destroyed"}
ENTITY_LIFECYCLE_TERMINAL={"merged","retired","dissolved","destroyed"}


def _entity_lifecycle_registry(state:dict)->Optional[dict]:
    reg=state.get("entity_lifecycle") if isinstance(state,dict) else None
    return reg if isinstance(reg,dict) else None


def _entity_lifecycle_integrity_report(state:dict,tasks:dict)->dict:
    """Validate canonical entity lifecycle and block retired entities from active/current authority.

    This intentionally checks machine-facing/current structures, not arbitrary historical prose.
    Historical mentions of a pre-merge entity remain valid in HISTORY and narrative evidence.
    """
    try:ver=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=ENTITY_LIFECYCLE_MIN_VERSION
    reg=_entity_lifecycle_registry(state);rows=[]
    if reg is None:
        if required:rows.append({'kind':'registry_missing','path':'STATE.entity_lifecycle'})
        return {'required':required,'minimum_version':version_text(ENTITY_LIFECYCLE_MIN_VERSION),'schema':ENTITY_LIFECYCLE_SCHEMA,'count':len(rows),'rows':rows}
    if reg.get('schema')!=ENTITY_LIFECYCLE_SCHEMA:rows.append({'kind':'schema','value':reg.get('schema'),'expected':ENTITY_LIFECYCLE_SCHEMA})
    ents=reg.get('entities')
    if not isinstance(ents,dict) or not ents:
        rows.append({'kind':'entities_missing_or_empty'});ents={}
    name_to_id={};terminal_names={}
    for eid,rec in ents.items():
        if not isinstance(eid,str) or not eid.strip() or not isinstance(rec,dict):
            rows.append({'kind':'entity_record','entity_id':eid});continue
        name=rec.get('canonical_name');status=rec.get('status')
        if not isinstance(name,str) or not name.strip():rows.append({'kind':'canonical_name','entity_id':eid});continue
        if name in name_to_id and name_to_id[name]!=eid:rows.append({'kind':'duplicate_canonical_name','name':name,'entity_ids':[name_to_id[name],eid]})
        name_to_id[name]=eid
        aliases=rec.get('aliases') or []
        if not isinstance(aliases,list) or not all(isinstance(x,str) and x.strip() for x in aliases):rows.append({'kind':'aliases','entity_id':eid});aliases=[]
        for a in aliases:
            if a in name_to_id and name_to_id[a]!=eid:rows.append({'kind':'duplicate_alias','alias':a,'entity_ids':[name_to_id[a],eid]})
            name_to_id[a]=eid
        if status not in ENTITY_LIFECYCLE_STATUSES:rows.append({'kind':'status','entity_id':eid,'value':status})
        if status in ENTITY_LIFECYCLE_TERMINAL:
            terminal_names[name]=eid
            for a in aliases:terminal_names[a]=eid
        if status=='merged':
            suc=rec.get('successor_id')
            if not isinstance(suc,str) or not suc.strip():rows.append({'kind':'merged_successor_missing','entity_id':eid})
    # successor integrity / loops
    for eid,rec in ents.items():
        if not isinstance(rec,dict) or rec.get('status')!='merged':continue
        suc=rec.get('successor_id')
        if suc not in ents:rows.append({'kind':'successor_missing','entity_id':eid,'successor_id':suc});continue
        seen={eid};cur=suc
        while cur in ents and isinstance(ents.get(cur),dict) and ents[cur].get('status')=='merged':
            if cur in seen:rows.append({'kind':'successor_loop','entity_id':eid,'at':cur});break
            seen.add(cur);cur=ents[cur].get('successor_id')
        if cur in ents and isinstance(ents.get(cur),dict) and ents[cur].get('status')!='active':
            rows.append({'kind':'successor_not_active','entity_id':eid,'resolved_successor_id':cur,'status':ents[cur].get('status')})
    def skip_path(path:str)->bool:
        z=path.lower()
        return any(tok in z for tok in ('.history','.historical','.archive','.archived','.legacy','.confirmed_history','.migration_archive'))
    # Any retired canonical/alias used as a dictionary key inside a current scope is a duplicate active entity surface.
    def walk_state(x,path='STATE',current_scope=False):
        if isinstance(x,dict):
            for k,v in x.items():
                p=f'{path}.{k}';cs=current_scope or ('current' in str(k).lower())
                if cs and not skip_path(p) and str(k) in terminal_names:
                    rows.append({'kind':'retired_entity_current_key','entity_id':terminal_names[str(k)],'name':str(k),'path':p})
                # A small set of explicit state reference fields remain machine-facing even outside *_current containers.
                if not skip_path(p) and isinstance(v,str) and str(k).lower() in {'threat_org','organization','organization_name','target_org','entity_name'} and v in terminal_names:
                    rows.append({'kind':'retired_entity_state_reference','entity_id':terminal_names[v],'name':v,'path':p})
                walk_state(v,p,cs)
        elif isinstance(x,list):
            for i,v in enumerate(x):walk_state(v,f'{path}[{i}]',current_scope)
    walk_state(state)
    # Active/queued task machine routes may never point at merged/retired names.
    def inspect_task_value(v,path,tid):
        if not isinstance(v,str):return
        for name,eid in terminal_names.items():
            if name and name in v:
                rows.append({'kind':'retired_entity_task_reference','entity_id':eid,'name':name,'task_id':tid,'path':path,'value':v[:300]});break
    for bucket in ('active_tasks','queued_tasks'):
        arr=tasks.get(bucket) or [] if isinstance(tasks,dict) else []
        if not isinstance(arr,list):continue
        for i,t in enumerate(arr):
            if not isinstance(t,dict):continue
            tid=str(t.get('task_id') or f'{bucket}[{i}]')
            rr=t.get('retrieval_route') or {}
            for j,v in enumerate(rr.get('state_paths') or []):inspect_task_value(v,f'TASKS.{bucket}[{i}].retrieval_route.state_paths[{j}]',tid)
            for j,v in enumerate(rr.get('query_order') or []):inspect_task_value(v,f'TASKS.{bucket}[{i}].retrieval_route.query_order[{j}]',tid)
            vr=t.get('view_rule') or {}
            for j,v in enumerate(vr.get('status_sources') or []):inspect_task_value(v,f'TASKS.{bucket}[{i}].view_rule.status_sources[{j}]',tid)
            td=t.get('task_data') or {}
            def walk_td(x,p='task_data'):
                if isinstance(x,dict):
                    for k,v in x.items():
                        q=f'{p}.{k}'
                        if isinstance(v,str) and str(k).lower() in {'target','target_org','organization','organization_name','entity_name','threat_org'}:inspect_task_value(v,f'TASKS.{bucket}[{i}].{q}',tid)
                        walk_td(v,q)
                elif isinstance(x,list):
                    for j,v in enumerate(x):walk_td(v,f'{p}[{j}]')
            walk_td(td)
    # Stable refs themselves must not route to a retired entity path.
    refs=(((state.get('engine_runtime') or {}).get('state_refs') or {}))
    if isinstance(refs,dict):
        for key,v in refs.items():inspect_task_value(v,f'STATE.engine_runtime.state_refs.{key}','STATE_REF')
    return {'required':required,'minimum_version':version_text(ENTITY_LIFECYCLE_MIN_VERSION),'schema':ENTITY_LIFECYCLE_SCHEMA,'entity_count':len(ents),'retired_name_count':len(terminal_names),'count':len(rows),'rows':rows[:100]}


def _exact_entity_lifecycle_query(base:Path,topic:str)->Optional[dict]:
    q=_normalize_search_text(topic)
    if not q:return None
    ensure_source_ready(base);st=read_json(base/'state.json');reg=_entity_lifecycle_registry(st)
    if not isinstance(reg,dict) or reg.get('schema')!=ENTITY_LIFECYCLE_SCHEMA:return None
    ents=reg.get('entities') or {};matches=[]
    for eid,rec in ents.items():
        if not isinstance(rec,dict):continue
        names=[rec.get('canonical_name')]+list(rec.get('aliases') or [])
        for name in names:
            if isinstance(name,str):
                nn=_normalize_search_text(name)
                if nn and nn in q:matches.append((len(nn),eid,name,rec));break
    if not matches:return None
    _,eid,matched,rec=sorted(matches,reverse=True,key=lambda x:x[0])[0]
    out={'packet':'ENTITY_LIFECYCLE_QUERY_V1','status':'COMPLETE','engine_version':ENGINE_VERSION,'topic':topic,'matched_name':matched,'entity_id':eid,'entity':copy.deepcopy(rec),'source':'STATE.entity_lifecycle','game_time':st.get('game_time'),'resolved_state_paths':['entity_lifecycle']}
    if rec.get('status')=='merged':
        sid=rec.get('successor_id');srec=ents.get(sid) if isinstance(ents,dict) else None
        if isinstance(srec,dict):
            out['redirect']={'status':'merged','successor_id':sid,'successor_name':srec.get('canonical_name'),'current_state_path':srec.get('current_state_path')}
            p=srec.get('current_state_path')
            if isinstance(p,str):
                try:out['successor_current']=_compact_value(get_by_path(st,p),1200)
                except KeyError:pass
    out['save_set_id']=(validate_authority_set(base) or {}).get('save_set_id')
    return out

ENTITY_REGISTRY_SCHEMA="ENTITY_REGISTRY_V1"
ENTITY_REGISTRY_MIN_VERSION=(10,283)
ENTITY_REGISTRY_AUTHORITY_MODE="routing_metadata_only_no_duplicate_dynamic_facts"
ENTITY_REGISTRY_ALLOWED_FIELDS={"entity_type","canonical_name","aliases","status","state_path","source_ref","successor_id","managed_by"}


def _entity_auto_id(name:str)->str:
    return "ENT-AUTO-"+hashlib.sha256(str(name).encode("utf-8")).hexdigest()[:12].upper()


def _entity_registry_expected(state:dict)->dict:
    """Build deterministic routing records from existing canonical registries.

    No live counts, inventory, money, combat power or other dynamic facts are copied here.
    The registry is an address book over existing authority, not another CURRENT surface.
    """
    out={}
    pf=((((state.get("engine_runtime") or {}).get("player_fleet_registry") or {}).get("fleets") or {}))
    if isinstance(pf,dict):
        for fid,rec in pf.items():
            if not isinstance(rec,dict):continue
            eid="FLEET-"+str(fid).upper()
            root=_phase2_state_path(str(rec.get("authority_root") or "")) if str(rec.get("authority_root") or "").strip() else ""
            status="retired" if rec.get("retired") is True else "active"
            out[eid]={"entity_type":"fleet","canonical_name":str(rec.get("display_name") or fid),"aliases":[str(fid)],"status":status,"state_path":root or None,"source_ref":f"engine_runtime.player_fleet_registry.fleets.{fid}","managed_by":"player_fleet_registry"}
    life=_entity_lifecycle_registry(state) or {};ents=life.get("entities") or {}
    if isinstance(ents,dict):
        for eid,rec in ents.items():
            if not isinstance(rec,dict):continue
            row={"entity_type":"organization","canonical_name":rec.get("canonical_name"),"aliases":copy.deepcopy(rec.get("aliases") or []),"status":rec.get("status"),"state_path":rec.get("current_state_path"),"source_ref":f"entity_lifecycle.entities.{eid}","managed_by":"entity_lifecycle"}
            if rec.get("successor_id"):row["successor_id"]=rec.get("successor_id")
            out[str(eid)]=row
    auto=((((state.get("world_state_overrides") or {}).get("autonomous_entity_registry") or {}).get("instantiated") or {}))
    if isinstance(auto,dict):
        for key,rec in auto.items():
            if not isinstance(rec,dict):continue
            name=str(rec.get("name") or key);eid=_entity_auto_id(name)
            out[eid]={"entity_type":str(rec.get("kind") or "autonomous_entity"),"canonical_name":name,"aliases":[] if name==str(key) else [str(key)],"status":"active","state_path":f"world_state_overrides.autonomous_entity_registry.instantiated.{key}","source_ref":f"world_state_overrides.autonomous_entity_registry.instantiated.{key}","managed_by":"autonomous_entity_registry"}
    return out


def _sync_entity_registry(state:dict)->dict:
    expected=_entity_registry_expected(state);reg=state.get("entity_registry")
    if not isinstance(reg,dict):reg={}
    ents=reg.get("entities") if isinstance(reg.get("entities"),dict) else {}
    before=json.dumps(reg,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    for eid,row in expected.items():ents[eid]=copy.deepcopy(row)
    reg["schema"]=ENTITY_REGISTRY_SCHEMA;reg["authority_mode"]=ENTITY_REGISTRY_AUTHORITY_MODE;reg["entities"]=ents
    reg["policy"]="stable identity and authority routing only; dynamic facts remain at canonical state_path"
    state["entity_registry"]=reg
    er=state.setdefault("engine_runtime",{});refs=er.setdefault("state_refs",{})
    if isinstance(refs,dict):refs["ENTITY_REGISTRY"]="entity_registry"
    after=json.dumps(reg,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return {"changed":before!=after,"entity_count":len(ents),"managed_count":len(expected),"schema":ENTITY_REGISTRY_SCHEMA}


def _entity_registry_integrity_report(state:dict)->dict:
    try:ver=parse_version(str(state.get("save_version") or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=ENTITY_REGISTRY_MIN_VERSION;rows=[];reg=state.get("entity_registry")
    if not isinstance(reg,dict):
        if required:rows.append({"kind":"registry_missing","path":"STATE.entity_registry"})
        return {"required":required,"minimum_version":version_text(ENTITY_REGISTRY_MIN_VERSION),"schema":ENTITY_REGISTRY_SCHEMA,"count":len(rows),"rows":rows}
    if reg.get("schema")!=ENTITY_REGISTRY_SCHEMA:rows.append({"kind":"schema","value":reg.get("schema"),"expected":ENTITY_REGISTRY_SCHEMA})
    if reg.get("authority_mode")!=ENTITY_REGISTRY_AUTHORITY_MODE:rows.append({"kind":"authority_mode","value":reg.get("authority_mode")})
    ents=reg.get("entities")
    if not isinstance(ents,dict):rows.append({"kind":"entities_missing"});ents={}
    names={}
    for eid,rec in ents.items():
        if not isinstance(eid,str) or not eid or not isinstance(rec,dict):rows.append({"kind":"record","entity_id":eid});continue
        extra=sorted(set(rec)-ENTITY_REGISTRY_ALLOWED_FIELDS)
        if extra:rows.append({"kind":"dynamic_or_unknown_fields","entity_id":eid,"fields":extra})
        nm=rec.get("canonical_name");aliases=rec.get("aliases") or []
        if not isinstance(nm,str) or not nm.strip():rows.append({"kind":"canonical_name","entity_id":eid});continue
        if not isinstance(aliases,list) or not all(isinstance(x,str) and x.strip() for x in aliases):rows.append({"kind":"aliases","entity_id":eid});aliases=[]
        for n in [nm]+aliases:
            nn=_normalize_search_text(n)
            if nn in names and names[nn]!=eid:rows.append({"kind":"duplicate_name","name":n,"entity_ids":[names[nn],eid]})
            names[nn]=eid
        p=rec.get("state_path")
        if rec.get("status")=="active" and p:
            try:get_by_path(state,str(p).removeprefix("STATE."))
            except Exception:rows.append({"kind":"state_path_missing","entity_id":eid,"path":p})
        if rec.get("status")=="merged":
            suc=rec.get("successor_id")
            if not suc or suc not in ents:rows.append({"kind":"merged_successor_missing","entity_id":eid,"successor_id":suc})
    expected=_entity_registry_expected(state)
    for eid,want in expected.items():
        got=ents.get(eid)
        if not isinstance(got,dict):rows.append({"kind":"managed_entity_missing","entity_id":eid});continue
        for k in ("entity_type","canonical_name","status","state_path","source_ref","managed_by","successor_id"):
            if got.get(k)!=want.get(k):rows.append({"kind":"managed_route_mismatch","entity_id":eid,"field":k,"value":got.get(k),"expected":want.get(k)})
        if list(got.get("aliases") or [])!=list(want.get("aliases") or []):rows.append({"kind":"managed_alias_mismatch","entity_id":eid})
    return {"required":required,"minimum_version":version_text(ENTITY_REGISTRY_MIN_VERSION),"schema":ENTITY_REGISTRY_SCHEMA,"entity_count":len(ents),"managed_count":len(expected),"count":len(rows),"rows":rows[:100]}


def _exact_entity_registry_query(base:Path,topic:str)->Optional[dict]:
    q=_normalize_search_text(topic)
    if not q:return None
    ensure_source_ready(base);st=read_json(base/"state.json");reg=st.get("entity_registry")
    if not isinstance(reg,dict) or reg.get("schema")!=ENTITY_REGISTRY_SCHEMA:return None
    ents=reg.get("entities") or {};matches=[]
    for eid,rec in ents.items():
        if not isinstance(rec,dict):continue
        probes=[eid,rec.get("canonical_name")]+list(rec.get("aliases") or [])
        for name in probes:
            if not isinstance(name,str):continue
            nn=_normalize_search_text(name)
            if nn and nn in q:matches.append((len(nn),eid,name,rec));break
    if not matches:return None
    _,eid,matched,rec=sorted(matches,reverse=True,key=lambda x:x[0])[0]
    out={"packet":"ENTITY_REGISTRY_QUERY_V2","status":"COMPLETE","engine_version":ENGINE_VERSION,"topic":topic,"matched_name":matched,"entity_id":eid,"entity":copy.deepcopy(rec),"source":"STATE.entity_registry","game_time":st.get("game_time"),"resolved_state_paths":["entity_registry"],"missing_fields":[]}
    wants_current=any(tok in q for tok in ['状态','当前','医疗','观察','康复','位置','情况'])
    if wants_current and isinstance(rec.get("state_path"),str) and rec.get("state_path"):
        try:
            rp=str(rec.get("state_path")).removeprefix("STATE.");out["current_state"]=copy.deepcopy(get_by_path(st,rp));out["resolved_state_paths"].append(rp)
        except Exception:out["status"]="PARTIAL";out["missing_fields"].append("current_state")
        try:
            tasks=read_json(base/'tasks.json');related=[]
            for task in (tasks.get('active_tasks') or []):
                if not isinstance(task,dict):continue
                ob=task.get('obligation') or {};subs=ob.get('subject_ids') or []
                if eid in subs:related.append({'task_id':task.get('task_id'),'title':task.get('title'),'phase':task.get('phase'),'status':task.get('status'),'obligation':copy.deepcopy(ob),'task_data':_compact_value(task.get('task_data'),1200)})
            if related:out['related_obligations']=related
        except Exception:pass
    if rec.get("status")=="merged" and rec.get("successor_id") in ents:
        sr=ents[rec.get("successor_id")];out["redirect"]={"successor_id":rec.get("successor_id"),"successor_name":sr.get("canonical_name"),"state_path":sr.get("state_path")}
    out["save_set_id"]=(validate_authority_set(base) or {}).get("save_set_id")
    return out


DATED_CURRENT_ALIAS_MIN_VERSION=(9,54)
DATED_CURRENT_ALIAS_RE=re.compile(r'(?i)^.*current[_-]\d{8,}$')

def _dated_current_alias_report(state:dict)->dict:
    try:ver=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=DATED_CURRENT_ALIAS_MIN_VERSION;rows=[]
    def walk(x,path='STATE'):
        if isinstance(x,dict):
            for k,v in x.items():
                p=f'{path}.{k}'
                if DATED_CURRENT_ALIAS_RE.fullmatch(str(k)):rows.append({'path':p,'key':str(k)})
                walk(v,p)
        elif isinstance(x,list):
            for i,v in enumerate(x):walk(v,f'{path}[{i}]')
    walk(state)
    return {'required':required,'minimum_version':version_text(DATED_CURRENT_ALIAS_MIN_VERSION),'count':len(rows),'rows':rows[:100]}

def _current_state_temporal_hygiene_report(state:dict)->dict:
    try:ver=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=DATED_CURRENT_ALIAS_MIN_VERSION;now=parse_iso(state.get('game_time'));rows=[]
    def walk(x,path='STATE',current_scope=False):
        if isinstance(x,dict):
            for k,v in x.items():
                p=f'{path}.{k}';cs=current_scope or ('current' in str(k).lower())
                if cs and str(k).startswith('next_') and isinstance(v,str) and 'legacy' not in p.lower() and 'histor' not in p.lower():
                    d=parse_iso(v)
                    if now and d and d<now:rows.append({'path':p,'value':v})
                walk(v,p,cs)
        elif isinstance(x,list):
            for i,v in enumerate(x):walk(v,f'{path}[{i}]',current_scope)
    walk(state)
    return {'required':required,'minimum_version':version_text(DATED_CURRENT_ALIAS_MIN_VERSION),'count':len(rows),'rows':rows[:100]}


ROUTING_ONLY_FACT_HYGIENE_MIN_VERSION=(12,28)
ROUTING_ONLY_ALLOWED_FIELDS={'canonical_ref','role','reporting_note'}

def _routing_only_fact_hygiene_report(state:dict)->dict:
    """Routing-only objects may identify authority, but never duplicate mutable facts."""
    try:ver=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=ROUTING_ONLY_FACT_HYGIENE_MIN_VERSION;rows=[]
    def walk(x,path='STATE'):
        if isinstance(x,dict):
            if x.get('role')=='routing_only':
                extra=sorted(set(x)-ROUTING_ONLY_ALLOWED_FIELDS)
                if extra:rows.append({'path':path,'fields':extra,'canonical_ref':x.get('canonical_ref')})
                if not isinstance(x.get('canonical_ref'),str) or not str(x.get('canonical_ref')).startswith('ref:'):
                    rows.append({'path':path,'kind':'canonical_ref_missing_or_invalid','value':x.get('canonical_ref')})
            for k,v in x.items():walk(v,f'{path}.{k}')
        elif isinstance(x,list):
            for i,v in enumerate(x):walk(v,f'{path}[{i}]')
    walk(state)
    return {'required':required,'minimum_version':version_text(ROUTING_ONLY_FACT_HYGIENE_MIN_VERSION),'count':len(rows),'rows':rows[:100]}

CURRENT_SETTLEMENT_RECORD_COHERENCE_MIN_VERSION=(12,28)

def _current_settlement_record_coherence_report(state:dict)->dict:
    """Reject duplicate temporal aliases in current settlement records.

    V12.28 makes `at` the only timestamp for the latest JinChuan settlement result.
    Keeping `settled_at` beside it recreates the copy-old-then-partially-update failure mode.
    """
    try:ver=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=CURRENT_SETTLEMENT_RECORD_COHERENCE_MIN_VERSION;rows=[]
    rec=((state.get('jinchuan_fleet') or {}).get('latest_daily_financial_settlement'))
    if isinstance(rec,dict) and 'settled_at' in rec:
        rows.append({'path':'STATE.jinchuan_fleet.latest_daily_financial_settlement','kind':'duplicate_temporal_alias','canonical':'at','duplicate':'settled_at','at':rec.get('at'),'settled_at':rec.get('settled_at')})
    return {'required':required,'minimum_version':version_text(CURRENT_SETTLEMENT_RECORD_COHERENCE_MIN_VERSION),'count':len(rows),'rows':rows[:20]}

CALDER_LEGACY_SCHEDULE_HYGIENE_MIN_VERSION=(9,55)

def _calder_legacy_schedule_hygiene_report(state:dict)->dict:
    try:ver=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=CALDER_LEGACY_SCHEDULE_HYGIENE_MIN_VERSION;rows=[]
    if not required:return {'required':False,'minimum_version':version_text(CALDER_LEGACY_SCHEDULE_HYGIENE_MIN_VERSION),'count':0,'rows':[]}
    def walk(x,path='STATE'):
        if isinstance(x,dict):
            if isinstance(x.get('legacy_552_profile'),dict):
                prof=x['legacy_552_profile']
                for key in ('next_settlement_at','next_settlement_reference_gold'):
                    if key in prof:rows.append({'path':path+'.legacy_552_profile.'+key,'value':prof.get(key)})
            for k,v in x.items():walk(v,path+'.'+str(k))
        elif isinstance(x,list):
            for i,v in enumerate(x):walk(v,f'{path}[{i}]')
    walk(state)
    return {'required':required,'minimum_version':version_text(CALDER_LEGACY_SCHEDULE_HYGIENE_MIN_VERSION),'count':len(rows),'rows':rows[:20]}

def _exact_alias_key(topic:str)->Optional[str]:
    q=_normalize_search_text(topic)
    tests=[("jinchuan_resource_network",["金川资源网络","金川矿业网络","金川矿业日产","金川资源日产"]),("jinchuan_latest_settlement",["金川最近日结","金川日结","金川财务结算","金川最近财务结算"]),("gold",["金币余额","当前金币","金币有多少","gold"]),("grey",["灰币余额","当前灰币","灰币有多少","grey"]),("game_time",["当前时间","游戏时间","现在时间"]),("voyager_ships",["远航者舰船数","远航者多少艘"]),("jinchuan_ships",["金川舰船数","金川多少艘"]),("shadow_ships",["暗影舰船数","暗影多少艘"])]
    for k,vals in tests:
        if any(_normalize_search_text(v) in q for v in vals):return k
    return None

def _exact_query(base:Path,topic:str)->Optional[dict]:
    entity=_exact_entity_lifecycle_query(base,topic)
    if entity:return entity
    vessel=_exact_vessel_location_query(base,topic)
    if vessel:return vessel
    key=_exact_alias_key(topic)
    if not key:return None
    base=Path(base).resolve();ready=ensure_source_ready(base)
    paths={"gold":"summary.funds.gold","grey":"summary.funds.grey","game_time":"game_time","voyager_ships":"summary.ships.voyager","jinchuan_ships":"summary.ships.jinchuan","shadow_ships":"summary.ships.shadow_active","jinchuan_resource_network":"world_state_overrides.mining_and_industry.jinchuan_resource_network_current","jinchuan_latest_settlement":"jinchuan_fleet.latest_daily_financial_settlement"}
    path=paths[key]
    # Explicit --base reads must never borrow or overwrite the active ROOT cache.
    if base!=ROOT.resolve():
        st=read_json(base/"state.json");auth=validate_authority_set(base) or {}
        return {"packet":"EXACT_QUERY_V1","status":"COMPLETE","engine_version":ENGINE_VERSION,"topic":topic,"path":path,"value":get_by_path(st,path),"source":"state.json","resolved_state_paths":[path],"save_set_id":auth.get("save_set_id")}
    expected_sid=str(ready.get("save_set_id") or (validate_authority_set(base) or {}).get("save_set_id") or "")
    # Hot exact queries use the SHA-bound STATE semantic sidecar.  This avoids
    # opening/rebuilding SQLite and, after the first query for a STATE revision,
    # avoids reparsing the full STATE document on mobile.
    try:
        idx=_state_semantic_index(base);aliases=idx.get("exact_alias_values") or idx.get("alias_values") or {}
        if path in aliases:
            return {"packet":"EXACT_QUERY_V1","status":"COMPLETE","engine_version":ENGINE_VERSION,"topic":topic,"path":path,"value":aliases[path],"source":"state.json","resolved_state_paths":[path],"save_set_id":expected_sid or None,"runtime_index":"state_semantic_sidecar_v2"}
    except Exception:
        pass
    st=read_json(base/"state.json")
    return {"packet":"EXACT_QUERY_V1","status":"COMPLETE","engine_version":ENGINE_VERSION,"topic":topic,"path":path,"value":get_by_path(st,path),"source":"state.json","resolved_state_paths":[path],"save_set_id":expected_sid or None}

def _read_runtime_cache_safe():
    try:
        obj=strict_json_load(_runtime_cache_path(ROOT))
        return obj if _runtime_session_cache_intact(obj) else None
    except Exception:return None

def _task_player_decision_gate_open(task: dict) -> bool:
    """Return only explicit machine-readable commander decision gates.

    A due semantic review is not itself a player decision.  Text in `decision_gate`
    is a standing authorization contract and must never be parsed heuristically.
    Future tasks can expose a current gate through either the task root, task_data,
    or monitor using an explicit boolean.
    """
    if not isinstance(task,dict):return False
    flag_names=("decision_gate_open","player_decision_required")
    if any(task.get(k) is True for k in flag_names):return True
    td=task.get("task_data") or {}
    if isinstance(td,dict) and any(td.get(k) is True for k in flag_names):return True
    mon=((task.get("runtime_policy") or {}).get("monitor") or {})
    return isinstance(mon,dict) and any(mon.get(k) is True for k in flag_names)


def _cold_start_review_surfaces(state: dict, tasks: dict, now: Optional[dt.datetime]) -> Tuple[List[dict],List[dict]]:
    """Separate AI semantic-review work from explicit commander decision gates.

    Player decision gates are authoritative current state and therefore surface even
    when the task has no due AI monitor.  Conversely, a due AI review never becomes
    a commander decision unless an explicit machine-readable gate flag is open.
    """
    if now is None:return [],[]
    active=[t for t in (tasks.get('active_tasks') or []) if isinstance(t,dict)]
    by_id={str(t.get('task_id') or t.get('id') or ''):t for t in active}
    semantic=[]
    for due in task_monitor_queue(tasks,now,now,state=state):
        if not isinstance(due,dict):continue
        tid=str(due.get('task_id') or '');task=by_id.get(tid) or {}
        semantic.append({'task_id':tid or None,'title':due.get('title') or task.get('title'),'status':'AI_REVIEW_DUE_NOW','next_review_at':due.get('next_review_at'),'watch_condition':due.get('watch_condition'),'trigger':due.get('trigger')})
    decisions=[]
    for task in active:
        if not _task_player_decision_gate_open(task):continue
        mon=((task.get('runtime_policy') or {}).get('monitor') or {})
        watch=_watch_condition_status(state,task)
        decisions.append({'task_id':task.get('task_id') or task.get('id'),'title':task.get('title'),'status':'PLAYER_DECISION_DUE_NOW','decision_gate':_compact_value(task.get('decision_gate'),320),'watch_condition':copy.deepcopy(watch) if watch.get('configured') else None,'next_review_at':mon.get('next_review_at')})
    # Current semantic reviews and explicit commander decision gates are correctness
    # surfaces, not optional summaries.  Never silently truncate them: a cold-start AI
    # must be able to see every currently due gate before time can advance.  Rows are
    # already compact and bounded by the number of active tasks.
    return semantic,decisions


def _cold_fleet_location_summary(state:dict)->dict:
    """Return bounded but complete current-location views for each player fleet.

    Counts remain for compact UI compatibility, but COMPLETE location queries must also
    expose the actual deployment/site map and transit/base details needed to answer
    "where" rather than merely "how many".
    """
    vf=state.get('voyager_fleet') or {};jf=state.get('jinchuan_fleet') or {};sf=state.get('shadow_fleet') or {}
    vp=vf.get('current_location_partition') or {};sp=sf.get('current_location') or {};jn=jf.get('fleet_navigation') or jf.get('current_location') or {}
    vbase=copy.deepcopy(vp.get('at_voyager_base') or {}) if isinstance(vp,dict) else {}
    vdep=copy.deepcopy(vp.get('deployments') or {}) if isinstance(vp,dict) else {}
    vtrans=copy.deepcopy(vp.get('transit') or {}) if isinstance(vp,dict) else {}
    sbase=copy.deepcopy(sp.get('at_shadow_base') or {}) if isinstance(sp,dict) else {}
    sdep=copy.deepcopy(sp.get('deployments') or {}) if isinstance(sp,dict) else {}
    strans=copy.deepcopy(sp.get('transit') or {}) if isinstance(sp,dict) else {}
    sites=copy.deepcopy(jn.get('commercial_guard_sites') or {}) if isinstance(jn,dict) else {}
    groups=copy.deepcopy(jn.get('development_groups') or {}) if isinstance(jn,dict) else {}
    return {
        'voyager':{'as_of':vp.get('as_of') if isinstance(vp,dict) else None,'base_ships':vbase.get('ships'),'deployment_count':len(vdep),'transit_ships':vtrans.get('ships'),'base':vbase,'deployments':vdep,'transit':vtrans},
        'jinchuan':{'as_of':jn.get('as_of') if isinstance(jn,dict) else None,'guard_site_count':len(sites),'development_group_count':len(groups),'commercial_guard_sites':sites,'development_groups':groups,'status':jn.get('status') if isinstance(jn,dict) else None},
        'shadow':{'as_of':sp.get('as_of') if isinstance(sp,dict) else None,'homeport':sp.get('homeport') if isinstance(sp,dict) else None,'base_ships':sbase.get('ships'),'deployment_count':len(sdep),'transit_ships':strans.get('ships'),'base':sbase,'deployments':sdep,'transit':strans,'note':sp.get('note') if isinstance(sp,dict) else None},
    }


def _cold_fleet_location_resume_summary(state:dict)->dict:
    """Compact cold-start location surface; full detail remains in fleet_location query."""
    full=_cold_fleet_location_summary(state);out={}
    v=full.get('voyager') or {}
    out['voyager']={'as_of':v.get('as_of'),'base_ships':v.get('base_ships'),'transit_ships':v.get('transit_ships'),'deployments':[{'deployment_id':k,'ships':r.get('ships'),'vessels':copy.deepcopy(r.get('vessels') or []),'status':r.get('status')} for k,r in (v.get('deployments') or {}).items() if isinstance(r,dict)]}
    j=full.get('jinchuan') or {}
    out['jinchuan']={'as_of':j.get('as_of'),'commercial_guard_sites':copy.deepcopy(j.get('commercial_guard_sites') or {}),'development_groups':copy.deepcopy(j.get('development_groups') or {})}
    sh=full.get('shadow') or {}
    out['shadow']={'as_of':sh.get('as_of'),'homeport':sh.get('homeport'),'base_ships':sh.get('base_ships'),'deployments':[{'deployment_id':k,'ships':r.get('ships'),'total_personnel':r.get('total_personnel'),'location_name':r.get('location_name'),'status':r.get('status')} for k,r in (sh.get('deployments') or {}).items() if isinstance(r,dict)]}
    return out


def _cold_obligation_rows(tasks:dict)->List[dict]:
    rows=[]
    for task in (tasks.get('active_tasks') or []):
        if not isinstance(task,dict):continue
        ob=task.get('obligation')
        if not isinstance(ob,dict) or ob.get('active') is not True:continue
        mon=((task.get('runtime_policy') or {}).get('monitor') or {})
        rows.append({'task_id':task.get('task_id'),'title':task.get('title'),'kind':ob.get('kind'),'subject_ids':copy.deepcopy(ob.get('subject_ids') or []),'phase':task.get('phase'),'deadline':ob.get('deadline'),'timing_status':ob.get('timing_status'),'trigger_condition':ob.get('trigger_condition') or task.get('trigger_condition'),'requires_player_authorization':bool(ob.get('requires_player_authorization')),'next_review_at':mon.get('next_review_at')})
    return rows


def _active_obligation_rows(tasks:dict,state:Optional[dict]=None)->List[dict]:
    """Expose only explicit machine-readable ongoing obligations.

    This is a recovery/query surface, not an executor. Unknown deadlines remain None and
    authorization-required actions remain blocked until an explicit commander decision.
    """
    rows=[]
    for task in (tasks.get('active_tasks') or []):
        if not isinstance(task,dict):continue
        ob=task.get('obligation')
        if not isinstance(ob,dict) or ob.get('active') is not True:continue
        mon=((task.get('runtime_policy') or {}).get('monitor') or {})
        watch=_watch_condition_status(state,task) if isinstance(state,dict) else {'configured':False,'triggered':False}
        rows.append({
            'task_id':task.get('task_id') or task.get('id'),'title':task.get('title'),'kind':ob.get('kind'),'subject_ids':copy.deepcopy(ob.get('subject_ids') or []),
            'phase':task.get('phase'),'status':task.get('status'),'deadline':ob.get('deadline'),'timing_status':ob.get('timing_status'),
            'trigger_condition':ob.get('trigger_condition') or task.get('trigger_condition'),'requires_player_authorization':bool(ob.get('requires_player_authorization')),
            'authorization_note':ob.get('authorization_note'),'next_review_at':mon.get('next_review_at'),'watch_condition':copy.deepcopy(watch) if watch.get('configured') else None,
            'source_paths':copy.deepcopy(ob.get('source_paths') or []),
        })
    return rows


def _v130_layer__source_transport_sync_status_01(base:Path,current_save_set_id:Optional[str])->dict:
    """Verify whether the currently present two-file Project source matches active authority.

    This proves only the source transport visible in this runtime directory. It never claims
    that an external UI replacement succeeded unless the replacement pack is actually present
    and fully validates here.
    """
    packs=sorted([p for pat in ('VOYAGER_SOURCE_*.zip','VOYAGER_SOURCE_*.vpack') for p in base.glob(pat) if p.is_file()])
    if not packs:return {'status':'NO_PROJECT_SOURCE_PRESENT','current_save_set_id':current_save_set_id,'source_save_set_id':None,'verified':False}
    if len(packs)!=1:return {'status':'PROJECT_SOURCE_AMBIGUOUS','current_save_set_id':current_save_set_id,'source_save_set_id':None,'verified':False,'count':len(packs)}
    try:
        chk=vpack_transport_check(base)
        if chk.get('status')!='PASS':return {'status':'PROJECT_SOURCE_INVALID','current_save_set_id':current_save_set_id,'source_save_set_id':None,'verified':False,'errors':(chk.get('errors') or [])[:8]}
        with zipfile.ZipFile(packs[0],'r') as z:m=json.loads(z.read('PACK.json').decode('utf-8','strict'))
        sid=m.get('save_set_id');same=bool(current_save_set_id and sid==current_save_set_id)
        receipt=m.get('publication_receipt');receipt_fp=sha256_bytes(json.dumps(receipt,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))[:24] if isinstance(receipt,dict) else None
        return {'status':'VERIFIED_PROJECT_SOURCE' if same else 'STALE_PROJECT_SOURCE','current_save_set_id':current_save_set_id,'source_save_set_id':sid,'parent_save_set_id':m.get('parent_save_set_id'),'verified':same,'transport_file':packs[0].name,'publication_receipt_fingerprint':receipt_fp}
    except Exception as ex:
        return {'status':'PROJECT_SOURCE_INVALID','current_save_set_id':current_save_set_id,'source_save_set_id':None,'verified':False,'error':f'{type(ex).__name__}:{ex}'}


def _v130_layer_cold_start_packet_01(base:Path=ROOT)->dict:
    """COLD_START_PACKET_V5: correctness-critical resume facts only.

    Long-running watcher details, external-force revision maps, 24h event lists and
    narrative/current mirrors are deliberately omitted.  They are available through
    Query Intent Registry V3 and therefore do not tax every new mobile conversation.
    """
    ready=ensure_source_ready(base,allow_cache=True);s=read_json(base/'state.json');t=read_json(base/'tasks.json')
    now=parse_iso(s.get('game_time'));until=(now+dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S') if now else s.get('game_time')
    plan=routineplan_packet(base,until) if now else {};auth=validate_authority_set(base) or {};summary=s.get('summary') or {};cr=((s.get('engine_runtime') or {}).get('combat_runtime') or {});mr=_maintenance_runtime(s,create=False)
    semantic_reviews_due,decision=_cold_start_review_surfaces(s,t,now);active=[x for x in (t.get('active_tasks') or []) if isinstance(x,dict)];obligations=_cold_obligation_rows(t)
    sleeping_watchers=0;deterministic_tasks=0
    for task in active:
        mon=((task.get('runtime_policy') or {}).get('monitor') or {})
        if mon.get('requires_ai_review') and mon.get('next_review_at') is None and mon.get('mode') in {'external_wait','continuous','on_advance'}:sleeping_watchers+=1
        if (not mon.get('requires_ai_review') and mon.get('next_review_at')
            and callable(RESOLVER_FUNCTIONS.get(str(mon.get('resolver') or '')))
            and not _task_execution_coverage(s,t,task,now,now+dt.timedelta(days=1))):deterministic_tasks+=1
    try:contacts=get_state_path(s,'ref:PENDING_SENSOR_CONTACTS_CURRENT')
    except Exception:contacts=(s.get('world_state_overrides') or {}).get('pending_sensor_contacts_current') or {}
    if isinstance(contacts,dict) and isinstance(contacts.get('contacts'),list):pending_count=len(contacts.get('contacts') or [])
    elif isinstance(contacts,list):pending_count=len(contacts)
    elif isinstance(contacts,dict):pending_count=len([k for k,v in contacts.items() if v not in (None,False,[],{},'')])
    else:pending_count=0
    next_events=(plan or {}).get('deterministic_events') or []
    packet={
        'packet':COLD_START_PACKET_SCHEMA,'engine_version':ENGINE_VERSION,'save_set_id':auth.get('save_set_id'),'game_time':s.get('game_time'),'voyage_day':s.get('voyage_day'),
        'fleet_core':_mobile_fleet_core(s),'fleet_locations':_cold_fleet_location_resume_summary(s),
        'task_counts':{'active':len(active),'queued':len(t.get('queued_tasks') or []),'deterministic_scheduled':deterministic_tasks,'sleeping_semantic_watchers':sleeping_watchers},
        'next_deterministic_event':next_events[0] if next_events else None,'next_semantic_barrier':(plan or {}).get('semantic_barrier'),
        'semantic_reviews_due':semantic_reviews_due,'open_decision_gates':decision,'ongoing_obligations':obligations,'pending_contact_count':pending_count,
        'combat_runtime':{'last_battle_id':cr.get('last_committed_battle_id'),'next_battle_sequence':int(cr.get('next_battle_sequence',1) or 1),'pending_loot_count':len(cr.get('pending_loot') or []) if isinstance(cr.get('pending_loot') or [],list) else 0},
        'maintenance_runtime':{'repair_active':len(mr.get('repair_queue') or []),'medical_active':len(mr.get('medical_queue') or []),'blocked':len(mr.get('blocked_jobs') or {}),'pending_replenishment':len(mr.get('pending_replenishment') or [])},
        'pending_turn':(s.get('engine_runtime') or {}).get('pending_turn'),'recoverable_turn_sessions':_recoverable_turn_sessions(base),
        'authority_fingerprint':sha256_bytes(json.dumps({'save_set_id':auth.get('save_set_id'),'version':auth.get('version'),'bundle':auth.get('bundle'),'manifest':auth.get('manifest')},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))[:24],
        'query_contract':QUERY_INTENT_REGISTRY_SCHEMA,'source_ready':{'status':ready.get('status'),'cached':ready.get('cached'),'mode':ready.get('mode'),'save_set_id':ready.get('save_set_id')},'source_sync':_source_transport_sync_status(base,auth.get('save_set_id'))
    }
    return packet

TURN_SESSION_META_FORMAT="TURN_SESSION_V3"
TURN_RECOVERY_CHECKPOINT_FORMAT="TURN_RECOVERY_CHECKPOINT_V1"
AUTOSAVE_POLICY_SCHEMA="AUTOSAVE_POLICY_V1"
TURN_SESSION_ID_RE=re.compile(r"^[0-9a-f]{12}$")

