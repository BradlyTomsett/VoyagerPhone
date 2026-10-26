import assert from 'node:assert/strict';
import {automaticSceneSettings,makeTurnRequest,currentSceneLabel} from '../browser/scene-routing.js';

const preserved={actor_id:'PER-HAWK-MALEN-01',place_id:'',base_url:'https://example.invalid',model_id:'synthetic',protocol:'chat_completions'};
for(const legacy of ['余火咖啡',' ',null,17,{},'SCENE-CLOSED-OLD']){
 const previous={...preserved,scene_id:legacy},copy=structuredClone(previous);
 const settings=automaticSceneSettings(previous);
 assert.deepEqual(settings,preserved);assert.deepEqual(previous,copy);
 assert.deepEqual(automaticSceneSettings(settings),settings);
 const request=makeTurnRequest({clientId:'WEB-routing-fixture',intent:'保留原始指令',mode:'action',actorId:settings.actor_id});
 assert.deepEqual(request,{client_id:'WEB-routing-fixture',intent:'保留原始指令',mode:'action',actor_id:'PER-HAWK-MALEN-01',scene_id:null});
}
assert.deepEqual(automaticSceneSettings(null),{});
assert.deepEqual(automaticSceneSettings('legacy'),{});
assert.equal(makeTurnRequest({clientId:'WEB-query-fixture',intent:'查询',mode:'query',actorId:''}).actor_id,null);
assert(currentSceneLabel({current:{scene_id:null}}).includes('尚未建立'));
assert(currentSceneLabel({current:{scene_id:'SCENE-NEW'}}).includes('自动跟随'));
console.log('PASS scene preference migration preserves other settings, never reuses manual/stale scene IDs, and follows engine current scene');
