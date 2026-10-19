"""Modeled SPI/I2C buses for exercising the production Pi sensor drivers.

These adapt ideal sensor models to register/packet transfers. They do not emulate
Linux ioctls, electrical timing, instruction sets, or physical sensor noise.
Wire constants are also covered by independent fixtures in test_sensor_drivers.
"""
import struct
from .sensors import LSM6DSO, SCL3300, MAXM10S, scl_command, ubx_packet
from .simulation import Simulated


class IMUBus:
    def __init__(self, model):
        self.model = model
        self.registers = {0x0f: 0x6c, 0x12: 0, 0x1e: 3}

    def transfer(self, data, **_):
        address = data[0] & 127
        if data[0] & 128:
            if address == 0x20:
                raw = self.model.read().raw
                return b"\0" + struct.pack("<7h", raw["temperature"], *raw["angular_rate"], *raw["acceleration"])
            return bytes([0, self.registers.get(address, 0)])
        self.registers[address] = 0 if address == 0x12 and data[1] == 1 else data[1]
        return bytes(len(data))


class TiltBus:
    def __init__(self, model):
        self.model, self.previous, self.mode = model, bytes(4), 0

    def transfer(self, frame, **_):
        result = self.previous
        opcode = frame[0]
        if opcode & 128:
            value = int.from_bytes(frame[1:3], "big")
            if opcode == 0xb4:
                self.mode = value & 3
        else:
            raw = self.model.read().raw
            registers = dict(zip((1, 2, 3, 9, 10, 11, 5, 6),
                (*raw["acceleration"], *raw["angle"], raw["temperature"], raw["device_status"])))
            registers.update({0x10: 0xc1, 0x0d: self.mode})
            value = registers[opcode >> 2]
        self.previous = scl_command(opcode | 1, value & 65535)
        return result


class GNSSBus:
    def __init__(self, model, clock):
        self.model, self.clock = model, clock
        self.pending, self.last_epoch, self.configured = b"", -1, False

    def exchange(self, address, write, count):
        if address != 0x42:
            raise OSError("wrong modeled GNSS address")
        if not count:
            if write[3] == 0x8a:
                self.pending = bytes.fromhex("b56205010200068a98c1")
            else:
                self.pending = ubx_packet(6, 0x8b, bytes.fromhex("01000000 01002130e803 020021300100 0600912001"))
                self.configured = True
            return b""
        if write == b"\xfd":
            epoch = self.clock() // 1_000_000_000
            if self.configured and not self.pending and epoch != self.last_epoch:
                self.pending = ubx_packet(1, 7, self.model.read().raw["nav_pvt"])
                self.last_epoch = epoch
            return len(self.pending).to_bytes(2, "big")
        result, self.pending = self.pending[:count], self.pending[count:]
        return result


class GeophoneBus:
    """Register-level ADC model, including reset, readback and inverted output.

    Conversion values come from the mechanical stimulus, not the driver decoder.
    Timing is ideal; scheduler loss is exercised separately by driver fault tests.
    """
    def __init__(self, model):
        self.model, self.regs, self.started = model, [0]*4, False

    def exchange(self, address, write, count):
        if address != 0x40: raise OSError('wrong modeled geophone address')
        op = write[0]
        if op == 6: self.regs, self.started = [0]*4, False; return b''
        if op == 8: self.started = True; return b''
        if op & 0xf0 == 0x40:
            self.regs[(op >> 2) & 3] = write[1]; return b''
        if op & 0xf0 == 0x20:
            i = (op >> 2) & 3
            data = bytes([self.regs[i] | (0x80 if i == 2 and self.started else 0)])
        elif op == 0x10 and self.started:
            raw = self.model.read().raw
            data = bytes([raw['conversion_counter']]) + raw['counts'].to_bytes(3, 'big', signed=True)
        else: raise OSError('unexpected ADC command')
        return data + bytes(b ^ 255 for b in data) if self.regs[2] & 0x30 == 0x10 else data

    def close(self): pass


class PressureBus:
    """SDP32 command-state model; waveform and wire CRCs come from the stimulus."""
    def __init__(self, model):
        self.model, self.started, self.product_stage = model, False, 0

    def exchange(self, address, write, count):
        if address != 0x21: raise OSError('wrong modeled SDP32 address')
        if write == bytes.fromhex('3ff9') and not count:
            self.started, self.product_stage = False, 0
        elif write == bytes.fromhex('367c') and not count and not self.started:
            self.product_stage = 1
        elif write == bytes.fromhex('e102') and not count and self.product_stage == 1:
            self.product_stage = 2
        elif not write and count == 18 and self.product_stage == 2:
            self.product_stage = 0
            return bytes.fromhex('03019d0201690123a045675389ab77cdef84')
        elif write == bytes.fromhex('361e') and not count and not self.started:
            self.started = True
        elif not write and count == 9 and self.started:
            return self.model.read().raw['sdp3x_response']
        else: raise OSError('unexpected SDP32 command/state')
        return b''

    def close(self): pass


class VirtualDriver:
    def __init__(self, sensor, scenario, clock):
        self.model = Simulated(sensor, seed=1, scenario=scenario, clock=clock)
        if sensor == 8:
            from .pressure import SDP32
            self.driver = SDP32(PressureBus(self.model), sleep=lambda _: None)
            return
        if sensor == 9:
            from .geophone import ADS122C04
            self.driver = ADS122C04(GeophoneBus(self.model), sleep=lambda _: None, clock=lambda: clock()/1e9)
            self.loss_unknown = True
            return
        bus_type, driver_type = (IMUBus, LSM6DSO) if sensor <= 4 else (TiltBus, SCL3300) if sensor == 5 else (GNSSBus, MAXM10S)
        bus = bus_type(self.model, clock) if sensor == 6 else bus_type(self.model)
        self.driver = driver_type(bus, sleep=lambda _: None)

    def configure(self, settings):
        self.model.configure(settings)
        return self.driver.configure(settings)

    def read(self):
        return self.driver.read()

    def close(self):
        self.model.close()
