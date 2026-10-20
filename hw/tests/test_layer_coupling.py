from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from layer_coupling import overlaps,verify,review


class CouplingTests(unittest.TestCase):
    def segment(self,net,a,z):return dict(net=net,a=a,z=z,width=.125,id=net)
    def test_parallel_fault_and_perpendicular_control(self):
        a=self.segment('CLOCK',(0,0),(10,0))
        close=self.segment('INPUT',(9,.1),(1,.1))
        rows=overlaps([a],[close],.1088)
        self.assertAlmostEqual(rows[0]['length_mm'],8)
        with self.assertRaisesRegex(ValueError,'parallel signal'):verify(rows)
        cross=self.segment('INPUT',(5,-5),(5,5))
        self.assertEqual(overlaps([a],[cross],.1088),[])
        far=self.segment('INPUT',(0,1),(10,1))
        self.assertEqual(overlaps([a],[far],.1088),[])
    def test_native_layers(self):
        import pcbnew as p
        path=Path(__file__).resolve().parents[1]/'groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.kicad_pcb'
        before=path.read_bytes();report=review(p.LoadBoard(str(path)))
        self.assertLessEqual(max(r['total_parallel_mm'] for r in report['signal_pair_totals']),5)
        self.assertEqual(before,path.read_bytes())
