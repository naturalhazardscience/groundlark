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
  removed=0
  for t in list(b.GetTracks()):
   if isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND' and abs(p.ToMM(t.GetPosition().x)-54.9)<.01 and abs(p.ToMM(t.GetPosition().y)-60.925)<.01:
    b.Delete(t);removed+=1
  self.assertEqual(removed,1,'Ground-stitch fault must actually remove a via')
  with self.assertRaises(ValueError):verify_board(b)
 def test_old_front_branch_cannot_escape_rf_model(self):
  import pcbnew as p
  from gnss_checks import rf_geometry
  b=self.load()
  branch=next(t for t in b.GetTracks() if t.GetNetname()=='GNSS_ANT')
  branch.SetLayer(p.F_Cu)
  with self.assertRaisesRegex(ValueError,'changes layers'):rf_geometry(b)
 def test_extra_rf_stub_cannot_escape_model(self):
  import pcbnew as p
  from gnss_checks import rf_geometry
  b=self.load();t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(p.FromMM(54),p.FromMM(65.8)))
  t.SetEnd(p.VECTOR2I(p.FromMM(54),p.FromMM(70)));t.SetWidth(p.FromMM(.17));t.SetLayer(p.B_Cu)
  t.SetNet(b.FindNet('GNSS_ANT'));b.Add(t)
  with self.assertRaisesRegex(ValueError,'Unmodeled'):rf_geometry(b)
 def test_isolator_old_orientation(self):
  b=self.load();fp=next(f for f in b.GetFootprints() if f.GetReference()=='U43')
  next(q for q in fp.Pads() if q.GetNumber()=='2').SetNet(b.GetNetsByName()['PI_I2C_SDA'])
  with self.assertRaises(ValueError):verify_board(b)
