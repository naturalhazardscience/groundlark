import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from pressure_pneumatics import tube,viscous_tube,transfer,evaluate,report


class PneumaticTests(unittest.TestCase):
    def test_low_frequency_limit_matches_poiseuille(self):
        r,l=tube(.01,.0012)
        z=viscous_tube([.01],.01,.0012,end_correction_radii=0)[0]
        self.assertAlmostEqual(z.real/r,1,delta=1e-6)
        self.assertAlmostEqual(z.imag/(2*np.pi*.01*l),4/3,delta=1e-5)
        self.assertTrue(np.all(viscous_tube(np.geomspace(.01,4400,100),.01,.0012).real>0))

    def test_reference_equalizes_and_short_circuit_destroys_signal(self):
        f=np.array([.00001,1,20,1000]);r,l=tube(.01,.0012)
        normal=transfer(f,[r,r],[l,l],[80e-6]*2,1e8,.002)
        short=transfer(f,[r,r],[l,l],[80e-6]*2,1,.002)
        self.assertLess(abs(normal[0]),.001)
        self.assertGreater(abs(normal[1]),.8)
        self.assertLess(abs(short[1]),1e-5)
        self.assertLess(abs(normal[-1]),abs(normal[1])*.01)

    def test_tube_restriction_and_reference_faults_do_not_pass(self):
        good=evaluate()
        blocked=evaluate(dimension_scale=.4)
        leaky_reference=evaluate(reference_ml=1)
        self.assertGreater(good['minimum_band_gain_db'],-3)
        self.assertLess(blocked['minimum_band_gain_db'],-6)
        self.assertLess(leaky_reference['minimum_band_gain_db'],-6)
        # An unfiltered short/small chamber arrangement must expose aliasing.
        self.assertGreater(evaluate(volume_ml=.01)['worst_alias_db'],-40)

    def test_conditional_corners_and_unknown_resistance_negative_control(self):
        result=report()
        self.assertEqual(result['corner_count'],256)
        self.assertTrue(result['conditional_design_pass'])
        self.assertLess(evaluate(sensor_resistance=1e7)['minimum_band_gain_db'],-6)

    def test_faster_acquisition_moves_first_alias_image(self):
        old=evaluate(100);new=evaluate(200)
        self.assertEqual(old['worst_alias_input_hz'],80)
        self.assertEqual(new['worst_alias_input_hz'],180)
        self.assertLess(new['worst_alias_db'],old['worst_alias_db']-15)


if __name__=='__main__':unittest.main()
