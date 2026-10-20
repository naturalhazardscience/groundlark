"""Fake bus fixtures check manufacturer wire constants and error behavior."""
import struct
import unittest
from groundlark.sensors import LSM6DSO, SCL3300, UBXParser, MAXM10S, NotReady, scl_command, ubx_packet
from groundlark.simulation import defaults


class IMUBus:
    def __init__(self):
        self.regs = {0x0f: 0x6c, 0x12: 0, 0x1e: 3}
        self.values = struct.pack("<7h", -123, -32768, 0, 32767, 1, -1, 16384)
        self.short, self.stuck, self.mismatch = False, False, False

    def transfer(self, data, **kwargs):
        address = data[0] & 127
        if data[0] & 128:
            if self.short: return b"\0"
            if address == 0x20: return b"\0" + self.values
            return bytes([0, self.regs.get(address, 0)])
        self.regs[address] = data[1]
        if address == 0x12 and data[1] == 1 and not self.stuck: self.regs[address] = 0
        if address == 0x10 and self.mismatch: self.regs[address] ^= 1
        return bytes(len(data))


class SensorTests(unittest.TestCase):
    def test_scl_off_frame_startup_and_signed_samples(self):
        class Bus:
            def __init__(self):
                self.previous, self.commands = bytes(4), []
                self.registers = {0x10: 0xc1, 0x0d: 0, 6: 0, 1: 0x8000, 2: 0, 3: 0x7fff,
                                  9: 0xffff, 10: 0, 11: 1, 5: 0xff9c}
            def transfer(self, frame, **kwargs):
                self.commands.append(frame.hex())
                result = self.previous
                opcode = frame[0]
                if opcode & 0x80:
                    value = int.from_bytes(frame[1:3], "big")
                    if opcode == 0xb4: self.registers[0x0d] = value & 3
                else: value = self.registers[opcode >> 2]
                self.previous = scl_command(opcode | 1, value)
                return result
        bus = Bus()
        driver = SCL3300(bus, sleep=lambda _: None)
        driver.configure(next(c for c in defaults(legacy_gnss=True) if c['sensor_id']==5))
        self.assertEqual(bus.commands[:7], ["b400001f", "b4002098", "b400001f", "b0001f6f",
                                            "180000e5", "180000e5", "180000e5"])
        reading = driver.read()
        self.assertEqual(reading.raw["acceleration"], [-32768, 0, 32767])
        self.assertEqual(reading.raw["angle"], [-1, 0, 1])
        self.assertEqual(reading.quality, 1)
        bus.registers[6] = 0x40
        self.assertEqual(driver.read().quality, 3)
        bus.registers[6] = 1
        self.assertEqual(driver.read().quality, 4)

    def test_gnss_effective_configuration_requires_ack_and_readback(self):
        class Bus:
            def __init__(self, reject=False):
                self.pending, self.writes, self.reject = b"", [], reject
            def exchange(self, addr, write, count):
                if count:
                    if write == b"\xfd": return len(self.pending).to_bytes(2, "big")
                    result, self.pending = self.pending[:count], self.pending[count:]
                    return result
                self.writes.append(write)
                if write[3] == 0x8a:
                    self.pending = ubx_packet(5, 0 if self.reject else 1, b"\x06\x8a")
                else:
                    self.pending = ubx_packet(6, 0x8b, bytes.fromhex("01000000 01002130e803 020021300100 0600912001"))
                return b""
        bus = Bus()
        driver = MAXM10S(bus, sleep=lambda _: None)
        self.assertEqual(driver.configure(defaults(legacy_gnss=True)[5]), defaults(legacy_gnss=True)[5])
        self.assertEqual(bus.writes[0][6:-2].hex(), "0001000001002130e8030200213001000600912001")
        with self.assertRaises(OSError): MAXM10S(Bus(reject=True), sleep=lambda _: None).configure(defaults(legacy_gnss=True)[5])

    def test_imu_configuration_and_signed_axis_order(self):
        bus = IMUBus()
        driver = LSM6DSO(bus, sleep=lambda _: None)
        effective = driver.configure(defaults()[0])
        self.assertEqual(effective["register_config"], bytes.fromhex("10 20 11 20 12 44 13 04 15 00 16 00 17 00 18 e2"))
        reading = driver.read()
        self.assertEqual(reading.raw["temperature"], -123)
        self.assertEqual(reading.raw["angular_rate"], (-32768, 0, 32767))
        self.assertEqual(reading.raw["acceleration"], (1, -1, 16384))
        self.assertEqual(reading.quality, 3)

    def test_imu_identity_readback_reset_and_short_read_fail(self):
        for fault in ("identity", "mismatch", "stuck", "short"):
            bus = IMUBus()
            if fault == "identity": bus.regs[0x0f] = 0
            else: setattr(bus, fault, True)
            with self.assertRaises(OSError): LSM6DSO(bus, sleep=lambda _: None).configure(defaults()[0])

    def test_imu_not_ready_is_not_zero_measurement(self):
        bus = IMUBus()
        bus.regs[0x1e] = 0
        with self.assertRaises(NotReady): LSM6DSO(bus).read()

    def test_imu_filter_readback_faults_are_rejected(self):
        for bad_register in (0x13,0x15,0x16,0x17,0x18):
            class FaultBus(IMUBus):
                def transfer(self,data,**kwargs):
                    result=super().transfer(data,**kwargs)
                    if data[0]==(bad_register|0x80):
                        return bytes([0,result[1]^0x80])
                    return result
            with self.assertRaises(OSError):
                LSM6DSO(FaultBus(),sleep=lambda _:None).configure(defaults()[0])

    def test_shared_spi_rejects_i2c_or_i3c_left_enabled(self):
        # Manufacturer bits are independent of the driver's settings mapping.
        for register, bit in ((0x13, 0x04), (0x18, 0x02)):
            class EnabledBus(IMUBus):
                def transfer(self, data, **kwargs):
                    result = super().transfer(data, **kwargs)
                    if data[0] == register:
                        self.regs[register] &= ~bit
                    return result
            with self.subTest(register=register), self.assertRaises(OSError):
                LSM6DSO(EnabledBus(), sleep=lambda _: None).configure(defaults()[0])

    def test_scl_manufacturer_command_vectors(self):
        for opcode, value, expected in ((4, 0, "040000f7"), (0xb4, 0x20, "b4002098"),
                                         (0xb0, 0x1f, "b0001f6f"), (0xb4, 3, "b4000338"), (0x40, 0, "40000091")):
            self.assertEqual(scl_command(opcode, value).hex(), expected)

    def test_scl_response_crc_and_address(self):
        # Datasheet rev. 4 section 6.8.1 supplies this SERIAL1 response.
        self.assertEqual(SCL3300.response(bytes.fromhex("65f7da19"), 0x64), (0xf7da, 1))
        with self.assertRaises(OSError): SCL3300.response(bytes.fromhex("65f7da18"), 0x64)
        with self.assertRaises(OSError): SCL3300.response(bytes.fromhex("65f7da19"), 0x04)

    def test_ubx_independent_ack_fragmentation_and_checksum(self):
        parser = UBXParser()
        ack = bytes.fromhex("b56205010200068a98c1")
        self.assertEqual(list(parser.feed(ack[:3])), [])
        self.assertEqual(list(parser.feed(ack[3:])), [(5, 1, b"\x06\x8a")])
        bad = ack[:-1] + b"\0"
        self.assertEqual(list(parser.feed(bad + ack)), [(5, 1, b"\x06\x8a")])
        self.assertEqual(parser.errors, 1)

    def test_ubx_bound_and_noise(self):
        parser = UBXParser()
        for _ in range(100): list(parser.feed(bytes.fromhex("b5620107ffff") + b"x" * 200))
        self.assertLessEqual(len(parser.buffer), 1287)
        with self.assertRaises(ValueError): list(parser.feed(b"x" * 257))

    def test_gnss_retains_back_to_back_nav_pvt(self):
        driver = MAXM10S(None)
        first, second = bytearray(92), bytearray(92)
        first[:4], second[:4] = (1000).to_bytes(4, "little"), (2000).to_bytes(4, "little")
        chunks = [[(1, 7, bytes(first)), (1, 7, bytes(second))]]
        driver.poll = lambda: chunks.pop(0) if chunks else []
        self.assertEqual(driver.read().raw["nav_pvt"], first)
        self.assertEqual(driver.read().raw["nav_pvt"], second)
        with self.assertRaises(NotReady): driver.read()


if __name__ == "__main__": unittest.main()
