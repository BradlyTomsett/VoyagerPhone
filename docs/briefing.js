// Clean player-facing prose only. Evidence and engine payloads remain unchanged.
const fileRef=String.raw`(?:[A-Za-z0-9_./-]+\.(?:jsonl?|md|py|sqlite3?))(?:\#[^\s\x60<>（）()【】\[\]，。；：:,;]*)?`;
const technicalRef=String.raw`(?:${fileRef}|(?:state|catalog|rules|tasks):[A-Za-z0-9_./-]+)`;
const metadataDate=/(?:资料|数据|来源)(?:日期|时间)\s*[：:]?\s*(?:\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?|未注明|未单列)/g;
export function briefingText(value){
 if(typeof value!=='string')return '';
 let text=value.replace(/\r\n?/g,'\n');
 text=text.replace(new RegExp(String.raw`\[[^\]\n]*\]\(\s*${technicalRef}\s*\)`,'g'),'');
 text=text.replace(new RegExp(String.raw`(?:\*\*)?(?:(?:资料|数据|记录)来源|来源文件|来源|引用)\s*(?:\*\*)?\s*[：:]?\s*(?:\*\*)?\s*\x60*${technicalRef}\x60*`,'g'),'');
 text=text.replace(new RegExp(String.raw`\x60*${technicalRef}\x60*`,'g'),'');
 text=text.replace(metadataDate,'').replace(/[（(【\[]\s*(?:现状记录|现状资料|历史参考|历史记录|原档记录|资料标记)\s*[）)】\]]/g,'');
 text=text.replace(/`?\b(?:PER|LOC|VES|ORG|CLS|EQP|RULE|ASSET|SAVESET|CMD|TSK|WEB|MOVE)-[A-Za-z0-9_-]+`?/g,'');
 // Removing nested citation fragments can leave empty brackets behind.
 for(let i=0;i<3;i++)text=text.replace(/[（(【\[]\s*[，,；;：:\s]*[）)】\]]/g,'');
 return text.split('\n').map(line=>line.replace(/(?:\*\*)?(?:来源|来源文件|资料来源)\s*[：:]\s*(?:\*\*)?\s*$/,'').replace(/^[\s，,；;。]+/,'').replace(/[ \t]+$/,'')).filter(line=>!/^\s*[`*#，,；;：:。\-–—]*\s*$/.test(line)||!line.trim()).join('\n').replace(/\n{3,}/g,'\n\n').trim();
}
