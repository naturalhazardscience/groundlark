"""Linux ABI short-transfer rejection and real pseudo-terminal CDC ingestion."""
import ctypes as c
import os
import struct
import sys
import unittest
from unittest.mock import patch
from groundlark import messages as m
from groundlark.linux_io import SPI, I2C, I2CTransfer
from groundlark.live import USB
from groundlark.session import Sessions
from groundlark.simulation import defaults
from groundlark.transport import Receiver
from groundlark_contract.framing import encode


class BusABITests(unittest.TestCase):
    def test_i2c_read_only_has_no_dummy_write(self):
        bus = I2C.__new__(I2C)
        bus.fd = 20
        def fake(fd, command, arg, mutate=False):
            request = I2CTransfer.from_buffer_copy(arg)
            self.assertEqual(request.count, 1)
            message = request.messages[0]
            self.assertEqual((message.addr, message.flags, message.length), (0x21, 1, 3))
            c.memmove(message.buffer, b'\xbe\xef\x92', 3)
            return 1
        with patch('groundlark.linux_io.ioctl', fake):
            self.assertEqual(bus.exchange(0x21, b'', 3), b'\xbe\xef\x92')
        with self.assertRaises(ValueError): bus.exchange(0x21, b'', 0)
        with patch('groundlark.linux_io.ioctl', return_value=0):
            with self.assertRaises(OSError): bus.exchange(0x21, b'', 3)

    def test_spi_buffer_layout_and_short_transfer(self):
        bus = SPI.__new__(SPI)
        bus.fd = 19
        def fake(fd, command, arg, mutate=False):
            if command == 0x40016b01: return bytes(arg)
            self.assertEqual(len(arg), 32)
            tx, rx, size, hz, *_ = struct.unpack("=QQIIHBBBBBB", arg)
            self.assertEqual(c.string_at(tx, size), b"\x8f\0")
            self.assertEqual(hz, 1_000_000)
            c.memmove(rx, b"\0\x6c", 2)
            return size
        with patch("groundlark.linux_io.ioctl", fake): self.assertEqual(bus.transfer(b"\x8f\0"), b"\0\x6c")
        with patch("groundlark.linux_io.ioctl", return_value=1):
            with self.assertRaises(OSError): bus.transfer(b"\x8f\0")

    def test_i2c_layout_repeated_start_and_short_transaction(self):
        bus = I2C.__new__(I2C)
        bus.fd = 20
        def fake(fd, command, arg, mutate=False):
            self.assertEqual(command, 0x0707)
            request = I2CTransfer.from_buffer_copy(arg)
            self.assertEqual(request.count, 2)
            self.assertEqual(request.messages[0].addr, 0x42)
            self.assertEqual(c.string_at(request.messages[0].buffer, 1), b"\xfd")
            self.assertEqual(request.messages[1].flags, 1)
            c.memmove(request.messages[1].buffer, b"\0\x64", 2)
            return 2
        with patch("groundlark.linux_io.ioctl", fake): self.assertEqual(bus.exchange(0x42, b"\xfd", 2), b"\0\x64")
        with patch("groundlark.linux_io.ioctl", return_value=1):
            with self.assertRaises(OSError): bus.exchange(0x42, b"\xfd", 2)


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux TTY integration")
class USBTests(unittest.TestCase):
    def test_actual_tty_fragmentation_disconnect_and_retry_limit(self):
        import pty
        master, slave = pty.openpty()
        usb = USB("/dev/ttyACM0", Receiver(Sessions(), board=2), retries=2)
        messages, events = [], []
        def event(code, detail, now, **kwargs): events.append(code)
        def receive(message, now): messages.append(message)
        try:
            os.set_blocking(slave, False)
            with patch("groundlark.live.os.open", return_value=os.dup(slave)):
                usb.poll(0, receive, event)
            wire = b"".join(encode(v.SerializeToString()) for v in (
                m.identity("head", 2, 2, [7]), m.configuration("head", 2, defaults(True)[:1]),
                m.batch("head", 2, 7, 0, 123, {"counts": (-8388608, 0, 8388607)})))
            os.write(master, wire[:7])
            usb.poll(1, receive, event)
            self.assertEqual(len(messages), 0)
            os.write(master, wire[7:])
            import select
            select.select([slave], [], [], .1)
            for i in range(100):
                usb.poll(2 + i, receive, event)
                if len(messages) == 3: break
            self.assertEqual(len(messages), 3)
            self.assertEqual(messages[-1].batch.samples[0].time.acquisition_ns, 123)
            os.close(master)
            master = None
            usb.poll(1000, receive, event)
            self.assertIn("usb_disconnected", events)
            with patch("groundlark.live.os.open", side_effect=OSError("absent")) as opening:
                for i in range(1, 10): usb.poll(i * 1_000_000_000, receive, event)
                self.assertEqual(opening.call_count, 1)
        finally:
            usb.close()
            os.close(slave)
            if master is not None: os.close(master)


if __name__ == "__main__": unittest.main()
