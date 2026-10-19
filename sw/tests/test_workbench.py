"""Research-facing controller tests; no browser/framework dependency."""
from io import BytesIO
import json
import tempfile
from pathlib import Path
import unittest

from groundlark.cli import export_scenario, replay
from groundlark.recording import Reader, Writer
from groundlark.workbench import MAX_BYTES, POINTS, Workbench


def advance(engine, milliseconds):
    engine.running = True
    while milliseconds:
        step = min(milliseconds, 200)
        engine.advance(step)
        milliseconds -= step
    engine.running = False


class WorkbenchTests(unittest.TestCase):
    def test_pressure_moves_to_hat_with_pi_clock_and_remote_magnetometer_stays(self):
        hat, head = Workbench(board='hat'), Workbench(board='burrowlark')
        self.assertEqual(set(hat.sensor_ids), {1,2,3,6,8,9})
        self.assertEqual(set(head.sensor_ids), {7,18,19,20,17})
        advance(hat, 20)
        self.assertEqual(hat.snapshot(8)['latest'][8]['clock_domain'], 1)
        data=hat.finish();hat.load_recording(data)
        self.assertEqual(hat.board,'hat')

    def test_pressure_clock_is_bound_to_identity_and_legacy_head_replays(self):
        from groundlark import messages
        from groundlark.session import Sessions
        cfg=dict(sensor_id=8, enabled=True, period_ns=10000000,
                 pressure_min_pa=-125, pressure_max_pa=125,
                 pressure_part_number='DLVR-F50D-E1BS-I-NI3F')
        for board,domain in [(1,1),(2,2)]:
            sessions=Sessions()
            sessions.accept(messages.identity('pressure',1,board,[8]))
            sessions.accept(messages.configuration('pressure',1,[cfg]))
            wrong=messages.batch('pressure',1,8,0,1,clock_domain=3-domain)
            with self.assertRaisesRegex(ValueError,'pressure clock'):
                sessions.accept(wrong)
            sessions.accept(messages.batch('pressure',1,8,0,1,clock_domain=domain))

    def test_pause_does_not_advance_clock(self):
        engine = Workbench()
        engine.advance(200)
        self.assertEqual(engine.now, 0)
        engine.toggle()
        engine.advance(50)
        engine.toggle()
        engine.advance(100)
        self.assertEqual(engine.now, 50_000_000)

    def test_zero_gravity_pose_and_all_sensors(self):
        engine = Workbench()
        advance(engine, 300)
        snap = engine.snapshot(1)
        self.assertEqual(set(snap["latest"]), {1, 2, 3, 6, 9, 7, 8, 17, 18, 19, 20})
        self.assertTrue(all(snap["latest"].values()))
        self.assertEqual(snap["latest"][1]["primary"], [0, 0, 16393])
        engine.controls({"orientation_deg": [90, 0, 0]})
        advance(engine, 100)
        point = engine.snapshot(1)["latest"][1]
        self.assertEqual(point["primary"], [0, 16393, 0])

    def test_fault_is_gap_not_zero_and_other_sensors_continue(self):
        engine = Workbench()
        engine.controls({"sensor_faults": {"1": "timeout"}})
        advance(engine, 200)
        snap = engine.snapshot(1)
        self.assertEqual(snap["latest"][1]["primary"], [None] * 3)
        self.assertEqual(snap["latest"][1]["quality"], "Missing")
        self.assertEqual(snap["latest"][2]["quality"], "Valid")
        self.assertGreater(snap["missing"], 0)

    def test_current_hat_has_geophone_and_gnss(self):
        engine = Workbench()
        advance(engine, 1)
        point = engine.snapshot(9)["latest"][9]
        self.assertEqual(point["primary"], [0, None, None])
        self.assertIn(6, engine.snapshot(9)["latest"])
        self.assertIn("Racotech", point["detail"])

    def test_raw_signed_magnetic_counts_and_pressure_status(self):
        engine = Workbench({"version": 1, "initial": {"magnetic_ut": [-10, 0, 20]}})
        advance(engine, 1)
        self.assertEqual(engine.snapshot(7)["latest"][7]["primary"], [-750, 0, 1500])
        self.assertEqual(engine.snapshot(8)["latest"][8]["secondary"], [5000, None, None])  # SDP32: 25 C * 200.
        self.assertIn('SDP32', engine.snapshot(8)['latest'][8]['detail'])

    def test_recording_roundtrip_and_backward_seek(self):
        engine = Workbench()
        advance(engine, 500)
        engine.controls({"magnetic_ut": [1, 2, 3]})
        advance(engine, 500)
        last = engine.snapshot(7)["latest"][7]
        data = engine.finish()
        engine.load_recording(data)
        engine.seek(.99)
        self.assertEqual(engine.snapshot(7)["latest"][7], last)
        engine.seek(.2)
        self.assertEqual(engine.snapshot(7)["latest"][7]["primary"], [0, 1500, -3375])
        engine.toggle()
        engine.advance(100)
        self.assertEqual(engine.now, 300_000_000)

    def test_replay_clock_origin_does_not_assume_synchronized_timestamps(self):
        engine = Workbench()
        advance(engine, 200)
        reader = Reader(BytesIO(engine.finish()))
        stream = BytesIO()
        writer = Writer(stream, reader.metadata)
        for arrived, item in reader:
            if isinstance(item, dict):
                fields = {k: v for k, v in item.items() if k not in ("code", "detail")}
                writer.event(item["code"], item["detail"], arrived + 100_000_000_000, **fields)
            else:
                writer.message(item, arrived + 100_000_000_000)
        engine.load_recording(stream.getvalue())
        engine.seek(.15)
        point = engine.snapshot(1)["latest"][1]
        self.assertLess(point["t"], .15)
        self.assertLess(point["acquisition_ns"], 200_000_000)

    def test_bad_recording_preserves_current_run(self):
        engine = Workbench()
        advance(engine, 100)
        before = engine.snapshot(1)
        with self.assertRaises(ValueError):
            engine.load_recording(b"bad recording")
        self.assertEqual(engine.snapshot(1), before)
        with self.assertRaises(ValueError):
            engine.load_recording(b"x" * (MAX_BYTES + 1))

    def test_recorded_controls_export_for_cli(self):
        engine = Workbench()
        advance(engine, 50)
        engine.controls({"pressure_pa": 50})
        advance(engine, 100)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "run.ssrec"
            path.write_bytes(engine.finish())
            self.assertTrue(replay(path)["completed"])
            export_scenario(path, Path(folder) / "scenario.json")
            document = json.loads((Path(folder) / "scenario.json").read_text())
            self.assertEqual(document["events"], [{"at_ns": 50_000_000, "set": {"pressure_pa": 50}}])

    def test_display_buffers_are_bounded(self):
        engine = Workbench()
        advance(engine, 4500)
        self.assertEqual(len(engine.snapshot(8)["points"]), POINTS)

    def test_batching_does_not_change_simulated_results(self):
        first, second = Workbench(seed=4), Workbench(seed=4)
        advance(first, 600)
        for _ in range(12):
            advance(second, 50)
        self.assertEqual(first.finish(), second.finish())

    def test_finished_and_replay_runs_reject_controls(self):
        engine = Workbench()
        advance(engine, 100)
        data = engine.finish()
        for action in (engine.toggle, lambda: engine.controls({"pressure_pa": 1})):
            with self.assertRaises(ValueError):
                action()
        engine.load_recording(data)
        with self.assertRaises(ValueError):
            engine.controls({"pressure_pa": 1})

    def test_invalid_scenario_does_not_replace_run(self):
        engine = Workbench()
        advance(engine, 100)
        with self.assertRaises(ValueError):
            engine.reset({"version": 700})
        self.assertEqual(engine.now, 100_000_000)

    def test_automatic_duration_limit_finishes_recording(self):
        engine = Workbench()
        engine.duration = 100_000_000
        advance(engine, 200)
        self.assertTrue(engine.ended)
        self.assertEqual(engine.now, engine.duration)
        items = list(Reader(BytesIO(engine.finish())))
        self.assertEqual(items[-1][1]["code"], "acquisition_summary")


if __name__ == "__main__":
    unittest.main()
