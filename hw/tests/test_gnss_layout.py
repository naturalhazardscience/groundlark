"""Native layout faults: a connected but remote bypass is not acceptable."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from gnss_checks import verify_board

class AntennaLayoutTests(unittest.TestCase):
 def load(self):
  import pcbnew as p
  return p.LoadBoard(str(Path(__file__).resolve().parents[1]/'groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.kicad_pcb'))
 def test_native_antenna(self):verify_board(self.load())
 def test_old_rf_width_fails_real_stack(self):
  import pcbnew as p
  from gnss_checks import rf_geometry
  b=self.load()
  for t in b.GetTracks():
   if t.GetNetname()=='GNSS_RF':t.SetWidth(p.FromMM(.3))
  with self.assertRaisesRegex(ValueError,'RF geometry'):rf_geometry(b)
 def test_bypass_omission(self):
  for ref in ['C151','C152']:
   b=self.load();next(f for f in b.GetFootprints() if f.GetReference()==ref).SetDNP(True)
   with self.subTest(ref=ref),self.assertRaises(AssertionError):verify_board(b)
 def test_limiter_pin_swap(self):
  b=self.load();fp=next(f for f in b.GetFootprints() if f.GetReference()=='U141')
  a=next(q for q in fp.Pads() if q.GetNumber()=='4');c=next(q for q in fp.Pads() if q.GetNumber()=='5')
  a.SetNumber('5');c.SetNumber('4')
  with self.assertRaises(ValueError):verify_board(b)
 def test_remote_rf_bypass(self):
  import pcbnew as p
  b=self.load();fp=next(f for f in b.GetFootprints() if f.GetReference()=='C151')
  fp.SetPosition(fp.GetPosition()+p.VECTOR2I(p.FromMM(10),0))
  with self.assertRaises((ValueError,AssertionError)):verify_board(b)
 def test_missing_rf_ground_stitch(self):
  import pcbnew as p
  b=self.load()
  for t in list(b.GetTracks()):
   if isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND' and abs(p.ToMM(t.GetPosition().x)-54)<.01 and abs(p.ToMM(t.GetPosition().y)-56.525)<.01:b.Delete(t)
  with self.assertRaises(ValueError):verify_board(b)
 def test_isolator_old_orientation(self):
  b=self.load();fp=next(f for f in b.GetFootprints() if f.GetReference()=='U43')
  next(q for q in fp.Pads() if q.GetNumber()=='2').SetNet(b.GetNetsByName()['PI_I2C_SDA'])
  with self.assertRaises(ValueError):verify_board(b)
