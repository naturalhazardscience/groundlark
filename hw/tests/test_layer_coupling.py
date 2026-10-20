from pathlib import Path
import sys
import unittest,math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from layer_coupling import overlaps,parallel_overlaps,verify,review


class CouplingTests(unittest.TestCase):
    def segment(self,net,a,z):return dict(net=net,a=a,z=z,width=.125,id=net)
    def test_parallel_fault_and_perpendicular_control(self):
        a=self.segment('CLOCK',(0,0),(10,0))
        close=self.segment('INPUT',(9,.1),(1,.1))
        rows=parallel_overlaps([a],[close],.1088)
        self.assertAlmostEqual(rows[0]['length_mm'],8)
        with self.assertRaisesRegex(ValueError,'parallel signal'):verify(rows)
        cross=self.segment('INPUT',(5,-5),(5,5))
        radius=.125+3*.1088
        self.assertAlmostEqual(sum(r['length_mm'] for r in overlaps([a],[cross],.1088)),2*radius)
        self.assertAlmostEqual(sum(r['length_mm'] for r in overlaps([a],[close],.1088)),
                               8+2*math.sqrt(radius**2-.1**2))
        far=self.segment('INPUT',(0,1),(10,1))
        self.assertEqual(overlaps([a],[far],.1088),[])
    def test_native_layers(self):
        import pcbnew as p
        path=Path(__file__).resolve().parents[1]/'groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.kicad_pcb'
        before=path.read_bytes();board=p.LoadBoard(str(path));report=review(board)
        self.assertLessEqual(max(r['total_parallel_mm'] for r in report['parallel_pair_totals']),5)
        pair=next((r for r in report['signal_pair_totals'] if r['nets']==['IMU3_INT','SPI_MISO']),
                  dict(nets=['IMU3_INT','SPI_MISO'],proximity_mm=0.))
        # Independent midpoint integration checks the native union length.
        # Do not require a minimum coupled length: routing improvements must
        # remain free to reduce it.
        import numpy as np
        layers=[]
        for layer in ('In2.Cu','In3.Cu'):
            layers.append([t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'
                and t.GetLayer()==board.GetLayerID(layer) and t.GetNetname() in pair['nets']])
        xy=lambda q:np.array([p.ToMM(q.x),p.ToMM(q.y)])
        estimate=0.
        for track in layers[0]:
            a,z=xy(track.GetStart()),xy(track.GetEnd());length=np.linalg.norm(z-a)
            count=math.ceil(length/.001);points=a+(z-a)*((np.arange(count)+.5)/count)[:,None]
            covered=np.zeros(count,dtype=bool)
            for other in layers[1]:
                if other.GetNetname()==track.GetNetname():continue
                b,d=xy(other.GetStart()),xy(other.GetEnd())-xy(other.GetStart())
                fraction=np.clip(((points-b)@d)/(d@d),0,1)
                distance=np.linalg.norm(points-(b+fraction[:,None]*d),axis=1)
                covered|=distance<=(p.ToMM(track.GetWidth()+other.GetWidth())/2+3*.1088)
            estimate+=length*covered.mean()
        self.assertAlmostEqual(pair['proximity_mm'],estimate,delta=.02)
        self.assertEqual(before,path.read_bytes())

    def test_angled_interval_and_tessellation_union(self):
        a=self.segment('A',(0,0),(10,0));b=self.segment('B',(0,-1),(10,1))
        measure=lambda aa,bb:sum(r['length_mm'] for r in overlaps(aa,bb,.1088))
        expected=2*(.125+3*.1088)/math.sin(math.atan(.2))
        self.assertAlmostEqual(measure([a],[b]),expected)
        aa=[self.segment('A',(0,0),(5,0)),self.segment('A',(5,0),(10,0))]
        bb=[self.segment('B',(0,-1),(5,0)),self.segment('B',(5,0),(10,1))]
        self.assertAlmostEqual(measure(aa,bb),expected)
        # Duplicate or adjacent opposing pieces cannot double-count path length.
        self.assertAlmostEqual(measure(aa,bb+bb),expected)
        self.assertAlmostEqual(measure(aa,list(reversed(bb))),expected)
        from collections import Counter
        def bins(aa,bb):
            result=Counter()
            for r in overlaps(aa,bb,.1088):result[round(r['center_gap_mm'],6)]+=r['length_mm']
            return result
        whole,split=bins([a],[b]),bins(aa,bb)
        self.assertEqual(set(whole),set(split))
        for gap in whole:self.assertAlmostEqual(whole[gap],split[gap])

    def test_endpoint_proximity_and_same_net(self):
        a=self.segment('A',(0,0),(10,0));b=self.segment('B',(10.2,0),(11,0))
        self.assertAlmostEqual(sum(r['length_mm'] for r in overlaps([a],[b],.1088)),.125+3*.1088-.2)
        b['net']='A';self.assertEqual(overlaps([a],[b],.1088),[])
        with self.assertRaises(ValueError):overlaps([self.segment('A',(0,0),(0,0))],[b],.1088)
