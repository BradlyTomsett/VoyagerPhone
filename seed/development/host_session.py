"""Trusted in-process host; one isolated root/session/viewer per instance.
Callbacks must authenticate the actual user, never approve model JSON by default.
No server, model API or cross-session process lifetime is assumed.
"""
from pathlib import Path
import hashlib,json,threading,types,copy
class HostSession:
    def __init__(self,root,session_id,viewer='player',authorize=None,authorize_viewer=None,review_narrative=None):
        if not isinstance(session_id,str) or not session_id:raise ValueError('SESSION_ID_REQUIRED')
        self.root=Path(root).resolve();self.session_id=session_id;self.viewer=viewer;self.authorize=authorize;self.authorize_viewer=authorize_viewer;self.review_narrative=review_narrative
        self._root_inode=(self.root.stat().st_dev,self.root.stat().st_ino)
        self._configuration=(self.root,session_id,viewer);self._api=None;self._binding=None;self._lock=threading.RLock();self.metrics={'engine_loads':0,'prepare_requests':0,'submit_requests':0,'setup_requests':0}
    def _engine(self):
        if self._configuration!=(self.root,self.session_id,self.viewer):raise ValueError('SESSION_CONFIGURATION_IMMUTABLE')
        if self.root.is_symlink() or self.root.resolve()!=self.root or (self.root.stat().st_dev,self.root.stat().st_ino)!=self._root_inode:raise ValueError('HOST_ROOT_REPLACED_CREATE_NEW_SESSION')
        for p in (self.root/'manifest.json',self.root/'engine.py',self.root/'guard.py'):
            if p.is_symlink():raise ValueError('HOST_SOURCE_SYMLINK')
        m=json.loads((self.root/'manifest.json').read_bytes());raw=(self.root/'engine.py').read_bytes();guard=(self.root/'guard.py').read_bytes();binding=(hashlib.sha256(raw).hexdigest(),hashlib.sha256(guard).hexdigest())
        if m['tool_bindings']!={'engine.py':binding[0],'guard.py':binding[1]}:raise ValueError('HOST_TOOL_BINDING')
        if self._api is None or binding!=self._binding:
            ns={'__name__':'voyager_host_session','__file__':str(self.root/'engine.py'),'_HOST_ENGINE_ROOT':str(self.root)}
            exec(compile(raw,str(self.root/'engine.py'),'exec',dont_inherit=True),ns)
            if ns['BUNDLED_GUARD_SHA256']!=binding[1]:raise ValueError('HOST_GUARD_BINDING')
            self._api=types.SimpleNamespace(**ns);self._binding=binding;self.metrics['engine_loads']+=1
        return self._api
    def _allowed(self):
        return self.viewer=='player' or self.viewer.startswith('observer:') or (self.viewer.startswith('npc:') and self.authorize_viewer is not None and self.authorize_viewer(self.root,self.session_id,self.viewer) is True)
    def prepare(self,**request):
        with self._lock:
            if not self._allowed():return {'status':'NEEDS_AUTHORIZATION','viewer':self.viewer}
            if request.pop('viewer',self.viewer)!=self.viewer:raise ValueError('HOST_VIEWER_MISMATCH')
            a=self._engine();self.metrics['prepare_requests']+=1;token=a._s3_view_scope.set(self.viewer)
            try:return a.RoundService.prepare(self.root,viewer=self.viewer,**request)
            finally:a._s3_view_scope.reset(token)
    def context(self,**request):
        """One read-only turn preparation plus overview/optional advance plan."""
        with self._lock:
            if not self._allowed():return {'status':'NEEDS_AUTHORIZATION','viewer':self.viewer}
            if request.pop('viewer',self.viewer)!=self.viewer:raise ValueError('HOST_VIEWER_MISMATCH')
            a=self._engine();self.metrics['prepare_requests']+=1;token=a._s3_view_scope.set(self.viewer)
            try:return a.PlayService.context(self.root,viewer=self.viewer,**request)
            finally:a._s3_view_scope.reset(token)
    def submit(self,envelope,version,dry_run=False):
        with self._lock:
            if not self._allowed():return {'status':'NEEDS_AUTHORIZATION','committed':False}
            payload=copy.deepcopy(envelope)
            if payload.get('command',{}).get('proposal',{}).get('viewer')!=self.viewer:raise ValueError('HOST_VIEWER_MISMATCH')
            if self.authorize is None or self.authorize(copy.deepcopy(payload)) is not True:return {'status':'NEEDS_AUTHORIZATION','committed':False}
            a=self._engine();self.metrics['submit_requests']+=1;token=a._s3_view_scope.set(self.viewer)
            try:
                proposal=payload['command']['proposal']
                if self.viewer=='player':
                    with a.narrative_review_context(proposal,self.review_narrative):return a.RoundService.submit(self.root,payload,version,dry_run)
                return a.RoundService.submit(self.root,payload,version,dry_run)
            finally:a._s3_view_scope.reset(token)
    def setup(self,envelope,version,dry_run=False):
        """Submit exact authenticated world/profile/planning setup, never self-approve.

        This completes the prepare -> setup -> prepare -> submit V2 flow. A real
        host callback may validate the user's adopted ordinary-NPC policy; an AI
        model cannot manufacture that approval or spend the player's resources.
        """
        with self._lock:
            if not self._allowed():return {'status':'NEEDS_AUTHORIZATION','committed':False}
            payload=copy.deepcopy(envelope)
            if payload.get('command',{}).get('kind')!='story_setup':raise ValueError('HOST_SETUP_REQUIRES_STORY_SETUP')
            if self.authorize is None or self.authorize(copy.deepcopy(payload)) is not True:return {'status':'NEEDS_AUTHORIZATION','committed':False}
            a=self._engine();self.metrics['setup_requests']+=1;token=a._s3_view_scope.set(self.viewer)
            try:
                rewrites=[x for x in payload['command'].get('actions',[]) if x.get('type')=='turn_rewrite' and x.get('viewer')=='player']
                if len(rewrites)>1:raise ValueError('HOST_ONE_REVIEWED_REWRITE_PER_COMMAND')
                if rewrites:
                    action=rewrites[0];state=a.read_json_view(self.root/'state.json');proposal=copy.deepcopy(a._s3_runtime(state)['turns'][action['turn_id']]['proposal']);proposal.update(segments=action['segments'],experience=action['experience'])
                    with a.narrative_review_context(proposal,self.review_narrative):return a.host_intent_command(self.root,payload,version,dry_run)
                return a.host_intent_command(self.root,payload,version,dry_run)
            finally:a._s3_view_scope.reset(token)
    def close(self):
        with self._lock:self._api=None;self._binding=None
