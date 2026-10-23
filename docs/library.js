// Read-only source browser. All text is rendered as text, never executable HTML.
const labels={name:'姓名',age:'年龄',role:'职责',occupation:'身份',background:'背景',family:'家庭',why_xilu9:'来到熄炉的原因',difficulty:'近况',priority:'诉求',status:'状态',as_of:'记录时间',source_kind:'记录性质',contract:'合同',property:'店铺',shop_area_m2_approx:'面积约（㎡）',current_use_area_m2:'使用面积（㎡）',local_employees:'正式员工',population_estimate:'人口记录',character:'地区特征',local_security:'当地治安',employment_policy:'雇佣待遇',daily_wage_copper_each:'每人日工资（铜）',rooms:'房间',location:'位置',knowledge:'知情范围',reason:'缘由',note:'说明',source:'来源',summary:'摘要',title:'标题',text:'原文',quantity:'数量',qty:'数量',conditions:'环境条件',current_status:'当前状态'};
function node(tag,className,text){const n=document.createElement(tag);if(className)n.className=className;if(text!==undefined)n.textContent=text;return n;}
function preview(text){try{const value=JSON.parse(text);if(typeof value==='string')return value;const lines=[];function walk(v,key='',depth=0){if(lines.length>=10||depth>3)return;if(v&&typeof v==='object'){for(const [k,x] of Object.entries(v)){if(['schema','schema_version','source_ref','basis_ref','authority','manifest_ref'].includes(k))continue;walk(x,k,depth+1);}}else if(v!==null)lines.push((labels[key]||key)+ '：'+String(v));}walk(value);return lines.join('；').slice(0,600)||text.slice(0,500);}catch{return text.slice(0,600);}}

export class SourceLibraryView{
 constructor(rpc,error){this.rpc=rpc;this.error=error;this.loaded=false;this.busy=false;this.query='';this.offset=0;this.next=null;this.result=null;
  document.querySelector('#library-search').onsubmit=e=>{e.preventDefault();this.query=document.querySelector('#library-query').value.trim();this.offset=0;this.search();};
  document.querySelector('#library-next').onclick=()=>{if(this.next!==null){this.offset=this.next;this.search();}};
  document.querySelector('#library-category').onchange=()=>{this.offset=0;this.search();};
  document.querySelector('#library-history').onchange=()=>{this.offset=0;this.search();};
 }
 invalidate(){this.loaded=false;}
 async open(ready){if(!ready){document.querySelector('#library-status').textContent='引擎就绪后可查阅原始资料，无需 API Key。';return;}if(this.loaded||this.busy)return;this.busy=true;
  try{const summary=await this.rpc('library_summary');document.querySelector('#library-coverage').textContent=`${summary.save_version} · ${summary.indexed_records.toLocaleString('zh-CN')} 条资料片段 · ${summary.history_archives} 份历史归档 · 游戏时间 ${summary.game_time.replace('T',' ')}`;
   document.querySelector('#library-notice').textContent=summary.notice;
   const cards=summary.cards.map(card=>{const n=node('article','source-card'),button=node('button','source-title',card.title);button.onclick=()=>{this.query=card.title;document.querySelector('#library-query').value=this.query;this.offset=0;this.search();};n.append(button,node('p','',card.text),node('small','source-ref',card.source_ref));return n;});
   document.querySelector('#library-featured').replaceChildren(...cards);this.loaded=true;
  }catch(e){document.querySelector('#library-status').textContent=this.error(e.message);}finally{this.busy=false;}
  if(this.loaded)await this.search();
 }
 async search(){if(this.busy){this.pending=true;return;}this.busy=true;const status=document.querySelector('#library-status');status.textContent='正在查阅原始记录…';document.querySelector('#library-next').disabled=true;
  try{this.result=await this.rpc('library_search',{query:this.query,offset:this.offset,limit:16,history:document.querySelector('#library-history').checked,category:document.querySelector('#library-category').value});this.next=this.result.next_offset;
   const cards=this.result.results.map(record=>{const card=node('article','source-record'),head=node('div','source-record-heading');head.append(node('h3','',record.label),node('span','source-kind',record.kind));card.append(head,node('small','source-date','记录日期：'+record.as_of),node('p','source-excerpt',preview(record.text)));
    const details=node('details'),summary=node('summary','','查看完整原始记录'+(record.parts>1?`（片段 ${record.part}/${record.parts}，其他片段可继续搜索）`:''));let text=record.text;try{text=JSON.stringify(JSON.parse(text),null,2);}catch{}details.append(summary,node('pre','',text));card.append(details,node('small','source-ref',record.ref));return card;});
   document.querySelector('#library-results').replaceChildren(...cards);status.textContent=this.result.total?`找到 ${this.result.total.toLocaleString('zh-CN')} 条，显示第 ${this.result.offset+1}—${Math.min(this.result.offset+16,this.result.total)} 条。`:'本次检索未找到匹配片段，可换用人物全名、地点名或勾选历史归档；这不代表原始数据不存在。';
   document.querySelector('#library-next').hidden=this.next===null;document.querySelector('#library-next').disabled=false;
  }catch(e){status.textContent=this.error(e.message);}finally{this.busy=false;if(this.pending){this.pending=false;this.search();}}
 }
}
