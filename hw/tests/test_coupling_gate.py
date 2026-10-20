"""Independent voltage-allocation faults, including failure evidence persistence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from simulate_signal_integrity import coupling_acceptance,save_report


class CouplingGateTests(unittest.TestCase):
    def rows(self,voltage):return [dict(nets=['CLOCK','INPUT'],worst=dict(peak_V=voltage))]

    def test_voltage_boundary_and_invalid_results(self):
        self.assertTrue(coupling_acceptance(self.rows(.2))['all_pairs_meet_target'])
        for voltage in (.200001,float('nan'),float('inf'),-.1):
            with self.subTest(voltage=voltage):
                self.assertFalse(coupling_acceptance(self.rows(voltage))['all_pairs_meet_target'])
        with self.assertRaises(ValueError):coupling_acceptance([])

    def test_failure_is_saved_and_raises_even_when_rf_passes(self):
        report=dict(rf=dict(all_corners_meet_targets=True),
                    coupling=dict(acceptance=coupling_acceptance(self.rows(.3))))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'result.json'
            with self.assertRaisesRegex(ValueError,'crosstalk allocation failed'):save_report(report,path)
            self.assertEqual(json.loads(path.read_text()),report)

    def test_good_coupling_does_not_mask_bad_rf(self):
        report=dict(rf=dict(all_corners_meet_targets=False),
                    coupling=dict(acceptance=coupling_acceptance(self.rows(.1))))
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'RF design envelope failed'):
                save_report(report,Path(temp)/'result.json')
