"""SDP3x v1.1 protocol vectors and wrong-device/corrupt-frame faults."""
import unittest
from groundlark.pressure import SDP32, SETTINGS, words
from groundlark_contract.validation import sht_crc, validate
from groundlark import messages
from groundlark.calibration import raw_values
from groundlark.workbench import project_sample
from groundlark.sensors import DataGap, NotReady

IDENTITY = bytes.fromhex('03019d0201690123a045675389ab77cdef84')
ZERO = bytes.fromhex('00008113880100f003')
NEGATIVE = bytes.fromhex('a2409af8306b00f003')  # -24000 counts, -2000 temperature.


class Bus:
    def __init__(self, identity=IDENTITY, sample=ZERO):
        self.identity, self.sample, self.calls = identity, sample, []
        self.closed = False

    def exchange(self, address, write, count):
        self.calls.append((address, write.hex(), count))
        if count == 18: return self.identity
        if count == 9: return self.sample
        return b''

    def close(self): self.closed = True


class SDP32Tests(unittest.TestCase):
    def test_average_window_bounds_long_read_and_recovery(self):
        now=[0]; bus=Bus(); device=SDP32(bus,lambda _:None,clock_ns=lambda:now[0])
        device.configure(SETTINGS)
        with self.assertRaises(NotReady):device.read()
        now[0]=10_000_000
        reading=device.read()
        self.assertEqual(reading.raw['read_interval_min_ns'],10_000_000)
        self.assertEqual(reading.raw['read_interval_max_ns'],10_000_000)
        frame=messages.batch('hat',1,8,1,now[0],reading.raw,dropped=None)
        validate(frame)
        self.assertFalse(frame.batch.HasField('dropped_before'))
        now[0]=40_000_001
        with self.assertRaisesRegex(DataGap,'1-25 ms'):device.read()
        now[0]+=10_000_000
        self.assertEqual(device.read().raw['sdp3x_response'],ZERO)
        self.assertEqual(sum(write=='3615' for _,write,_ in bus.calls),1)

    def test_crc_failure_makes_next_window_unknown_without_device_reset(self):
        now=[0]; bus=Bus(); device=SDP32(bus,lambda _:None,clock_ns=lambda:now[0])
        device.configure(SETTINGS);now[0]=10_000_000;bus.sample=bytes(9)
        with self.assertRaises(OSError):device.read()
        bus.sample=ZERO;now[0]+=10_000_000
        with self.assertRaisesRegex(DataGap,'unknown'):device.read()
        now[0]+=10_000_000
        self.assertEqual(device.read().raw['read_interval_min_ns'],10_000_000)
        self.assertEqual(sum(write=='3ff9' for _,write,_ in bus.calls),1)

    def test_transaction_duration_and_clock_regression_do_not_hide_invalid_windows(self):
        ticks=iter((0, 100_000, 10_000_000, 10_200_000, 9_000_000, 9_100_000,
                    19_000_000, 19_100_000, 29_000_000, 45_000_000))
        device=SDP32(Bus(),lambda _:None,clock_ns=lambda:next(ticks))
        device.configure(SETTINGS)
        reading=device.read()
        self.assertEqual((reading.raw['read_interval_min_ns'],reading.raw['read_interval_max_ns']),
                         (9_900_000,10_200_000))
        with self.assertRaises(DataGap):device.read()
        self.assertEqual(device.read().raw['read_interval_max_ns'],10_100_000)
        with self.assertRaises(DataGap):device.read()

    def test_configuration_and_interval_metadata_preserve_legacy_absence(self):
        current=messages.configuration('hat',1,[SETTINGS])
        self.assertEqual(current.configuration.sensors[0].pressure_measurement_command,0x3615)
        legacy=dict(SETTINGS);del legacy['pressure_measurement_command']
        validate(messages.configuration('hat',1,[legacy]))
        with self.assertRaises(ValueError):messages.configuration('hat',1,[dict(SETTINGS,pressure_measurement_command=0x3603)])
        for fields in (dict(read_interval_min_ns=0),dict(read_interval_min_ns=10,read_interval_max_ns=10),
                       dict(read_interval_min_ns=10_000_000,read_interval_max_ns=26_000_000)):
            with self.assertRaises(ValueError):messages.batch('hat',1,8,0,0,dict(sdp3x_response=ZERO,**fields))

    def test_session_rejects_averaging_bounds_for_explicit_unaveraged_configuration(self):
        from groundlark.session import Sessions
        sessions=Sessions()
        sessions.accept(messages.identity('hat',1,1,[8]))
        sessions.accept(messages.configuration('hat',1,[dict(SETTINGS,pressure_measurement_command=0x361e)]))
        raw=dict(sdp3x_response=ZERO,read_interval_min_ns=10_000_000,read_interval_max_ns=10_000_000)
        with self.assertRaisesRegex(ValueError,'measurement command'):
            sessions.accept(messages.batch('hat',1,8,0,10_000_000,raw,clock_domain=1))
        sessions.accept(messages.batch('hat',1,8,0,10_000_000,dict(sdp3x_response=ZERO),clock_domain=1))

    def test_startup_identity_and_recovery_command_order(self):
        bus, delays = Bus(), []
        device = SDP32(bus, delays.append)
        self.assertEqual(device.configure(SETTINGS), SETTINGS)
        expected = [(0x21, '3ff9', 0), (0x21, '367c', 0), (0x21, 'e102', 0),
                    (0x21, '', 18), (0x21, '3615', 0), (0x21, '', 9)]
        self.assertEqual(bus.calls, expected)
        self.assertEqual(delays, [.025, .001, .020])
        device.configure(SETTINGS)
        self.assertEqual(bus.calls[6:], expected)
        device.close()
        self.assertTrue(bus.closed)
        self.assertEqual(bus.calls[-1], (0x21, '3ff9', 0))

    def test_crc_known_vector_and_all_single_bit_corruptions(self):
        self.assertEqual(sht_crc(bytes.fromhex('beef')), 0x92)
        for frame, count in ((ZERO, 3), (IDENTITY, 6)):
            for bit in range(len(frame) * 8):
                corrupt = bytearray(frame); corrupt[bit // 8] ^= 1 << (bit % 8)
                with self.subTest(bit=bit, count=count), self.assertRaises(OSError): words(corrupt, count)
            for size in range(len(frame)):
                with self.assertRaises(OSError): words(frame[:size], count)

    def test_rejects_other_product_scale_and_configuration(self):
        # SDP31 product word 0x0101 with valid CRC, rather than SDP32 0x0201.
        wrong = bytearray(IDENTITY); wrong[3:6] = bytes.fromhex('010144')
        with self.assertRaisesRegex(OSError,'product identity'): SDP32(Bus(identity=wrong), lambda _: None).configure(SETTINGS)
        with self.assertRaises(ValueError): SDP32(Bus()).configure(dict(SETTINGS, pressure_max_pa=500))
        bad_scale = ZERO[:6] + bytes.fromhex('003c39')
        with self.assertRaisesRegex(OSError,'pressure scale'): SDP32(Bus(sample=bad_scale)).read()

    def test_negative_raw_recording_validation_and_display(self):
        for frame, pressure, temperature in ((ZERO, 0, 5000), (NEGATIVE, -24000, -2000)):
            reading = SDP32(Bus(sample=frame)).read()
            envelope = messages.batch('hat', 1, 8, 0, 123, reading.raw)
            validate(envelope)
            recovered = type(envelope).FromString(envelope.SerializeToString())
            sample = recovered.batch.samples[0]
            self.assertEqual(sample.pressure.sdp3x_response, frame)
            self.assertEqual(raw_values(sample, 'pressure_pa'), [pressure])
            self.assertEqual(raw_values(sample, 'temperature_k'), [temperature])
            self.assertEqual(project_sample(8, sample)['primary'][0], pressure)
            sample.pressure.response = bytes(4)
            with self.assertRaises(ValueError): validate(recovered)

    def test_out_of_range_is_saturated_and_bus_errors_are_not_zero(self):
        self.assertEqual(SDP32(Bus(sample=bytes.fromhex('7fff8f13880100f003'))).read().quality, 3)
        class FailedBus:
            def exchange(self, *args): raise OSError('NACK')
        with self.assertRaises(OSError): SDP32(FailedBus()).read()

    def test_simulated_sdp32_produces_signed_crc_checked_frame(self):
        from groundlark.simulation import Simulated
        sim = Simulated(8)
        sim.configure(SETTINGS)
        reading = sim.read()
        self.assertEqual(len(reading.raw['sdp3x_response']), 9)
        validate(messages.batch('hat', 1, 8, 0, 0, reading.raw))
