"""Small polling drivers with injected buses; manufacturer references in docs."""
from dataclasses import dataclass
from collections import deque
import struct
import time


class NotReady(OSError):
    pass


class DataGap(OSError):
    """Communication succeeded, but conversion continuity was lost.

    Emit a missing marker and unknown loss without resetting a healthy device.
    """


@dataclass
class Reading:
    raw: dict
    quality: int = 1
    acquisition_ns: int | None = None


class LSM6DSO:
    PERIODS = {38461538: 2, 19230769: 3, 9615385: 4, 4807692: 5}

    def __init__(self, bus, sleep=time.sleep, clock=time.monotonic):
        self.bus, self.sleep, self.clock = bus, sleep, clock

    def reg(self, address, count=1):
        data = self.bus.transfer(bytes([address | 0x80]) + bytes(count), mode=0, hz=1_000_000)
        if len(data) != count + 1: raise OSError("short IMU read")
        return data[1:]

    def write(self, address, value):
        self.bus.transfer(bytes([address, value]), mode=0, hz=1_000_000)

    def configure(self, cfg):
        if cfg["period_ns"] not in self.PERIODS: raise ValueError("IMU supports this driver's 26/52/104/208 Hz profiles only")
        if self.reg(0x0f) != b"\x6c": raise OSError("LSM6DSO identity mismatch")
        self.write(0x12, 1)
        for _ in range(100):
            if not self.reg(0x12)[0] & 1: break
            self.sleep(.001)
        else: raise TimeoutError("IMU reset timeout")
        odr = self.PERIODS[cfg["period_ns"]] << 4
        accel = {2: 0, 4: 8, 8: 12, 16: 4}[cfg["acceleration_range_g"]]
        gyro = {125: 2, 250: 0, 500: 4, 1000: 8, 2000: 12}[cfg["angular_rate_range_dps"]]
        # AN5192 UI path: high performance, accelerometer LPF1 only; gyro
        # LPF2, LPF1 bypassed, high-pass disabled. Record filter state as well
        # as ODR so a recording describes its actual bandwidth.
        # Shared SPI: disable I2C (CTRL4_C bit 2) and I3C (CTRL9_XL bit 1)
        # before starting conversion; preserve CTRL9_XL's reset DEN_X/Y/Z bits.
        settings = {0x10: odr | accel, 0x11: odr | gyro, 0x12: 0x44,
                    0x13: 0x04, 0x15: 0, 0x16: 0, 0x17: 0, 0x18: 0xE2}
        for address in (0x12, 0x13, 0x18, 0x15, 0x16, 0x17, 0x10, 0x11): self.write(address, settings[address])
        for address, value in settings.items():
            if self.reg(address)[0] != value: raise OSError("IMU configuration readback mismatch")
        self.sleep(.1)
        return dict(cfg, register_config=b"".join(bytes([r, v]) for r, v in sorted(settings.items())))

    def read(self):
        if self.reg(0x1e)[0] & 3 != 3: raise NotReady("IMU data not ready")
        values = struct.unpack("<7h", self.reg(0x20, 14))
        return Reading(dict(temperature=values[0], angular_rate=values[1:4], acceleration=values[4:7]),
                       3 if any(v in (-32768, 32767) for v in values[1:]) else 1)


def scl_crc(data):
    crc = 255
    for byte in data:
        crc ^= byte
        for _ in range(8): crc = ((crc << 1) ^ (0x1d if crc & 128 else 0)) & 255
    return crc ^ 255


def scl_command(opcode, value=0):
    data = bytes([opcode]) + value.to_bytes(2, "big")
    return data + bytes([scl_crc(data)])


class SCL3300:
    def __init__(self, bus, sleep=time.sleep):
        self.bus, self.sleep = bus, sleep

    def transfer(self, frame):
        self.sleep(.00002)  # CS high >=10 us; scheduler oversleep is safe.
        data = self.bus.transfer(frame, mode=0, hz=1_000_000)
        if len(data) != 4: raise OSError("short SCL3300 transfer")
        return data

    @staticmethod
    def response(data, opcode):
        if scl_crc(data[:3]) != data[3]: raise OSError("SCL3300 CRC mismatch")
        if data[0] & 0xfc != opcode: raise OSError("SCL3300 off-frame address mismatch")
        return int.from_bytes(data[1:3], "big"), data[0] & 3

    def reg(self, address):
        frame = scl_command(address << 2)
        self.transfer(frame)
        return self.response(self.transfer(frame), address << 2)

    def configure(self, cfg):
        mode = cfg["tilt_mode"]
        if mode not in (1, 2, 3, 4) or cfg["period_ns"] < 10_000_000: raise ValueError("SCL3300 polling profile")
        self.transfer(scl_command(0xb4, 0))
        self.sleep(.003)
        self.transfer(scl_command(0xb4, 0x20))
        self.sleep(.003)
        self.transfer(scl_command(0xb4, mode - 1))
        self.transfer(scl_command(0xb0, 0x1f))
        self.sleep({1: .025, 2: .015, 3: .100, 4: .100}[mode])
        frame = scl_command(0x18)
        self.transfer(frame)
        self.transfer(frame)
        _, rs = self.response(self.transfer(frame), 0x18)
        if rs != 1: raise OSError("SCL3300 startup flags did not clear")
        who, rs = self.reg(0x10)
        actual, mode_rs = self.reg(0x0d)
        if who != 0xc1 or rs != 1 or mode_rs != 1 or actual & 3 != mode - 1:
            raise OSError("SCL3300 identity/mode readback mismatch")
        return cfg

    def read(self):
        values, statuses = [], []
        for address in (1, 2, 3, 9, 10, 11, 5, 6):
            value, rs = self.reg(address)
            values.append(value)
            statuses.append(rs)
        signed = [v - 65536 if v & 32768 else v for v in values[:-1]]
        summary = values[-1]
        quality = 1 if not summary and all(s == 1 for s in statuses) else 4
        if summary == 0x40 and all(s in (1, 3) for s in statuses): quality = 3
        return Reading(dict(acceleration=signed[:3], angle=signed[3:6], temperature=signed[6], device_status=summary), quality)


def ubx_packet(cls, ident, payload):
    data = bytes([cls, ident]) + len(payload).to_bytes(2, "little") + payload
    a = b = 0
    for byte in data:
        a = (a + byte) & 255
        b = (b + a) & 255
    return b"\xb5\x62" + data + bytes([a, b])


class UBXParser:
    def __init__(self):
        self.buffer = bytearray()
        self.errors = 0

    def feed(self, data):
        if len(data) > 256: raise ValueError("UBX input chunk limit")
        self.buffer.extend(data)
        while True:
            start = self.buffer.find(b"\xb5\x62")
            if start < 0:
                self.buffer[:] = self.buffer[-1:] if self.buffer.endswith(b"\xb5") else b""
                return
            del self.buffer[:start]
            if len(self.buffer) < 6: return
            size = int.from_bytes(self.buffer[4:6], "little")
            if size > 1024:
                self.errors += 1
                del self.buffer[0]
                continue
            if len(self.buffer) < size + 8: return
            cls, ident = self.buffer[2:4]
            payload = bytes(self.buffer[6:6 + size])
            if bytes(self.buffer[:size + 8]) != ubx_packet(cls, ident, payload):
                self.errors += 1
                del self.buffer[0]
                continue
            del self.buffer[:size + 8]
            yield cls, ident, payload


class MAXM10S:
    KEYS = ((0x30210001, 2), (0x30210002, 2), (0x20910006, 1))

    def __init__(self, bus, sleep=time.sleep):
        self.bus, self.sleep, self.parser = bus, sleep, UBXParser()
        self.last_tow = None
        self.pending = deque()

    def poll(self):
        count = self.bus.exchange(0x42, b"\xfd", 2)
        if len(count) != 2: raise OSError("short GNSS byte count")
        count = int.from_bytes(count, "big")
        if count == 65535: raise OSError("GNSS stream unavailable")
        if not count: return []
        count = min(count, 256)
        data = self.bus.exchange(0x42, b"\xff", count)
        if len(data) != count: raise OSError("short GNSS stream")
        before = self.parser.errors
        packets = list(self.parser.feed(data))
        if self.parser.errors != before: raise OSError("GNSS corrupt UBX frame rejected")
        return packets

    def configuration_values(self, cfg):
        ns = cfg["period_ns"]
        if ns % 1_000_000 or not 1000 <= ns // 1_000_000 <= 60000: raise ValueError("GNSS profile requires integer milliseconds, 1..60 seconds")
        return (ns // 1_000_000, 1, 1)

    def configure(self, cfg):
        wanted = self.configuration_values(cfg)
        fields = b"".join(key.to_bytes(4, "little") + value.to_bytes(size, "little")
                          for (key, size), value in zip(self.KEYS, wanted))
        self.bus.exchange(0x42, ubx_packet(6, 0x8a, b"\x00\x01\x00\x00" + fields), 0)
        acknowledged = False
        for _ in range(100):
            for cls, ident, payload in self.poll():
                if cls == 5 and payload == b"\x06\x8a":
                    if ident == 0: raise OSError("GNSS rejected configuration")
                    if ident == 1: acknowledged = True
            if acknowledged: break
            self.sleep(.01)
        if not acknowledged: raise TimeoutError("GNSS configuration ACK timeout")
        keys = b"".join(key.to_bytes(4, "little") for key, _ in self.KEYS)
        self.bus.exchange(0x42, ubx_packet(6, 0x8b, b"\x00\x00\x00\x00" + keys), 0)
        for _ in range(100):
            for cls, ident, payload in self.poll():
                if (cls, ident) == (6, 0x8b) and len(payload) >= 4:
                    values, offset = {}, 4
                    sizes = dict(self.KEYS)
                    while offset < len(payload):
                        if offset + 4 > len(payload): raise OSError("GNSS readback truncated")
                        key = int.from_bytes(payload[offset:offset + 4], "little")
                        size = sizes.get(key)
                        if size is None or key in values or offset + 4 + size > len(payload): raise OSError("GNSS readback key/size")
                        values[key] = int.from_bytes(payload[offset + 4:offset + 4 + size], "little")
                        offset += 4 + size
                    if values != dict(zip(sizes, wanted)): raise OSError("GNSS configuration readback mismatch")
                    return cfg
            self.sleep(.01)
        raise TimeoutError("GNSS readback timeout")

    def read(self):
        # Bound bus work per acquisition call even if the receiver streams NMEA.
        for _ in range(8):
            if self.pending:
                payload = self.pending.popleft()
                self.last_tow = int.from_bytes(payload[:4], "little")
                return Reading(dict(nav_pvt=payload))
            for cls, ident, payload in self.poll():
                if (cls, ident) == (1, 7) and len(payload) == 92:
                    tow = int.from_bytes(payload[:4], "little")
                    if tow == self.last_tow or any(p[:4] == payload[:4] for p in self.pending): continue
                    if len(self.pending) >= 8: raise OSError("GNSS pending queue overflow")
                    self.pending.append(payload)
        if self.pending:
            payload = self.pending.popleft()
            self.last_tow = int.from_bytes(payload[:4], "little")
            return Reading(dict(nav_pvt=payload))
        raise NotReady("GNSS NAV-PVT not ready")
