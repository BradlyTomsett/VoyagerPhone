import copy
import json
import unittest
from decimal import Decimal
from pathlib import Path
from backend.source_library import SourceLibrary
from backend.logistics import Logistics, KEY, at, ships

ROOT=Path(__file__).resolve().parents[1]

class LogisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.library=SourceLibrary(ROOT/'seed')
    def setUp(self):self.service=Logistics(self.library)
    def item(self,lid,name):return next(r['id'] for r in self.service.contents(lid)['items'] if r['name']==name)
    def move(self,src,dst,name,n):return self.service.plan({'kind':'items','source':src,'destination':dst,'item':self.item(src,name),'quantity':str(n)})
    def accept(self,p):self.service.state=p['state']
    def test_initial_physical_buckets_and_no_plan_or_person_as_stock(self):
        book=self.service.book()
        self.assertEqual(sum(r['quantity'] for rows in book['people'].values() for r in rows),23946)
        rows=self.service.contents('farstar')['items'];self.assertEqual(next(r['quantity'] for r in rows if r['name']=='M2动力甲'),'4234')
        names={r['name'] for r in self.service.contents('VES-EXPLORER1')['items']}
        self.assertNotIn('scientific_personnel',names);self.assertNotIn('marines',names)
        self.assertEqual(len([n for n in names if '夜鹰' in n]),1)
        self.assertEqual(next(r['quantity'] for r in self.service.contents('shadow:warehouse')['items'] if r['name']=='多功能手雷'),'24695')
        self.assertEqual(sum(int(r['quantity']) for r in self.service.contents('voyager:warehouse')['items'] if 'SCV' in r['name']),400)
    def test_read_and_preview_never_mutate_and_keep_private_authority(self):
        before=(ROOT/'seed/state.json').read_bytes();p=self.move('voyager:warehouse','jinchuan:warehouse','堡垒-6',2)
        self.assertEqual(before,(ROOT/'seed/state.json').read_bytes())
        self.assertEqual(p['state']['engine_runtime']['seed_anchor'],json.loads(before)['engine_runtime']['seed_anchor'])
        self.assertEqual(p['state']['world_state_overrides']['freeport_xilu9_current']['whitesleep_case_current']['gm_private_initial_conditions'],json.loads(before)['world_state_overrides']['freeport_xilu9_current']['whitesleep_case_current']['gm_private_initial_conditions'])
        self.assertEqual(p['state']['inventories']['current_voyager_weapon_inventory_net']['external_current_owned']['堡垒-6']['total_owned'],165541)
    def test_public_allocation_and_reverse_transfer(self):
        p=self.move('voyager:warehouse','farstar','M2动力甲',10);net=p['state']['inventories']['current_voyager_weapon_inventory_net']['self_owned_public']['M2动力甲']
        self.assertEqual((net['qty'],net['available'],net['allocated']['远星军']),(10000,5756,4244))
        self.accept(p);p=self.move('farstar','jinchuan:warehouse','M2动力甲',10);self.accept(p)
        net=p['state']['inventories']['current_voyager_weapon_inventory_net']['self_owned_public']['M2动力甲']
        self.assertEqual((net['qty'],net['available'],net['allocated']['远星军']),(9990,5756,4234))
        self.assertEqual(p['state']['inventories']['weapon_inventory']['self_owned']['m2_exoskeletons']['value'],9990)
        for rows in p['book']['stock'].values():
            for row in rows.values():self.assertEqual(sum((Decimal(b['quantity']) for b in row.get('batches',[])),Decimal(0)),Decimal(row['quantity']))
    def test_fraction_negative_nonfinite_insufficient_and_same_location(self):
        for q in ('-1','0','NaN','Infinity','0.5','999999999999999'):
            with self.assertRaises(ValueError):self.move('voyager:warehouse','jinchuan:warehouse','堡垒-6',q)
        with self.assertRaisesRegex(ValueError,'SAME_LOCATION'):self.move('voyager:warehouse','voyager:warehouse','堡垒-6',1)
        p=self.move('shadow:warehouse','voyager:warehouse','工业炸药','0.125');self.assertEqual(p['preview']['source_after'],'3959.875')
    def test_personnel_preserves_T_and_group_selection(self):
        p=self.service.plan({'kind':'personnel','source':'farstar','destination':'qrf','quantity':'10','personnel_group':'100'})
        self.assertEqual(p['state']['summary']['personnel']['voyager'],17193);self.assertEqual(p['state']['summary']['personnel']['shadow'],6044)
        self.assertEqual(p['book']['people']['qrf'][-1]['T'],100);self.accept(p)
        p=self.service.plan({'kind':'personnel','source':'qrf','destination':'farstar','quantity':'10','personnel_group':'100'})
        self.assertEqual(sum(c['quantity'] for c in p['book']['people']['qrf']),2653)
        self.assertEqual({c['T'] for c in p['book']['people']['qrf']},{70})
    def test_vessel_roundtrip_rebinds_shifted_roster_and_preserves_attributes(self):
        vid='VES-EXPLORER1';before=ships(self.service.state)[vid][1]
        p=self.service.plan({'kind':'vessels','vessel':vid,'destination':'shadow'})
        self.assertEqual(p['state']['shadow_fleet']['vessels_owned_total'],22)
        self.assertEqual(p['state']['summary']['ships']['voyager'],50)
        self.assertEqual(ships(p['state'])[vid][1]['science_lead'],before['science_lead'])
        self.accept(p);p=self.move(vid,'shadow:warehouse','SCV工程机器人',1)
        self.assertEqual(p['state']['shadow_fleet']['vessels'][vid]['fixed_engineering_science_assets']['scv'],39)
        self.accept(p);p=self.service.plan({'kind':'vessels','vessel':vid,'destination':'voyager'})
        self.assertEqual(len(ships(p['state'])),79);self.assertEqual(p['state']['shadow_fleet']['vessels_owned_total'],21)
        self.assertEqual(p['book']['locations'][vid]['fleet'],'voyager')
    def test_new_warehouse_starts_empty(self):
        p=self.service.plan({'kind':'warehouse','name':'测试仓','fleet':'shadow'})
        row=next(l for l in p['book']['locations'].values() if l['name']=='测试仓')
        self.assertEqual(p['book']['stock'][row['id']],{})

if __name__=='__main__':unittest.main()
