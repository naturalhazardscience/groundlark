"""Shared bounded acquisition loop for modeled and Linux sensor adapters."""
from dataclasses import dataclass
from . import messages
from .sensors import NotReady, DataGap
from .transport import Outbox
from .fifo import Drain, FifoFault


@dataclass
class Channel:
    device: str
    boot: int
    settings: dict
    adapter: object
    sequence: int = 0
    due: int = 0
    last_time: int = -1
    failures: int = 0
    retries: int = 0
    offline: bool = False
    restart_at: int = 0
    clock_domain: int | None = None


class Acquisition:
    def __init__(self, writer, sessions, channels, capacity=64, calibration_ids=None,
                 retry_limit=2, failure_limit=3, cooldown_ns=1_000_000_000):
        if not 1 <= len(channels) <= 16 or not 0 <= retry_limit <= 10 or not 1 <= failure_limit <= 10 or cooldown_ns < 1:
            raise ValueError("acquisition bounds")
        self.writer, self.sessions, self.channels = writer, sessions, channels
        keys = [(c.device, c.boot, c.settings["sensor_id"]) for c in channels]
        if len(set(keys)) != len(keys): raise ValueError("duplicate acquisition channel")
        self.outbox = Outbox(keys, capacity)
        self.retry_limit, self.failure_limit, self.cooldown = retry_limit, failure_limit, cooldown_ns
        self.calibration_ids = calibration_ids or {}
        self.reads = self.missing = self.recoveries = 0

    def drain(self):
        while self.outbox.queue:
            message, arrived = self.outbox.pop()
            self.sessions.accept(message)
            self.writer.message(message, arrived)

    def emit(self, message, now):
        self.drain()
        self.sessions.accept(message)
        self.writer.message(message, now)

    def event(self, code, detail, now, **fields):
        self.drain()
        self.writer.event(code, detail, now, **fields)

    def start(self, now):
        groups = {}
        for c in self.channels:
            c.due = now
            groups.setdefault((c.device, c.boot), []).append(c)
            # Never advertise an effective configuration before successful readback.
            c.settings = c.adapter.configure(c.settings)
        for (device, boot), channels in groups.items():
            sensors = [c.settings["sensor_id"] for c in channels]
            board = 3 if set(sensors) <= set(range(10, 17)) else 2 if set(sensors) <= {7, 8, 17, 18, 19, 20} else 1
            for c in channels:
                if c.settings['sensor_id'] == 8: c.clock_domain = 1 if board == 1 else 2
            self.emit(messages.identity(device, boot, board, sensors), now)
            self.emit(messages.configuration(device, boot, [c.settings for c in channels]), now)

    def report(self, c, code, detail, now):
        self.emit(messages.status(c.device, c.boot, c.settings["sensor_id"], code, detail), now)

    def tick(self, clock):
        for c in self.channels:
            if getattr(c.adapter, 'buffered', False):
                self.tick_buffered(c, clock)
                continue
            now = clock()
            if now < c.due: continue
            period = c.settings["period_ns"]
            skipped = (now - c.due) // period
            c.sequence += skipped
            c.due += (skipped + 1) * period
            raw, quality = None, 2
            if c.offline and now >= c.restart_at and c.retries < self.retry_limit:
                c.retries += 1
                try:
                    effective = c.adapter.configure(c.settings)
                    if effective != c.settings: raise ValueError("configuration readback changed during recovery")
                    c.offline, c.failures = False, 0
                    self.recoveries += 1
                    self.report(c, 1, "sensor recovered", clock())
                except (OSError, ValueError) as error:
                    c.restart_at = clock() + self.cooldown
                    self.report(c, 3, error, clock())
            if not c.offline:
                try:
                    reading = c.adapter.read()
                    raw, quality, c.failures = reading.raw, reading.quality, 0
                except NotReady:
                    # A polling miss is visible but does not reset a healthy sensor.
                    pass
                except DataGap as error:
                    # A scheduler overrun is not a failed bus or configuration.
                    c.failures = 0
                    self.report(c, 4, error, clock())
                except (OSError, ValueError) as error:
                    c.failures += 1
                    self.report(c, 3, error, clock())
                    if c.failures >= self.failure_limit or isinstance(error, TimeoutError):
                        c.offline, c.restart_at = True, clock() + self.cooldown
                        self.report(c, 2, "offline; finite retry policy active", clock())
            acquired = clock()
            if acquired <= c.last_time: raise ValueError("acquisition clock did not advance")
            c.last_time = acquired
            message = messages.batch(c.device, c.boot, c.settings["sensor_id"], c.sequence, acquired,
                                     raw, quality, dropped=None if getattr(c.adapter, "loss_unknown", False) else skipped,
                                     clock_domain=c.clock_domain)
            ident = self.calibration_ids.get(c.settings["sensor_id"])
            if ident:
                cfg = self.sessions.devices[c.device].settings[c.settings["sensor_id"]]
                message = self.sessions.calibrations.apply(message, ident, cfg)
            self.outbox.put(message, acquired)
            c.sequence += 1
            self.reads += 1
            self.missing += raw is None

    def tick_buffered(self, c, clock):
        now = clock()
        if now < c.due and not c.adapter.ready(): return
        c.due = now + 20_000_000  # IRQ wakeup plus periodic drain if an edge is lost.
        if c.offline:
            if now < c.restart_at or c.retries >= self.retry_limit: return
            c.retries += 1
            try:
                if c.adapter.configure(c.settings) != c.settings: raise ValueError('FIFO configuration changed')
                c.offline, c.failures = False, 0
                self.recoveries += 1
                self.report(c, 1, 'FIFO recovered; timestamp mapping restarted', clock())
            except (OSError, ValueError) as error:
                c.restart_at = clock() + self.cooldown
                self.report(c, 3, error, clock())
                return
        try:
            drain = c.adapter.read()
            if not isinstance(drain, Drain) or len(drain.readings) > 32: raise ValueError('FIFO IPC bound')
            # Validate complete drain before emitting any of it.
            last = c.last_time
            for reading in drain.readings:
                if reading.acquisition_ns is None or not last < reading.acquisition_ns <= clock():
                    raise FifoFault('FIFO timestamp ordering; drain discarded')
                last = reading.acquisition_ns
            for event in getattr(drain, 'events', []):
                fields = dict(event)
                code = fields.pop('code')
                self.event(code, 'GNSS timing evidence; UTC not yet correlated', clock(), **fields)
            c.failures = 0
        except (OSError, ValueError) as error:
            c.failures += 1
            self.report(c, 4 if isinstance(error, FifoFault) else 3, error, clock())
            # One explicit missing marker; unknown conversion loss is never zero.
            at = clock()
            self.outbox.put(messages.batch(c.device, c.boot, c.settings['sensor_id'], c.sequence,
                                           at, None, 2, dropped=None), at)
            c.sequence += 1
            c.last_time = at
            self.reads += 1
            self.missing += 1
            if c.failures >= self.failure_limit or isinstance(error, TimeoutError):
                c.offline, c.restart_at = True, clock() + self.cooldown
                self.report(c, 2, 'FIFO offline; finite retry policy active', clock())
            return
        for index, reading in enumerate(drain.readings):
            gap = getattr(drain, 'gaps', {}).get(index)
            if gap: self.report(c, 4, gap, clock())
            sid, at = c.settings['sensor_id'], reading.acquisition_ns
            message = messages.batch(c.device, c.boot, sid, c.sequence, at, reading.raw,
                                     reading.quality, dropped=None)
            ident = self.calibration_ids.get(sid)
            if ident:
                message = self.sessions.calibrations.apply(message, ident, self.sessions.devices[c.device].settings[sid])
            self.outbox.put(message, clock())
            c.sequence += 1
            c.last_time = at
            self.reads += 1
            self.missing += reading.raw is None

    def finish(self, now):
        self.drain()
        self.writer.event("acquisition_summary", "bounded acquisition stopped", now,
                          reads=self.reads, missing=self.missing, queue_dropped=self.outbox.dropped_samples,
                          recoveries=self.recoveries,
                          pending_loss=[dict(device=k[0], sensor=k[2], count=v) for k, v in self.outbox.pending.items() if v != 0])

    def close(self):
        errors = []
        for c in self.channels:
            try: c.adapter.close()
            except Exception as error: errors.append(error)
        if errors: raise errors[0]
