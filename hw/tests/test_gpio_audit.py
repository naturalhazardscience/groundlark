"""Fault injection for GPIO mapping: exercise known wiring hazards."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import gpio_audit as audit
import pcbnew

class GPIOFaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        board = pcbnew.LoadBoard(str(audit.ROOT / 'hw/groundlark-fpga-hat/layout/trenz_hat/trenz_hat.kicad_pcb'))
        cls.original = {(f.GetReference(),p.GetNumber()):p.GetNetname()
                        for f in board.GetFootprints() for p in f.Pads() if p.GetNumber()}

    def setUp(self):
        self.pins = self.original.copy()

    def test_valid_compiled_circuit(self):
        report=audit.check(self.pins)
        self.assertEqual(report['exposed_gpio'],0)
        self.assertEqual(report['unused_user_gpio'],149)

    def test_atomic_footprint_uuid_repair(self):
        from kicad_support import unique_ids
        b=pcbnew.BOARD()
        original=pcbnew.FootprintLoad(str(audit.ROOT/'hw/shared/elec'),'Package_SO__TSSOP-16_4.4x5mm_P0.65mm')
        for ref in ('U100','U101'):
            f=pcbnew.FOOTPRINT(original)
            f.SetReference(ref);b.Add(f)
        ids=lambda:[q.m_Uuid.AsString() for f in b.GetFootprints() for q in f.Pads()]
        self.assertNotEqual(len(ids()),len(set(ids())))
        unique_ids(b)
        repaired=ids()
        self.assertEqual(len(repaired),len(set(repaired)))
        unique_ids(b)
        self.assertEqual(ids(),repaired)

    def test_save_preserves_project_rules(self):
        import json, tempfile
        from kicad_support import save_board
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'rules.kicad_pcb'
            project=path.with_suffix('.kicad_pro')
            content=json.dumps({'net_settings':{'classes':[{'name':'Default','clearance':0.15}]}}).encode()
            project.write_bytes(content)
            save_board(path,pcbnew.BOARD())
            self.assertEqual(project.read_bytes(),content)

    def test_old_grounded_gpio(self):
        self.pins['J80','32'] = 'GND'  # Module JM1.31, B16_L22_P.
        with self.assertRaises(AssertionError): audit.check(self.pins)

    def test_old_grounded_ethernet(self):
        self.pins['J80','11'] = 'GND'  # Module JM1.12, PHY ETH_RD_N.
        with self.assertRaises(AssertionError): audit.check(self.pins)

    def test_reversed_mating_parity(self):
        self.pins['J81','21'],self.pins['J81','22'] = self.pins['J81','22'],self.pins['J81','21']
        with self.assertRaises(AssertionError): audit.check(self.pins)

    def test_missing_quad_connection(self):
        self.pins['U101','5'] = 'UNCONNECTED'
        with self.assertRaises(AssertionError): audit.check(self.pins)

    def test_wrong_reference_voltage(self):
        self.pins['U100','16'] = 'PI_5V'
        with self.assertRaises(AssertionError): audit.check(self.pins)

    def test_trenz_mode_and_noseq_are_distinct_from_sequence_enable(self):
        for key,net in ((('EXTRA','1'),'FPGA_MODE'),(('JP80','1'),'FPGA_NOSEQ'),
                        (('R81','2'),'FPGA_3V3'),(('J80','31'),'GND')):
            self.pins=self.original.copy();self.pins[key]=net
            with self.subTest(pin=key),self.assertRaises(AssertionError):audit.check(self.pins)

    def test_unintended_shared_gpio(self):
        self.pins['EXTRA','1'] = self.pins['J80','32']
        with self.assertRaises(AssertionError): audit.check(self.pins)

    def test_switch_bypass_is_rejected(self):
        self.pins['J84','1'] = 'JTAG_TCK'
        with self.assertRaises(AssertionError): audit.check(self.pins)

    def test_wrong_gate_pinout_is_rejected(self):
        self.pins['U103','2'],self.pins['U103','3'] = self.pins['U103','3'],self.pins['U103','2']
        with self.assertRaises(AssertionError): audit.check(self.pins)

    def test_missing_safe_start_bias_is_rejected(self):
        self.pins['R107','2'] = 'PI_3V3'
        with self.assertRaises(AssertionError): audit.check(self.pins)

    def test_parking_path_must_not_ground_pi_output(self):
        self.pins['U101','3'] = 'GND'
        with self.assertRaises(AssertionError): audit.check(self.pins)

if __name__ == '__main__': unittest.main()
