"""Construct v1 messages without replacing missing data with measurements."""
from functools import lru_cache
from groundlark_contract.schema import envelope_type
from groundlark_contract.validation import validate


@lru_cache(maxsize=1)
def Envelope():
    return envelope_type()


def envelope(device, boot):
    return Envelope()(version=1, device_id=device, boot_id=boot)


def identity(device, boot, board, sensors):
    m = envelope(device, boot)
    m.identity.board = board
    m.identity.firmware_version = "groundlark-0.2.0"
    m.identity.sensors.extend(sensors)
    return validate(m)


def configuration(device, boot, entries, revision=1):
    m = envelope(device, boot)
    m.configuration.revision = revision
    for entry in entries:
        s = m.configuration.sensors.add()
        for name, value in entry.items():
            setattr(s, name, value)
    return validate(m)


def status(device, boot, sensor, code, detail, dropped=None):
    m = envelope(device, boot)
    m.status.sensor_id, m.status.code = sensor, code
    m.status.detail = "".join(c if 32 <= ord(c) < 127 else "?" for c in str(detail))[:96]
    if dropped is not None:
        m.status.dropped_total = dropped
    return validate(m)


def batch(device, boot, sensor, sequence, acquired, raw=None, quality=1, revision=1, dropped=0, clock_domain=None, magnetic_timing=None):
    m = envelope(device, boot)
    b = m.batch
    b.sensor_id, b.configuration_revision = sensor, revision
    if dropped is not None: b.dropped_before = dropped
    s = b.samples.add(sequence=sequence, quality=quality if raw is not None else 2)
    s.time.domain = 2 if sensor in (7, 8) or sensor >= 10 else 1
    if clock_domain is not None: s.time.domain = clock_domain
    s.time.acquisition_ns = acquired
    if magnetic_timing is not None:
        for field, value in magnetic_timing.items(): setattr(s.magnetic_timing, field, value)
    if raw is not None:
        name = "imu" if sensor <= 4 else {5: "tilt", 6: "gnss", 7: "magnetic", 8: "pressure", 9: "geophone", **{i: "gas" for i in range(10, 14)}, 14: "particulate", 15: "climate", 16: "barometer", 17: "climate", 18: "magnetic", 19: "magnetic", 20: "magnetic"}[sensor]
        payload = getattr(s, name)
        for field, value in raw.items():
            if isinstance(value, (tuple, list)):
                v = getattr(payload, field)
                v.x, v.y, v.z = value
            else: setattr(payload, field, value)
    return validate(m)
