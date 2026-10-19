"""SDP3x v1.1 protocol vectors and wrong-device/corrupt-frame faults."""
import unittest
from groundlark.pressure import SDP32, SETTINGS, words
from groundlark_contract.validation import sht_crc, validate
from groundlark import messages
from groundlark.calibration import raw_values
from groundlark.workbench import project_sample

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
    def test_startup_identity_and_recovery_command_order(self):
        bus, delays = Bus(), []
        device = SDP32(bus, delays.append)
        self.assertEqual(device.configure(SETTINGS), SETTINGS)
        expected = [(0x21, '3ff9', 0), (0x21, '367c', 0), (0x21, 'e102', 0),
                    (0x21, '', 18), (0x21, '361e', 0), (0x21, '', 9)]
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
