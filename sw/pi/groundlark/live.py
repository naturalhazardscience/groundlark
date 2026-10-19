"""Explicit Linux bus mapping and a bounded, reconnecting USB CDC reader."""
from dataclasses import dataclass
import os
import re
from .sensors import LSM6DSO, SCL3300, MAXM10S


@dataclass
class Factory:
    sensor: int
    path: str
    fifo: bool = False
    utc: bool = False
    drdy: dict | None = None

    def __call__(self):
        from .linux_io import SPI, I2C
        if self.sensor <= 4:
            if self.fifo:
                from .fifo import LSM6DSOFIFO
                return LSM6DSOFIFO(SPI(self.path))
            return LSM6DSO(SPI(self.path))
        if self.sensor == 5: return SCL3300(SPI(self.path))
        if self.sensor == 9:
            from .geophone import ADS122C04
            device = ADS122C04(I2C(self.path))
            if self.drdy:
                from .drdy import AutonomousADC
                from .linux_io import FallingEdges
                try: return AutonomousADC(device, FallingEdges(**self.drdy))
                except BaseException:
                    device.close()
                    raise
            return device
        if self.sensor == 8:
            from .pressure import SDP32
            return SDP32(I2C(self.path))
        if self.sensor == 6:
            if self.utc:
                from .gnss_timing import TimedGNSS
                return TimedGNSS(I2C(self.path))
            return MAXM10S(I2C(self.path))
        raise ValueError("remote sensors use USB firmware")


class USB:
    def __init__(self, path, receiver, retries=8):
        if not re.fullmatch(r"/dev/ttyACM\d+|/dev/serial/by-id/[A-Za-z0-9_.:+-]+", path):
            raise ValueError("explicit USB CDC device path required")
        self.path, self.receiver, self.retries = path, receiver, retries
        self.fd = None
        self.attempts, self.next_try = 0, 0
        self.device = None

    def poll(self, now, on_message, on_event):
        import termios
        import tty
        if self.fd is None:
            if now < self.next_try or self.attempts >= self.retries: return
            self.attempts += 1
            self.next_try = now + 1_000_000_000
            try:
                self.fd = os.open(self.path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC)
                tty.setraw(self.fd, termios.TCSANOW)
                attr = termios.tcgetattr(self.fd)
                attr[4] = attr[5] = termios.B115200
                termios.tcsetattr(self.fd, termios.TCSANOW, attr)
            except OSError as error:
                self.close()
                on_event("usb_open_failed", str(error), now)
                return
            on_event("usb_connected", "await identity and effective configuration", now)
        try:
            chunk = os.read(self.fd, 4096)
            if not chunk: raise OSError("USB CDC EOF")
        except BlockingIOError:
            before = dict(self.receiver.errors)
            list(self.receiver.feed(b"", now))
            if before != dict(self.receiver.errors):
                on_event("usb_rejected", "partial frame expired", now, counts=dict(self.receiver.errors))
            return
        except OSError as error:
            self.close()
            self.receiver.disconnect(self.device)
            on_event("usb_disconnected", str(error), now, device=self.device)
            return
        before = dict(self.receiver.errors)
        for message in self.receiver.feed(chunk, now):
            self.device = message.device_id
            on_message(message, now)
        if before != dict(self.receiver.errors):
            on_event("usb_rejected", "invalid or incomplete input rejected", now, counts=dict(self.receiver.errors))

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
