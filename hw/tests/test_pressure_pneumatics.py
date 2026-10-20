import sys
import unittest
import subprocess
import tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from pressure_pneumatics import tube,viscous_tube,transfer,evaluate,report


class PneumaticTests(unittest.TestCase):
    def test_independent_ngspice_vented_network(self):
        # Pressure=voltage, volume flow=current. Unequal elements prevent a
        # symmetric fixture from hiding an incorrectly connected stage/vent.
        text = """Independent vented acoustic network
Vambient ambient 0 AC 1
Rfirst ambient a 1.2meg
Lfirst a first 3200
Cfirst first 0 2.3n
Rsecond first b 1.8meg
Lsecond b sense 4100
Csense sense 0 1.9n
Rsensor sense reference 10meg
Creference reference 0 28n
Rvent ambient c 900meg
Lvent c reference 170000
.control
set wr_singlescale
set wr_vecnames
ac dec 8 .1 1000
let differential=v(sense)-v(reference)
wrdata pressure.txt differential
quit
.endc
.end
"""
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);(path/'pressure.cir').write_text(text)
            subprocess.run(['ngspice','-b','pressure.cir'],cwd=path,check=True,
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            rows=np.loadtxt(path/'pressure.txt',skiprows=1)
        f=rows[:,0];pressure=100000;gamma=1.4
        actual=transfer(f,[1.2e6,1.8e6],[3200,4100],
                        np.array([2.3e-9,1.9e-9])*gamma*pressure,
                        1e7,28e-9*gamma*pressure,pressure,gamma,
                        reference_admittance=1/(900e6+2j*np.pi*f*170000))
        np.testing.assert_allclose(actual,rows[:,1]+1j*rows[:,2],rtol=1e-7,atol=1e-9)

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

    def test_wide_resistance_envelope_and_old_network_negative_control(self):
        result=report()
        self.assertEqual(result['corner_count'],4096)
        self.assertEqual(result['interior_count'],101)
        self.assertTrue(result['conditional_design_pass'])
        self.assertFalse(result['validity']['manufacturer_resistance_bound_established'])
        self.assertGreater(evaluate(sensor_resistance=1e7)['minimum_band_gain_db'],-6)
        self.assertLess(evaluate(sensor_resistance=1e6)['minimum_band_gain_db'],-6)
        old=evaluate(sensor_resistance=1e7,parallel=1,volume_ml=80,reference_ml=2000)
        self.assertLess(old['minimum_band_gain_db'],-6)

    def test_parallel_bank_scaling_and_independent_vent(self):
        # Exact acoustic scaling: Z/N, V*N and Rs/N preserve transfer.
        r,l=tube(.01,.0012);f=np.geomspace(.1,400,40)
        a=transfer(f,[r,r],[l,l],[80e-6]*2,1e8,.002)
        b=transfer(f,[r/4,r/4],[l/4,l/4],[320e-6]*2,1e8/4,.008)
        np.testing.assert_allclose(a,b,rtol=1e-12,atol=1e-12)
        # The known vent equalizes the reference even when sensor flow tends
        # to zero. A sensor-only reference cannot provide this bound.
        f=[1e-7];vent_r,_=tube(.01,.0003)
        vented=transfer(f,[r,r],[l,l],[320e-6]*2,1e16,.004,reference_admittance=1/vent_r)
        sealed=transfer(f,[r,r],[l,l],[320e-6]*2,1e16,.004)
        self.assertLess(abs(vented[0]),.001);self.assertGreater(abs(sealed[0]),.99)

    def test_independent_stage_faults_and_reference_vent_short(self):
        for scale in ((.4,1),(1,.4)):
            self.assertLess(evaluate(dimension_scale=scale)['minimum_band_gain_db'],-6)
        self.assertLess(evaluate(vent_diameter_mm=3)['minimum_band_gain_db'],-6)
        with self.assertRaises(ValueError):evaluate(parallel=0)

    def test_faster_acquisition_moves_first_alias_image(self):
        old=evaluate(100);new=evaluate(200)
        self.assertEqual(old['worst_alias_input_hz'],80)
        self.assertEqual(new['worst_alias_input_hz'],180)
        self.assertLess(new['worst_alias_db'],old['worst_alias_db']-15)


if __name__=='__main__':unittest.main()
