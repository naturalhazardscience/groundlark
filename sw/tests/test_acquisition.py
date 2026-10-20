"""Independent expected outcomes for acquisition, recording and fault recovery."""
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from groundlark_contract.framing import encode
from groundlark import messages as m
from groundlark.calibration import Calibrations, configuration_hash
from groundlark.cli import replay
from groundlark.recording import Reader, Writer, RecordingError
from groundlark.runtime import Acquisition, Channel
from groundlark.session import Sessions
from groundlark.simulation import Simulated, defaults
from groundlark.transport import Outbox, Receiver
from groundlark.worker import Worker

ROOT = Path(__file__).resolve().parents[2]
RAW = dict(acceleration=(-32768, 0, 32767), angular_rate=(1, 2, 3), temperature=-100)


def handshake(sessions, boot=1):
    sessions.accept(m.identity("pi", boot, 1, [1]))
    sessions.accept(m.configuration("pi", boot, defaults()[:1]))


def sample(sequence=0, acquired=0, boot=1, dropped=0):
    return m.batch("pi", boot, 1, sequence, acquired, RAW, dropped=dropped)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.sessions = Sessions()
        handshake(self.sessions)

    def test_reject_before_identity_or_configuration(self):
        for state in (Sessions(),):
            with self.assertRaises(ValueError): state.accept(sample())
            state.accept(m.identity("pi", 1, 1, [1]))
            with self.assertRaises(ValueError): state.accept(sample())

    def test_zero_is_valid_and_duplicate_rejection_is_transactional(self):
        self.sessions.accept(sample())
        with self.assertRaises(ValueError): self.sessions.accept(sample())
        self.sessions.accept(sample(1, 1))

    def test_gap_must_match_known_loss(self):
        with self.assertRaises(ValueError): self.sessions.accept(sample(4, 5, dropped=3))
        self.sessions.accept(sample(4, 5, dropped=4))
        self.sessions.accept(sample(10, 8, dropped=None))

    def test_regressed_clock_rejected_until_new_boot(self):
        self.sessions.accept(sample(0, 100))
        with self.assertRaises(ValueError): self.sessions.accept(sample(1, 99))
        handshake(self.sessions, 2)
        self.sessions.accept(sample(0, 0, 2))
        with self.assertRaises(ValueError): handshake(self.sessions, 1)

    def test_disconnect_requires_repeated_handshake_preserves_sequence(self):
        self.sessions.accept(sample())
        self.sessions.disconnect("pi")
        with self.assertRaises(ValueError): self.sessions.accept(sample(1, 1))
        handshake(self.sessions)
        with self.assertRaises(ValueError): self.sessions.accept(sample())
        self.sessions.accept(sample(1, 1))

    def test_configuration_is_copied_and_revision_checked(self):
        cfg = m.configuration("pi", 1, defaults()[:1])
        self.sessions.accept(cfg)
        cfg.configuration.sensors[0].enabled = False
        self.sessions.accept(sample())
        changed = m.configuration("pi", 1, [dict(defaults()[0], period_ns=10)])
        with self.assertRaises(ValueError): self.sessions.accept(changed)

    def test_identity_inventory_capacity_and_retired_boots(self):
        state = Sessions(max_devices=1, max_resets=1)
        handshake(state)
        with self.assertRaises(ValueError): state.accept(m.identity("other", 1, 1, [1]))
        with self.assertRaises(ValueError): state.accept(m.identity("pi", 1, 1, [2]))
        handshake(state, 2)
        with self.assertRaises(ValueError): handshake(state, 3)

    def test_status_loss_total_never_decreases(self):
        self.sessions.accept(m.status("pi", 1, 1, 4, "loss", dropped=7))
        with self.assertRaises(ValueError): self.sessions.accept(m.status("pi", 1, 1, 4, "loss", dropped=6))


class TransportTests(unittest.TestCase):
    def test_remote_cannot_replace_local_identity(self):
        receiver = Receiver(Sessions(), board=2, forbidden_devices=["pi"])
        for value in (m.identity("pi", 1, 2, [7]), m.identity("other", 1, 1, [1])):
            self.assertEqual(list(receiver.feed(encode(value.SerializeToString()), 0)), [])
        self.assertEqual(receiver.sessions.devices, {})
        self.assertEqual(receiver.errors["invalid_message"], 2)

    def test_bytewise_usb_and_crc_recovery(self):
        receiver = Receiver(Sessions())
        msgs = [m.identity("pi", 1, 1, [1]), m.configuration("pi", 1, defaults()[:1]), sample()]
        wire = b"".join(encode(msg.SerializeToString()) for msg in msgs)
        decoded = []
        for i, byte in enumerate(wire): decoded.extend(receiver.feed(bytes([byte]), i))
        self.assertEqual(len(decoded), 3)
        self.assertEqual(decoded[-1].batch.samples[0].imu.acceleration.x, -32768)
        damaged = bytearray(encode(sample(1, 1).SerializeToString()))
        damaged[-3] ^= 4
        self.assertEqual(list(receiver.feed(damaged, len(wire))), [])
        self.assertEqual(len(list(receiver.feed(encode(sample(1, 1).SerializeToString()), len(wire) + 1))), 1)
        self.assertEqual(receiver.errors["corrupt_frame"], 1)

    def test_partial_timeout_discards_tail_then_resynchronizes(self):
        receiver = Receiver(Sessions(), partial_timeout_ns=10)
        wire = encode(m.identity("pi", 1, 1, [1]).SerializeToString())
        self.assertEqual(list(receiver.feed(wire[:5], 0)), [])
        self.assertEqual(list(receiver.feed(wire[5:], 20)), [])
        self.assertEqual(len(list(receiver.feed(wire, 21))), 1)
        self.assertEqual(receiver.errors["partial_timeout"], 1)

    def test_oversized_noise_bounded_and_reset_not_replay(self):
        receiver = Receiver(Sessions())
        for i in range(100): list(receiver.feed(b"x" * 4096, i))
        self.assertLessEqual(len(receiver.decoder.buffer), 1033)
        list(receiver.feed(b"\0", 101))
        with self.assertRaises(ValueError): list(receiver.feed(b"x" * 4097, 102))

    def test_slow_consumer_exact_loss_and_control_backpressure(self):
        box = Outbox([("pi", 1, 1)], capacity=1)
        self.assertTrue(box.put(sample(), 0))
        self.assertFalse(box.put(sample(1, 1), 1))
        self.assertFalse(box.put(sample(2, 2), 2))
        with self.assertRaises(BufferError): box.put(m.status("pi", 1, 1, 4, "overflow"), 2)
        state = Sessions()
        handshake(state)
        state.accept(box.pop()[0])
        box.put(sample(3, 3), 3)
        value = box.pop()[0]
        self.assertEqual(value.batch.dropped_before, 2)
        state.accept(value)
        self.assertEqual(box.dropped_samples, 2)

    def test_overflow_retains_unknown_loss(self):
        box = Outbox([("pi", 1, 1)], 1)
        box.put(sample(), 0)
        box.put(sample(1, 1, dropped=None), 1)
        box.pop()
        box.put(sample(2, 2), 2)
        self.assertFalse(box.pop()[0].batch.HasField("dropped_before"))


class RecordingTests(unittest.TestCase):
    def test_unidentified_usb_disconnect_does_not_invalidate_pi(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unidentified.ssrec"
            with path.open("wb") as stream:
                writer = Writer(stream, {"format": "groundlark-acquisition-v1"})
                writer.message(m.identity("pi", 1, 1, [1]), 0)
                writer.message(m.configuration("pi", 1, defaults()[:1]), 0)
                writer.event("usb_disconnected", "before identity", 1, device=None)
                writer.message(sample(), 2)
            result = replay(path)
            self.assertEqual(result["samples"], 1)
            self.assertFalse(result["completed"])

    def make(self):
        stream = io.BytesIO()
        writer = Writer(stream, {"format": "groundlark-acquisition-v1"})
        writer.message(m.identity("pi", 1, 1, [1]), 0)
        writer.message(m.configuration("pi", 1, defaults()[:1]), 0)
        writer.message(sample(), 1)
        return stream.getvalue()

    def test_raw_precision_and_arrival_separate(self):
        reader = Reader(io.BytesIO(self.make()))
        arrival, item = list(reader)[-1]
        self.assertEqual(arrival, 1)
        self.assertEqual(item.batch.samples[0].time.acquisition_ns, 0)
        self.assertEqual(item.batch.samples[0].imu.acceleration.x, -32768)

    def test_corruption_and_truncation_rejected(self):
        wire = self.make()
        for bad in (wire[:-1], wire[:20], wire[:-5] + bytes([wire[-5] ^ 1]) + wire[-4:]):
            with self.assertRaises((ValueError, RecordingError)): list(Reader(io.BytesIO(bad)))

    def test_size_and_arrival_budgets(self):
        writer = Writer(io.BytesIO(), {}, max_bytes=4096)
        writer.event("test", "test", 100)
        with self.assertRaises(ValueError): writer.message(sample(), 99)
        with self.assertRaises(RecordingError):
            for i in range(1000): writer.message(sample(i, i), 101 + i)
        self.assertLessEqual(writer.written, 4096)

    def test_descriptor_calibration_identity_and_raw_preserved(self):
        cfg = m.configuration("pi", 1, defaults()[:1]).configuration.sensors[0]
        registry = Calibrations()
        ident = registry.add(dict(sensor_id=1, configuration_sha256=configuration_hash(cfg), provenance="independent fixture",
            fields={"acceleration_m_s2": dict(scale=[.001, .002, .003], offset=[1, 2, 3])}))
        converted = registry.apply(sample(), ident, cfg)
        self.assertEqual(converted.batch.samples[0].imu.acceleration.x, -32768)
        self.assertAlmostEqual(converted.batch.samples[0].calibrated.acceleration_m_s2.x, -31.768)
        state = Sessions(registry)
        handshake(state)
        state.accept(converted)
        cfg.period_ns += 1
        with self.assertRaises(ValueError): registry.verify(ident, 1, cfg)


class RuntimeTests(unittest.TestCase):
    def test_scheduled_gap_missing_and_finite_recovery(self):
        faults = [dict(sensor=1, sample=i, action="timeout") for i in range(5)]
        channel = Channel("pi", 1, defaults()[0], Simulated(1, faults=faults))
        stream = io.BytesIO()
        app = Acquisition(Writer(stream, {}), Sessions(), [channel], cooldown_ns=1, retry_limit=2)
        app.start(0)
        for now in (0, 100_000_000, 200_000_000, 300_000_000, 400_000_000):
            app.tick(lambda: now)
            app.drain()
        app.finish(500_000_000)
        self.assertTrue(channel.offline)
        self.assertEqual(channel.retries, 2)
        self.assertEqual(app.missing, 5)
        batches = [v.batch for _, v in Reader(io.BytesIO(stream.getvalue())) if not isinstance(v, dict) and v.WhichOneof("body") == "batch"]
        self.assertEqual([b.samples[0].sequence for b in batches], [0, 2, 5, 7, 10])
        self.assertEqual([b.dropped_before for b in batches], [0, 1, 2, 1, 2])
        self.assertTrue(all(b.samples[0].WhichOneof("raw") is None for b in batches))

    def test_clock_regression_fails_closed(self):
        channel = Channel("pi", 1, defaults()[0], Simulated(1))
        app = Acquisition(Writer(io.BytesIO(), {}), Sessions(), [channel])
        app.start(0)
        app.tick(lambda: 0)
        channel.due = 0
        with self.assertRaises(ValueError): app.tick(lambda: 0)

    def test_actual_cli_repeatable_fault_run_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            outputs, summaries = [], []
            for name in ("one", "two"):
                path = Path(directory) / (name + ".ssrec")
                command = [sys.executable, str(ROOT / "sw/tools/sensor.py"), "simulate", "--remote", "--seconds", "2",
                           "--faults", str(ROOT / "sw/tests/fixtures/acquisition_faults.json"), "--output", str(path)]
                result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=15)
                summaries.append(json.loads(result.stdout))
                outputs.append(path.read_bytes())
                self.assertEqual(replay(path), summaries[-1])
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(summaries[0]["samples"], 1100)  # Three IMUs, geophone, four magnetometers, legacy pressure and two SHT45 frames.
            self.assertEqual(summaries[0]["missing"], 30)
            self.assertEqual(summaries[0]["saturated"], 2)

    def test_cli_slow_consumer_preserves_order_with_visible_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slow.ssrec"
            result = subprocess.run([sys.executable, str(ROOT / "sw/tools/sensor.py"), "simulate", "--remote",
                "--seconds", "1", "--queue", "1", "--drain-every", "100", "--output", str(path)],
                check=True, capture_output=True, text=True, timeout=15)
            self.assertTrue(json.loads(result.stdout)["completed"])
            with path.open("rb") as stream:
                items = list(Reader(stream))
            self.assertGreater(items[-1][1]["queue_dropped"], 100)
            self.assertLess(json.loads(result.stdout)["samples"], 20)


class HangingDevice:
    def configure(self, settings): return settings
    def read(self): time.sleep(30)


class GappedDevice:
    def configure(self, settings): return settings
    def read(self):
        from groundlark.sensors import DataGap
        raise DataGap('conversion gap; loss unknown')


class PressureGapDevice:
    """Real SDP32 driver, deterministic successful bus and late service."""
    def __init__(self):
        from groundlark.pressure import SDP32
        self.now=0;self.index=0
        self.driver=SDP32(self,lambda _:None,clock_ns=lambda:self.now)
    def exchange(self,address,write,count):
        if count==18:return bytes.fromhex('03019d0201690123a045675389ab77cdef84')
        if count==9:return bytes.fromhex('00008113880100f003')
        return b''
    def configure(self,settings):return self.driver.configure(settings)
    def read(self):
        self.now=(10_000_000,40_000_000,50_000_000)[self.index];self.index+=1
        return self.driver.read()


class WorkerTests(unittest.TestCase):
    def test_sdp32_late_average_survives_worker_ipc_and_recovers_without_restart(self):
        from groundlark.pressure import SETTINGS
        from groundlark.sensors import DataGap
        worker=Worker(PressureGapDevice,SETTINGS,startup_timeout=5)
        try:
            worker.configure();pid=worker.process.pid
            self.assertEqual(worker.read().raw['read_interval_max_ns'],10_000_000)
            with self.assertRaisesRegex(DataGap,'1-25 ms'):worker.read()
            self.assertEqual(worker.read().raw['read_interval_max_ns'],10_000_000)
            self.assertEqual(worker.process.pid,pid)
            self.assertEqual(worker.restarts,0)
        finally:worker.close()

    def test_conversion_gap_type_survives_real_worker_ipc(self):
        from groundlark.sensors import DataGap
        worker = Worker(GappedDevice, {}, startup_timeout=5)
        try:
            worker.configure()
            pid = worker.process.pid
            for _ in range(4):
                with self.assertRaises(DataGap): worker.read()
                self.assertTrue(worker.process.is_alive())
                self.assertEqual(worker.process.pid, pid)
                self.assertEqual(worker.restarts, 0)
        finally: worker.close()

    def test_hung_bus_is_reaped_and_restart_budget_enforced(self):
        worker = Worker(HangingDevice, {}, timeout=.05, startup_timeout=5, restart_limit=1)
        try:
            worker.configure()
            start = time.monotonic()
            with self.assertRaises(TimeoutError): worker.read()
            self.assertLess(time.monotonic() - start, 2)
            self.assertIsNone(worker.process)
            worker.configure()
            with self.assertRaises(OSError): worker.configure()
            self.assertIsNone(worker.process)
        finally: worker.close()


if __name__ == "__main__": unittest.main()
