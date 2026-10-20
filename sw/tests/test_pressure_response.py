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
        for i in range(1, 801):
            now[0] = i * 5_000_000
            frame = device.read().raw['sdp3x_response']
            points.append(int.from_bytes(frame[:2], 'big', signed=True)/240)
        alias = abs((frequency+100)%200-100)
        sine = 2/len(points)*sum(v*math.sin(2*math.pi*alias*(i+1)/200) for i,v in enumerate(points))
        cosine = 2/len(points)*sum(v*math.cos(2*math.pi*alias*(i+1)/200) for i,v in enumerate(points))
        return math.hypot(sine,cosine), math.degrees(math.atan2(cosine,sine))

    def test_landslide_band_sub_pascal_gain_and_phase(self):
        for amplitude in (.05, .1, .5):
            for f in (1, 5, 12.5, 20):
                with self.subTest(pa=amplitude, hz=f):
                    gain, phase = self.tone(f, amplitude)
                    # Continuous rectangular integral is independent of the
                    # discrete bus implementation. Allow two quantization LSBs.
                    expected = amplitude * math.sin(math.pi*f/200)/(math.pi*f/200)
                    self.assertAlmostEqual(gain, expected, delta=2/240)
                    self.assertAlmostEqual(phase, -360*f*.00225, delta=3)

    def test_out_of_band_tone_exposes_alias_not_false_rejection(self):
        # The previous 80 -> 20 Hz alias is outside the research band now.
        self.assertEqual(boxcar(80)['aliased_hz'],80)
        gain, _ = self.tone(180, .5)
        self.assertGreater(gain, .05)  # The new first image still needs pneumatic AA.
        self.assertLess(gain, .06)
        self.assertEqual(boxcar(180)['aliased_hz'],20)

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
            self.assertLess(abs(boxcar(200,rate)['gain']),1e-12)
            self.assertGreater(boxcar(20,rate)['gain_db'],-.15)
        for changes in ({'pressure_measurement_command':0x361e},{'period_ns':20_000_000}):
            with self.assertRaises(ValueError):report(dict(SETTINGS,**changes))
        for f,rate,read in ((float('nan'),2000,100),(1,1700,100),(1,2000,25),(1,2000,101)):
            with self.assertRaises(ValueError):boxcar(f,rate,read)

    def test_jittered_reads_preserve_windows_and_band_tone(self):
        now=[0];frequency=20;amplitude=.5
        scenario=Scenario({'version':1,'initial':{'pressure_pa':
            {'amplitude':amplitude,'frequency_hz':frequency}}})
        device=VirtualDriver(8,scenario,lambda:now[0]);device.configure(SETTINGS)
        previous=0
        for i in range(1,401):
            # Alternating 1 ms delay is a coherent hostile scheduler pattern.
            now[0]=i*5_000_000+(1_000_000 if i%2 else 0)
            reading=device.read();raw=reading.raw
            self.assertEqual(raw['read_interval_min_ns'],now[0]-previous)
            self.assertEqual(raw['read_interval_max_ns'],now[0]-previous)
            start,end=previous/1e9,now[0]/1e9;w=2*math.pi*frequency
            integral=amplitude*(math.cos(w*start)-math.cos(w*end))/(w*(end-start))
            measured=int.from_bytes(raw['sdp3x_response'][:2],'big',signed=True)/240
            # Independent continuous integral; allow one internal half-tick
            # phase plus two quantization counts, not an arbitrary jitter pass.
            self.assertAlmostEqual(measured,integral,delta=amplitude*w*.00025+2/240)
            previous=now[0]
