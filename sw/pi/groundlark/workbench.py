"""UI-independent workbench: bounded simulation, raw traces, recording and replay.

All mutations are serialized. The browser renders snapshots, never owns samples.
The simulated clock advances in 1 ms steps, independent of wall-clock/UI load.
"""
from collections import deque
from io import BytesIO
import struct
from threading import RLock

from .calibration import Calibrations
from .recording import Reader, Writer, is_acquisition_metadata
from .runtime import Acquisition, Channel
from .session import Sessions
from .simulation import Simulated, defaults
from .stimulus import Scenario
from . import skylark
from .gnss_sim import GNSSSimulation, emit_pps

MAX_BYTES = 8 * 1024 * 1024
MAX_SECONDS = 180
POINTS = 400
NAMES = {1: "IMU 1", 2: "IMU 2", 3: "IMU 3", 4: "IMU 4", 5: "Inclinometer",
         6: "GNSS", 7: "Magnetometer", 8: "Infrasound", 9: "Geophone"}
NAMES.update(skylark.NAMES)
NAMES[17] = "Enclosure climate"
NAMES.update({7: "Magnetometer 1", 18: "Magnetometer 2", 19: "Magnetometer 3", 20: "Magnetometer 4"})
BOARDS = {"all": "HAT + Burrowlark", "hat": "Groundlark FPGA HAT",
          "burrowlark": "Burrowlark USB", "skylark": "Skylark USB"}

def board_configs(board):
    if board not in BOARDS: raise ValueError("Unknown or deferred board")
    if board == 'skylark': return skylark.defaults()
    hat = defaults() + [cfg for cfg in defaults(True) if cfg['sensor_id'] == 8]
    head = [cfg for cfg in defaults(True) if cfg['sensor_id'] in (7, 18, 19, 20, 17)]
    return (hat if board in ('all','hat') else []) + (head if board in ('all','burrowlark') else [])

QUALITY = {1: "Valid", 2: "Missing", 3: "Saturated", 4: "Fault"}


def vectors(raw, field):
    value = getattr(raw, field)
    return [getattr(value, axis) if value.HasField(axis) else None for axis in "xyz"]


def project_sample(sensor, sample):
    """Plot raw counts, without invented zeros, calibration or clock correlation."""
    result = dict(quality=QUALITY[sample.quality], primary=[None] * 3,
                  secondary=[None] * 3, detail="No measurement")
    kind = sample.WhichOneof("raw")
    if not kind:
        return result
    raw = getattr(sample, kind)
    if sensor <= 5:
        result.update(primary=vectors(raw, "acceleration"),
                      secondary=vectors(raw, "angular_rate" if sensor <= 4 else "angle"),
                      detail=f"Temperature register: {raw.temperature}" if raw.HasField("temperature") else "Temperature unknown")
    elif sensor == 9:
        result.update(primary=[raw.counts, None, None], detail=f"Racotech vertical • ADC counts • conversion {raw.conversion_counter}")
    elif sensor in (7, 18, 19, 20):
        result.update(primary=vectors(raw, "counts"), detail="RM3100 • raw signed XYZ counts")
    elif sensor == 8:
        p, t = struct.unpack(">HH", raw.response)
        result.update(primary=[p & 0x3fff, None, None], secondary=[t >> 5, None, None],
                      detail=f"Sensor status bits: {p >> 14} • raw DLVR response")
    elif 10 <= sensor <= 13:
        result.update(primary=[raw.counts, None, None], detail=f"ADS122C04 counts • conversion {raw.conversion_counter} • gas concentration uncalibrated")
    elif sensor == 14:
        result.update(primary=list(struct.unpack_from(">HHH", raw.response, 10)), detail="PMS5003 atmospheric PM1 / PM2.5 / PM10 (µg/m³) • original 32-byte frame retained")
    elif sensor in (15, 17):
        temperature = -45 + 175 * int.from_bytes(raw.response[:2], "big") / 65535
        humidity = max(0, min(100, -6 + 125 * int.from_bytes(raw.response[3:5], "big") / 65535))
        result.update(primary=[temperature, None, None], secondary=[humidity, None, None], detail=f"{'SHT45' if sensor == 17 else 'SHT40'} °C / %RH • CRC-checked raw frame retained")
    elif sensor == 16:
        pressure, temperature = skylark.barometer_units(raw.response, raw.calibration)
        result.update(primary=[pressure, None, None], secondary=[temperature, None, None], detail="Bosch BMP3 Pa / °C • factory compensation; raw frame and trim retained")
    else:
        payload = raw.nav_pvt
        fixed = bool(payload[21] & 1) and payload[20] >= 2
        if fixed:
            lon, lat, height = struct.unpack_from("<iii", payload, 24)
            result.update(primary=list(struct.unpack_from("<iii", payload, 48)),
                          detail=f"Fix {payload[20]} • {lat / 1e7:.7f}°, {lon / 1e7:.7f}° • {height / 1000:.2f} m")
        else:
            result["detail"] = "No GNSS fix • position and velocity unavailable"
    return result


class TraceSink:
    def __init__(self, owner, writer):
        self.owner, self.writer = owner, writer

    def message(self, message, arrived):
        self.writer.message(message, arrived)
        self.owner.observe(message, arrived)

    def event(self, code, detail, arrived, **fields):
        self.writer.event(code, detail, arrived, **fields)
        self.owner.observe_event(code, arrived, fields)
        self.owner.events.append((arrived / 1e9, code, str(detail)))


class Workbench:
    def __init__(self, document=None, seed=1, board="all"):
        self.lock = RLock()
        self.reset(document, seed, board)

    def clear_traces(self):
        self.traces = {i: deque(maxlen=POINTS) for i in self.sensor_ids}
        self.events = deque(maxlen=20)
        self.samples = self.missing = 0
        self.timing = dict(pps_count=0, last_pps_ns=None, locked=False, source="modeled" if getattr(self, "mode", "") == "Simulate" else "recorded", qualified=False)

    def reset(self, document=None, seed=1, board=None):
        # Validate before replacing the existing run.
        board = board or getattr(self, "board", "all")
        configs = board_configs(board)
        scenario = Scenario(document)
        if type(seed) is not int or not 0 <= seed < 1 << 64:
            raise ValueError("Seed must be a nonnegative 64-bit integer")
        with self.lock:
            if hasattr(self, "acquisition"):
                self.acquisition.close()
            self.board = board
            self.sensor_ids = tuple(cfg["sensor_id"] for cfg in configs)
            self.scenario, self.seed = scenario, seed
            self.mode, self.running, self.ended = "Simulate", False, False
            self.now = 0
            self.duration = MAX_SECONDS * 1_000_000_000
            self.error = ""
            self.clear_traces()
            self.stream = BytesIO()
            self.writer = Writer(self.stream, dict(format="groundlark-acquisition-v1", source="modeled-timing" if board in ("hat", "all") else "simulation",
                calibrations=[], utc_capture="m10-tim-tp-v1" if board in ("hat", "all") else None, timing="modeled GNSS/PPS evidence; UTC requires correlation", seed=seed, faults=[],
                remote=board in ("all", "burrowlark"), board=board, stimulus_model="ideal-v1", scenario=scenario.export()), max_bytes=MAX_BYTES)
            channels = [Channel("sim-head" if cfg["sensor_id"] in (7, 18, 19, 20, 17) else "sim-skylark" if cfg["sensor_id"] in skylark.SENSORS else "sim-pi",
                2 if cfg["sensor_id"] in (7, 18, 19, 20, 17) else 1, cfg,
                GNSSSimulation(scenario, lambda: self.now) if cfg["sensor_id"] == 6 else Simulated(cfg["sensor_id"], seed, scenario=scenario, clock=lambda: self.now))
                for cfg in configs]
            self.acquisition = Acquisition(TraceSink(self, self.writer), Sessions(), channels)
            self.acquisition.start(0)

    def observe_event(self, code, arrived, fields):
        if code == "pps_edge":
            self.timing["pps_count"] += 1
            self.timing["last_pps_ns"] = arrived
        elif code == "gnss_tim_tp":
            from .utc import tim_tp
            try:
                tim_tp(bytes.fromhex(fields["payload_hex"]))
                self.timing["locked"] = True
                self.timing["last_lock_ns"] = arrived
            except (ValueError, KeyError):
                self.timing["locked"] = False
        elif code in ("timing_fault", "gnss_timing_config"):
            self.timing["locked"] = False

    def observe(self, message, arrived):
        kind = message.WhichOneof("body")
        if kind == "batch":
            sid = message.batch.sensor_id
            for sample in message.batch.samples:
                point = project_sample(sid, sample)
                point.update(t=arrived / 1e9, sequence=sample.sequence,
                             acquisition_ns=sample.time.acquisition_ns if sample.time.HasField("acquisition_ns") else None,
                             clock_domain=sample.time.domain)
                self.traces.setdefault(sid, deque(maxlen=POINTS)).append(point)
                self.samples += 1
                self.missing += sample.quality == 2
        elif kind == "status":
            if message.status.sensor_id == 6 and message.status.code != 1:
                self.timing["locked"] = False
            self.events.append((arrived / 1e9, NAMES.get(message.status.sensor_id, "Device"), message.status.detail))

    def controls(self, changes):
        with self.lock:
            if self.mode != "Simulate" or self.ended:
                raise ValueError("Start a new simulation to change stimulus")
            self.scenario.schedule(self.now, changes)

    def toggle(self):
        with self.lock:
            if self.ended:
                raise ValueError("Run finished; start a new run or seek in replay")
            self.running = not self.running

    def pause(self):
        with self.lock:
            self.running = False

    def advance(self, milliseconds=50):
        if type(milliseconds) is not int or not 1 <= milliseconds <= 200:
            raise ValueError("Advance must be 1–200 ms")
        with self.lock:
            if not self.running:
                return
            try:
                if self.mode == "Replay":
                    self._read_until(min(self.duration, self.now + milliseconds * 1_000_000))
                    return
                for _ in range(milliseconds):
                    if self.now >= self.duration or self.writer.written > MAX_BYTES - 32768:
                        self.finish()
                        break
                    for change in self.scenario.advance(self.now):
                        self.acquisition.event("stimulus_change", "simulation controls changed", self.now, **change)
                    if 6 in self.sensor_ids: emit_pps(self.scenario, self.now, self.acquisition.event)
                    self.acquisition.tick(lambda: self.now)
                    self.acquisition.drain()
                    self.now += 1_000_000
            except (ValueError, OSError) as error:
                self.running = False
                self.error = str(error)

    def finish(self):
        with self.lock:
            if self.mode == "Simulate" and not self.ended:
                self.acquisition.finish(self.now)
                self.acquisition.close()
            self.running, self.ended = False, True
            return self.stream.getvalue()

    def scenario_json(self):
        with self.lock:
            if self.mode != "Simulate":
                raise ValueError("Use the CLI export-scenario command for imported recordings")
            return self.scenario.export()

    def load_recording(self, data):
        if not isinstance(data, bytes) or len(data) > MAX_BYTES:
            raise ValueError("Recording must be at most 8 MiB")
        reader = Reader(BytesIO(data))
        if not is_acquisition_metadata(reader.metadata):
            raise ValueError("Recording application metadata")
        sessions = Sessions(Calibrations(reader.metadata.get("calibrations", [])), checkpoint=reader.metadata.get("session_checkpoint"))
        first, last, completed = None, 0, False
        inventory = set()
        for arrived, item in reader:
            first = arrived if first is None else first
            last = arrived
            if last - first > 3_600_000_000_000:
                raise ValueError("Replay exceeds one-hour bound")
            completed = isinstance(item, dict) and item.get("code") == "acquisition_summary"
            if not isinstance(item, dict):
                sessions.accept(item)
                if item.WhichOneof("body") == "identity": inventory.update(item.identity.sensors)
            elif item.get("code") == "usb_disconnected" and item.get("device") is not None:
                sessions.disconnect(item["device"])
        if first is None:
            raise ValueError("Recording contains no records")
        if not inventory:
            raise ValueError("Recording contains no sensor identity")
        with self.lock:
            self.acquisition.close()
            self.sensor_ids = tuple(sorted(inventory))
            self.board = "skylark" if inventory and inventory <= set(skylark.SENSORS) else "burrowlark" if inventory <= {7, 18, 19, 20, 17} else "hat" if not inventory & {7, 18, 19, 20, 17, *skylark.SENSORS} else "all"
            self.recorded = data
            self.origin, self.duration = first, last - first
            self.mode, self.running, self.error = "Replay", False, "" if completed else "Recording has no completion summary"
            self.seek(0)

    def _read_until(self, target):
        while self.pending is not None and self.pending[0] - self.origin <= target:
            arrived, item = self.pending
            relative = arrived - self.origin
            if isinstance(item, dict):
                self.observe_event(item.get("code"), relative, item)
                self.events.append((relative / 1e9, item.get("code", "event"), item.get("detail", "")))
            else:
                self.observe(item, relative)
            self.pending = next(self.reader, None)
        self.now = target
        if self.pending is None:
            self.running, self.ended = False, True

    def seek(self, seconds):
        if type(seconds) not in (int, float) or not 0 <= seconds <= self.duration / 1e9:
            raise ValueError("Replay position outside recording")
        with self.lock:
            if self.mode != "Replay":
                raise ValueError("Seeking is only available in replay")
            self.running, self.ended = False, False
            self.clear_traces()
            self.reader = iter(Reader(BytesIO(self.recorded)))
            self.pending = next(self.reader, None)
            self._read_until(int(seconds * 1e9))

    def snapshot(self, sensor):
        with self.lock:
            latest = {sid: dict(points[-1]) if points else None for sid, points in self.traces.items()}
            return dict(mode=self.mode, running=self.running, ended=self.ended, seconds=self.now / 1e9,
                duration=self.duration / 1e9, error=self.error, samples=self.samples, missing=self.missing,
                latest=latest, points=list(self.traces.get(sensor, ())), events=list(self.events),
                timing={**self.timing, "locked": self.timing["locked"] and self.now-self.timing.get("last_lock_ns", 0) <= 1_500_000_000, "pps_recent": self.timing["last_pps_ns"] is not None and self.now-self.timing["last_pps_ns"] <= 1_500_000_000})
