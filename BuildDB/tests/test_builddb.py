import unittest
from pathlib import Path
from BuildDB.parser import parse_courses, subjects
from BuildDB.relations import analyze, link_courses
from BuildDB.client import candidate_terms
from datetime import date

HTML = (Path(__file__).parent / 'fixtures/elec3400.html').read_text()


class ParserTests(unittest.TestCase):
    def test_attachment(self):
        c = parse_courses(HTML)['ELEC3400']
        self.assertEqual([c['Meta'][k] for k in ('Quota', 'Enroll', 'Waitlist')], [80, 74, 14])
        self.assertEqual(len(c['Data']['Labs']), 4)
        self.assertEqual(len(c['Data']['Tutorial']), 2)
        self.assertEqual(c['Data']['Lecture']['L1']['Instructor'], ['YUE, Chik Patrick'])
        self.assertFalse(c['Meta']['Consent'])

    def test_flags_suffix_and_popup(self):
        h = HTML.replace('ELEC 3400', 'ENGG 3961J').replace('>80</td>', '><span>80</span><div class="quotadetail">Quota/Enrol/Avail 20/10/10</div></td>')
        h = h.replace('<div class="course">', '<div class="course"><div class="popup consent">Instructor Consent Required</div><span>Common Core (A) for 30-credit prog in 22-24</span><span>Common Core (UxOP-UROP) for 30-cr prog in 26</span>')
        c = parse_courses(h)['ENGG3961J']
        self.assertTrue(c['Meta']['Consent'])
        self.assertEqual(c['CC'], {'CC22': {'A': True}, 'CC26': {'UxOP-UROP': True}})
        self.assertEqual(c['Meta']['Quota'], 80)

    def test_rowspan_and_other_sections(self):
        h = '''<div class="course"><div class="subject">TEST 1000 - Test (1 unit)</div><table class="sections"><tr><th>Section</th><th>Instructor</th><th>Quota</th><th>Enrol</th><th>Avail</th><th>Wait</th></tr><tr><td rowspan="2">L1 (123)</td><td>A</td><td rowspan="2">10</td><td rowspan="2">8</td><td rowspan="2">2</td><td rowspan="2">0</td></tr><tr><td>B</td></tr><tr><td>R1 (124)</td><td></td><td>1</td><td>1</td><td>0</td><td>0</td></tr><tr><td>SEM1 (125)</td><td></td><td>2</td><td>1</td><td>1</td><td>0</td></tr></table></div>'''
        c = parse_courses(h)['TEST1000']
        self.assertEqual(c['Meta']['Quota'], 10)
        self.assertEqual(c['Data']['Lecture']['L1']['Instructor'], ['A', 'B'])
        self.assertIn('R1', c['Data']['Research'])
        self.assertIn('SEM1', c['Data']['Others'])

    def test_discovery(self):
        self.assertEqual(subjects('<div class="depts"><a class="ug" href="/wcq/cgi-bin/2610/subject/COMP">COMP</a><a class="pg" href="/wcq/cgi-bin/2610/subject/ACCT">ACCT</a></div>'), ['COMP'])
        self.assertEqual(candidate_terms(date(2026, 9, 7)), ['2610', '2620', '2540', '2530', '2520'])

    def test_relations(self):
        result = analyze('(ELEC3310 OR ELEC2350) AND ENGG3961J')
        self.assertIn('AND', result['Expression'])
        self.assertIn('OR', result['Expression']['AND'][0])
        self.assertEqual(analyze('Grade C in ELEC3310')['Expression'], {'Text': 'Grade C in ELEC3310'})
        db = parse_courses(HTML)
        db.update(parse_courses(HTML.replace('ELEC 3400', 'ELEC 2400').replace('<td>ELEC 2400</td>', '<td></td>')))
        link_courses(db)
        link_courses(db)
        self.assertEqual(db['ELEC2400']['Meta']['Pre-Requisite-of'], ['ELEC3400'])


if __name__ == '__main__':
    unittest.main()
