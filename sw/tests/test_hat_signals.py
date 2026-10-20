"""End-to-end Pi driver signals and negative controls for the signal oracle."""
from copy import deepcopy
from io import BytesIO
from unittest.mock import patch
import unittest

from groundlark.hat_signals import PROFILE, run_bench, check_recording
from groundlark.recording import Reader, Writer
from groundlark.sensors import LSM6DSO, SCL3300
from groundlark.geophone import ADS122C04
from groundlark.pressure import SDP32
from groundlark_contract.validation import sht_crc


def altered(data, edit):
    """Re-encode valid CRCs, so failures come from signal validity, not framing."""
    reader = Reader(BytesIO(data))
    stream = BytesIO()
    writer = Writer(stream, reader.metadata)
    for arrived, message in reader:
        if isinstance(message, dict):
            fields = {k: v for k, v in message.items() if k not in ("code", "detail")}
            writer.event(message["code"], message["detail"], arrived, **fields)
        else:
            edit(message)
            writer.message(message, arrived)
    return stream.getvalue()


class HatSignalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.report = run_bench()

    def assert_check_fails(self, data, name):
        report = check_recording(data)
        self.assertFalse(report["passed"])
        self.assertFalse(next(c for c in report["checks"] if c["name"] == name)["passed"])

    def test_known_signal_runs_through_all_production_hat_drivers(self):
        # Spy on real methods rather than replacing them with model adapters.
        counts = dict(imu=0, tilt=0, geophone=0, pressure=0)
        def spy(original, key):
            def read(driver):
                counts[key] += 1
                return original(driver)
            return read
        with patch.object(LSM6DSO, "read", spy(LSM6DSO.read, "imu")), \
             patch.object(SCL3300, "read", spy(SCL3300.read, "tilt")), \
             patch.object(ADS122C04, "read", spy(ADS122C04.read, "geophone")), \
             patch.object(SDP32, "read", spy(SDP32.read, "pressure")):
            data, report = run_bench()
        self.assertTrue(report["passed"], report)
        self.assertEqual(counts, dict(imu=624, tilt=0, geophone=2640, pressure=801))
        self.assertEqual(data, self.data)
        self.assertEqual(len(report["checks"]), 12)
        self.assertEqual(report['samples'],4072)
        self.assertIn('SDP32',report['scope'])

    def test_infrasound_gain_status_and_temperature_faults_fail(self):
        for fault in ('gain','crc','temperature','scale'):
            def edit(m):
                if m.WhichOneof('body')=='batch' and m.batch.sensor_id==8:
                    for sample in m.batch.samples:
                        if sample.quality==2:continue
                        frame=bytearray(sample.pressure.sdp3x_response)
                        if fault=='gain':frame[:2]=(2*int.from_bytes(frame[:2],'big',signed=True)).to_bytes(2,'big',signed=True)
                        elif fault=='temperature':frame[3]^=1
                        elif fault=='scale':frame[7]^=1
                        for i in (0,3,6):frame[i+2]=sht_crc(frame[i:i+2])
                        if fault=='crc':frame[2]^=1
                        sample.pressure.sdp3x_response=bytes(frame)
            with self.subTest(fault=fault):
                if fault in ('crc','scale'):
                    with self.assertRaisesRegex(ValueError,'SDP32'):
                        check_recording(altered(self.data,edit))
                else:self.assert_check_fails(altered(self.data,edit),'Infrasound raw response & waveform')

    def test_infrasound_missing_sample_fails_quality(self):
        def edit(m):
            if m.WhichOneof('body')=='batch' and m.batch.sensor_id==8 and m.batch.samples[0].sequence==1:
                m.batch.samples[0].ClearField('pressure')
                m.batch.samples[0].quality=2
        self.assert_check_fails(altered(self.data,edit),'Inventory & quality')

    def test_unaveraged_pressure_values_fail_even_with_valid_crc(self):
        import math
        def edit(m):
            if m.WhichOneof('body')=='batch' and m.batch.sensor_id==8:
                for sample in m.batch.samples:
                    if sample.quality!=1:continue
                    word=round(120*math.sin(10*math.pi*sample.time.acquisition_ns/1e9)).to_bytes(2,'big',signed=True)
                    sample.pressure.sdp3x_response=word+bytes([sht_crc(word)])+sample.pressure.sdp3x_response[3:]
        self.assert_check_fails(altered(self.data,edit),'Infrasound raw response & waveform')

    def test_consistent_but_wrong_rocking_motion_is_rejected(self):
        profile = deepcopy(PROFILE)
        profile["initial"]["orientation_deg"] = [0, 0, 0]
        with patch("groundlark.hat_signals.PROFILE", profile):
            data, _ = run_bench()
        self.assert_check_fails(data, "Known roll waveform")

    def test_wrong_gain_fails_even_with_valid_framing(self):
        def edit(m):
            if m.WhichOneof("body") == "batch" and m.batch.sensor_id <= 4:
                for s in m.batch.samples:
                    s.imu.acceleration.x *= 2
        self.assert_check_fails(altered(self.data, edit), "IMU frequency, gain & phase")

    def test_wrong_frequency_fails(self):
        profile = deepcopy(PROFILE)
        profile["initial"]["acceleration_m_s2"][0]["frequency_hz"] = 3
        with patch("groundlark.hat_signals.PROFILE", profile):
            data, _ = run_bench()
        self.assert_check_fails(data, "IMU frequency, gain & phase")

    def test_inverted_signal_phase_fails(self):
        def edit(m):
            if m.WhichOneof("body") == "batch" and m.batch.sensor_id <= 4:
                for s in m.batch.samples:
                    s.imu.acceleration.x *= -1
        self.assert_check_fails(altered(self.data, edit), "IMU frequency, gain & phase")

    def test_stuck_sensor_breaks_coherence(self):
        def edit(m):
            if m.WhichOneof("body") == "batch" and m.batch.sensor_id == 3:
                for s in m.batch.samples:
                    s.imu.acceleration.x = 0
        self.assert_check_fails(altered(self.data, edit), "Three-IMU coherence")

    def test_gyro_scale_error_breaks_integrated_roll(self):
        def edit(m):
            if m.WhichOneof("body") == "batch" and m.batch.sensor_id <= 4:
                for s in m.batch.samples:
                    s.imu.angular_rate.x = round(s.imu.angular_rate.x * .9)
        self.assert_check_fails(altered(self.data, edit), "Gyro / gravity consistency")

    def test_gravity_scale_error_fails(self):
        def edit(m):
            if m.WhichOneof("body") == "batch" and m.batch.sensor_id <= 4:
                for s in m.batch.samples:
                    s.imu.acceleration.z = round(s.imu.acceleration.z * .99)
        self.assert_check_fails(altered(self.data, edit), "Gravity magnitude")

    def test_geophone_gain_error_fails(self):
        def edit(m):
            if m.WhichOneof("body") == "batch" and m.batch.sensor_id == 9:
                for sample in m.batch.samples: sample.geophone.counts *= -1
        self.assert_check_fails(altered(self.data, edit), "Geophone gain, phase & counter")

    def test_timestamp_shift_fails(self):
        def edit(m):
            if m.WhichOneof("body") == "batch":
                for s in m.batch.samples:
                    s.time.acquisition_ns += 2_000_000
        self.assert_check_fails(altered(self.data, edit), "Timing & continuity")

    def test_missing_sample_cannot_be_a_pass(self):
        def edit(m):
            if m.WhichOneof("body") == "batch" and m.batch.sensor_id == 1:
                s = m.batch.samples[0]
                if s.sequence == 1:
                    s.ClearField("imu")
                    s.quality = 2
        self.assert_check_fails(altered(self.data, edit), "Inventory & quality")


if __name__ == "__main__":
    unittest.main()
