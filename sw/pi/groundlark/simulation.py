"""Deterministic device models, not electrical or instruction-set emulation."""
from .sensors import NotReady
from .stimulus import Scenario, reading
from .skylark import defaults as skylark_defaults
from .burrowlark import SETTINGS as CLIMATE_SETTINGS


class Simulated:
    def __init__(self, sensor, seed=1, faults=(), scenario=None, clock=None):
        if type(sensor) is not int or not 1 <= sensor <= 20: raise ValueError("simulated sensor ID")
        if type(seed) is not int or not 0 <= seed < 1 << 64: raise ValueError("seed must be uint64")
        self.sensor, self.seed, self.index = sensor, seed, 0
        self.scenario, self.clock = scenario or Scenario(), clock
        self.settings = next(c for c in defaults(legacy_gnss=True) + defaults(True) + defaults() + skylark_defaults() if c["sensor_id"] == sensor)
        if len(faults) > 256: raise ValueError("fault fixture bound")
        self.faults = {}
        for f in faults:
            if set(f) != {"sensor", "sample", "action"} or f["sensor"] not in range(1, 21) or type(f["sample"]) is not int or not 0 <= f["sample"] <= 1_000_000:
                raise ValueError("fault fixture fields")
            if f["action"] not in ("timeout", "nack", "disconnect", "not_ready", "saturation", "short_read"):
                raise ValueError("unknown fault action")
            if f["sensor"] == sensor:
                if f["sample"] in self.faults: raise ValueError("duplicate fault")
                self.faults[f["sample"]] = f["action"]

    def configure(self, settings):
        self.settings = dict(settings)
        return dict(settings)

    def read(self):
        i = self.index
        self.index += 1
        now = self.clock() if self.clock is not None else i * self.settings["period_ns"]
        controls, _ = self.scenario.state_at(now)
        fault = controls["sensor_faults"].get(str(self.sensor), self.faults.get(i))
        if fault == "not_ready": raise NotReady("simulated data not ready")
        if fault == "timeout": raise TimeoutError("simulated timeout")
        if fault in ("nack", "disconnect", "short_read"): raise OSError("simulated " + fault)
        result = reading(self.sensor, self.settings, self.scenario, now, self.seed)
        if fault == "saturation" and self.sensor != 6:
            result.quality = 3
            if self.sensor <= 5:
                result.raw["acceleration"] = (32767, *result.raw["acceleration"][1:])
                if self.sensor == 5: result.raw["device_status"] |= 64
            elif self.sensor == 9 or 10 <= self.sensor <= 13: result.raw["counts"] = 8388607
            elif self.sensor in (7, 18, 19, 20): result.raw["counts"] = (8388607, *result.raw["counts"][1:])
            elif self.sensor == 8: result.raw["response"] = b"\x3f\xff" + result.raw["response"][2:]
        return result

    def close(self): pass


def defaults(remote=False, legacy_gnss=False):
    entries = [dict(sensor_id=i, enabled=True, period_ns=38_461_538, acceleration_range_g=2, angular_rate_range_dps=250) for i in range(1, 5 if legacy_gnss else 4)]
    entries += [dict(sensor_id=5, enabled=True, period_ns=40_000_000, tilt_mode=1),
                dict(sensor_id=6, enabled=True, period_ns=1_000_000_000)]
    if remote:
        return [dict(sensor_id=i, enabled=True, period_ns=100_000_000, cycle_count_x=200,
                     cycle_count_y=200, cycle_count_z=200) for i in (7,18,19,20)] + [
                dict(sensor_id=8, enabled=True, period_ns=10_000_000, pressure_min_pa=-250,
                     pressure_max_pa=250, pressure_part_number="SIMULATED-DLVR"), dict(CLIMATE_SETTINGS)]
    if not legacy_gnss:
        from .geophone import SETTINGS
        entries = entries[:3] + [dict(SETTINGS), dict(sensor_id=6, enabled=True, period_ns=1_000_000_000)]
    return entries
