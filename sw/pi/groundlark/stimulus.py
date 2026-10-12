"""Bounded, versioned signal scenarios. Units and approximations: docs/stimulus-models.md."""
from copy import deepcopy
import hashlib
import math
import struct
from .calibration import canonical
from .sensors import Reading

G = 9.80665
LIMIT_NS = 3_600_000_000_000
# Authored control schedules stay bounded to one hour. Evaluating their final
# state must continue for unattended station capture without restarting clocks.
TIME_LIMIT_NS = (1 << 63) - 1
DEFAULTS = {
    "orientation_deg": [0, 0, 0], "head_orientation_deg": [0, 0, 0],
    "acceleration_m_s2": [0, 0, 0], "magnetic_ut": [0, 20, -45],
    "pressure_pa": 0, "temperature_c": 25, "pressure_temperature_count": 768,
    "gnss_position": [49, -123, 0], "gnss_velocity_ned_m_s": [0, 0, 0],
    "so2_ppm": 0, "h2s_ppm": 0, "pm25_ug_m3": 5, "humidity_percent": 50, "ambient_pressure_pa": 101325,
    "geophone_velocity_m_s": 0, "gnss_fix": True, "gnss_pps": True,
    "gnss_antenna": "normal", "sensor_faults": {},
}
VECTOR_SIGNALS = {"orientation_deg", "head_orientation_deg", "acceleration_m_s2", "magnetic_ut"}
SCALAR_SIGNALS = {"pressure_pa", "temperature_c", "so2_ppm", "h2s_ppm", "pm25_ug_m3", "humidity_percent", "ambient_pressure_pa"}
WAVE_KEYS = {"offset", "amplitude", "frequency_hz", "phase_deg", "drift_per_s", "noise_peak",
             "pulse_start_s", "pulse_duration_s", "pulse_amplitude"}


def number(value, low=-1e6, high=1e6):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("finite stimulus number outside permitted range")


def signal_spec(value, orientation=False):
    if type(value) in (int, float):
        number(value)
        return
    if not isinstance(value, dict) or not value or not set(value) <= WAVE_KEYS:
        raise ValueError("unknown waveform fields")
    for key, item in value.items():
        number(item, 0 if key in ("frequency_hz", "noise_peak", "pulse_start_s", "pulse_duration_s") else -1e6,
               500 if key == "frequency_hz" else 3600 if key in ("pulse_start_s", "pulse_duration_s") else 1e6)
    if orientation and (value.get("noise_peak", 0) or value.get("pulse_amplitude", 0)):
        raise ValueError("orientation supports smooth sine/drift signals; use timed changes for pose steps")
    if value.get("pulse_amplitude", 0) and value.get("pulse_duration_s", 0) <= 0:
        raise ValueError("pulse needs positive duration")


def validate_changes(changes):
    if not isinstance(changes, dict) or not set(changes) <= DEFAULTS.keys(): raise ValueError("unknown controls")
    for name, value in changes.items():
        if name == "geophone_velocity_m_s":
            signal_spec(value)
            if isinstance(value, dict) and set(value) - {"amplitude", "frequency_hz", "phase_deg", "offset"}:
                raise ValueError("geophone model supports stationary sine/constant velocity only")
            continue
        if name in VECTOR_SIGNALS:
            if not isinstance(value, list) or len(value) != 3: raise ValueError("three-axis control required")
            for item in value: signal_spec(item, "orientation" in name)
        elif name in SCALAR_SIGNALS: signal_spec(value)
        elif name in ("gnss_fix", "gnss_pps"):
            if type(value) is not bool: raise ValueError(f"{name} must be boolean")
        elif name == "gnss_antenna":
            if not isinstance(value, str) or value not in ("normal", "open", "short"):
                raise ValueError("gnss_antenna must be normal, open or short")
        elif name == "sensor_faults":
            actions = {"none", "timeout", "nack", "disconnect", "not_ready", "saturation", "short_read"}
            if not isinstance(value, dict) or not set(value) <= {str(i) for i in range(1, 21)}:
                raise ValueError("fault controls require sensor IDs 1..20")
            if any(type(action) is not str or action not in actions for action in value.values()):
                raise ValueError("unknown timed fault action")
        elif name == "pressure_temperature_count":
            if type(value) is not int or not 0 <= value <= 2047: raise ValueError("11-bit temperature count")
        else:
            if not isinstance(value, list) or len(value) != 3: raise ValueError("three-component GNSS control")
            bounds = [(-85, 85), (-180, 180), (-1000, 100000)] if name == "gnss_position" else [(-300, 300)] * 3
            for item, (low, high) in zip(value, bounds): number(item, low, high)


class Scenario:
    """Schedule is owned by the acquisition thread; UI commands can append future events.

    Export contains every control change. Evaluation is pure with respect to
    sample order; advance only tracks which events need recording.
    """
    def __init__(self, document=None):
        document = deepcopy(document if document is not None else {"version": 1})
        if not isinstance(document, dict) or not set(document) <= {"version", "initial", "events"} or type(document.get("version")) is not int or document["version"] != 1:
            raise ValueError("stimulus scenario version/fields")
        initial = document.get("initial", {})
        validate_changes(initial)
        events = document.get("events", [])
        if not isinstance(events, list) or len(events) > 256: raise ValueError("scenario event limit")
        self._document = dict(version=1, initial=initial, events=[])
        self.now, self.emitted = -1, 0
        previous = -1
        for event in events:
            if not isinstance(event, dict) or set(event) != {"at_ns", "set"}: raise ValueError("scenario event fields")
            if type(event["at_ns"]) is not int or event["at_ns"] < previous: raise ValueError("scenario events must be chronological")
            self.schedule(event["at_ns"], event["set"])
            previous = event["at_ns"]
        self._check_size(self._document)

    @staticmethod
    def _check_size(document):
        if len(canonical(document)) > 8192: raise ValueError("scenario exceeds 8192 bytes")

    def export(self): return deepcopy(self._document)

    def schedule(self, at_ns, changes):
        if type(at_ns) is not int or not 0 <= at_ns <= LIMIT_NS or at_ns <= self.now:
            raise ValueError("control event must be in the unobserved future")
        events = self._document["events"]
        if len(events) >= 256: raise ValueError("event count limit")
        validate_changes(changes)
        event = {"at_ns": at_ns, "set": deepcopy(changes)}
        if len(canonical(event)) > 1536: raise ValueError("individual control event exceeds record budget")
        candidate = dict(self._document, events=sorted(events + [event], key=lambda e: e["at_ns"]))
        self._check_size(candidate)
        self._document = candidate

    def advance(self, now):
        if type(now) is not int or not self.now <= now <= TIME_LIMIT_NS: raise ValueError("scenario clock regressed/out of range")
        self.now = now
        start = self.emitted
        events = self._document["events"]
        while self.emitted < len(events) and events[self.emitted]["at_ns"] <= now: self.emitted += 1
        return deepcopy(events[start:self.emitted])

    def state_at(self, now):
        if type(now) is not int or not 0 <= now <= TIME_LIMIT_NS: raise ValueError("scenario time")
        state = deepcopy(DEFAULTS)
        state.update(self._document["initial"])
        displacement, previous = [0., 0., 0.], 0
        for event in self._document["events"]:
            if event["at_ns"] > now: break
            dt = (event["at_ns"] - previous) / 1e9
            displacement = [d + v * dt for d, v in zip(displacement, state["gnss_velocity_ned_m_s"])]
            state.update(event["set"])
            if "gnss_position" in event["set"]: displacement = [0., 0., 0.]
            previous = event["at_ns"]
        displacement = [d + v * ((now - previous) / 1e9) for d, v in zip(displacement, state["gnss_velocity_ned_m_s"])]
        return deepcopy(state), displacement


def signal(spec, now, seed, sensor, key):
    if type(spec) in (int, float): return float(spec), 0.
    t = now / 1e9
    omega = math.tau * spec.get("frequency_hz", 0)
    phase = omega * t + math.radians(spec.get("phase_deg", 0))
    amplitude, drift = spec.get("amplitude", 0), spec.get("drift_per_s", 0)
    value = spec.get("offset", 0) + amplitude * math.sin(phase) + drift * t
    derivative = amplitude * omega * math.cos(phase) + drift
    start = spec.get("pulse_start_s", 0)
    if start <= t < start + spec.get("pulse_duration_s", 0): value += spec.get("pulse_amplitude", 0)
    if spec.get("noise_peak", 0):
        digest = hashlib.sha256(f"{seed}:{sensor}:{key}:{now}".encode()).digest()
        uniform = int.from_bytes(digest[:8], "big") / ((1 << 64) - 1) * 2 - 1
        value += uniform * spec["noise_peak"]
    return value, derivative


def body_vector(vector, angles):
    """Rz(yaw) Ry(pitch) Rx(roll): world ENU into package frame."""
    r, p, y = map(math.radians, angles)
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    x, n, z = vector
    return (cp * cy * x + cp * sy * n - sp * z,
            (sr * sp * cy - cr * sy) * x + (sr * sp * sy + cr * cy) * n + sr * cp * z,
            (cr * sp * cy + sr * sy) * x + (cr * sp * sy - sr * cy) * n + cr * cp * z)


def gnss_locked(state):
    # Conservative loss-of-reception fixture, not RF/acquisition dynamics.
    # U141 FAULT is NC: this stimulus is never reported as device telemetry.
    return state["gnss_fix"] and state["gnss_antenna"] == "normal"


def nav_pvt(now, state, displacement):
    latitude, longitude, height = state["gnss_position"]
    north, east, down = displacement
    longitude += math.degrees(east / (6378137 * math.cos(math.radians(latitude))))
    latitude += math.degrees(north / 6378137)
    if not -89.9 <= latitude <= 89.9: raise ValueError("GNSS local-tangent model crossed polar bound")
    longitude = (longitude + 180) % 360 - 180
    vn, ve, vd = state["gnss_velocity_ned_m_s"]
    fix = gnss_locked(state)
    data = bytearray(92)
    struct.pack_into("<I", data, 0, (now // 1_000_000) % 604800000)
    data[20], data[21], data[23] = (3, 1, 12) if fix else (0, 0, 0)
    struct.pack_into("<iiiiII", data, 24, round(longitude * 1e7), round(latitude * 1e7),
                     round((height - down) * 1000), round((height - down) * 1000), 1000, 1500)
    struct.pack_into("<iiii", data, 48, round(vn * 1000), round(ve * 1000), round(vd * 1000), round(math.hypot(vn, ve) * 1000))
    heading = math.degrees(math.atan2(ve, vn)) % 360 if vn or ve else 0
    struct.pack_into("<iIIH", data, 64, round(heading * 1e5), 100, 100000, 100)
    data[78] = 0 if fix else 1  # invalidLlh; no UTC validity is asserted.
    return bytes(data)


def reading(sensor, cfg, scenario, now, seed):
    if sensor == 17:
        from .burrowlark import modeled_reading
        return modeled_reading(scenario, now, seed)
    if 10 <= sensor <= 16:
        from .skylark import modeled_reading
        return modeled_reading(sensor, scenario, now, seed)
    state, displacement = scenario.state_at(now)
    def scalar(name): return signal(state[name], now, seed, sensor, name)[0]
    def vector(name): return [signal(v, now, seed, sensor, f"{name}:{i}")[0] for i, v in enumerate(state[name])]
    clipped = False
    def quantize(value, low=-32768, high=32767):
        nonlocal clipped
        clipped |= not low <= value <= high
        return max(low, min(high, round(value)))
    temp = scalar("temperature_c")
    if sensor <= 5:
        angles = vector("orientation_deg")
        linear = vector("acceleration_m_s2")
        accel = body_vector([linear[0], linear[1], linear[2] + G], angles)
        if sensor <= 4:
            fs_a, fs_g = cfg["acceleration_range_g"], cfg["angular_rate_range_dps"]
            sensitivity_a = {2: .061, 4: .122, 8: .244, 16: .488}[fs_a] * G / 1000
            sensitivity_g = {125: 4.375, 250: 8.75, 500: 17.5, 1000: 35, 2000: 70}[fs_g] / 1000
            rates = [signal(v, now, seed, sensor, f"orientation_deg:{i}")[1] for i, v in enumerate(state["orientation_deg"])]
            r, p = map(math.radians, angles[:2])
            rd, pd, yd = rates
            gyro = [rd - yd * math.sin(p), pd * math.cos(r) + yd * math.sin(r) * math.cos(p),
                    -pd * math.sin(r) + yd * math.cos(r) * math.cos(p)]
            clipped |= any(abs(v) > fs_a * G for v in accel) or any(abs(v) > fs_g for v in gyro)
            raw = dict(acceleration=tuple(quantize(v / sensitivity_a) for v in accel),
                       angular_rate=tuple(quantize(v / sensitivity_g) for v in gyro), temperature=quantize((temp - 25) * 256))
        else:
            mode = cfg["tilt_mode"]
            gain = {1: 6000, 2: 3000, 3: 12000, 4: 12000}[mode]
            limit_g = {1: 1.2, 2: 2.4, 3: 1.2, 4: 1.2}[mode]
            clipped |= any(abs(v) > limit_g * G for v in accel)
            norm = math.sqrt(sum(v * v for v in accel))
            tilt = [math.asin(max(-1, min(1, v / norm))) if norm else 0 for v in accel]
            raw = dict(acceleration=tuple(quantize(v / G * gain) for v in accel),
                       angle=tuple(quantize(a * 32768 / math.pi) for a in tilt), temperature=quantize((temp + 273) * 18.9))
            raw["device_status"] = 64 if clipped else 0
            if norm < 1e-12: return Reading(raw, 4)  # No gravity vector from which to infer tilt.
    elif sensor == 9:
        # Steady-state mechanical transfer, electrical loading and RC pole.
        # DC velocity has zero output. Changes switch steady states, not transients.
        wave = state["geophone_velocity_m_s"]
        wave = wave if isinstance(wave, dict) else {"offset": wave}
        f = wave.get("frequency_hz", 0)
        s = complex(0, 2 * math.pi * f)
        omega = 2 * math.pi * 4.5
        load = 2_000_000 / (2_000_000 + 2395)
        h = 23.4 * s*s / (s*s + 1.4*omega*s + omega*omega) * load / (1 + s*2395*100.5e-9*load)
        value = wave.get("amplitude", 0) * (h * complex(math.cos(2*math.pi*f*now/1e9 + math.radians(wave.get("phase_deg", 0))), math.sin(2*math.pi*f*now/1e9 + math.radians(wave.get("phase_deg", 0))))).imag
        raw = dict(counts=quantize(value * cfg["geophone_gain"] / cfg["geophone_reference_v"] * 8388608, -8388608, 8388607), conversion_counter=(now // cfg["period_ns"]) & 255)
    elif sensor == 6: return Reading(dict(nav_pvt=nav_pvt(now, state, displacement)))
    elif sensor in (7, 18, 19, 20):
        # Nominal model gain at cycle count 200; not a fitted calibration.
        if any(cfg[f"cycle_count_{axis}"] != 200 for axis in "xyz"): raise ValueError("magnetic model requires cycle count 200")
        values = body_vector(vector("magnetic_ut"), vector("head_orientation_deg"))
        raw = dict(counts=tuple(quantize(v * 75, -(1 << 23), (1 << 23) - 1) for v in values))
    else:
        pressure = scalar("pressure_pa")
        low, high = cfg["pressure_min_pa"], cfg["pressure_max_pa"]
        clipped |= not low <= pressure <= high
        count = quantize(1638.4 + (pressure - low) * 13107.2 / (high - low), 0, 16383)
        raw = dict(response=struct.pack(">HH", count, state["pressure_temperature_count"] << 5))
    return Reading(raw, 3 if clipped else 1)
