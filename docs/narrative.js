import {briefingText} from './briefing.js?v=0.8.23';
// Old drafts sometimes mixed a scene with an implementation checklist. Display
// the scene without rewriting stored evidence or inventing replacement prose.
export function narrativeText(value){
 if(typeof value!=='string')return '';
 let text=value.replace(/\r\n?/g,'\n');
 const scene=/^[ \t]*(?:#{1,4}[ \t]*|\*\*)?(?:现场开场|开场片段|场景正文)(?:[^\n]*)\n/m.exec(text);
 if(scene)text=text.slice(scene.index+scene[0].length);
 const technical=/^[ \t]*(?:#{1,4}[ \t]*|\*\*)?(?:提交内容|技术面确认|一处需要你确认|一处需要你或宿主确认|参数说明|结构化提交|行动参数)[^\n]*(?:\n|$)/m.exec(text);
 if(technical)text=text.slice(0,technical.index);
 return briefingText(text).replace(/\*\*([^*\n]+)\*\*/g,'$1').trim();
}
