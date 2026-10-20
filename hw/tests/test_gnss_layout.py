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
 def void(self,b,box):
  import pcbnew as p
  layer=b.GetLayerID('In4.Cu');cut=p.SHAPE_POLY_SET();cut.NewOutline()
  x,y,z,w=box
  for a,c in ((x,y),(z,y),(z,w),(x,w)):cut.Append(p.FromMM(a),p.FromMM(c))
  removed=0
  for zone in b.Zones():
   if zone.GetNetname()=='GND' and zone.IsOnLayer(layer):
    polygon=p.SHAPE_POLY_SET(zone.GetFilledPolysList(layer));area=polygon.Area()
    polygon.BooleanSubtract(cut);removed+=area-polygon.Area()
    zone.SetFilledPolysList(layer,polygon)
  self.assertGreater(removed,0,'Fault must remove actual filled reference copper')
 def test_sma_return_void_inside_old_exemption(self):
  from gnss_checks import rf_geometry
  b=self.load()
  # 1.15 mm from the launch: inside the former blanket 1.2 mm skip.
  self.void(b,(53.97,64.62,54.03,64.67))
  with self.assertRaisesRegex(ValueError,'return annulus void'):rf_geometry(b)
 def test_reference_void_away_from_connector(self):
  from gnss_checks import rf_geometry
  b=self.load();self.void(b,(57.48,66.10,57.57,66.18))
  with self.assertRaisesRegex(ValueError,'reference plane void'):rf_geometry(b)
 def test_unreferenced_branches_reported(self):
  from gnss_checks import rf_geometry
  r=rf_geometry(self.load());rows={r['role']:r for r in r['tracks']}
  self.assertTrue(rows['ESD']['fully_inside_antipad'])
  self.assertTrue(rows['BIAS']['fully_inside_antipad'])
  self.assertEqual(rows['ESD']['reference_samples_checked'],0)
  self.assertGreater(r['sma_return_annulus_samples'],1900)
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
