"""Independent tone measurements through the real driver and modeled bus."""
import math
import unittest
from groundlark.pressure import SETTINGS
from groundlark.pressure_response import boxcar, report
from groundlark.stimulus import Scenario
from groundlark.virtual_hat import VirtualDriver


class PressureResponseTests(unittest.TestCase):
    def tone(self, frequency, amplitude):
        now = [0]
        scenario = Scenario({'version':1, 'initial':{'pressure_pa':
                            {'amplitude':amplitude, 'frequency_hz':frequency}}})
        device = VirtualDriver(8, scenario, lambda:now[0])
        device.configure(SETTINGS)
        points = []
        for i in range(1, 401):
            now[0] = i * 10_000_000
            frame = device.read().raw['sdp3x_response']
            points.append(int.from_bytes(frame[:2], 'big', signed=True)/240)
        alias = frequency if frequency < 50 else 100-frequency
        sine = 2/len(points)*sum(v*math.sin(2*math.pi*alias*(i+1)/100) for i,v in enumerate(points))
        cosine = 2/len(points)*sum(v*math.cos(2*math.pi*alias*(i+1)/100) for i,v in enumerate(points))
        return math.hypot(sine,cosine), math.degrees(math.atan2(cosine,sine))

    def test_landslide_band_sub_pascal_gain_and_phase(self):
        for amplitude in (.05, .1, .5):
            for f in (1, 5, 12.5, 20):
                with self.subTest(pa=amplitude, hz=f):
                    gain, phase = self.tone(f, amplitude)
                    # Continuous rectangular integral is independent of the
                    # discrete bus implementation. Allow two quantization LSBs.
                    expected = amplitude * math.sin(math.pi*f/100)/(math.pi*f/100)
                    self.assertAlmostEqual(gain, expected, delta=2/240)
                    self.assertAlmostEqual(phase, -360*f*.00475, delta=3)

    def test_out_of_band_tone_exposes_alias_not_false_rejection(self):
        gain, _ = self.tone(80, .5)
        self.assertGreater(gain, .10)  # 80 Hz aliases to 20 Hz: not a complete AA filter.
        self.assertLess(gain, .13)
        self.assertEqual(boxcar(80)['aliased_hz'], 20)

    def test_averaging_does_not_hide_injected_saturation(self):
        now=[0]
        device=VirtualDriver(8,Scenario(),lambda:now[0]);device.configure(SETTINGS)
        device.model.faults[1]='saturation'
        now[0]=10_000_000
        self.assertEqual(device.read().quality,3)

    def test_model_profile_and_oscillator_limits(self):
        result = report()
        self.assertEqual(result['band_hz'], (1,20))
        self.assertIsNone(result['required_noise_floor_pa'])
        self.assertFalse(result['qualified'])
        for rate in (1800,2000,2200):
            self.assertAlmostEqual(boxcar(0,rate)['gain'],1)
            self.assertLess(abs(boxcar(100,rate)['gain']),1e-12)
            self.assertGreater(boxcar(20,rate)['gain_db'],-.59)
        for changes in ({'pressure_measurement_command':0x361e},{'period_ns':20_000_000}):
            with self.assertRaises(ValueError):report(dict(SETTINGS,**changes))
        for f,rate,read in ((float('nan'),2000,100),(1,1700,100),(1,2000,25),(1,2000,101)):
            with self.assertRaises(ValueError):boxcar(f,rate,read)
