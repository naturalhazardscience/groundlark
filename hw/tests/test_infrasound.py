import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from infrasound_checks import PINS, PADS, NC, MPN, verify
import copy


class InfrasoundTests(unittest.TestCase):
    def setUp(self):
        self.pins={**PINS, ('J1','18'):'GNSS_PPS',('J1','31'):'PI_SHUTDOWN_N',('J1','33'):'PI_HALTED'}
        self.pins.update({('U23',str(n)):'NC_'+str(n) for n in NC})
        self.pads=copy.deepcopy(PADS)

    def check(self, **changes):
        args=dict(pins=self.pins,pads=self.pads,pose=(0,False),mpn=MPN,dnp=False)
        args.update(changes)
        return verify(**args)

    def test_rejects_wrong_supply_and_swapped_bus(self):
        self.assertEqual(self.check()['additional_pi_pins'],0)
        for key in PINS:
            for net in ('PI_5V','FPGA_3V3','PI_I2C_SDA','WRONG'):
                with self.subTest(key=key,net=net),self.assertRaises(ValueError):
                    self.check(pins={**self.pins,key:net})

    def test_rejects_reversed_package_and_wrong_variant(self):
        for pose in ((90,False),(0,True),(180,False)):
            with self.assertRaises(ValueError):self.check(pose=pose)
        with self.assertRaises(ValueError):self.check(pads={**self.pads,'1':self.pads['4'],'4':self.pads['1']})
        with self.assertRaises(ValueError):self.check(mpn='SDP31-500PA-TR-250PCS')
        with self.assertRaises(ValueError):self.check(dnp=True)

    def test_reserved_pads_and_address_must_not_float_or_short(self):
        for n in NC:
            with self.assertRaises(ValueError):self.check(pins={**self.pins,('U23',str(n)):'GND'})
        with self.assertRaises(ValueError):self.check(pins={**self.pins,('U23','9'):'SENS_3V3'})
        with self.assertRaises(ValueError):self.check(pads={**self.pads,'17':self.pads['17'][:1]})

    def test_rejects_consumed_power_control_pin(self):
        for pin in ('18','31','33'):
            with self.assertRaises(ValueError):self.check(pins={**self.pins,('J1',pin):'I2C_SDA'})


class NativePressureGeometryTests(unittest.TestCase):
    def test_actual_peg_paste_and_vent_with_fault_injection(self):
        import pcbnew as p
        from infrasound_checks import verify_mechanics
        path=Path(__file__).resolve().parents[1]/'groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.kicad_pcb'
        before=path.read_bytes()
        for fault in ('none','drill','paste','vent','chamfer'):
            board=p.LoadBoard(str(path))
            fp=next(f for f in board.GetFootprints() if f.GetReference()=='U23')
            if fault=='drill':
                next(a for a in fp.Pads() if a.GetAttribute()==p.PAD_ATTRIB_NPTH).SetDrillSize(p.VECTOR2I(p.FromMM(.6),p.FromMM(.6)))
            elif fault=='paste':
                next(a for a in fp.Pads() if not a.GetNumber() and a.GetLayerSet().Contains(p.F_Paste)).SetSize(p.VECTOR2I(p.FromMM(1.8),p.FromMM(.9)))
            elif fault=='vent':next(iter(fp.Zones())).SetDoNotAllowCopperPour(False)
            elif fault=='chamfer':
                next(a for a in fp.Pads() if a.GetNumber()=='17' and a.GetChamferPositions()).SetChamferPositions(0)
            with self.subTest(fault=fault):
                if fault=='none':self.assertEqual(verify_mechanics(board)['locating_pegs'],3)
                else:
                    with self.assertRaises(ValueError):verify_mechanics(board)
        self.assertEqual(path.read_bytes(),before)
