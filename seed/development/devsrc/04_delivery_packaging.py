# === VOYAGER_DEV_MODULE: delivery_packaging ===
def project_source_check(base: Path = ROOT, strict_fileset: bool = True) -> dict:
    """Verify a cold-start-capable Project source. Project delivery is always exactly 7 files.

    Authority files must match INDEX, and top-level versioned tool files must contain
    exactly one bound GAME_ENGINE plus exactly one bound SAVE_GUARD. A/B slot files,
    SAVESETs and .runtime are local transaction/recovery infrastructure and are never
    Project source requirements, even when the committed INDEX records A/B storage.
    """
    base=base.resolve();errors=[];auth=validate_authority_set(base)
    if auth is None:
        return {"status":"FAIL","base":str(base),"errors":["AUTHORITY_MANIFEST_INVALID"]}
    idx=auth.get("index") or {};ev=str(idx.get("engine_version") or "").strip();eh=idx.get("engine_sha256");gh=idx.get("save_guard_sha256")
    ep=base/f"GAME_ENGINE_v{ev}.py"
    engine_files=sorted(p.name for p in base.glob("GAME_ENGINE_v*.py") if p.is_file())
    if engine_files!=[ep.name]:errors.append(f"PROJECT_ENGINE_FILESET_INVALID:expected={[ep.name]}:actual={engine_files}")
    if not ep.is_file():errors.append(f"PROJECT_ENGINE_MISSING:{ep.name}")
    else:
        actual=sha256_file(ep)
        if actual!=eh:errors.append(f"PROJECT_ENGINE_HASH_MISMATCH:{ep.name}:expected={eh}:actual={actual}")
        try:
            txt=ep.read_text(encoding="utf-8",errors="strict")[:16000]
            vm=re.search(r'^ENGINE_VERSION\s*=\s*["\']([^"\']+)["\']',txt,re.M);mm=re.search(r'^ENGINE_MAGIC\s*=\s*["\']VOYAGER_FLEET_GAME_ENGINE["\']',txt,re.M)
            if not vm or vm.group(1)!=ev or not mm:errors.append(f"PROJECT_ENGINE_IDENTITY_INVALID:{ep.name}")
            compile(ep.read_bytes(),str(ep),'exec')
        except Exception as exc:errors.append(f"PROJECT_ENGINE_INVALID:{ep.name}:{type(exc).__name__}:{exc}")
    guard_files=sorted(p.name for p in base.glob("SAVE_GUARD_v*.py") if p.is_file())
    guard_matches=[];expected_guard_name=None
    for name in guard_files:
        gp=base/name
        try:
            gv=_guard_source_version(gp)
            if gv>(0,0,0):
                embedded_name=f"SAVE_GUARD_v{gv[0]}.{gv[1]}.{gv[2]}.py"
                if len(guard_files)==1:expected_guard_name=embedded_name
                if name!=embedded_name:errors.append(f"PROJECT_GUARD_FILENAME_VERSION_MISMATCH:file={name}:embedded={embedded_name}")
            if sha256_file(gp)==gh and _guard_protocol(gp)==GUARD_PROTOCOL:
                compile(gp.read_bytes(),str(gp),'exec');guard_matches.append(gp.name)
        except Exception: pass
    if strict_fileset and len(guard_files)!=1:errors.append(f"PROJECT_GUARD_FILESET_INVALID:expected_exactly_one:actual={guard_files}")
    if len(guard_matches)!=1:errors.append(f"PROJECT_GUARD_HASH_MISSING_OR_AMBIGUOUS:expected={gh}:matches={guard_matches}")
    expected_files=set(AUTH_FILES+[ep.name])
    if expected_guard_name:expected_files.add(expected_guard_name)
    elif len(guard_files)==1:expected_files.add(guard_files[0])
    all_visible_files=sorted(p.name for p in base.iterdir() if p.is_file() and not p.name.startswith('.')) if base.is_dir() else []
    # Local A/B transaction files are runtime infrastructure, not Project source candidates.
    runtime_infra_files={AB_ACTIVE_FILE,*AB_SLOT_FILES.values()}
    visible_files=sorted(x for x in all_visible_files if x not in runtime_infra_files)
    if strict_fileset and set(visible_files)!=expected_files:
        errors.append(f"PROJECT_FILESET_INVALID:expected={sorted(expected_files)}:actual={visible_files}")
    elif not strict_fileset and not expected_files.issubset(set(visible_files)):
        errors.append(f"RUNTIME_REQUIRED_FILESET_MISSING:required={sorted(expected_files)}:actual={visible_files}")
    return {"status":"FAIL" if errors else "PASS","mode":"project" if strict_fileset else "runtime","base":str(base),"save_set_id":auth.get("save_set_id"),"engine_version":ev,"engine_file":ep.name,"guard_files":guard_files,"extra_files":sorted(set(visible_files)-expected_files),"ignored_runtime_files":sorted(set(all_visible_files)&runtime_infra_files),"errors":errors}


def _v130_layer_build_project_source_package_01(snapshot: dict, root: Path = ROOT) -> dict:
    """Build an immutable seven-file Project delivery.

    This avoids handing out mutable root paths that can later be overwritten by a
    Project source refresh. The package is derived only from committed snapshot bytes
    and exact tool hashes bound by that snapshot's INDEX/COMMIT envelope. A/B pointer
    and slot files remain local recovery infrastructure and are intentionally excluded.
    """
    if not isinstance(snapshot,dict) or not snapshot.get("dir"):raise EngineError("PROJECT_PACKAGE_SNAPSHOT_INVALID")
    snap=validate_game_snapshot_available(Path(snapshot["dir"]),root)
    if snap is None:raise EngineError("PROJECT_PACKAGE_SNAPSHOT_VERIFY_FAILED")
    idx=snap.get("index") or {};ev=str(idx.get("engine_version") or "");eh=idx.get("engine_sha256");gh=idx.get("save_guard_sha256")
    engine=_find_tool_candidate(root,snap,"engine",eh);guardp=_find_tool_candidate(root,snap,"guard",gh)
    if engine is None or guardp is None:raise EngineError("PROJECT_PACKAGE_BOUND_TOOLS_MISSING")
    gv=_guard_source_version(guardp)
    if gv<=(0,0,0):raise EngineError("PROJECT_PACKAGE_GUARD_VERSION_INVALID")
    guard_name=f"SAVE_GUARD_v{gv[0]}.{gv[1]}.{gv[2]}.py";engine_name=f"GAME_ENGINE_v{ev}.py"
    stem=f"{version_text(snap['version'])}_PROJECT_SOURCE_{snap['bundle'][:16]}";final_dir=root/stem
    zip_dir=root/".runtime"/"packages";zip_dir.mkdir(parents=True,exist_ok=True)
    final_zip=zip_dir/f"{stem}.zip"
    tmp=Path(tempfile.mkdtemp(prefix=f".{stem}.package.",dir=str(root)));zip_tmp=zip_dir/f".{stem}.{os.getpid()}.zip.tmp"
    try:
        for fn in AUTH_FILES:shutil.copy2(snap["dir"]/fn,tmp/fn)
        shutil.copy2(engine,tmp/engine_name);shutil.copy2(guardp,tmp/guard_name)
        names=AUTH_FILES+[engine_name,guard_name]
        sc=project_source_check(tmp)
        if sc.get("status")!="PASS":raise EngineError("PROJECT_PACKAGE_SOURCECHECK_FAILED: "+"; ".join(sc.get("errors",[])))
        with zipfile.ZipFile(zip_tmp,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for name in names:z.write(tmp/name,arcname=name)
        with zipfile.ZipFile(zip_tmp,"r") as z:
            if sorted(z.namelist())!=sorted(names):raise EngineError("PROJECT_PACKAGE_ZIP_FILESET_MISMATCH")
            for name in names:
                if sha256_bytes(z.read(name))!=sha256_file(tmp/name):raise EngineError(f"PROJECT_PACKAGE_ZIP_HASH_MISMATCH:{name}")
        if final_dir.exists():writable_tree(final_dir);shutil.rmtree(final_dir)
        os.replace(tmp,final_dir);readonly_tree(final_dir)
        if final_zip.exists():
            try:final_zip.chmod(0o644)
            except OSError:pass
            final_zip.unlink()
        os.replace(zip_tmp,final_zip)
        try:
            final_zip.chmod(0o444)
        except OSError:
            pass
        final_sc = project_source_check(final_dir)
        if final_sc.get("status") != "PASS":
            raise EngineError("PROJECT_PACKAGE_FINAL_SOURCECHECK_FAILED: " + "; ".join(final_sc.get("errors", [])))
        with zipfile.ZipFile(final_zip, "r") as z:
            if len(z.namelist()) != len(names) or len(set(z.namelist())) != len(names):
                raise EngineError("PROJECT_PACKAGE_FINAL_ZIP_COUNT_INVALID")
            for name in z.namelist():
                if not (final_dir / name).is_file() or sha256_bytes(z.read(name)) != sha256_file(final_dir / name):
                    raise EngineError(f"PROJECT_PACKAGE_FINAL_ZIP_HASH_MISMATCH:{name}")
        return {
            "status": "READY",
            "save_set_id": snap["save_set_id"],
            "directory": str(final_dir),
            "zip": str(final_zip),
            "files": names,
            "sourcecheck": final_sc,
            "zip_sha256": sha256_file(final_zip),
            "verified_entry_count": len(names),
        }
    finally:
        if tmp.exists():shutil.rmtree(tmp,ignore_errors=True)
        try:
            if zip_tmp.exists():zip_tmp.unlink()
        except OSError:pass


_VPACK_BOOTSTRAP_B64 = 'IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwojIC0qLSBjb2Rpbmc6IHV0Zi04IC0qLQoiIiJWb3lhZ2VyIFByb2plY3Qtc291cmNlIGNvbXBhdGliaWxpdHkgZW50cnlwb2ludC4KClRoZSBQcm9qZWN0IGluc3RydWN0aW9uIGludGVudGlvbmFsbHkga2VlcHMgdGhlIGhpc3RvcmljYWwgZmlsZW5hbWUKU0FWRV9HVUFSRF92Mi40LjEucHkuIFRoaXMgZmlsZSBpcyBub3QgdGhlIGF1dGhvcml0YXRpdmUgZ2FtZSBTQVZFX0dVQVJELgpJdCB2YWxpZGF0ZXMgb25lIGltbXV0YWJsZSBWT1lBR0VSX1NPVVJDRV8qLnppcC8udnBhY2ssIG1hdGVyaWFsaXplcyB0aGUgZXhhY3Qgc2V2ZW4KYm91bmQgc291cmNlIGZpbGVzIHdoZW4gbmVlZGVkLCB0aGVuIGRlbGVnYXRlcyAtLXJlc3VtZSB0byB0aGUgU0FWRV9HVUFSRCB2ZXJzaW9uCmJvdW5kIGluc2lkZSB0aGF0IHBhY2svY3VycmVudCBJTkRFWC4KIiIiCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppbXBvcnQgaGFzaGxpYixpbXBvcnRsaWIudXRpbCxqc29uLG9zLHJlLHN5cyx6aXBmaWxlLHV1aWQKIyBEZWZhdWx0IHRvIHRoZSBsYXVuY2hlcidzIG93biBQcm9qZWN0IGRpcmVjdG9yeSBzbyBhIHR3by1maWxlIGNvbGQgc3RhcnQgaXMKIyBzZWxmLWNvbnRhaW5lZC4gVk9ZQUdFUl9ST09UIHJlbWFpbnMgYW4gZXhwbGljaXQgb3ZlcnJpZGUgZm9yIG1hbmFnZWQgcnVudGltZXMuClJPT1Q9UGF0aChvcy5lbnZpcm9uLmdldCgnVk9ZQUdFUl9ST09UJykgb3IgUGF0aChfX2ZpbGVfXykucmVzb2x2ZSgpLnBhcmVudCkucmVzb2x2ZSgpCkJPT1RTVFJBUF9GT1JNQVQ9J1ZPWUFHRVJfVlBBQ0tfQk9PVFNUUkFQX1YxJwpQQUNLX0ZPUk1BVD0nVk9ZQUdFUl9TT1VSQ0VfVlBBQ0tfVjEnCkFVVEhfRklMRVM9KCdJTkRFWC5tZCcsJ1dPUkxELm1kJywnSElTVE9SWS5qc29ubCcsJ1RBU0tTLmpzb24nLCdTVEFURS5qc29uJykKU1JDX09SREVSPSgnV09STEQubWQnLCdISVNUT1JZLmpzb25sJywnVEFTS1MuanNvbicsJ1NUQVRFLmpzb24nKQoKZGVmIF9zaGFfYnl0ZXMoYik6cmV0dXJuIGhhc2hsaWIuc2hhMjU2KGIpLmhleGRpZ2VzdCgpCmRlZiBfc2hhX2ZpbGUocCk6CiAgICBoPWhhc2hsaWIuc2hhMjU2KCkKICAgIHdpdGggcC5vcGVuKCdyYicpIGFzIGY6CiAgICAgICAgZm9yIGIgaW4gaXRlcihsYW1iZGE6Zi5yZWFkKDEwMjQqMTAyNCksYicnKTpoLnVwZGF0ZShiKQogICAgcmV0dXJuIGguaGV4ZGlnZXN0KCkKZGVmIF9idW5kbGUoaCk6cmV0dXJuIGhhc2hsaWIuc2hhMjU2KCcnLmpvaW4oZid7bn1cdHtoW25dfVxuJyBmb3IgbiBpbiBTUkNfT1JERVIpLmVuY29kZSgpKS5oZXhkaWdlc3QoKQpkZWYgX29uZSh0ZXh0LHBhdCk6CiAgICB4PXJlLmZpbmRhbGwocGF0LHRleHQscmUuTSk7cmV0dXJuIHhbMF0gaWYgbGVuKHgpPT0xIGVsc2UgTm9uZQoKZGVmIF9pbmRleF9pZGVudGl0eShyYXcpOgogICAgdGV4dD1yYXdbJ0lOREVYLm1kJ10uZGVjb2RlKCd1dGYtOCcsJ3N0cmljdCcpCiAgICBtbT1yZS5maW5kYWxsKHInXj4gXCpcKuW9k+WJjeWtmOaho+eJiOacrFwqXCrvvJpWKFxkKylcLihcZCspJCcsdGV4dCxyZS5NKQogICAgaWYgbGVuKG1tKSE9MTpyYWlzZSBSdW50aW1lRXJyb3IoJ0lOREVYX1ZFUlNJT05fSU5WQUxJRCcpCiAgICB2ZXI9KGludChtbVswXVswXSksaW50KG1tWzBdWzFdKSk7ZGVjbD17fQogICAgZm9yIGZuIGluIFNSQ19PUkRFUjoKICAgICAgICBoPV9vbmUodGV4dCxyZideLSBge3JlLmVzY2FwZShmbil9YO+8mmAoWzAtOWEtZl17ezY0fX0pYCQnKQogICAgICAgIGlmIG5vdCBoOnJhaXNlIFJ1bnRpbWVFcnJvcihmJ0lOREVYX1NPVVJDRV9IQVNIX01JU1NJTkc6e2ZufScpCiAgICAgICAgZGVjbFtmbl09aAogICAgYWN0dWFsPXtmbjpfc2hhX2J5dGVzKHJhd1tmbl0pIGZvciBmbiBpbiBTUkNfT1JERVJ9O2J1bmRsZT1fYnVuZGxlKGFjdHVhbCkKICAgIHNpZD1mJ1NBVkVTRVQtVnt2ZXJbMF19Lnt2ZXJbMV19LXtidW5kbGVbOjE2XX0nCiAgICBpZiBkZWNsIT1hY3R1YWw6cmFpc2UgUnVudGltZUVycm9yKCdJTkRFWF9TT1VSQ0VfSEFTSF9NSVNNQVRDSCcpCiAgICBpZiBfb25lKHRleHQscideLSBgYnVuZGxlX3NoYTI1NmDvvJpgKFswLTlhLWZdezY0fSlgJCcpIT1idW5kbGU6cmFpc2UgUnVudGltZUVycm9yKCdJTkRFWF9CVU5ETEVfTUlTTUFUQ0gnKQogICAgaWYgX29uZSh0ZXh0LHInXi0gYHNhdmVfc2V0X2lkYO+8mmAoW15gXSspYCQnKSE9c2lkOnJhaXNlIFJ1bnRpbWVFcnJvcignSU5ERVhfU0FWRVNFVF9NSVNNQVRDSCcpCiAgICBldj1fb25lKHRleHQscideLSBgZ2FtZV9lbmdpbmVfdmVyc2lvbmDvvJpgKFteYF0rKWAkJyk7ZWg9X29uZSh0ZXh0LHInXi0gYGdhbWVfZW5naW5lX3NoYTI1NmDvvJpgKFswLTlhLWZdezY0fSlgJCcpO2doPV9vbmUodGV4dCxyJ14tIGBzYXZlX2d1YXJkX3NoYTI1NmDvvJpgKFswLTlhLWZdezY0fSlgJCcpCiAgICBpZiBub3QgZXYgb3Igbm90IGVoIG9yIG5vdCBnaDpyYWlzZSBSdW50aW1lRXJyb3IoJ0lOREVYX1RPT0xfQklORElOR19NSVNTSU5HJykKICAgIHJldHVybiB2ZXIsc2lkLGV2LGVoLGdoCgpkZWYgX2xvYWRfcGFjaygpOgogICAgcGFja3M9c29ydGVkKFtwIGZvciBwYXQgaW4gKCdWT1lBR0VSX1NPVVJDRV8qLnppcCcsJ1ZPWUFHRVJfU09VUkNFXyoudnBhY2snKSBmb3IgcCBpbiBST09ULmdsb2IocGF0KSBpZiBwLmlzX2ZpbGUoKV0pCiAgICBpZiBsZW4ocGFja3MpIT0xOnJhaXNlIFJ1bnRpbWVFcnJvcihmJ1ZQQUNLX0NPVU5UX0lOVkFMSUQ6e2xlbihwYWNrcyl9JykKICAgIHBhY2s9cGFja3NbMF0KICAgIHdpdGggemlwZmlsZS5aaXBGaWxlKHBhY2ssJ3InKSBhcyB6OgogICAgICAgIG5hbWVzPXoubmFtZWxpc3QoKQogICAgICAgIGlmIGxlbihuYW1lcykhPWxlbihzZXQobmFtZXMpKSBvciBhbnkoJy8nIGluIG4gb3IgJ1xcJyBpbiBuIG9yIG4uc3RhcnRzd2l0aCgnLicpIGZvciBuIGluIG5hbWVzKTpyYWlzZSBSdW50aW1lRXJyb3IoJ1ZQQUNLX01FTUJFUl9QQVRIX0lOVkFMSUQnKQogICAgICAgIGlmICdQQUNLLmpzb24nIG5vdCBpbiBuYW1lczpyYWlzZSBSdW50aW1lRXJyb3IoJ1ZQQUNLX01BTklGRVNUX01JU1NJTkcnKQogICAgICAgIG1hbmlmZXN0PWpzb24ubG9hZHMoei5yZWFkKCdQQUNLLmpzb24nKS5kZWNvZGUoJ3V0Zi04Jywnc3RyaWN0JykpCiAgICAgICAgaWYgbWFuaWZlc3QuZ2V0KCdmb3JtYXQnKSE9UEFDS19GT1JNQVQ6cmFpc2UgUnVudGltZUVycm9yKCdWUEFDS19GT1JNQVRfSU5WQUxJRCcpCiAgICAgICAgbWVtYmVycz1tYW5pZmVzdC5nZXQoJ21lbWJlcnMnKSBvciB7fQogICAgICAgIGlmIHNldChuYW1lcykhPXNldChtZW1iZXJzKXx7J1BBQ0suanNvbid9OnJhaXNlIFJ1bnRpbWVFcnJvcignVlBBQ0tfTUVNQkVSU0VUX0lOVkFMSUQnKQogICAgICAgIGlmIG5vdCBzZXQoQVVUSF9GSUxFUykuaXNzdWJzZXQobWVtYmVycyk6cmFpc2UgUnVudGltZUVycm9yKCdWUEFDS19BVVRIT1JJVFlfTUlTU0lORycpCiAgICAgICAgZWY9c3RyKG1hbmlmZXN0LmdldCgnZW5naW5lX2ZpbGUnKSBvciAnJyk7Z2Y9c3RyKG1hbmlmZXN0LmdldCgnZ3VhcmRfZmlsZScpIG9yICcnKQogICAgICAgIGlmIGVmIG5vdCBpbiBtZW1iZXJzIG9yIGdmIG5vdCBpbiBtZW1iZXJzOnJhaXNlIFJ1bnRpbWVFcnJvcignVlBBQ0tfVE9PTF9NSVNTSU5HJykKICAgICAgICByYXc9e246ei5yZWFkKG4pIGZvciBuIGluIG1lbWJlcnN9CiAgICBmb3IgbixoIGluIG1lbWJlcnMuaXRlbXMoKToKICAgICAgICBpZiBub3QgcmUuZnVsbG1hdGNoKHInWzAtOWEtZl17NjR9JyxzdHIoaCkpIG9yIF9zaGFfYnl0ZXMocmF3W25dKSE9aDpyYWlzZSBSdW50aW1lRXJyb3IoZidWUEFDS19IQVNIX01JU01BVENIOntufScpCiAgICB2ZXIsc2lkLGV2LGVoLGdoPV9pbmRleF9pZGVudGl0eShyYXcpCiAgICBpZiBtYW5pZmVzdC5nZXQoJ3NhdmVfc2V0X2lkJykhPXNpZCBvciBtYW5pZmVzdC5nZXQoJ3NhdmVfdmVyc2lvbicpIT1mJ1Z7dmVyWzBdfS57dmVyWzFdfSc6cmFpc2UgUnVudGltZUVycm9yKCdWUEFDS19JREVOVElUWV9NSVNNQVRDSCcpCiAgICBpZiBtYW5pZmVzdC5nZXQoJ2VuZ2luZV9zaGEyNTYnKSE9ZWggb3IgbWFuaWZlc3QuZ2V0KCdndWFyZF9zaGEyNTYnKSE9Z2g6cmFpc2UgUnVudGltZUVycm9yKCdWUEFDS19UT09MX0JJTkRJTkdfTUlTTUFUQ0gnKQogICAgaWYgX3NoYV9ieXRlcyhyYXdbZWZdKSE9ZWggb3IgX3NoYV9ieXRlcyhyYXdbZ2ZdKSE9Z2g6cmFpc2UgUnVudGltZUVycm9yKCdWUEFDS19CT1VORF9UT09MX0hBU0hfTUlTTUFUQ0gnKQogICAgaWYgbm90IHJlLmZ1bGxtYXRjaChyZidHQU1FX0VOR0lORV92e3JlLmVzY2FwZShldil9XC5weScsZWYpOnJhaXNlIFJ1bnRpbWVFcnJvcignVlBBQ0tfRU5HSU5FX0ZJTEVOQU1FX01JU01BVENIJykKICAgIHJldHVybiBwYWNrLG1hbmlmZXN0LHJhdyx2ZXIsc2lkCgpkZWYgX3Jvb3RfaWRlbnRpdHkoKToKICAgIHRyeToKICAgICAgICByYXc9e2ZuOihST09UL2ZuKS5yZWFkX2J5dGVzKCkgZm9yIGZuIGluIEFVVEhfRklMRVN9CiAgICAgICAgdmVyLHNpZCwqXz0gX2luZGV4X2lkZW50aXR5KHJhdyk7cmV0dXJuIHZlcixzaWQKICAgIGV4Y2VwdCBFeGNlcHRpb246cmV0dXJuIE5vbmUKCmRlZiBfbWF0ZXJpYWxpemUobWFuaWZlc3QscmF3LHZlcixzaWQpOgogICAgY3VyPV9yb290X2lkZW50aXR5KCkKICAgIGlmIGN1cjoKICAgICAgICBpZiBjdXJbMF0+dmVyOnJldHVybiAnS0VFUF9ORVdFUl9SVU5USU1FJwogICAgICAgIGlmIGN1clswXT09dmVyIGFuZCBjdXJbMV0hPXNpZDpyYWlzZSBSdW50aW1lRXJyb3IoJ1ZQQUNLX1NBTUVfVkVSU0lPTl9GT1JLJykKICAgICAgICBpZiBjdXJbMF09PXZlciBhbmQgY3VyWzFdPT1zaWQ6CiAgICAgICAgICAgIG1pc3Npbmc9W24gZm9yIG4saCBpbiBtYW5pZmVzdFsnbWVtYmVycyddLml0ZW1zKCkgaWYgbm90IChST09UL24pLmlzX2ZpbGUoKSBvciBfc2hhX2ZpbGUoUk9PVC9uKSE9aF0KICAgICAgICAgICAgaWYgbm90IG1pc3Npbmc6cmV0dXJuICdBTFJFQURZX01BVEVSSUFMSVpFRCcKICAgICMgQWxsIGJ5dGVzIGhhdmUgYWxyZWFkeSBiZWVuIGZ1bGx5IHZlcmlmaWVkLiBFYWNoIGRlc3RpbmF0aW9uIGlzIHJlcGxhY2VkIGF0b21pY2FsbHkuCiAgICBST09ULm1rZGlyKHBhcmVudHM9VHJ1ZSxleGlzdF9vaz1UcnVlKQogICAgZm9yIG4sYiBpbiByYXcuaXRlbXMoKToKICAgICAgICB0bXA9Uk9PVC9mJy57bn0udnBhY2sue29zLmdldHBpZCgpfS57dXVpZC51dWlkNCgpLmhleFs6Nl19LnRtcCc7dG1wLndyaXRlX2J5dGVzKGIpO29zLnJlcGxhY2UodG1wLFJPT1QvbikKICAgIGlmIF9yb290X2lkZW50aXR5KCkhPSh2ZXIsc2lkKTpyYWlzZSBSdW50aW1lRXJyb3IoJ1ZQQUNLX1BPU1RfTUFURVJJQUxJWkVfVkVSSUZZX0ZBSUxFRCcpCiAgICByZXR1cm4gJ01BVEVSSUFMSVpFRCcKCmRlZiBfYm91bmRfaW5uZXJfZ3VhcmQoKToKICAgIHJhdz17Zm46KFJPT1QvZm4pLnJlYWRfYnl0ZXMoKSBmb3IgZm4gaW4gQVVUSF9GSUxFU307XyxfLF8sXyxnaD1faW5kZXhfaWRlbnRpdHkocmF3KQogICAgbWF0Y2hlcz1bXQogICAgZm9yIHAgaW4gbGlzdChST09ULmdsb2IoJ1NBVkVfR1VBUkRfdioucHknKSkrW1JPT1QvJy5zYXZlX2d1YXJkLnB5J106CiAgICAgICAgaWYgcC5pc19maWxlKCk6CiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIGlmIF9zaGFfZmlsZShwKT09Z2g6bWF0Y2hlcy5hcHBlbmQocCkKICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjpwYXNzCiAgICB1bmlxPVtdO3NlZW49c2V0KCkKICAgIGZvciBwIGluIG1hdGNoZXM6CiAgICAgICAgaD1fc2hhX2ZpbGUocCkKICAgICAgICBpZiBoIG5vdCBpbiBzZWVuOnNlZW4uYWRkKGgpO3VuaXEuYXBwZW5kKHApCiAgICBpZiBsZW4odW5pcSkhPTE6cmFpc2UgUnVudGltZUVycm9yKGYnQk9VTkRfSU5ORVJfR1VBUkRfTk9UX1VOSVFVRTp7W3AubmFtZSBmb3IgcCBpbiB1bmlxXX0nKQogICAgcmV0dXJuIHVuaXFbMF0KCmRlZiBtYWluKGFyZ3Y9Tm9uZSk6CiAgICBhcmd2PWxpc3Qoc3lzLmFyZ3ZbMTpdIGlmIGFyZ3YgaXMgTm9uZSBlbHNlIGFyZ3YpCiAgICBpZiBhcmd2PT1bJy0tdmVyc2lvbi1pbmZvJ106CiAgICAgICAgcHJpbnQoanNvbi5kdW1wcyh7J2Jvb3RzdHJhcF9mb3JtYXQnOkJPT1RTVFJBUF9GT1JNQVQsJ3RyYW5zcG9ydF9mb3JtYXQnOlBBQ0tfRk9STUFULCdjb21wYXRpYmlsaXR5X2ZpbGVuYW1lJzonU0FWRV9HVUFSRF92Mi40LjEucHknfSxlbnN1cmVfYXNjaWk9RmFsc2UsaW5kZW50PTIpKTtyZXR1cm4gMAogICAgaWYgYXJndiE9WyctLXJlc3VtZSddOgogICAgICAgIHN5cy5zdGRlcnIud3JpdGUoJ3VzYWdlOiBTQVZFX0dVQVJEX3YyLjQuMS5weSAtLXJlc3VtZVxuJyk7cmV0dXJuIDIKICAgIHRyeToKICAgICAgICBfLG1hbmlmZXN0LHJhdyx2ZXIsc2lkPV9sb2FkX3BhY2soKTtfbWF0ZXJpYWxpemUobWFuaWZlc3QscmF3LHZlcixzaWQpO2dwPV9ib3VuZF9pbm5lcl9ndWFyZCgpCiAgICAgICAgIyBUaGUgYXV0aG9yaXRhdGl2ZSBpbm5lciBHdWFyZCByZXNvbHZlcyBST09UIGF0IGltcG9ydCB0aW1lLiBQaW4gaXQgdG8gdGhlCiAgICAgICAgIyBzYW1lIGRpcmVjdG9yeSBzZWxlY3RlZCBieSB0aGlzIGJvb3RzdHJhcDsgb3RoZXJ3aXNlIGFuIGlzb2xhdGVkIHR3by1maWxlCiAgICAgICAgIyBsYXVuY2ggY2FuIGFjY2lkZW50YWxseSBhdHRhY2ggdG8gYSBwcmUtZXhpc3RpbmcgL21udC9kYXRhIHJ1bnRpbWUuCiAgICAgICAgb2xkX3Jvb3Q9b3MuZW52aXJvbi5nZXQoJ1ZPWUFHRVJfUk9PVCcpO29zLmVudmlyb25bJ1ZPWUFHRVJfUk9PVCddPXN0cihST09UKQogICAgICAgIHRyeToKICAgICAgICAgICAgbmFtZT1mJ192b3lhZ2VyX2JvdW5kX2d1YXJkX3t1dWlkLnV1aWQ0KCkuaGV4Wzo4XX0nO3NwZWM9aW1wb3J0bGliLnV0aWwuc3BlY19mcm9tX2ZpbGVfbG9jYXRpb24obmFtZSxzdHIoZ3ApKQogICAgICAgICAgICBpZiBzcGVjIGlzIE5vbmUgb3Igc3BlYy5sb2FkZXIgaXMgTm9uZTpyYWlzZSBSdW50aW1lRXJyb3IoJ0lOTkVSX0dVQVJEX0xPQURfRkFJTEVEJykKICAgICAgICAgICAgbW9kPWltcG9ydGxpYi51dGlsLm1vZHVsZV9mcm9tX3NwZWMoc3BlYyk7c3lzLm1vZHVsZXNbbmFtZV09bW9kO3NwZWMubG9hZGVyLmV4ZWNfbW9kdWxlKG1vZCkKICAgICAgICAgICAgdHJ5OnJldHVybiBpbnQobW9kLm1haW4oWyctLXJlc3VtZSddKSkKICAgICAgICAgICAgZmluYWxseTpzeXMubW9kdWxlcy5wb3AobmFtZSxOb25lKQogICAgICAgIGZpbmFsbHk6CiAgICAgICAgICAgIGlmIG9sZF9yb290IGlzIE5vbmU6b3MuZW52aXJvbi5wb3AoJ1ZPWUFHRVJfUk9PVCcsTm9uZSkKICAgICAgICAgICAgZWxzZTpvcy5lbnZpcm9uWydWT1lBR0VSX1JPT1QnXT1vbGRfcm9vdAogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOgogICAgICAgIHN5cy5zdGRlcnIud3JpdGUoZidWUEFDS19CT09UU1RSQVBfRkFJTEVEOnt0eXBlKGUpLl9fbmFtZV9ffTp7ZX1cbicpO3JldHVybiA1CmlmIF9fbmFtZV9fPT0nX19tYWluX18nOnJhaXNlIFN5c3RlbUV4aXQobWFpbigpKQo='

def _vpack_bootstrap_bytes()->bytes:
    try:return base64.b64decode(_VPACK_BOOTSTRAP_B64.encode('ascii'),validate=True)
    except Exception as exc:raise EngineError(f'VPACK_BOOTSTRAP_EMBED_INVALID:{exc}')

def build_vpack_source_package(snapshot:dict,root:Path=ROOT)->dict:
    """Build two-file Project transport: compatibility bootstrap + immutable VPACK.

    The VPACK contains the exact seven-file trusted source.  The outer bootstrap is only
    transport infrastructure and delegates to the SAVE_GUARD bound by INDEX after full
    member/hash/authority verification.  It is never a game authority file.
    """
    if not isinstance(snapshot,dict) or not snapshot.get('dir'):raise EngineError('VPACK_SNAPSHOT_INVALID')
    snap=validate_game_snapshot_available(Path(snapshot['dir']),root)
    if snap is None:raise EngineError('VPACK_SNAPSHOT_VERIFY_FAILED')
    idx=snap.get('index') or {};ev=str(idx.get('engine_version') or '');eh=idx.get('engine_sha256');gh=idx.get('save_guard_sha256')
    engine=_find_tool_candidate(root,snap,'engine',eh);guardp=_find_tool_candidate(root,snap,'guard',gh)
    if engine is None or guardp is None:raise EngineError('VPACK_BOUND_TOOLS_MISSING')
    gv=_guard_source_version(guardp)
    if gv<=(0,0,0):raise EngineError('VPACK_GUARD_VERSION_INVALID')
    engine_name=f'GAME_ENGINE_v{ev}.py';guard_name=f'SAVE_GUARD_v{gv[0]}.{gv[1]}.{gv[2]}.py'
    members={fn:sha256_file(snap['dir']/fn) for fn in AUTH_FILES};members[engine_name]=sha256_file(engine);members[guard_name]=sha256_file(guardp)
    parent_sid=((snap.get('commit') or {}).get('parent_save_set_id') or idx.get('parent_save_set_id'));receipt={'schema':'SOURCE_PUBLICATION_RECEIPT_V1','save_set_id':snap['save_set_id'],'parent_save_set_id':parent_sid,'bundle_sha256':snap.get('bundle'),'index_sha256':sha256_file(snap['dir']/'INDEX.md'),'engine_sha256':eh,'guard_sha256':gh};manifest={'format':VPACK_TRANSPORT_FORMAT,'save_set_id':snap['save_set_id'],'save_version':version_text(snap['version']),'parent_save_set_id':parent_sid,'publication_precondition_parent_save_set_id':parent_sid,'publication_receipt':receipt,'engine_file':engine_name,'guard_file':guard_name,'engine_sha256':eh,'guard_sha256':gh,'members':members}
    stem=f"VOYAGER_SOURCE_{version_text(snap['version'])}_{snap['bundle'][:16]}"
    outdir=root/'.runtime'/'packages'/f'{stem}_2FILE';outdir.mkdir(parents=True,exist_ok=True)
    vp=outdir/f'{stem}.zip';tmp=outdir/f'.{stem}.{os.getpid()}.tmp'
    if tmp.exists():tmp.unlink()
    with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        z.writestr('PACK.json',json.dumps(manifest,ensure_ascii=False,separators=(',',':'))+'\n')
        for fn in AUTH_FILES:z.write(snap['dir']/fn,fn)
        z.write(engine,engine_name);z.write(guardp,guard_name)
    with zipfile.ZipFile(tmp,'r') as z:
        names=z.namelist();expected=set(members)|{'PACK.json'}
        if set(names)!=expected or len(names)!=len(expected):raise EngineError('VPACK_MEMBERSET_VERIFY_FAILED')
        for n,h in members.items():
            if sha256_bytes(z.read(n))!=h:raise EngineError(f'VPACK_MEMBER_HASH_VERIFY_FAILED:{n}')
    if vp.exists():vp.chmod(0o644);vp.unlink()
    os.replace(tmp,vp);vp.chmod(0o444)
    bp=outdir/VPACK_BOOTSTRAP_FILENAME;bp.write_bytes(_vpack_bootstrap_bytes());bp.chmod(0o444)
    # Compile the compatibility entrypoint before publishing it.
    compile(bp.read_bytes(),str(bp),'exec')
    return {'status':'READY','format':VPACK_TRANSPORT_FORMAT,'save_set_id':snap['save_set_id'],'directory':str(outdir),'files':[VPACK_BOOTSTRAP_FILENAME,vp.name],'bootstrap':str(bp),'vpack':str(vp),'bootstrap_sha256':sha256_file(bp),'vpack_sha256':sha256_file(vp),'vpack_bytes':vp.stat().st_size,'embedded_member_count':len(members),'inner_engine_version':ev,'inner_guard_version':'.'.join(map(str,gv)),'parent_save_set_id':parent_sid,'publication_receipt':receipt,'note':'Project来源切换到2文件后仍由包内绑定Guard/Engine执行游戏恢复；外层2.4.1文件仅为兼容入口。'}

def vpack_transport_check(source_dir:Path)->dict:
    """Static fail-closed check for an already-built two-file transport directory.

    This intentionally mirrors the compatibility bootstrap's trust checks so a package
    cannot pass `vpackcheck` and then fail during the real cold-start identity gate.
    """
    source_dir=source_dir.resolve()
    packs=sorted([p for pat in ('VOYAGER_SOURCE_*.zip','VOYAGER_SOURCE_*.vpack') for p in source_dir.glob(pat) if p.is_file()]);errors=[]
    bootstrap_candidates=sorted([p for p in source_dir.glob('SAVE_GUARD_v*.py') if p.is_file() and _is_vpack_compat_bootstrap(p)])
    bp=bootstrap_candidates[0] if len(bootstrap_candidates)==1 else None
    if not bootstrap_candidates:errors.append('BOOTSTRAP_MISSING')
    elif len(bootstrap_candidates)!=1:errors.append(f'BOOTSTRAP_AMBIGUOUS:{[p.name for p in bootstrap_candidates]}')
    if bp is not None:
        try:
            braw=bp.read_bytes();compile(braw,str(bp),'exec')
            if braw!=_vpack_bootstrap_bytes():errors.append('BOOTSTRAP_NONCANONICAL')
        except Exception as ex:errors.append(f'BOOTSTRAP_INVALID:{type(ex).__name__}:{ex}')
    if len(packs)!=1:errors.append(f'VPACK_COUNT_INVALID:{len(packs)}')
    detail={}
    if len(packs)==1:
        try:
            with zipfile.ZipFile(packs[0],'r') as z:
                names=z.namelist()
                if len(names)!=len(set(names)):errors.append('VPACK_DUPLICATE_MEMBER')
                if any('/' in n or '\\' in n or n.startswith('.') for n in names):errors.append('VPACK_MEMBER_PATH_INVALID')
                if 'PACK.json' not in names:raise EngineError('VPACK_MANIFEST_MISSING')
                m=json.loads(z.read('PACK.json').decode('utf-8','strict'));members=m.get('members') or {}
                if not isinstance(members,dict):raise EngineError('VPACK_MEMBERS_INVALID')
                if m.get('format')!=VPACK_TRANSPORT_FORMAT:errors.append('VPACK_FORMAT_INVALID')
                if set(names)!=set(members)|{'PACK.json'} or len(names)!=len(members)+1:errors.append('VPACK_MEMBERSET_INVALID')
                if not set(AUTH_FILES).issubset(members):errors.append('VPACK_AUTHORITY_MISSING')
                ef=str(m.get('engine_file') or '');gf=str(m.get('guard_file') or '')
                if ef not in members or gf not in members:errors.append('VPACK_TOOL_MISSING')
                raw={}
                for n,h in members.items():
                    if not isinstance(n,str) or n not in names:
                        errors.append(f'VPACK_MEMBER_MISSING:{n}');continue
                    if not re.fullmatch(r'[0-9a-f]{64}',str(h)):
                        errors.append(f'VPACK_HASH_INVALID:{n}');continue
                    b=z.read(n);raw[n]=b
                    if sha256_bytes(b)!=h:errors.append(f'VPACK_HASH_MISMATCH:{n}')
                if set(AUTH_FILES).issubset(raw):
                    parsed=parse_index_manifest(raw['INDEX.md'].decode('utf-8','strict'))
                    if not parsed:errors.append('VPACK_INDEX_INVALID')
                    else:
                        actual={fn:sha256_bytes(raw[fn]) for fn in SRC_ORDER};bundle=bundle_hash(actual);sid=f"SAVESET-{version_text(parsed['version'])}-{bundle[:16]}"
                        if actual!=parsed.get('hashes') or bundle!=parsed.get('bundle') or sid!=parsed.get('save_set_id'):errors.append('VPACK_INDEX_IDENTITY_MISMATCH')
                        if m.get('save_set_id')!=sid or m.get('save_version')!=version_text(parsed['version']):errors.append('VPACK_IDENTITY_MISMATCH')
                        receipt=m.get('publication_receipt')
                        if receipt is not None:
                            if not isinstance(receipt,dict) or receipt.get('schema')!='SOURCE_PUBLICATION_RECEIPT_V1' or receipt.get('save_set_id')!=sid or receipt.get('bundle_sha256')!=bundle or receipt.get('index_sha256')!=sha256_bytes(raw['INDEX.md']):errors.append('VPACK_PUBLICATION_RECEIPT_MISMATCH')
                        ev=str(parsed.get('engine_version') or '');eh=str(parsed.get('engine_sha256') or '');gh=str(parsed.get('save_guard_sha256') or '')
                        if not ev or not re.fullmatch(r'[0-9a-f]{64}',eh) or not re.fullmatch(r'[0-9a-f]{64}',gh):errors.append('VPACK_INDEX_TOOL_BINDING_MISSING')
                        else:
                            if m.get('engine_sha256')!=eh or m.get('guard_sha256')!=gh:errors.append('VPACK_TOOL_BINDING_MISMATCH')
                            if ef in raw and sha256_bytes(raw[ef])!=eh:errors.append('VPACK_BOUND_ENGINE_HASH_MISMATCH')
                            if gf in raw and sha256_bytes(raw[gf])!=gh:errors.append('VPACK_BOUND_GUARD_HASH_MISMATCH')
                            if ef and not re.fullmatch(rf'GAME_ENGINE_v{re.escape(ev)}\.py',ef):errors.append('VPACK_ENGINE_FILENAME_MISMATCH')
                detail={'save_set_id':m.get('save_set_id'),'save_version':m.get('save_version'),'engine_file':m.get('engine_file'),'guard_file':m.get('guard_file'),'member_count':len(members),'vpack_bytes':packs[0].stat().st_size,'bootstrap_file':bp.name if bp is not None else None,'parent_save_set_id':m.get('parent_save_set_id'),'publication_receipt':m.get('publication_receipt')}
        except Exception as ex:errors.append(f'VPACK_INVALID:{type(ex).__name__}:{ex}')
    return {'packet':'VPACK_TRANSPORT_CHECK_V1','status':'FAIL' if errors else 'PASS','base':str(source_dir),'files':[p.name for p in source_dir.iterdir() if p.is_file()] if source_dir.is_dir() else [],'detail':detail,'errors':errors}

def deterministic_unit(seed_anchor: str, *parts: Any) -> float:
    raw = "|".join([str(seed_anchor)] + [str(x) for x in parts]).encode("utf-8")
    n = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")
    return (n + 0.5) / 18446744073709551616.0


def secondhand_hidden_issue_gate(seed_anchor: str, transaction_id: str, probability: float = 0.02,
                                 hard_probability_cap_exclusive: float = 0.03) -> dict:
    """Canonical deterministic one-shot hidden-issue gate for a secondhand transaction.

    This decides only whether the probability gate fires. Concrete defect content remains
    a simulation/narrative outcome and is never generated by this infrastructure function.
    """
    tid=str(transaction_id or "").strip(); seed=str(seed_anchor or "").strip()
    if not seed: raise EngineError("SECONDHAND_GATE_SEED_MISSING")
    if not tid: raise EngineError("SECONDHAND_GATE_TRANSACTION_ID_MISSING")
    try: prob=float(probability); cap=float(hard_probability_cap_exclusive)
    except Exception: raise EngineError("SECONDHAND_GATE_PROBABILITY_INVALID")
    if not math.isfinite(prob) or not math.isfinite(cap) or prob < 0 or cap <= 0 or cap >= 1 or prob >= cap:
        raise EngineError("SECONDHAND_GATE_PROBABILITY_INVALID")
    threshold=max(0,min(SECONDHAND_ROLL_SCALE,int(round(prob*SECONDHAND_ROLL_SCALE))))
    roll=min(SECONDHAND_ROLL_SCALE-1,int(deterministic_unit(seed,"secondhand_hidden_issue_gate_v1",tid)*SECONDHAND_ROLL_SCALE))
    triggered=roll < threshold
    return {
        "gate_version":SECONDHAND_GATE_VERSION,"transaction_id":tid,"deterministic_key":tid,
        "probability":round(prob,12),"hard_probability_cap_exclusive":round(cap,12),
        "roll_basis_0_9999":roll,"threshold_lt":threshold,"triggered":triggered,
        "result":"hidden_issue_gate_triggered" if triggered else "pass_no_undisclosed_issue"
    }


def _secondhand_gate_config(runtime_rules: dict) -> dict:
    rf=(runtime_rules.get("random_event_framework") or {}) if isinstance(runtime_rules,dict) else {}
    cfg=rf.get("secondhand_hidden_issue") if isinstance(rf,dict) else None
    return cfg if isinstance(cfg,dict) else {}


def _secondhand_gate_ledger(state: dict) -> dict:
    er=state.get("engine_runtime") or {}
    rg=(er.get("random_gates") or {}) if isinstance(er,dict) else {}
    led=rg.get("secondhand_hidden_issue") if isinstance(rg,dict) else None
    return led if isinstance(led,dict) else {}


def _validate_secondhand_gate_record(record: dict, seed_anchor: str, cfg: dict) -> Optional[str]:
    if not isinstance(record,dict): return "record must be object"
    if record.get("gate_version")!=SECONDHAND_GATE_VERSION:return "gate_version invalid"
    tid=record.get("transaction_id") or record.get("deterministic_key")
    if not isinstance(tid,str) or not tid.strip():return "transaction_id missing"
    if record.get("deterministic_key")!=tid:return "deterministic_key must equal transaction_id"
    try: expected=secondhand_hidden_issue_gate(seed_anchor,tid,float(cfg.get("probability",0.02)),float(cfg.get("hard_probability_cap_exclusive",0.03)))
    except EngineError as exc:return str(exc)
    for fld in ("probability","hard_probability_cap_exclusive","roll_basis_0_9999","threshold_lt","triggered","result"):
        if record.get(fld)!=expected.get(fld):return f"{fld} mismatch expected={expected.get(fld)!r} actual={record.get(fld)!r}"
    return None


def _validate_secondhand_gate_ledger(state: dict, runtime_rules: dict) -> List[str]:
    er=state.get("engine_runtime") or {}; seed=str(er.get("seed_anchor") or "")
    cfg=_secondhand_gate_config(runtime_rules); led=_secondhand_gate_ledger(state); bad=[]
    for tid,rec in sorted(led.items()):
        if not isinstance(tid,str) or not tid.strip():bad.append("ledger key invalid");continue
        if not isinstance(rec,dict):bad.append(f"{tid}: record must be object");continue
        if rec.get("transaction_id")!=tid:bad.append(f"{tid}: transaction_id must equal ledger key");continue
        err=_validate_secondhand_gate_record(rec,seed,cfg)
        if err:bad.append(f"{tid}: {err}")
    return bad


def secondhand_gate_packet(base: Path, transaction_id: str) -> dict:
    ready=ensure_source_ready(base);state=read_json(base/"state.json");rules=load_runtime_rules(base)
    cfg=_secondhand_gate_config(rules)
    if not cfg:raise EngineError("SECONDHAND_GATE_CONFIG_MISSING")
    rec=secondhand_hidden_issue_gate(str((state.get("engine_runtime") or {}).get("seed_anchor") or ""),transaction_id,float(cfg.get("probability",0.02)),float(cfg.get("hard_probability_cap_exclusive",0.03)))
    existing=_secondhand_gate_ledger(state).get(str(transaction_id))
    if existing is not None and existing!=rec:
        # checked_at / provenance metadata may exist in authority; deterministic fields must still match.
        err=_validate_secondhand_gate_record(existing,str((state.get("engine_runtime") or {}).get("seed_anchor") or ""),cfg)
        if err:raise EngineError("SECONDHAND_GATE_EXISTING_RECORD_INVALID:"+err)
        rec=copy.deepcopy(existing)
    return {"engine_version":ENGINE_VERSION,"packet":"SECONDHAND_GATE_V1","source_ready":ready,"transaction_id":str(transaction_id),"existing_record":existing is not None,"gate":rec,"commit_rule":"Persist exactly one record under STATE.engine_runtime.random_gates.secondhand_hidden_issue[transaction_id]. Existing records are immutable; concrete defect content is simulated only if triggered=true."}


CONTACT_INITIATIVE_CLASSES = {
    "pirate_civilian_regular_mercenary": "pirate_civilian_regular_mercenary_player_first_unaware_probability",
    "regular_military_research_low_emission": "regular_military_research_low_emission_player_first_unaware_probability",
    "external_top_stealth_recon": "external_top_stealth_recon_player_first_unaware_probability",
}


def contact_sensor_initiative_gate(seed_anchor: str, runtime_event_id: str, target_class: str, contact_cfg: dict) -> dict:
    """Deterministic baseline sensor-initiative gate for a random ship contact.

    The immutable runtime_event_id owns the random roll. target_class selects only the
    threshold, so changing classification cannot reroll the same encounter. Explicit
    sensor failures or causal exceptions remain simulation inputs and must be recorded
    separately instead of mutating this baseline roll.
    """
    seed=str(seed_anchor or "").strip();event_id=str(runtime_event_id or "").strip();klass=str(target_class or "").strip()
    if not seed:raise EngineError("CONTACT_GATE_SEED_MISSING")
    if not event_id:raise EngineError("CONTACT_GATE_RUNTIME_EVENT_ID_MISSING")
    key=CONTACT_INITIATIVE_CLASSES.get(klass)
    if key is None:raise EngineError("CONTACT_GATE_TARGET_CLASS_INVALID")
    if not isinstance(contact_cfg,dict):raise EngineError("CONTACT_GATE_CONFIG_MISSING")
    prob=contact_cfg.get(key)
    if not isinstance(prob,(int,float)) or isinstance(prob,bool) or not math.isfinite(float(prob)) or not 0<=float(prob)<=1:
        raise EngineError("CONTACT_GATE_PROBABILITY_INVALID")
    threshold=max(0,min(SECONDHAND_ROLL_SCALE,int(round(float(prob)*SECONDHAND_ROLL_SCALE))))
    roll=min(SECONDHAND_ROLL_SCALE-1,int(deterministic_unit(seed,"contact_sensor_initiative_gate_v1",event_id)*SECONDHAND_ROLL_SCALE))
    success=roll<threshold
    return {
        "version":"CONTACT_SENSOR_INITIATIVE_GATE_V1",
        "runtime_event_id":event_id,
        "target_class":klass,
        "probability":float(prob),
        "threshold_lt":threshold,
        "roll_basis_0_9999":roll,
        "player_first_and_target_unaware":success,
        "result":"player_first_target_unaware" if success else "baseline_gate_not_met",
    }


def contact_gate_packet(base: Path, runtime_event_id: str, target_class: str) -> dict:
    ready=ensure_source_ready(base);state=read_json(base/"state.json");rules=load_runtime_rules(base)
    rf=rules.get("random_event_framework") if isinstance(rules,dict) else None
    cfg=rf.get("contact_sensor_initiative") if isinstance(rf,dict) else None
    gate=contact_sensor_initiative_gate(str((state.get("engine_runtime") or {}).get("seed_anchor") or ""),runtime_event_id,target_class,cfg)
    return {
        "engine_version":ENGINE_VERSION,"packet":"CONTACT_SENSOR_INITIATIVE_GATE_V1","source_ready":ready,
        "gate":gate,"rule_id":"RULE-CONTACT-SENSOR-INITIATIVE-01",
        "override_rule":"This is the normal-sensor/no-explicit-causal-exception baseline. If an explicit sensor failure or causal exception applies, record the exception and its evidence; do not reroll the baseline gate.",
        "identity_rule":"A successful initiative gate does not itself identify the target; identity still requires an available signature or intelligence source.",
    }


def _hazard_threshold(seed_anchor: str, clock_id: str, cycle: int) -> float:
    u = min(max(deterministic_unit(seed_anchor, "hazard_threshold", clock_id, cycle), 1e-15), 1-1e-15)
    return -math.log(1.0-u)


def _profile_annual_rate(profile: dict, seed_anchor: str, clock_id: str, cycle: int) -> float:
    if isinstance(profile.get("annual_rate"), (int,float)):
        return max(0.0, float(profile["annual_rate"]))
    rr = profile.get("annual_rate_range")
    if isinstance(rr, list) and len(rr) == 2 and all(isinstance(x,(int,float)) for x in rr):
        lo, hi = sorted([float(rr[0]), float(rr[1])])
        u = deterministic_unit(seed_anchor, "hazard_rate", clock_id, cycle)
        return max(0.0, lo + (hi-lo)*u)
    p = profile.get("annual_probability_per_entity")
    count = profile.get("entity_count", 1)
    if isinstance(p,(int,float)) and isinstance(count,(int,float)) and 0 <= float(p) < 1 and float(count) >= 0:
        return -math.log(max(1e-15, 1.0-float(p))) * float(count)
    return 0.0



