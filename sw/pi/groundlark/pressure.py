"""SDP32 fitted pressure sensor and legacy DLVR recording/test support."""
import time
from groundlark_contract.validation import sht_crc
from .sensors import Reading, NotReady, DataGap

DLVR_SETTINGS = dict(sensor_id=8, enabled=True, period_ns=10_000_000,
                pressure_min_pa=-125, pressure_max_pa=125,
                pressure_part_number='DLVR-F50D-E1BS-I-NI3F')
SETTINGS = dict(DLVR_SETTINGS, pressure_part_number='SDP32-125PA-TR-250PCS',
                pressure_measurement_command=0x3615)


def words(data, count):
    if len(data) != 3 * count or any(sht_crc(data[i:i+2]) != data[i+2]
                                   for i in range(0, len(data), 3)):
        raise OSError('SDP3x response length/CRC mismatch')
    return b''.join(data[i:i+2] for i in range(0, len(data), 3))


class SDP32:
    """Differential-pressure compensation, average until read; RAW completion.

    Sensirion SDP3x digital datasheet v1.1, sections 6.3 and 6.4.
    Recovery stops only this sensor; general-call reset would reset its bus peers.
    """
    loss_unknown = True

    def __init__(self, bus, sleep=time.sleep, clock_ns=time.monotonic_ns):
        self.bus, self.sleep, self.clock_ns = bus, sleep, clock_ns
        self.previous_read = None
        self.configured = False

    def command(self, value):
        self.bus.exchange(0x21, value.to_bytes(2, 'big'), 0)

    def configure(self, cfg):
        if any(cfg.get(k) != v for k, v in SETTINGS.items()):
            raise ValueError('SDP32 requires the fitted +/-125 Pa profile')
        self.configured = False
        self.previous_read = None
        self.sleep(.025)  # Maximum power-up delay.
        self.command(0x3ff9)
        self.sleep(.001)  # Stop-to-command minimum 500 us.
        self.command(0x367c)
        self.command(0xe102)
        identity = words(self.bus.exchange(0x21, b'', 18), 6)
        if int.from_bytes(identity[:4], 'big') & 0xffffff00 != 0x03010200:
            raise OSError('SDP32 product identity mismatch')
        self.identity = identity
        self.command(0x3615)
        self.sleep(.020)  # First result 8 ms plus 12 ms settling.
        self.read()  # Validate scale and communications before advertising ready.
        self.configured = True
        return cfg

    def read(self):
        start = self.clock_ns()
        previous = self.previous_read
        if self.configured and previous and 0 <= start - previous[1] < 1_000_000:
            # More than one conversion even at the 1.8 kHz oscillator limit.
            raise NotReady('SDP32 averaging interval shorter than one conversion')
        try:
            data = self.bus.exchange(0x21, b'', 9)
            end = self.clock_ns()
            payload = words(data, 3)
            if int.from_bytes(payload[4:6], 'big') != 240:
                raise OSError('SDP32 pressure scale mismatch')
        except OSError:
            # A partially completed read may have reset the sensor averager.
            self.previous_read = None
            raise
        self.previous_read = (start, end)
        timing = {}
        if self.configured:
            if previous is None:
                raise DataGap('SDP32 averaging interval unknown after failed read; re-anchored')
            low, high = start - previous[1], end - previous[0]
            # Beyond 25 ms the sensor changes from arithmetic to exponential
            # averaging. Drain/reset that window but do not publish it as normal.
            if end < start or low < 1_000_000 or high > 25_000_000:
                if end < start:
                    self.previous_read = None
                raise DataGap('SDP32 averaging interval outside 1-25 ms; re-anchored')
            timing = dict(read_interval_min_ns=low, read_interval_max_ns=high)
        counts = int.from_bytes(payload[:2], 'big', signed=True)
        return Reading(dict(sdp3x_response=data, **timing), 3 if abs(counts) > 30000 else 1)

    def close(self):
        try:
            self.command(0x3ff9)
        finally:
            self.bus.close()


class DLVR:
    def __init__(self, bus): self.bus = bus

    def configure(self, cfg):
        if any(cfg.get(k) != v for k, v in DLVR_SETTINGS.items()):
            raise ValueError('DLVR requires the fitted F50D fast-mode profile')
        # This factory-configured part has no writable range or identity register.
        self.read()
        return cfg

    def read(self):
        data = self.bus.exchange(0x28, b'', 4)
        if len(data) != 4: raise OSError('short DLVR response')
        status = data[0] >> 6
        if status == 2: raise NotReady('DLVR busy/stale response')
        if status: raise OSError('DLVR command/diagnostic state')
        return Reading(dict(response=data))
