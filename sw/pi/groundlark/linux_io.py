"""Linux device APIs only. Import is safe on hosts without these devices."""
import ctypes as c
import os
import re
import struct


def ioctl(fd, request, arg=0, mutate=False):
    import fcntl
    return fcntl.ioctl(fd, request, arg, mutate) if isinstance(arg, (bytes, bytearray)) else fcntl.ioctl(fd, request, arg)


class SPI:
    def __init__(self, path):
        if not re.fullmatch(r"/dev/spidev\d+\.\d+", path): raise ValueError("explicit spidev path required")
        self.fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)

    def transfer(self, data, mode=0, hz=1_000_000):
        if not 1 <= len(data) <= 256: raise ValueError("SPI transfer bound")
        ioctl(self.fd, 0x40016b01, bytes([mode]))
        tx, rx = c.create_string_buffer(data), c.create_string_buffer(len(data))
        transfer = struct.pack("=QQIIHBBBBBB", c.addressof(tx), c.addressof(rx), len(data), hz, 0, 8, 0, 0, 0, 0, 0)
        result = ioctl(self.fd, 0x40206b00, bytearray(transfer), True)
        if result != len(data): raise OSError("short SPI transfer")
        return rx.raw

    def close(self): os.close(self.fd)


class I2CMessage(c.Structure):
    _fields_ = [("addr", c.c_uint16), ("flags", c.c_uint16), ("length", c.c_uint16), ("buffer", c.c_void_p)]


class I2CTransfer(c.Structure):
    _fields_ = [("messages", c.POINTER(I2CMessage)), ("count", c.c_uint32)]


class I2C:
    def __init__(self, path):
        if not re.fullmatch(r"/dev/i2c-\d+", path): raise ValueError("explicit I2C path required")
        self.fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        try:
            ioctl(self.fd, 0x0702, 10)  # 100 ms adapter timeout.
            ioctl(self.fd, 0x0701, 0)   # No implicit adapter retries.
        except BaseException:
            self.close()
            raise

    def exchange(self, address, write, count):
        if not 0 <= address < 128 or not 0 <= count <= 256 or not 0 <= len(write) <= 256 or not (write or count): raise ValueError("I2C transfer bounds")
        tx, rx = c.create_string_buffer(write), c.create_string_buffer(max(1, count))
        messages = (I2CMessage * (bool(write) + bool(count)))()
        if write: messages[0] = I2CMessage(address, 0, len(write), c.addressof(tx))
        if count: messages[int(bool(write))] = I2CMessage(address, 1, count, c.addressof(rx))
        request = I2CTransfer(messages, len(messages))
        result = ioctl(self.fd, 0x0707, bytearray(bytes(request)), True)
        if result != len(messages): raise OSError("short I2C transaction")
        return rx.raw[:count]

    def close(self): os.close(self.fd)


class GPIORequest(c.Structure):
    _fields_ = [("offsets", c.c_uint32 * 64), ("flags", c.c_uint32), ("values", c.c_uint8 * 64),
                ("consumer", c.c_char * 32), ("lines", c.c_uint32), ("fd", c.c_int)]


class SensorEnable:
    """Active-low OE, requested disabled. Caller supplies verified chip/offset."""
    def __init__(self, chip, line):
        if not re.fullmatch(r"/dev/gpiochip\d+", chip) or not 0 <= line < 1024: raise ValueError("GPIO chip/line")
        chipfd = os.open(chip, os.O_RDONLY | os.O_CLOEXEC)
        try:
            request = GPIORequest()
            request.offsets[0], request.values[0], request.flags, request.lines = line, 1, 2, 1
            request.consumer = b"groundlark-sensor-oe"
            data = bytearray(bytes(request))
            ioctl(chipfd, (3 << 30) | (c.sizeof(request) << 16) | (0xb4 << 8) | 3, data, True)
            self.fd = GPIORequest.from_buffer_copy(data).fd
        finally: os.close(chipfd)

    def enabled(self, value): ioctl(self.fd, 0xc040b409, bytes([0 if value else 1]) + bytes(63))

    def close(self):
        try: self.enabled(False)
        finally: os.close(self.fd)


class GPIOEventRequest(c.Structure):
    _fields_ = [("offset", c.c_uint32), ("handleflags", c.c_uint32),
                ("eventflags", c.c_uint32), ("consumer", c.c_char * 32), ("fd", c.c_int)]


class RisingEdges:
    """GPIO v1 rising-edge notifications; timestamps are MONOTONIC, NOT RAW."""
    edge_kind = 1
    def __init__(self, chip, line):
        import fcntl
        if not re.fullmatch(r"/dev/gpiochip\d+", chip) or not 0 <= line < 1024: raise ValueError("GPIO chip/line")
        chipfd = os.open(chip, os.O_RDONLY | os.O_CLOEXEC)
        self.fd = None
        try:
            request = GPIOEventRequest(offset=line, handleflags=1, eventflags=self.edge_kind,
                                       consumer=b'groundlark-edge')
            data = bytearray(bytes(request))
            ioctl(chipfd, (3 << 30) | (c.sizeof(request) << 16) | (0xb4 << 8) | 4, data, True)
            self.fd = GPIOEventRequest.from_buffer_copy(data).fd
            fcntl.fcntl(self.fd, fcntl.F_SETFL, os.O_NONBLOCK)
        except BaseException:
            if self.fd is not None: os.close(self.fd); self.fd = None
            raise
        finally: os.close(chipfd)

    def read(self):
        try: data = os.read(self.fd, 16 * 64)
        except BlockingIOError: return []
        if not data or len(data) % 16: raise OSError('short GPIO edge record')
        result = []
        for timestamp, kind in struct.iter_unpack('=QI4x', data):
            if kind != self.edge_kind: raise OSError('unexpected GPIO edge')
            result.append(timestamp)
        return result

    def poll(self): return bool(self.read())

    def wait(self, timeout):
        import select
        return self.read() if select.select([self.fd], [], [], timeout)[0] else []

    def close(self):
        if self.fd is not None: os.close(self.fd); self.fd = None


class FallingEdges(RisingEdges):
    """Active-low ADC DRDY; GPIO v1 falling-edge event ID and flag are both 2."""
    edge_kind = 2
