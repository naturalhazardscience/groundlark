"""SDP32 fitted pressure sensor and legacy DLVR recording/test support."""
import time
from groundlark_contract.validation import sht_crc
from .sensors import Reading, NotReady

DLVR_SETTINGS = dict(sensor_id=8, enabled=True, period_ns=10_000_000,
                pressure_min_pa=-125, pressure_max_pa=125,
                pressure_part_number='DLVR-F50D-E1BS-I-NI3F')
SETTINGS = dict(DLVR_SETTINGS, pressure_part_number='SDP32-125PA-TR-250PCS')


def words(data, count):
    if len(data) != 3 * count or any(sht_crc(data[i:i+2]) != data[i+2]
                                   for i in range(0, len(data), 3)):
        raise OSError('SDP3x response length/CRC mismatch')
    return b''.join(data[i:i+2] for i in range(0, len(data), 3))


class SDP32:
    """Differential-pressure compensation, no averaging; RAW read completion.

    Sensirion SDP3x digital datasheet v1.1, sections 6.3 and 6.4.
    Recovery stops only this sensor; general-call reset would reset its bus peers.
    """
    def __init__(self, bus, sleep=time.sleep):
        self.bus, self.sleep = bus, sleep

    def command(self, value):
        self.bus.exchange(0x21, value.to_bytes(2, 'big'), 0)

    def configure(self, cfg):
        if any(cfg.get(k) != v for k, v in SETTINGS.items()):
            raise ValueError('SDP32 requires the fitted +/-125 Pa profile')
        self.sleep(.025)  # Maximum power-up delay.
        self.command(0x3ff9)
        self.sleep(.001)  # Stop-to-command minimum 500 us.
        self.command(0x367c)
        self.command(0xe102)
        identity = words(self.bus.exchange(0x21, b'', 18), 6)
        if int.from_bytes(identity[:4], 'big') & 0xffffff00 != 0x03010200:
            raise OSError('SDP32 product identity mismatch')
        self.identity = identity
        self.command(0x361e)
        self.sleep(.020)  # First result 8 ms plus 12 ms settling.
        self.read()  # Validate scale and communications before advertising ready.
        return cfg

    def read(self):
        data = self.bus.exchange(0x21, b'', 9)
        payload = words(data, 3)
        if int.from_bytes(payload[4:6], 'big') != 240:
            raise OSError('SDP32 pressure scale mismatch')
        counts = int.from_bytes(payload[:2], 'big', signed=True)
        return Reading(dict(sdp3x_response=data), 3 if abs(counts) > 30000 else 1)

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
