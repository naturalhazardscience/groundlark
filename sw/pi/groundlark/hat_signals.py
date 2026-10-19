"""Quantitative oracle for a fixed, eight-second modeled HAT bench experiment.

Measures the recorded output, not private simulator state. Tests deliberately
distort otherwise valid recordings to establish that wrong signals fail.
This is not a general-purpose accept/reject test for unknown physical motion.
"""
from copy import deepcopy
from io import BytesIO
import hashlib
import math
import struct

from .recording import Reader, Writer
from .runtime import Acquisition, Channel
from .session import Sessions
from .simulation import defaults
from .pressure import SETTINGS as PRESSURE_SETTINGS
from groundlark_contract.validation import sht_crc
from .stimulus import Scenario
from .virtual_hat import VirtualDriver
from .gnss_sim import GNSSSimulation, emit_pps, modeled_policy

PROFILE = {"version": 1, "initial": {
    "orientation_deg": [{"amplitude": 5, "frequency_hz": .5}, 0, 0],
    "acceleration_m_s2": [{"amplitude": .3, "frequency_hz": 2}, 0, 0],
    "geophone_velocity_m_s": {"amplitude": .0001, "frequency_hz": 10}, "gnss_position": [0, 0, 10], "gnss_velocity_ned_m_s": [1, 2, -.5],
    "pressure_pa": {"amplitude": 20, "frequency_hz": 1}}}
SECONDS = 8
SCOPE = "Modeled IMU/ADC/GNSS/SDP32 buses through production Pi drivers; physical timing and noise unqualified"


def configurations():
    return defaults()+[dict(PRESSURE_SETTINGS)]
# Independent nominal conversions from the effective bench configuration.
ACCEL_M_S2_PER_COUNT = .00059820565
GYRO_DEG_S_PER_COUNT = .00875
G = 9.80665


def xyz(vector):
    return tuple(getattr(vector, axis) for axis in "xyz")


def tone_metrics(points):
    """Frequency from interpolated positive zero crossings; amplitude via LS fit."""
    crossings = []
    for (t0, y0), (t1, y1) in zip(points, points[1:]):
        if y0 <= 0 < y1:
            crossings.append(t0 - y0 * (t1 - t0) / (y1 - y0))
    if len(crossings) < 3:
        return 0., 0., 0.
    frequency = (len(crossings) - 1) / (crossings[-1] - crossings[0])
    sine = [math.sin(2 * math.pi * frequency * t) for t, _ in points]
    cosine = [math.cos(2 * math.pi * frequency * t) for t, _ in points]
    ss = sum(s*s for s in sine)
    cc = sum(c*c for c in cosine)
    sc = sum(s*c for s, c in zip(sine, cosine))
    ys = sum(y*s for (_, y), s in zip(points, sine))
    yc = sum(y*c for (_, y), c in zip(points, cosine))
    determinant = ss * cc - sc * sc
    if determinant <= 1e-12:
        return frequency, 0., 0.
    a, b = (ys*cc-yc*sc)/determinant, (yc*ss-ys*sc)/determinant
    return frequency, math.hypot(a, b), math.degrees(math.atan2(b, a))


def check_recording(data):
    """Accept only the fixed-profile capture, with explicit quantitative tolerances."""
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("HAT bench recording exceeds 2 MiB")
    reader = Reader(BytesIO(data))
    sessions = Sessions()
    samples = {sid: [] for sid in (1, 2, 3, 9, 6, 8)}
    timing_events = []
    checks, configs, completed = [], {}, False
    def check(name, passed, detail):
        checks.append(dict(name=name, passed=bool(passed), detail=detail))
    for arrived, message in reader:
        completed = isinstance(message, dict) and message.get("code") == "acquisition_summary"
        if isinstance(message, dict):
            timing_events.append((arrived, message))
            continue
        kind = sessions.accept(message)
        if kind == "configuration":
            configs.update({cfg.sensor_id: cfg for cfg in message.configuration.sensors})
        elif kind == "batch":
            sid = message.batch.sensor_id
            if sid not in samples:
                raise ValueError("HAT bench expects only sensors 1, 2, 3, 6, 8 and 9")
            samples[sid].extend(message.batch.samples)
            if len(samples[sid]) > 4000:
                raise ValueError("HAT bench sample bound")
    inventory = all(samples.values()) and set(configs) == set(samples)
    check("Inventory & quality", inventory and completed and all(s.quality == 1 for rows in samples.values() for s in rows),
          f"{sum(map(len, samples.values()))} samples; six HAT sensors; completion={completed}")
    settings_ok = inventory and all(configs[i].period_ns == next(c["period_ns"] for c in configurations() if c["sensor_id"] == i) for i in samples)
    if settings_ok:
        settings_ok = all(configs[i].acceleration_range_g == 2 and configs[i].angular_rate_range_dps == 250 for i in range(1, 4))
        settings_ok &= (configs[8].pressure_min_pa,configs[8].pressure_max_pa,configs[8].pressure_part_number)==(-125,125,'SDP32-125PA-TR-250PCS')
    check("Effective configuration", settings_ok, "26 Hz / Ã‚Â±2 g / Ã‚Â±250 Ã‚Â°/s IMUs; 330 SPS vertical geophone")
    if not inventory or not settings_ok or any(s.quality != 1 for rows in samples.values() for s in rows):
        return dict(passed=False, checks=checks, samples=sum(map(len, samples.values())), recording_sha256=hashlib.sha256(data).hexdigest(), scope=SCOPE)
    timing_errors = []
    continuity = True
    for sid, rows in samples.items():
        if sid == 6: continue
        period = configs[sid].period_ns
        continuity &= len(rows) == SECONDS * (26 if sid in (1, 2, 3) else 100 if sid==8 else 330)
        for index, sample in enumerate(rows):
            continuity &= sample.sequence == index and sample.time.domain == 1 and sample.time.HasField("acquisition_ns")
            timing_errors.append(abs(sample.time.acquisition_ns - index * period))
    worst_timing = max(timing_errors)
    check("Timing & continuity", continuity and worst_timing <= 1_000_000, f"Maximum polling offset {worst_timing / 1e6:.3f} ms; limit 1 ms; no missing sequences")
    from .utc import intervals
    spans, _ = intervals(timing_events, modeled_policy(hashlib.sha256(data).hexdigest()))
    check("GNSS PPS / UTC association", len(spans) >= 4 and all(x["raw_end_ns"]-x["raw_start_ns"] == 1_000_000_000 for x in spans),
          f"{len(spans)} accepted modeled one-second intervals; explicit uncertainty policy")
    check("GNSS navigation", len(samples[6]) == SECONDS and all(struct.unpack_from("<iii", x.gnss.nav_pvt, 48) == (1000,2000,-500) for x in samples[6]),
          "Actual UBX driver: eight fixes and signed N/E/D velocity 1 / 2 / -0.5 m/s")
    tones, rocking, gravity_errors, gyro_errors = [], [], [], []
    for sid in range(1, 4):
        rows = samples[sid]
        times = [s.time.acquisition_ns / 1e9 for s in rows]
        accel = [tuple(v * ACCEL_M_S2_PER_COUNT for v in xyz(s.imu.acceleration)) for s in rows]
        tones.append(tone_metrics([(t, a[0]) for t, a in zip(times, accel)]))
        gravity_errors.extend(abs(math.hypot(a[1], a[2]) - G) for a in accel)
        # Independent kinematic identity: integrated gyro equals roll inferred
        # from gravity. This does not call the stimulus rotation/derivative code.
        roll = [math.degrees(math.atan2(a[1], a[2])) for a in accel]
        rocking.append(tone_metrics(list(zip(times, roll))))
        integrated = roll[0]
        for index in range(1, len(rows)):
            rates = (rows[index-1].imu.angular_rate.x, rows[index].imu.angular_rate.x)
            integrated += sum(rates) * .5 * GYRO_DEG_S_PER_COUNT * (times[index] - times[index-1])
            gyro_errors.append(abs(integrated - roll[index]))
            gyro_errors.extend(abs(getattr(rows[index].imu.angular_rate, axis) * GYRO_DEG_S_PER_COUNT) for axis in "yz")
    check("IMU frequency, gain & phase", all(abs(f - 2) <= .01 and abs(a - .3) <= .003 and abs(p) <= 2 for f, a, p in tones),
          f"IMU 1: {tones[0][0]:.4f} Hz, {tones[0][1]:.4f} m/sÃ‚Â², {tones[0][2]:.3f}Ã‚Â°; limits 2 Ã‚Â±0.01 Hz, 0.300 Ã‚Â±0.003 m/sÃ‚Â², phase Ã‚Â±2Ã‚Â° (all three checked)")
    check("Gravity magnitude", max(gravity_errors) <= .001,
          f"Maximum YZ gravity error {max(gravity_errors):.6f} m/sÃ‚Â²; limit 0.001")
    check("Known roll waveform", all(abs(f-.5) <= .005 and abs(a-5) <= .02 and abs(p) <= 2 for f, a, p in rocking),
          f"Gravity-derived roll: {rocking[0][0]:.4f} Hz, {rocking[0][1]:.4f}Ã‚Â°; expected 0.5 Ã‚Â±0.005 Hz, 5 Ã‚Â±0.02Ã‚Â°, phase Ã‚Â±2Ã‚Â°")
    check("Gyro / gravity consistency", max(gyro_errors) <= .02,
          f"Maximum integrated roll error {max(gyro_errors):.4f}Ã‚Â°; limit 0.02Ã‚Â°")
    coherent = all(len(samples[i]) == len(samples[1]) and all(
        a.imu.SerializeToString() == b.imu.SerializeToString() for a, b in zip(samples[1], samples[i])) for i in (2, 3))
    check("Three-IMU coherence", coherent, "All three raw IMU streams agree for identical noiseless excitation")
    # Independent fixture: Racotech mechanical response + loaded input RC at 10 Hz.
    # 100 um/s produces 2.299408 mV peak and +37.44222 degrees (nominal).
    rows = samples[9]
    gain, phase = 602776.1, math.radians(37.44222)
    errors = [abs(sample.geophone.counts - gain*math.sin(20*math.pi*sample.time.acquisition_ns/1e9 + phase)) for sample in rows]
    counters_ok = all(s.geophone.conversion_counter == i % 256 for i,s in enumerate(rows))
    check("Geophone gain, phase & counter", max(errors) < 150 and counters_ok,
          f"10 Hz / 100 um/s reference; maximum count error {max(errors):.2f}; limit 150; counter wrap checked")
    # Independent SDP32 nominal transfer: signed pressure *240, temperature *200.
    frames=[s.pressure.sdp3x_response for s in samples[8]]
    valid_frames=all(len(frame)==9 for frame in frames)
    pressure_errors=[]
    if valid_frames:
        for sample,frame in zip(samples[8],frames):
            word=int.from_bytes(frame[:2],'big',signed=True)
            temp=int.from_bytes(frame[3:5],'big',signed=True)
            valid_frames &= temp==5000 and int.from_bytes(frame[6:8],'big')==240
            valid_frames &= all(sht_crc(frame[i:i+2])==frame[i+2] for i in (0,3,6))
            expected=4800*math.sin(2*math.pi*sample.time.acquisition_ns/1e9)
            pressure_errors.append(abs(word-expected))
    check("Infrasound raw response & waveform", valid_frames and bool(pressure_errors) and max(pressure_errors)<=.501,
          "SDP32 driver: 100 Hz, 1 Hz / 20 Pa sine; signed pressure within 0.501 count, temperature and three CRCs preserved")
    return dict(passed=all(c["passed"] for c in checks), checks=checks, samples=sum(map(len, samples.values())),
                recording_sha256=hashlib.sha256(data).hexdigest(), scope=SCOPE)


def run_bench():
    scenario, stream, now = Scenario(deepcopy(PROFILE)), BytesIO(), 0
    clock = lambda: now
    channels = [Channel("bench-pi", 1, cfg, GNSSSimulation(scenario, clock) if cfg["sensor_id"] == 6 else
                        VirtualDriver(cfg["sensor_id"], scenario, clock)) for cfg in configurations()]
    writer = Writer(stream, dict(format="groundlark-acquisition-v1", source="modeled-timing", utc_capture="m10-tim-tp-v1",
        calibrations=[], bench="hat-signals-v3", scenario=deepcopy(PROFILE), timing="modeled 1 ms polling clock", model_scope=SCOPE), max_bytes=2 * 1024 * 1024)
    acquisition = Acquisition(writer, Sessions(), channels)
    try:
        acquisition.start(0)
        while now < SECONDS * 1_000_000_000:
            emit_pps(scenario, now, acquisition.event)
            acquisition.tick(clock)
            acquisition.drain()
            now += 1_000_000
        acquisition.finish(now)
    finally:
        acquisition.close()
    data = stream.getvalue()
    return data, check_recording(data)
