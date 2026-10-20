"""Bounded, transactional cross-message validation for live input and replay."""
from dataclasses import dataclass, field
from groundlark_contract.validation import validate, require


@dataclass
class State:
    boot: int
    identity: bytes
    sensors: frozenset
    retired: set = field(default_factory=set)
    configuration: bytes = b""
    revision: int = 0
    settings: dict = field(default_factory=dict)
    last: dict = field(default_factory=dict)
    identity_seen: bool = True
    config_seen: bool = False
    dropped_totals: dict = field(default_factory=dict)
    board: int = 0


class Sessions:
    def __init__(self, calibrations=None, max_devices=4, max_resets=32, checkpoint=None):
        if not 1 <= max_devices <= 16 or not 1 <= max_resets <= 256:
            raise ValueError("session capacity outside supported bounds")
        self.devices = {}
        self.max_devices, self.max_resets = max_devices, max_resets
        self.calibrations = calibrations
        if checkpoint is not None:
            self.restore(checkpoint)

    def checkpoint(self):
        """Recording boundary state; no samples are synthesized or rewritten."""
        return [dict(device=device, boot=state.boot, identity=state.identity.hex(),
                     configuration=state.configuration.hex(),
                     last={str(k): list(v) for k, v in state.last.items()},
                     retired=sorted(state.retired), dropped_totals={str(k): v for k, v in state.dropped_totals.items()},
                     identity_seen=state.identity_seen, config_seen=state.config_seen)
                for device, state in sorted(self.devices.items())]

    def restore(self, checkpoint):
        from .messages import envelope
        require(isinstance(checkpoint, list) and len(checkpoint) <= self.max_devices, 'checkpoint devices')
        require(not self.devices, 'checkpoint requires empty session')
        candidate = Sessions(self.calibrations, self.max_devices, self.max_resets)
        for entry in checkpoint:
            require(isinstance(entry, dict) and set(entry) == {'device', 'boot', 'identity', 'configuration',
                    'last', 'retired', 'dropped_totals', 'identity_seen', 'config_seen'}, 'checkpoint fields')
            device, boot = entry['device'], entry['boot']
            require(isinstance(device,str) and type(boot) is int and 0<boot<1<<64,
                    'checkpoint identity')
            require(all(isinstance(entry[k],str) and len(entry[k])<=4096
                        for k in ('identity','configuration')), 'checkpoint control bytes')
            require(device not in candidate.devices, 'duplicate checkpoint device')
            m = envelope(device, boot)
            m.identity.ParseFromString(bytes.fromhex(entry['identity']))
            candidate.accept(m)
            if entry['configuration']:
                m = envelope(device, boot)
                m.configuration.ParseFromString(bytes.fromhex(entry['configuration']))
                candidate.accept(m)
            state = candidate.devices[device]
            retired = entry['retired']
            require(isinstance(retired, list) and len(retired) <= self.max_resets and
                    all(type(v) is int and 0 < v < 1 << 64 and v != boot for v in retired) and
                    len(set(retired)) == len(retired), 'checkpoint retired boots')
            state.retired = set(retired)
            for field in ('identity_seen', 'config_seen'):
                require(type(entry[field]) is bool, 'checkpoint handshake')
                setattr(state, field, entry[field])
            require(not state.config_seen or bool(state.configuration), 'checkpoint configuration missing')
            require(isinstance(entry['last'], dict) and len(entry['last']) <= 8, 'checkpoint history')
            for sid, pair in entry['last'].items():
                require(isinstance(sid,str) and sid.isdecimal() and str(int(sid)) == sid and int(sid) in state.settings,
                        'checkpoint sensor')
                require(isinstance(pair, list) and len(pair) == 2 and
                        all(type(v) is int and 0 <= v < 1 << 64 for v in pair), 'checkpoint ordering')
                state.last[int(sid)] = tuple(pair)
            require(isinstance(entry['dropped_totals'], dict) and len(entry['dropped_totals']) <= 9,
                    'checkpoint loss totals')
            for sid, value in entry['dropped_totals'].items():
                require(isinstance(sid,str) and sid.isdecimal() and str(int(sid)) == sid and (int(sid) == 0 or int(sid) in state.sensors)
                        and type(value) is int and 0 <= value < 1 << 64, 'checkpoint loss total')
                state.dropped_totals[int(sid)] = value
        self.devices = candidate.devices

    def disconnect(self, device=None):
        for key, state in self.devices.items():
            if device is None or key == device:
                state.identity_seen = state.config_seen = False

    def accept(self, message):
        validate(message)
        device, boot, kind = message.device_id, message.boot_id, message.WhichOneof("body")
        state = self.devices.get(device)
        if kind == "identity":
            wire = message.identity.SerializeToString(deterministic=True)
            if state is not None and state.boot == boot:
                require(state.identity == wire, "identity changed within boot")
                state.identity_seen = True
                return kind
            retired = set() if state is None else state.retired | {state.boot}
            require(boot not in retired, "retired boot replay")
            require(len(retired) <= self.max_resets, "reset history exhausted; open a new recording")
            require(state is not None or len(self.devices) < self.max_devices, "device capacity exhausted")
            self.devices[device] = State(boot, wire, frozenset(message.identity.sensors), retired, board=message.identity.board)
            return kind
        require(state is not None and state.boot == boot and state.identity_seen, "identity handshake required")
        if kind == "configuration":
            c = message.configuration
            require({s.sensor_id for s in c.sensors} <= state.sensors, "configuration for undeclared sensor")
            wire = c.SerializeToString(deterministic=True)
            require(c.revision >= state.revision, "stale configuration")
            if c.revision == state.revision:
                require(wire == state.configuration, "configuration changed without revision")
            state.configuration, state.revision = wire, c.revision
            state.settings = {s.sensor_id: type(s).FromString(s.SerializeToString()) for s in c.sensors}
            state.config_seen = True
        elif kind == "status":
            s = message.status
            require(s.sensor_id == 0 or s.sensor_id in state.sensors, "status for undeclared sensor")
            if s.HasField("dropped_total"):
                require(s.dropped_total >= state.dropped_totals.get(s.sensor_id, 0), "loss total regressed")
                state.dropped_totals[s.sensor_id] = s.dropped_total
        else:
            b = message.batch
            require(state.config_seen and b.configuration_revision == state.revision, "effective configuration required")
            cfg = state.settings.get(b.sensor_id)
            require(cfg is not None and cfg.enabled, "sensor not enabled")
            if b.sensor_id == 8:
                require(all(s.time.domain == (1 if state.board == 1 else 2) for s in b.samples),
                        'pressure clock does not match board identity')
                if cfg.HasField('pressure_measurement_command'):
                    require(all(not s.pressure.HasField('read_interval_min_ns') or
                                cfg.pressure_measurement_command == 0x3615 for s in b.samples),
                            'pressure averaging interval disagrees with measurement command')
            previous = state.last.get(b.sensor_id)
            first, last = b.samples[0], b.samples[-1]
            next_sequence = 0 if previous is None else previous[0] + 1
            require(first.sequence >= next_sequence, "duplicate or reordered sample")
            if b.HasField("dropped_before"):
                require(first.sequence - next_sequence == b.dropped_before, "sequence gap disagrees with loss count")
            if previous is not None:
                require(first.time.acquisition_ns > previous[1], "acquisition clock moved backwards")
            if b.calibration_id:
                require(self.calibrations is not None, "calibration metadata missing")
                self.calibrations.verify(b.calibration_id, b.sensor_id, cfg, device)
            state.last[b.sensor_id] = (last.sequence, last.time.acquisition_ns)
        return kind
