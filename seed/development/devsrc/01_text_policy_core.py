# === VOYAGER_DEV_MODULE: text_policy_core ===
def canonicalize_game_text(text: str) -> str:
    out = str(text)
    for old, new in TEXT_CANONICAL_REPLACEMENTS.items():
        out = out.replace(old, new)
    return out


def canonicalize_game_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return canonicalize_game_text(obj)
    if isinstance(obj, list):
        return [canonicalize_game_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: canonicalize_game_obj(v) for k, v in obj.items()}
    return obj


def _is_han_codepoint(cp: int) -> bool:
    return (
        0x3400 <= cp <= 0x4DBF or
        0x4E00 <= cp <= 0x9FFF or
        0xF900 <= cp <= 0xFAFF or
        0x20000 <= cp <= 0x2EBEF or
        0x30000 <= cp <= 0x323AF
    )


def _emoji_support_codepoint(cp: int, cat: str) -> bool:
    # Permit emoji composition marks in ordinary prose when an emoji is used.
    return cp in (0x200D, 0xFE0E, 0xFE0F, 0x20E3) or 0x1F3FB <= cp <= 0x1F3FF


def game_text_violations(text: str, limit: int = 80) -> list:
    """Return globally disallowed textual codepoints.

    Ordinary game prose may use ASCII printable text, numeric notation, Han ideographs,
    Unicode punctuation/spacing, mathematical/symbol glyphs and emoji. Alphabetic scripts
    other than ASCII Latin remain disallowed globally. Proper-name restrictions are checked
    separately by name_symbol_policy_report().
    """
    import unicodedata
    found=[]; seen=set()
    for ch in text:
        cp=ord(ch)
        if ch in "\n\r\t":
            continue
        if 0x20 <= cp <= 0x7E:
            continue
        if _is_han_codepoint(cp):
            continue
        cat=unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("Z"):
            continue
        # Explicitly permit math/symbol glyphs and emoji in non-name prose.
        if cat.startswith("S") or 0x2460 <= cp <= 0x24FF or _emoji_support_codepoint(cp,cat):
            continue
        if ch not in seen:
            seen.add(ch)
            found.append({"char":ch,"codepoint":f"U+{cp:04X}","category":cat,"name":unicodedata.name(ch,"")})
            if len(found)>=limit:
                break
    return found


def name_symbol_violations(text: str, limit: int = 40) -> list:
    """Return characters outside the commander-approved proper-name character set."""
    import unicodedata
    found=[]; seen=set()
    for ch in str(text):
        cp=ord(ch); cat=unicodedata.category(ch)
        allowed=(ch in "\n\r\t" or 0x20 <= cp <= 0x7E or _is_han_codepoint(cp) or cat.startswith("P") or cat.startswith("Z") or cat == "Sm")
        if not allowed and ch not in seen:
            seen.add(ch); found.append({"char":ch,"codepoint":f"U+{cp:04X}","category":cat,"name":unicodedata.name(ch,"")})
            if len(found)>=limit: break
    return found

def _scan_json_name_fields(obj: Any, path: str = "", out: Optional[list] = None) -> list:
    if out is None: out=[]
    if isinstance(obj,dict):
        for k,v in obj.items():
            p=f"{path}.{k}" if path else str(k)
            key=str(k).lower()
            if isinstance(v,str) and (key in NAME_FIELD_KEYS or key.endswith("_name")):
                bad=name_symbol_violations(v)
                if bad: out.append({"path":p,"value":v,"violations":bad})
            _scan_json_name_fields(v,p,out)
    elif isinstance(obj,list):
        for i,v in enumerate(obj): _scan_json_name_fields(v,f"{path}[{i}]",out)
    return out


def _md_cells(line: str) -> list:
    if not line.lstrip().startswith("|"): return []
    return [x.strip() for x in line.strip().strip("|").split("|")]


def _is_md_separator(cells: list) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?",c.replace(" ","")) for c in cells)


def _strip_md_name_markup(text: str) -> str:
    # Name-table cells may append descriptive parameters in parentheses. Only the
    # leading entity/model name is subject to the proper-name symbol restriction.
    out=re.sub(r"[`*_~]", "", str(text)).strip()
    out=re.split(r"[（(]",out,maxsplit=1)[0].strip()
    return out


def _scan_world_name_tables(text: str) -> list:
    lines=text.splitlines(); out=[]; i=0
    while i+1 < len(lines):
        hdr=_md_cells(lines[i]); sep=_md_cells(lines[i+1])
        if hdr and sep and len(hdr)==len(sep) and _is_md_separator(sep):
            idx=[j for j,h in enumerate(hdr) if _strip_md_name_markup(h) in WORLD_NAME_TABLE_HEADERS]
            j=i+2
            while j < len(lines):
                cells=_md_cells(lines[j])
                if not cells: break
                for col in idx:
                    if col < len(cells):
                        val=_strip_md_name_markup(cells[col]); bad=name_symbol_violations(val)
                        if bad: out.append({"line":j+1,"column":hdr[col],"value":val,"violations":bad})
                j+=1
            i=j; continue
        i+=1
    return out


_VALIDATION_FILE_MEMO: Dict[Tuple[str,str], Any] = {}
_VALIDATION_FILE_MEMO_MAX = 256

def _memoized_file_validation(policy: str, path: Path, compute) -> Any:
    """Memoize pure validation by exact file SHA within one Engine process.

    The memo is non-authoritative and cannot make changed bytes pass: any byte change
    produces a new SHA key. Results are copied on read/write so callers cannot poison
    another validation pass. The cache is deliberately small and process-local.
    """
    digest=sha256_file(path);key=(str(policy),digest)
    if key in _VALIDATION_FILE_MEMO:
        return copy.deepcopy(_VALIDATION_FILE_MEMO[key])
    value=compute()
    if len(_VALIDATION_FILE_MEMO)>=_VALIDATION_FILE_MEMO_MAX:
        _VALIDATION_FILE_MEMO.clear()
    _VALIDATION_FILE_MEMO[key]=copy.deepcopy(value)
    return value


def name_symbol_policy_report(base: Path) -> dict:
    bad={}
    for fn in ("state.json","tasks.json"):
        p=base/fn
        if not p.is_file(): continue
        def compute_json(p=p):
            try:return _scan_json_name_fields(read_json(p))[:80]
            except Exception as e:return [{"error":str(e)}]
        v=_memoized_file_validation("name_json_v1",p,compute_json)
        if v:bad[fn]=v
    hp=base/"events.jsonl"
    if hp.is_file():
        def compute_history():
            try:
                meta,events,_=read_history_view(hp);return _scan_json_name_fields({"metadata":meta,"events":events})[:80]
            except Exception as e:return [{"error":str(e)}]
        v=_memoized_file_validation("name_history_v1",hp,compute_history)
        if v:bad["events.jsonl"]=v
    wp=base/"WORLD.md"
    if wp.is_file():
        def compute_world():
            try:return _scan_world_name_tables(wp.read_text(encoding="utf-8"))[:80]
            except Exception as e:return [{"error":str(e)}]
        v=_memoized_file_validation("name_world_v1",wp,compute_world)
        if v:bad["WORLD.md"]=v
    return bad


def text_policy_active(world_text: str) -> bool:
    return TEXT_POLICY_RULE_ID in world_text


def authority_text_policy_report(base: Path) -> dict:
    bad={}
    for fn in AUTH_FILES:
        p=base/fn
        if not p.is_file():continue
        def compute(p=p):
            try:return game_text_violations(p.read_text(encoding="utf-8"))
            except Exception as e:return [{"error":str(e)}]
        v=_memoized_file_validation("authority_text_v1",p,compute)
        if v:bad[fn]=v
    return bad


def _history_physical_event_lines(path: Path) -> List[bytes]:
    """Return non-metadata physical HISTORY records exactly as stored.

    Normal commits append to this physical record stream. HISTORY_EPOCH_V1 is the only
    approved operation that may rewrite old physical records while preserving the exact
    logical event byte stream.
    """
    out=[]
    for raw in path.read_bytes().splitlines():
        if not raw.strip():
            continue
        rec=strict_json_loads(raw.decode("utf-8"))
        if rec.get("record_type")=="metadata":
            continue
        out.append(raw)
    return out


def _history_epoch_compaction_allowed(parent_path: Path, current_path: Path, parent_raw: list, current_raw: list, current_events: list, parent_event_count: int) -> bool:
    """Narrow exception for verified physical Epoch compaction.

    The exception is valid only when the entire parent logical event byte prefix is
    unchanged, every Epoch container decodes successfully (enforced by read_history_raw),
    at least one physical Epoch record exists, and a newly appended zero-time
    history_epoch_compaction audit event explicitly records the operation.
    """
    if len(current_raw) < len(parent_raw) or current_raw[:len(parent_raw)] != parent_raw:
        return False
    try:
        physical=_history_physical_event_lines(current_path)
        epoch_records=[]
        for i,raw in enumerate(physical,1):
            rec=strict_json_loads(raw.decode("utf-8"))
            if rec.get("record_type")=="history_epoch":
                _decode_history_epoch_record(rec,i,current_path.parent)
                epoch_records.append(rec)
        if not epoch_records:
            return False
    except Exception:
        return False
    newevents=current_events[parent_event_count:]
    proofs=[e for e in newevents if isinstance(e,dict) and e.get("type")=="history_epoch_compaction"]
    if not proofs:
        return False
    for e in proofs:
        if e.get("zero_time") is not True:
            continue
        changes=e.get("changes") or []
        if isinstance(changes,dict):
            changes=[changes]
        if any(isinstance(c,dict) and c.get("target")=="events.jsonl" and c.get("action")=="physical_epoch_compaction_logical_stream_unchanged" for c in changes):
            return True
    return False


def _history_text_migration_allowed(parent_base: Path, base: Path, parent_raw: list, current_raw: list, current_events: list, parent_event_count: int, world_text: str) -> bool:
    """Permit exactly one semantic-preserving canonical text migration of prior event bytes.

    No prior event may change except by TEXT_CANONICAL_REPLACEMENTS, and a new explicit
    text_charset_migration event plus the permanent WORLD rule must be present.
    """
    if not text_policy_active(world_text):
        return False
    if len(current_raw) < len(parent_raw):
        return False
    newevents=current_events[parent_event_count:]
    if not any(isinstance(e,dict) and e.get("type")==TEXT_POLICY_EVENT_TYPE for e in newevents):
        return False
    for old, new in zip(parent_raw, current_raw[:len(parent_raw)]):
        try:
            expected=canonicalize_game_text(old.decode("utf-8")).encode("utf-8")
        except Exception:
            return False
        if new != expected:
            return False
    return True


class EngineError(RuntimeError):
    pass


class TransactionNotCommitted(EngineError):
    def __init__(self,save_set_id,reason):
        self.save_set_id=save_set_id
        super().__init__('TRANSACTION_NOT_COMMITTED:'+str(reason))


class ForkError(EngineError):
    pass


class CorruptedLatestError(EngineError):
    def __init__(self, version, candidates):
        self.version = version
        self.candidates = list(candidates)
        super().__init__(f"CORRUPTED_LATEST_SNAPSHOT {version}: {self.candidates}")


_LOCK_DEPTH = threading.local()

@contextmanager
def engine_lock(root: Path = ROOT, exclusive: bool = True):
    """Process-level advisory lock for guard/stage/save. Nested calls in one process are safe."""
    depths = getattr(_LOCK_DEPTH, 'roots', None)
    if depths is None:
        depths = {}; _LOCK_DEPTH.roots = depths
    key = str(Path(root).resolve())
    if key in depths:
        if exclusive and not depths[key][1]:
            raise EngineError('LOCK_UPGRADE_FORBIDDEN')
        depths[key][0] += 1
        try:
            yield
        finally:
            depths[key][0] -= 1
        return
    root.mkdir(parents=True, exist_ok=True)
    lp = root / ".game_engine.lock"
    fd = os.open(lp, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        depths[key] = [1, exclusive]
        yield
    finally:
        del depths[key]
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_object_pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError(f"duplicate JSON key: {k}")
        out[k]=v
    return out

def _reject_json_constant(value):
    raise ValueError(f"non-finite/non-standard JSON numeric constant: {value}")

def strict_json_loads(text:str):
    return json.loads(text,object_pairs_hook=_strict_object_pairs,parse_constant=_reject_json_constant)

def strict_json_load(path:Path):
    return strict_json_loads(path.read_text(encoding="utf-8"))

def _cli_json_input(raw: str, label: str = "INPUT") -> dict:
    """Parse inline JSON, @path, or an existing plain file path.

    Inline JSON is detected before any filesystem probe.  This avoids Android/Linux
    ENAMETOOLONG failures when a normal battle payload is longer than a pathname.
    """
    text=str(raw or "").strip()
    if not text:
        raise EngineError(f"{label}_EMPTY")
    try:
        if text[0] in "{[":
            obj=strict_json_loads(text)
        elif text.startswith("@"):
            p=Path(text[1:])
            if not p.is_file():
                raise EngineError(f"{label}_FILE_NOT_FOUND:{p}")
            obj=strict_json_load(p)
        else:
            p=Path(text)
            try:
                is_file=p.is_file()
            except OSError:
                is_file=False
            if is_file:
                obj=strict_json_load(p)
            else:
                obj=strict_json_loads(text)
    except EngineError:
        raise
    except (json.JSONDecodeError, OSError, UnicodeError, ValueError) as exc:
        raise EngineError(f"{label}_JSON_INVALID:{type(exc).__name__}:{exc}") from exc
    if label=='QUERY_BATCH' and isinstance(obj,list):return obj
    if not isinstance(obj,dict):
        raise EngineError(f"{label}_JSON_OBJECT_REQUIRED:{type(obj).__name__}")
    return obj


def bundle_hash(hashes: Dict[str, str]) -> str:
    payload = "".join(f"{fn}\t{hashes[fn]}\n" for fn in SRC_ORDER).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_version(text: str) -> Tuple[int, int]:
    m = re.fullmatch(r"V(\d+)\.(\d+)", str(text).strip())
    if not m:
        raise EngineError(f"invalid version: {text}")
    return int(m.group(1)), int(m.group(2))


def version_text(ver: Tuple[int, int]) -> str:
    return f"V{ver[0]}.{ver[1]}"


def semver_tuple(text: Optional[str]) -> Tuple[int,int,int]:
    m=re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", str(text or "").strip())
    return (int(m.group(1)),int(m.group(2)),int(m.group(3) or 0)) if m else (0,0,0)


def parse_iso(text: Optional[str]) -> Optional[dt.datetime]:
    """Parse the canonical in-game timestamp format only (naive YYYY-MM-DDTHH:MM:SS)."""
    if not text or not isinstance(text, str) or not STRICT_GAME_TIME_RE.fullmatch(text.strip()):
        return None
    try:
        return dt.datetime.strptime(text.strip(), "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return None


def _world_revision_from_text(text: str) -> Optional[str]:
    m=re.search(r"^> \*\*设定修订号\*\*：([^\n]+)$",text,re.M)
    return m.group(1).strip() if m else None


def _index_world_revision_from_text(text: str) -> Optional[str]:
    m=re.search(r"^> \*\*WORLD设定修订号\*\*：([^（\n]+)(?:（派生自WORLD）)?\s*$",text,re.M)
    return m.group(1).strip() if m else None


def _sync_index_world_revision(index_text: str, world_text: str) -> str:
    rev=_world_revision_from_text(world_text)
    if not rev:return index_text
    return _replace_or_insert(index_text,r"^> \*\*WORLD设定修订号\*\*：.*$",f"> **WORLD设定修订号**：{rev}（派生自WORLD）")




def authoritative_event_stage(event:dict):
    """Processing phase; legacy status is a fallback only when phase is absent.

    event.status is lifecycle, event.phase is event processing, task.phase is task
    processing. A task's current_event_stage mirrors the event, not its lifecycle.
    """
    if not isinstance(event,dict): raise EngineError('EVENT_STAGE_OBJECT_REQUIRED')
    return event.get('phase') or event.get('status')

