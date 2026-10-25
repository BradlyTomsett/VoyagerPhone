export function setupReferenceText(job){
 const issues=job.reference_issues||[],names=kind=>[...new Set(issues.filter(i=>i.kind===kind).map(i=>i.name))].join('、');
 const parts=[];
 if(names('actor'))parts.push('当前视角人物“'+names('actor')+'”未能对应到这份存档的人物记录。');
 if(names('person'))parts.push('开场草案中的参与者“'+names('person')+'”未能唯一对应到人物记录；这不表示你选定的视角人物有误。');
 if(names('place'))parts.push('开场草案中的地点“'+names('place')+'”未能对应到可用地点。');
 if(!parts.length)parts.push('开场草案中有未识别的人物或地点，也可能是其他参与者，并不一定是你选择的视角人物。');
 parts.push(job.uncommitted||job.status==='FAILED'?'这一回合没有执行，此前进度保留。可核对人物与地点后重新准备。':'请先核对这次提交的结果，避免重复执行。');
 return parts.join('');
}
