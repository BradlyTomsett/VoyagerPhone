#!/usr/bin/env python3
"""Human interaction boundary. An embedding host may instead call host_intent_command
only after authenticating the actual user and checking their exact instruction.
This is a trusted-local-host boundary, not protection against arbitrary same-user
Python execution. Do not expose it as an automatically approving model tool.
"""
import argparse,importlib.util,json,os,pathlib,subprocess,sys,secrets,hmac,time

def main():
 p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--version');p.add_argument('--dry-run',action='store_true');args=p.parse_args()
 root=pathlib.Path(os.environ.get('VOYAGER_ROOT',str(pathlib.Path(__file__).resolve().parent.parent))).resolve()
 if not sys.stdin.isatty():raise SystemExit('HUMAN_TERMINAL_REQUIRED: use an authenticated embedding host for ChatGPT integration')
 request=json.loads(pathlib.Path(args.request).read_text());envelope=request
 if envelope.get('schema')!='HOST_COMMAND_INTENT_V1':raise SystemExit('HOST_COMMAND_INTENT_V1_REQUIRED')
 print(json.dumps(envelope,ensure_ascii=False,indent=2),flush=True)
 command=envelope['command'];cid=command['command_id'];print('核对本次指令、目标、金额与期限；输入 执行 '+cid+' 确认：',flush=True)
 if input().strip()!='执行 '+cid:raise SystemExit('USER_DECLINED')
 envelope['decision']='approved';envelope['evidence_ref']='human-terminal:'+cid;envelope['confirmation']='exact_command_reviewed_by_operator'
 keypath=root/'.runtime'/'host_gateway.key';keypath.parent.mkdir(parents=True,exist_ok=True)
 try:
  fd=os.open(keypath,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
  with os.fdopen(fd,'wb') as stream:stream.write(secrets.token_bytes(32));stream.flush();os.fsync(stream.fileno())
 except FileExistsError:pass
 if keypath.is_symlink():raise SystemExit('GATEWAY_KEY_PATH_INVALID')
 envelope['received_at_unix']=time.time()
 envelope['_gateway_proof']=hmac.new(keypath.read_bytes(),json.dumps(envelope,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode(),'sha256').hexdigest()
 r,w=os.pipe();env=dict(os.environ,VOYAGER_ROOT=str(root));argv=[sys.executable,str(root/'engine.py'),'hostinvoke','--intent-fd',str(r)]
 if args.version:argv+=['--version',args.version]
 if args.dry_run:argv+=['--dry-run']
 cp=subprocess.Popen(argv,env=env,pass_fds=(r,),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);os.close(r)
 try:
  with os.fdopen(w,'wb') as stream:stream.write(json.dumps(envelope,ensure_ascii=False).encode())
  out,err=cp.communicate();print(out,end='');print(err,end='',file=sys.stderr);return cp.returncode
 finally:
  if cp.poll() is None:cp.terminate();cp.wait()
if __name__=='__main__':raise SystemExit(main())
