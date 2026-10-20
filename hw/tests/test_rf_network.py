import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from simulate_signal_integrity import transmission,scattering,rf_network,shunt


class RFTests(unittest.TestCase):
    def test_matched_line_and_shunt_analytical_reference(self):
        s11,s21=scattering(transmission(50,3.2,100,1.57542e9))
        self.assertLess(abs(s11),1e-14);self.assertAlmostEqual(abs(s21),1)
        y=1j*.01;s11,s21=scattering(shunt(y))
        self.assertAlmostEqual(abs(s11),abs(-y*50/(2+y*50)))
        self.assertAlmostEqual(abs(s11)**2+abs(s21)**2,1)

    def test_nominal_network_and_high_capacitance_fault(self):
        args=(1.57542e9,46.2,3.425,{'GNSS_ANT':1.92,'GNSS_RF':1.87},{'GNSS_ANT':.404,'GNSS_RF':.685})
        nominal=rf_network(*args,diode_pf=.4)
        self.assertGreater(nominal['return_loss_db'],10)
        self.assertLess(nominal['insertion_loss_db'],.5)
        fault=rf_network(*args,diode_pf=5)
        self.assertLess(fault['return_loss_db'],10)
        self.assertGreater(fault['insertion_loss_db'],1)

    def test_passivity_across_frequency(self):
        for f in np.geomspace(1e6,4e9,50):
            result=rf_network(f,46,3.4,{'GNSS_ANT':1.92,'GNSS_RF':1.87},{'GNSS_ANT':.4,'GNSS_RF':.68})
            self.assertGreaterEqual(result['insertion_loss_db'],0)

    def test_native_component_change_cannot_reuse_old_model(self):
        import pcbnew as p
        from simulate_signal_integrity import rf_review
        from project_paths import board_dir
        board=p.LoadBoard(str(board_dir('groundlark-daqhat-01')/'groundlark-daqhat-01.kicad_pcb'))
        next(f for f in board.GetFootprints() if f.GetReference()=='C148').SetValue('4.7p')
        with self.assertRaisesRegex(ValueError,'native C148'):rf_review(board)
