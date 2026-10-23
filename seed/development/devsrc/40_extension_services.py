# === VOYAGER_DEV_MODULE: extension_services ===
class ExtensionServices:
    """Explicit bounded extension dispatch. Existing security/commit pipeline owns IO.

    Handler work objects are transaction-private; returned public objects are copies.
    Registration is code-owned, never read from a content package.
    """
    handlers={}
    dependencies={'storage':[], 'authorization':['storage'], 'domain':['authorization'],
                  'knowledge':['storage'], 'content':['domain','knowledge'],
                  'memory':['knowledge'], 'scheduler':['domain','knowledge'], 'narrative':['domain','knowledge'], 'experience':['memory'], 'commands':['content','experience','scheduler','narrative']}
    @staticmethod
    def check_dependencies(graph):
        done=set();active=set();ordered=[]
        def visit(name):
            if name in active:raise EngineError('SERVICE_DEPENDENCY_CYCLE')
            if name in done:return
            if name not in graph:raise EngineError('SERVICE_DEPENDENCY_MISSING')
            active.add(name)
            for dep in graph[name]:visit(dep)
            active.remove(name);done.add(name);ordered.append(name)
        for name in sorted(graph):visit(name)
        return ordered
    @classmethod
    def register(cls,kind,required,apply,targets,cost):
        if kind in cls.handlers:raise EngineError('SERVICE_DUPLICATE_REGISTRATION')
        cls.handlers[kind]={'apply':apply,'targets':targets,'cost':cost}
        DOMAIN_PUBLIC_KINDS.add(kind);DOMAIN_COMMAND_KINDS.add(kind);DOMAIN_REQUIRED_FIELDS[kind]=tuple(required)
    @classmethod
    def apply(cls,stage,state,tasks,payload):
        handler=cls.handlers.get(payload['kind'])
        return handler['apply'](stage,state,tasks,payload) if handler else _s3_previous_apply(stage,state,tasks,payload)
    @classmethod
    def targets(cls,payload):
        handler=cls.handlers.get(payload['kind'])
        return handler['targets'](payload) if handler else _s3_previous_targets(payload)
    @classmethod
    def cost(cls,payload):
        handler=cls.handlers.get(payload['kind'])
        return handler['cost'](payload) if handler else _s3_previous_cost(payload)
    @staticmethod
    def context(base,state,sid,viewer,intent,facts):
        return _s4_context_policy(base,state,sid,viewer,intent,facts)
    @staticmethod
    def scene_definition(base,state,sid,viewer):
        return _s4_scene_context(base,state,sid,viewer)
    @staticmethod
    def contracts():
        rows=[
          ('storage','TransactionService','validated stage + parent identity','atomic receipt or recovery refusal','native file schemas','authority write lock; private stage; manifest last',[]),
          ('authorization','AuthorizationService','actor/action/targets/window/budgets + actual trusted scope','verified cost and provenance or refusal','gold/grey scale10000, grey quantum100, copper scale1','permission decision only; no story authoring',['storage']),
          ('domain','ExtensionServices.apply','canonical DOMAIN_COMMAND + private state/tasks','checked effects + changes','DOMAIN_COMMAND schema; units per original domain','mutates only transaction work objects; native layer commits',['authorization']),
          ('scheduler','Scheduler/story_timeline','current time/tasks/knowledge + horizon','stable due nodes and AI/evidence barriers','ISO game time; inclusive consequence window','deterministic planning; no guessed accounting',['domain','knowledge']),
          ('knowledge','StoryTurnService/MemoryLayerService','scene/actor/viewer/intent or source query','same-snapshot permitted facts and source refs','STORY_TURN_V1 / memory search v2','read copies and role-specific derived cache; writes only typed learning',['storage']),
          ('narrative','StoryTurnService','proposal + version + actual authorization','single committed turn and receipt-based narration','STORY_TURN_PROPOSAL_V1','AI drafts never directly mutate authority',['domain','knowledge']),
          ('content','ContentVersionService','pure package + exact preview plan','version-pinned definitions or atomic refusal','CONTENT_PACKAGE_V2; no executable expression','writes catalog only except separately authorized real scene creation',['domain','knowledge']),
          ('experience','ObservedExperienceService','actual engine probe or explicit feedback + scope','bounded ordering/hints with evidence digest','EXPERIENCE_V2; <=7/30 game days','append-only receipts; no code/world/auth/RNG mutation',['memory']),
          ('commands','main/domain_command_packet','typed CLI/API request','buffered same-snapshot JSON or stable error code','engine2.67 / protocol4','schema/dispatch/presentation; no second domain calculator',['content','experience'])]
        return [{'boundary':r[0],'owner':r[1],'input':r[2],'output':r[3],'schema_units':r[4],'ownership_permissions':r[5],'dependencies':r[6],'error_contract':'stable EngineError; failed write leaves parent or committed target recoverable','idempotency':'reads side-effect-free except disposable caches; writes native command_id/full payload receipt','dependency_version':'V14.56 / Engine2.67.0 / protocol4'} for r in rows]


def _s4_story_apply(stage,state,tasks,payload):
    effect=_s3_apply(stage,state,tasks,payload)
    if payload['kind']=='story_turn':
        strategy=_s4_strategy(stage,payload['proposal']['viewer'],'conversation')
        _s3_runtime(state)['turns'][payload['command_id']]['decision_record']['strategy']=strategy
    return effect


def _s4_event_id(payload):return 'DOMAIN-'+payload['command_id']+'-'+sha256_bytes(str(_domain_payload_digest(payload)).encode())[:8]


def _s4_host_required(payload):
    host=_host_intent_scope.get()
    if payload.get('authorization')!='host_intent' or not host:raise EngineError('EXTENSION_REAL_HOST_REQUIRED')
    return host


def _s4_zero_cost(payload):return {'uses':1,'gold_units':0,'grey_units':0,'quantity':1}


ExtensionServices.check_dependencies(ExtensionServices.dependencies)
for _s4_story_kind in ('story_turn','story_setup','npc_policy'):
    ExtensionServices.register(_s4_story_kind,DOMAIN_REQUIRED_FIELDS[_s4_story_kind],_s4_story_apply,_s3_targets,_s3_cost)
_apply_domain_command=ExtensionServices.apply
_domain_command_targets=ExtensionServices.targets
_domain_authorization_cost=ExtensionServices.cost

