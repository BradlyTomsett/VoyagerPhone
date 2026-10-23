import hashlib
import json
from pathlib import Path
import unittest
from backend.source_library import SourceLibrary,clean

ROOT=Path(__file__).resolve().parents[1]/'seed'

class SourceLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.library=SourceLibrary(ROOT)

    def test_original_shop_and_people_are_present(self):
        summary=self.library.summary();cards={r['title']:r['text'] for r in summary['cards']}
        self.assertIn('270',cards['余火咖啡'])
        for name in ('莉娅·莫恩','格伦·萨克','妮卡·维尔','托马·里恩'):self.assertIn(name,cards['四名正式员工'])
        self.assertIn('55',cards['韩默·维斯']);self.assertIn('63',cards['伊沃'])
        self.assertIn('61',cards['马洛·柯恩']);self.assertIn('42',cards['雷托'])
        self.assertEqual(summary['history_archives'],22)
        self.assertGreater(summary['indexed_records'],1000)

    def test_every_requested_subject_is_retrievable(self):
        for topic in ('余火','熄炉-9','韩默','伊沃','马洛','雷托'):
            rows=self.library.search(topic,limit=30)['results']
            self.assertTrue(rows,topic)
            self.assertTrue(all(r['ref'] and r['source'] and r['as_of'] for r in rows))

    def test_context_is_bounded_and_contains_real_records(self):
        packet=self.library.context('余火店员工人数、都是谁、店铺面积，以及韩默、伊沃、马洛、雷托是谁？')
        text=json.dumps(packet,ensure_ascii=False)
        for word in ('270','莉娅·莫恩','韩默','伊沃','马洛','雷托'):self.assertIn(word,text)
        self.assertLessEqual(packet['bytes'],30000)
        self.assertTrue(packet['partial_retrieval'])
        self.assertEqual(packet['audience'],'commander_reference_only')

    def test_unposted_shop_day_stays_a_draft(self):
        rows=self.library.search('yu_huo_draft_close_83631210',limit=30)['results']
        target=[r for r in rows if 'yu_huo_draft_close_83631210' in r['path']]
        self.assertTrue(target)
        self.assertTrue(all(r['kind']=='草案或待核实' for r in target))

    def test_reading_never_writes_game_files_and_hidden_fields_stay_hidden(self):
        before=hashlib.sha256((ROOT/'state.json').read_bytes()).hexdigest()
        self.library.search('雷托',limit=10)
        self.assertEqual(before,hashlib.sha256((ROOT/'state.json').read_bytes()).hexdigest())
        out=clean({'visible':'yes','gm_private':'SYNTHETIC_SECRET','world_truth':'SYNTHETIC_SECRET','child':{'visibility':'gm','text':'SYNTHETIC_SECRET'}})
        self.assertNotIn('SYNTHETIC_SECRET',json.dumps(out))

    def test_original_cold_history_codec_is_searchable(self):
        result=self.library.search('灰烬帮',history=True,limit=30)
        self.assertTrue(any(r['source'].startswith('archives/') for r in result['results']))
        self.assertTrue(all(r['kind']=='历史归档' for r in self.library.history_rows))

if __name__=='__main__':unittest.main()
