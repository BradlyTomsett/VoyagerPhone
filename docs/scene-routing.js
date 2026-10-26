// Scene routing follows the engine's current scene. A browser preference must
// never pin later requests to a stale ID or confuse a place name with an ID.
export function automaticSceneSettings(value){
 const settings=value&&typeof value==='object'&&!Array.isArray(value)?value:{};
 const {scene_id:obsolete,...current}=settings;
 return current;
}
export function makeTurnRequest({clientId,intent,mode,actorId}){
 return {client_id:clientId,intent,mode,actor_id:typeof actorId==='string'?actorId.trim()||null:null,scene_id:null};
}
export function currentSceneLabel(scenes){
 return scenes?.current?.scene_id?'自动跟随当前游玩场景':'尚未建立场景，发送行动后准备开场';
}
