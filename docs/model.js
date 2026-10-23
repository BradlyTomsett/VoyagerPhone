export function matches(value,s){if(s.type==='object')return value!==null&&typeof value==='object'&&!Array.isArray(value)&&(s.required||[]).every(k=>k in value)&&Object.entries(value).every(([k,v])=>s.properties[k]?matches(v,s.properties[k]):s.additionalProperties!==false);if(s.type==='array')return Array.isArray(value)&&value.every(v=>matches(v,s.items));if(s.type==='string')return typeof value==='string'&&(!s.enum||s.enum.includes(value));return false;}
export function validateSettings(c){const u=new URL(c.base_url);if(u.protocol!=='https:'||u.username||u.password||u.search||u.hash)throw Error('MODEL_URL_INVALID');if(!c.api_key||!c.model_id)throw Error('MODEL_NOT_CONFIGURED');if(!['responses','chat_completions'].includes(c.protocol))throw Error('MODEL_PROTOCOL_UNSUPPORTED');return {...c,base_url:u.href.replace(/\/$/,'')};}
export async function modelCall(config,contract,packet,review=false){
 const c=validateSettings(config),deep=new URL(c.base_url).hostname==='api.deepseek.com';
 const name=review?'voyager_review':'voyager_plan',schema=contract.schema,model=(review&&c.review_model_id)||c.model_id;
 let body,endpoint;
 if(c.protocol==='responses'){body={model,instructions:contract.instructions,input:JSON.stringify(packet),store:false,max_output_tokens:10000,text:{format:{type:'json_schema',name,strict:true,schema}}};endpoint='/responses';if(deep){delete body.store;delete body.text.format.strict;}}
 else{body={model,messages:[{role:'system',content:contract.instructions},{role:'user',content:JSON.stringify(packet)}],max_completion_tokens:10000,response_format:{type:'json_schema',json_schema:{name,strict:true,schema}}};endpoint='/chat/completions';if(deep){body.max_tokens=body.max_completion_tokens;delete body.max_completion_tokens;body.response_format={type:'json_object'};body.messages[0].content+='\n只输出符合以下 JSON Schema 的 JSON 对象，不要 Markdown：\n'+JSON.stringify(schema);}}
 const control=new AbortController(),timeout=setTimeout(()=>control.abort(),180000);
 try{
  const r=await fetch(c.base_url+endpoint,{method:'POST',mode:'cors',credentials:'omit',redirect:'error',headers:{Authorization:'Bearer '+c.api_key,'Content-Type':'application/json'},body:JSON.stringify(body),signal:control.signal});
  if(!r.ok)throw Error('MODEL_HTTP_'+r.status);
  const reader=r.body.getReader();let size=0,parts=[];
  while(true){const {value,done}=await reader.read();if(done)break;size+=value.byteLength;if(size>4*1024*1024){await reader.cancel();throw Error('MODEL_RESPONSE_TOO_LARGE');}parts.push(value);}
  let v;try{v=JSON.parse(await new Blob(parts).text());}catch{throw Error('MODEL_JSON_INVALID');}
  let text;
  if(c.protocol==='responses'){if(v.status!=='completed')throw Error('MODEL_INCOMPLETE_OR_REFUSED');text=(v.output||[]).filter(x=>x.type==='message').flatMap(x=>x.content||[]).filter(x=>x.type==='output_text').map(x=>x.text).join('');}
  else{const choice=v.choices?.[0];if(choice?.finish_reason!=='stop'||choice.message?.refusal)throw Error('MODEL_INCOMPLETE_OR_REFUSED');text=choice.message?.content;}
  let result;try{result=JSON.parse(text);}catch{throw Error('MODEL_JSON_INVALID');}if(!matches(result,schema))throw Error('MODEL_SCHEMA_INVALID');return {result,usage:v.usage||{}};
 }catch(e){if(e instanceof TypeError||e.name==='AbortError')throw Error('MODEL_NETWORK_OR_CORS');throw e;}finally{clearTimeout(timeout);}
}
