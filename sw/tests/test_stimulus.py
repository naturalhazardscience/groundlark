"""Physical expectations, scenario boundary cases and public CLI reproduction."""
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from groundlark.simulation import Simulated, defaults
from groundlark.stimulus import Scenario, reading, signal, G
from groundlark.recording import Reader, Writer
from groundlark.cli import replay, export_scenario

ROOT = Path(__file__).resolve().parents[2]


def model(sensor, initial=None, now=0, events=(), seed=1, cfg=None):
    scenario = Scenario(dict(version=1, initial=initial or {}, events=list(events)))
    configuration = cfg or next(c for c in defaults() + defaults(True) + defaults(legacy_gnss=True) if c["sensor_id"] == sensor)
    return reading(sensor, configuration, scenario, now, seed)


class PhysicsTests(unittest.TestCase):
    def test_stationary_gravity_temperature_and_level(self):
        imu = model(1)
        self.assertEqual(imu.raw["acceleration"], (0, 0, 16393))
        self.assertEqual(imu.raw["angular_rate"], (0, 0, 0))
        self.assertEqual(imu.raw["temperature"], 0)
        tilt = model(5)
        self.assertEqual(tilt.raw["acceleration"], (0, 0, 6000))
        self.assertEqual(tilt.raw["angle"], (0, 0, 16384))
        self.assertEqual(tilt.raw["temperature"], 5632)
        self.assertEqual(tilt.quality, 1)

    def test_roll_rotates_gravity_and_all_imus_share_motion(self):
        values = [model(sid, {"orientation_deg": [90, 0, 0]}).raw["acceleration"] for sid in range(1, 5)]
        self.assertEqual(values, [(0, 16393, 0)] * 4)
        self.assertEqual(model(5, {"orientation_deg": [0, 30, 0]}).raw["angle"], (-5461, 0, 10923))

    def test_gyro_derivative_of_smooth_orientation(self):
        wave = {"orientation_deg": [{"amplitude": 10, "frequency_hz": 1}, 0, 0]}
        imu = model(1, wave)
        self.assertEqual(imu.raw["angular_rate"], (7181, 0, 0))
        self.assertEqual(model(1, wave, 250_000_000).raw["angular_rate"], (0, 0, 0))

    def test_gyro_euler_coupling_at_tilt(self):
        imu = model(1, {"orientation_deg": [0, 30, {"drift_per_s": 10}]})
        self.assertEqual(imu.raw["angular_rate"], (-571, 0, 990))

    def test_sensor_configuration_changes_raw_scale(self):
        cfg = dict(defaults()[0], acceleration_range_g=4)
        self.assertEqual(model(1, cfg=cfg).raw["acceleration"][2], 8197)
        cfg = dict(next(c for c in defaults(legacy_gnss=True) if c["sensor_id"] == 5), tilt_mode=2)
        self.assertEqual(model(5, cfg=cfg).raw["acceleration"][2], 3000)

    def test_rail_saturation_and_freefall_are_explicit(self):
        imu = model(1, {"acceleration_m_s2": [1000000, 0, 0]})
        self.assertEqual(imu.quality, 3)
        self.assertEqual(imu.raw["acceleration"][0], 32767)
        tilt = model(5, {"acceleration_m_s2": [0, 0, -G]})
        self.assertEqual(tilt.quality, 4)

    def test_magnetic_rotation_independent_of_hat(self):
        a = model(7, {"magnetic_ut": [20, 0, 0], "orientation_deg": [0, 0, 90]})
        b = model(7, {"magnetic_ut": [20, 0, 0], "head_orientation_deg": [0, 0, 90]})
        self.assertEqual(a.raw["counts"], (1500, 0, 0))
        self.assertEqual(b.raw["counts"], (0, -1500, 0))
        self.assertEqual(model(7, {"magnetic_ut": [1000000, 0, 0]}).raw["counts"][0], 8388607)
        with self.assertRaises(ValueError): model(7, cfg=dict(defaults(True)[0], cycle_count_x=100))

    def test_pressure_transfer_pulse_and_temperature_bits(self):
        for pressure, count in ((-250, 1638), (0, 8192), (250, 14746)):
            result = model(8, {"pressure_pa": pressure, "pressure_temperature_count": 2047})
            self.assertEqual(struct.unpack(">HH", result.raw["response"]), (count, 65504))
            self.assertEqual(result.quality, 1)
        spec = {"pressure_pa": {"pulse_start_s": .5, "pulse_duration_s": .25, "pulse_amplitude": 300}}
        self.assertEqual(model(8, spec, 499999999).quality, 1)
        self.assertEqual(model(8, spec, 500000000).quality, 3)
        self.assertEqual(model(8, spec, 750000000).quality, 1)

    def test_gnss_wire_fields_and_north_east_down_motion(self):
        raw = model(6, {"gnss_position": [0, 0, 10], "gnss_velocity_ned_m_s": [1, 2, 3]}, 1_000_000_000).raw["nav_pvt"]
        self.assertEqual(len(raw), 92)
        self.assertEqual(struct.unpack_from("<I", raw, 0)[0], 1000)
        self.assertEqual(tuple(raw[i] for i in (20, 21, 23)), (3, 1, 12))
        self.assertEqual(struct.unpack_from("<iiii", raw, 24), (180, 90, 7000, 7000))
        self.assertEqual(struct.unpack_from("<iiii", raw, 48), (1000, 2000, 3000, 2236))
        self.assertEqual(raw[11], 0)  # UTC validity never invented.

    def test_gnss_velocity_change_is_continuous_and_fix_loss_is_not_bus_loss(self):
        events = [{"at_ns": 1_000_000_000, "set": {"gnss_velocity_ned_m_s": [0, 2, 0], "gnss_fix": False}}]
        result = model(6, {"gnss_position": [0, 0, 0], "gnss_velocity_ned_m_s": [1, 0, 0]}, 2_000_000_000, events)
        raw = result.raw["nav_pvt"]
        self.assertEqual(struct.unpack_from("<ii", raw, 24), (180, 90))
        self.assertEqual((raw[20], raw[21], raw[23], raw[78]), (0, 0, 0, 1))
        self.assertEqual(result.quality, 1)


class ScenarioTests(unittest.TestCase):
    def test_sine_drift_and_deterministic_noise(self):
        spec = dict(offset=2, amplitude=3, frequency_hz=1, drift_per_s=4)
        value, derivative = signal(spec, 250_000_000, 1, 1, "x")
        self.assertAlmostEqual(value, 6)
        self.assertAlmostEqual(derivative, 4)
        noise = dict(noise_peak=1)
        self.assertEqual(signal(noise, 123, 2, 1, "x"), signal(noise, 123, 2, 1, "x"))
        self.assertNotEqual(signal(noise, 123, 2, 1, "x"), signal(noise, 123, 2, 2, "x"))
        self.assertNotEqual(signal(noise, 123, 2, 1, "x"), signal(noise, 123, 3, 1, "x"))
        self.assertLessEqual(abs(signal(noise, 123, 2, 1, "x")[0]), 1)

    def test_scheduled_controls_boundary_order_export_and_immutability(self):
        initial = {"pressure_pa": 1}
        scenario = Scenario(dict(version=1, initial=initial))
        initial["pressure_pa"] = 900
        scenario.schedule(200, {"pressure_pa": 3})
        scenario.schedule(100, {"pressure_pa": 2})
        scenario.schedule(100, {"pressure_pa": 4})
        self.assertEqual(scenario.state_at(99)[0]["pressure_pa"], 1)
        self.assertEqual(scenario.state_at(100)[0]["pressure_pa"], 4)
        self.assertEqual(len(scenario.advance(100)), 2)
        self.assertEqual(scenario.advance(100), [])
        with self.assertRaises(ValueError): scenario.schedule(100, {"pressure_pa": 5})
        with self.assertRaises(ValueError): scenario.advance(99)
        exported = scenario.export()
        self.assertEqual(Scenario(exported).state_at(200)[0]["pressure_pa"], 3)
        exported["initial"]["pressure_pa"] = 99
        self.assertEqual(scenario.state_at(0)[0]["pressure_pa"], 1)

    def test_reject_bad_units_types_unknown_controls_and_nonfinite(self):
        for changes in ({"typo": 1}, {"pressure_pa": True}, {"orientation_deg": [0, 1]},
                        {"pressure_pa": float("nan")}, {"gnss_position": [90, 0, 0]}, {"gnss_fix": 1},
                        {"pressure_pa": {"frequency_hz": -1}}, {"pressure_pa": {"pulse_amplitude": 1}},
                        {"orientation_deg": [{"noise_peak": 1}, 0, 0]}, {"pressure_temperature_count": 2048}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError): Scenario(dict(version=1, initial=changes))
        with self.assertRaises(ValueError): Scenario({"version": True})
        with self.assertRaises(ValueError): Scenario({"version": 1, "events": [{"at_ns": 2, "set": {}}, {"at_ns": 1, "set": {}}]})

    def test_bounded_events_rejection_does_not_mutate(self):
        scenario = Scenario()
        for i in range(256): scenario.schedule(i, {})
        previous = scenario.export()
        with self.assertRaises(ValueError): scenario.schedule(257, {})
        self.assertEqual(scenario.export(), previous)

    def test_time_based_wave_is_independent_of_read_and_recovery_count(self):
        now = 250_000_000
        scenario = Scenario({"version": 1, "initial": {"pressure_pa": {"amplitude": 10, "frequency_hz": 1, "noise_peak": .1}}})
        adapter = Simulated(8, scenario=scenario, clock=lambda: now)
        first = adapter.read()
        adapter.configure(next(c for c in defaults(True) if c["sensor_id"] == 8))
        self.assertEqual(adapter.read(), first)
        now = 750_000_000
        self.assertLess(int.from_bytes(adapter.read().raw["response"][:2], "big"), 8192)

    def test_timed_fault_override_clear_and_validation(self):
        scenario = Scenario({"version": 1, "initial": {"sensor_faults": {"1": "disconnect"}},
                             "events": [{"at_ns": 50, "set": {"sensor_faults": {"1": "saturation"}}},
                                        {"at_ns": 100, "set": {"sensor_faults": {}}}]})
        now = 0
        adapter = Simulated(1, scenario=scenario, clock=lambda: now)
        with self.assertRaises(OSError): adapter.read()
        now = 50
        self.assertEqual(adapter.read().quality, 3)
        now = 100
        self.assertEqual(adapter.read().quality, 1)
        for controls in ({"21": "disconnect"}, {"1": "unknown"}, {"1": []}):
            with self.assertRaises(ValueError): Scenario({"version": 1, "initial": {"sensor_faults": controls}})

    def test_actual_application_records_events_and_reproduces_from_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second, scenario_file = [Path(directory) / name for name in ("a.ssrec", "b.ssrec", "scenario.json")]
            cli = [sys.executable, str(ROOT / "sw/tools/sensor.py"), "simulate", "--remote", "--seconds", "2", "--seed", "7"]
            def run(profile, output):
                return subprocess.run(cli + ["--scenario", str(profile), "--output", str(output)], check=True, capture_output=True, timeout=15)
            run(ROOT / "sw/pi/profiles/stimulus-demo.json", first)
            with first.open("rb") as stream:
                reader = Reader(stream)
                events = [(t, v) for t, v in reader if isinstance(v, dict) and v.get("code") == "stimulus_change"]
            self.assertEqual([t for t, _ in events], [500000000, 1000000000, 1500000000])
            self.assertEqual([v["at_ns"] for _, v in events], [500000000, 1000000000, 1500000000])
            exported = subprocess.run([sys.executable, str(ROOT / "sw/tools/sensor.py"), "export-scenario", str(first),
                "--output", str(scenario_file)], check=True, capture_output=True, text=True, timeout=15)
            self.assertEqual(json.loads(exported.stdout)["seed"], 7)
            run(scenario_file, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(replay(first)["samples"], 1100)  # Three IMUs, geophone, four magnetometers, legacy pressure and two SHT45 frames.
            self.assertEqual(replay(first)["saturated"], 50)

    def test_export_includes_interactive_events_absent_from_initial_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            recording, output = Path(directory) / "live.ssrec", Path(directory) / "controls.json"
            with recording.open("wb") as stream:
                writer = Writer(stream, dict(format="groundlark-acquisition-v1", stimulus_model="ideal-v1",
                    scenario={"version": 1}, seed=1, remote=False))
                writer.event("stimulus_change", "UI control", 100, at_ns=100, set={"pressure_pa": 10})
                writer.event("acquisition_summary", "stopped", 200)
            exported = export_scenario(recording, output)
            self.assertEqual(exported["events"], 1)
            self.assertEqual(Scenario(json.loads(output.read_text())).state_at(100)[0]["pressure_pa"], 10)

    def test_pretty_export_remains_usable_when_larger_than_normalized_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            profile, recording = Path(directory) / "pretty.json", Path(directory) / "short.ssrec"
            scenario = Scenario({"version": 1, "events": [
                {"at_ns": i * 1000000, "set": {"pressure_pa": i}} for i in range(120)]})
            profile.write_text(json.dumps(scenario.export(), indent=4))
            self.assertGreater(profile.stat().st_size, 8192)
            result = subprocess.run([sys.executable, str(ROOT / "sw/tools/sensor.py"), "simulate", "--seconds", ".001",
                "--scenario", str(profile), "--output", str(recording)], check=True, capture_output=True, text=True, timeout=15)
            self.assertTrue(json.loads(result.stdout)["completed"])


if __name__ == "__main__": unittest.main()
