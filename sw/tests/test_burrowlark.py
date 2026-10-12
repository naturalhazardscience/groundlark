"""Independent SHT45 protocol, board identity, stimulus and replay fixtures."""
from io import BytesIO
import unittest

from groundlark import messages
from groundlark.burrowlark import SHT45, SETTINGS, ModeledBus, decode_frame
from groundlark.board_bench import run_bench
from groundlark.recording import Reader
from groundlark.workbench import Workbench
from groundlark_contract.validation import validate


class BurrowlarkTests(unittest.TestCase):
    def test_manufacturer_crc_vector_and_each_word_corruption(self):
        # Sensirion documented CRC example: BE EF -> 92, independent of encoder.
        frame = bytes.fromhex('be ef 92 be ef 92')
        self.assertEqual(decode_frame(frame).raw['response'], frame)
        for offset in range(6):
            bad = bytearray(frame); bad[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaisesRegex(OSError, 'CRC'):
                decode_frame(bad)
        for length in (0, 4, 5, 7):
            with self.assertRaisesRegex(OSError, 'short'):
                decode_frame(bytes(length))

    def test_command_timing_and_no_heater(self):
        bus = ModeledBus(25, 50)
        driver = SHT45(bus, sleep=bus.sleep)
        self.assertEqual(driver.configure(SETTINGS), SETTINGS)
        frame = driver.read().raw['response']
        self.assertEqual(int.from_bytes(frame[:2], 'big'), 26214)
        self.assertEqual(int.from_bytes(frame[3:5], 'big'), 29360)
        bus.write(0x44, b'\xfd')
        with self.assertRaisesRegex(OSError, 'not ready'): bus.read(0x44, 6)
        with self.assertRaisesRegex(OSError, 'heater'): bus.write(0x44, b'\x39')
        with self.assertRaises(ValueError): driver.configure({**SETTINGS, 'period_ns': 10_000_000})

    def test_climate_is_head_owned_with_mcu_clock_and_checked_raw_frame(self):
        messages.identity('head', 1, 2, [7,17])
        for board in (1,3):
            with self.assertRaisesRegex(ValueError, 'belong'):
                messages.identity('wrong', 1, board, [17])
        frame = bytes.fromhex('be ef 92 be ef 92')
        m = messages.batch('head', 1, 17, 0, 1, {'response':frame})
        self.assertEqual(m.batch.samples[0].time.domain, 2)
        m.batch.samples[0].time.domain = 1
        with self.assertRaisesRegex(ValueError, 'clock'): validate(m)

    def test_board_experiment_preserves_climate_and_fault_gaps_in_replay(self):
        data, report = run_bench('burrowlark')
        self.assertTrue(report['passed'], report)
        frames, missing = [], 0
        for _, message in Reader(BytesIO(data)):
            if isinstance(message, dict) or message.WhichOneof('body') != 'batch' or message.batch.sensor_id != 17:
                continue
            for sample in message.batch.samples:
                if sample.quality == 2:
                    missing += 1
                    self.assertIsNone(sample.WhichOneof('raw'))
                else: frames.append(sample.climate.response)
        self.assertGreater(missing, 0)
        self.assertTrue(frames)
        self.assertTrue(all(len(frame)==6 for frame in frames))
        e = Workbench(); e.load_recording(data); e.seek(e.duration/1e9)
        self.assertEqual(e.board,'burrowlark')
        self.assertEqual(set(e.sensor_ids), {7,18,19,20,17})
        self.assertEqual(e.snapshot(17)['latest'][17]['quality'],'Valid')

    def test_legacy_magnetometer_only_recording_remains_readable(self):
        from groundlark.recording import Writer
        from groundlark.simulation import defaults
        stream = BytesIO()
        writer = Writer(stream, dict(format='groundlark-acquisition-v1', source='simulation', calibrations=[]))
        writer.message(messages.identity('legacy',1,2,[7]),0)
        writer.message(messages.configuration('legacy',1,[defaults(True)[0]]),0)
        writer.message(messages.batch('legacy',1,7,0,1,{'counts':(0,0,0)}),1)
        e = Workbench(); e.load_recording(stream.getvalue())
        self.assertEqual(e.board,'burrowlark')
        self.assertEqual(e.sensor_ids,(7,))
