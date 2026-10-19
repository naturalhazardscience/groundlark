"""Independent byte fixtures for the fitted pressure sensor."""
import unittest
from groundlark.pressure import DLVR, DLVR_SETTINGS as SETTINGS
from groundlark.sensors import NotReady


class PressureTests(unittest.TestCase):
    def driver(self, value):
        class Bus:
            def exchange(bus, address, write, size):
                self.assertEqual((address,write,size),(0x28,b'',4))
                return value
        return DLVR(Bus())

    def test_zero_and_filler_bits_preserved(self):
        raw=b'\x00\x00\x00\x1f'
        sensor=self.driver(raw)
        self.assertEqual(sensor.configure(SETTINGS),SETTINGS)
        self.assertEqual(sensor.read().raw,dict(response=raw))

    def test_faults_and_busy_are_not_zero(self):
        for data in (b'',b'\x40\x00\x00\x00',b'\xc0\x00\x00\x00'):
            with self.assertRaises(OSError): self.driver(data).read()
        with self.assertRaises(NotReady): self.driver(b'\x80\x00\x00\x00').read()
        with self.assertRaises(ValueError): self.driver(bytes(4)).configure(dict(SETTINGS,pressure_max_pa=250))
