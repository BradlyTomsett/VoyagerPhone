// Convert decimal text with integer arithmetic; never round a balance via a float product.
export function minorUnits(value,places=0){
 const m=String(value).trim().match(/^([+-]?)(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i);
 if(!m)throw Error('MONEY_VALUE_INVALID');
 const exponent=Number(m[4]||0);if(Math.abs(exponent)>30)throw Error('MONEY_VALUE_INVALID');
 const digits=BigInt(m[2]+(m[3]||'')),shift=places+exponent-(m[3]||'').length;
 let result;if(shift>=0)result=digits*10n**BigInt(shift);else{const divisor=10n**BigInt(-shift);result=digits/divisor+(digits%divisor*2n>=divisor?1n:0n);}
 return m[1]==='-'?-result:result;
}
function group(value){return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g,',');}
export function formatCoins(value,unit='copper'){
 try{let copper=minorUnits(value,unit==='gold'?4:unit==='silver'?2:0),sign=copper<0n?'−':'';if(copper<0n)copper=-copper;
  return `${sign}${group(copper/10000n)} 金币 ${copper/100n%100n} 银币 ${copper%100n} 铜币`;
 }catch{return '金额待核实';}
}
export function formatAccount(value,key){
 if(key.endsWith('_grey')){try{return '约 '+group(minorUnits(value))+' 灰币';}catch{return '金额待核实';}}
 return formatCoins(value,key.endsWith('_gold')?'gold':'copper');
}
