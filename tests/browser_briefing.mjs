import assert from 'node:assert/strict';
import {briefingText} from '../browser/briefing.js';

const facts='指挥官，伊沃63岁，是民用维修工程师。';
const ref='state.json#/world_state_overrides/freeport_xilu9_current/whitesleep_case_current/Ivo';
assert.equal(briefingText(facts+'\n来源：`'+ref+'`，资料日期 8363-12-11（现状记录）。'),facts);
assert.equal(briefingText(facts+'（来源：`'+ref+'`，资料日期 8363-12-11（现状记录））\n尚未核实其当前位置。'),facts+'\n尚未核实其当前位置。');
assert.equal(briefingText(facts+'\n[来源]('+ref+')\n资料日期：8363-12-11T08:00:00（现状记录）'),facts);
assert.equal(briefingText('来源：`'+ref+'`，资料日期 8363-12-11（现状记录）。'),'');
const operation='8363-12-11 08:00，暗影舰队返回 S-B5。熄炉-9人口约1,000人，尚未完成普查。\n情报来源：霍克小组。';
assert.equal(briefingText(operation),operation);
assert.equal(briefingText('伊沃（PER-IVO）驻守熄炉-9。'),'伊沃驻守熄炉-9。');
assert.equal(briefingText('无人机124；战机36；夜鹰52；大力神12；蓝鲸2；沙丘150。'),'无人机124；战机36；夜鹰52；大力神12；蓝鲸2；沙丘150。');
assert.equal(briefingText('来源：catalog.json#/catalog_registry/entities/CLS-QINFENG\n秦锋号旗舰仍在服役。'),'秦锋号旗舰仍在服役。');
assert.equal(briefingText(undefined),'');assert.equal(briefingText({}), '');
console.log('PASS fleet briefing: user citation example, inline and linked refs, internal IDs removed, operational facts/dates and in-world sources preserved');
