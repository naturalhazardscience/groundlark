"""Stateless v1 semantic checks. Session ordering belongs to Pi acquisition."""
import math
import re
from .framing import MAX_PAYLOAD


def require(condition, description):
    if not condition:
        raise ValueError(description)


def identifier(value, limit=32, optional=False):
    require((optional and not value) or
            (len(value) <= limit and re.fullmatch(r"[A-Za-z0-9_.:-]+", value)),
            "invalid identifier")


def vector(value, bits=None):
    for axis in ("x", "y", "z"):
        require(value.HasField(axis), "incomplete vector")
        number = getattr(value, axis)
        if bits:
            require(-(1 << (bits - 1)) <= number < (1 << (bits - 1)), "raw count out of range")
        else:
            require(math.isfinite(number), "nonfinite calibrated value")


def validate(message):
    require(message.ByteSize() <= MAX_PAYLOAD, "message exceeds payload limit")
    require(message.version == 1, "unsupported contract version")
    identifier(message.device_id)
    require(message.boot_id != 0, "boot identity required")
    kind = message.WhichOneof("body")
    require(kind is not None, "unknown or missing body")
    body = getattr(message, kind)
    if kind == "identity":
        require(body.board in (1, 2, 3), "unknown board")
        identifier(body.firmware_version)
        allowed = (set(range(1, 7)) | {8, 9}) if body.board == 1 else {7, 8, 17, 18, 19, 20} if body.board == 2 else set(range(10, 17))
        require(1 <= len(body.sensors) <= 8 and len(set(body.sensors)) == len(body.sensors), "sensor list size/duplicates")
        require(set(body.sensors) <= allowed, "sensor does not belong on board")
    elif kind == "configuration":
        require(body.revision > 0, "configuration revision required")
        require(1 <= len(body.sensors) <= 8, "configuration sensor bound")
        require(len({s.sensor_id for s in body.sensors}) == len(body.sensors), "duplicate configuration")
        for sensor in body.sensors:
            require(1 <= sensor.sensor_id <= 20, "unknown sensor")
            require((0 < sensor.period_ns <= 60_000_000_000) if sensor.enabled else sensor.period_ns == 0, "invalid sample period")
            data = sensor.register_config
            require(len(data) <= 64 and len(data) % 2 == 0, "invalid register configuration")
            addresses = list(data[::2])
            require(addresses == sorted(set(addresses)), "registers must be unique and sorted")
            require(not data or sensor.sensor_id in (1, 2, 3, 4, 7, 18, 19, 20), "8-bit register snapshot not applicable")
            allowed = ({"acceleration_range_g", "angular_rate_range_dps"} if sensor.sensor_id <= 4 else
                       {5: {"tilt_mode"}, 6: set(), 7: {"cycle_count_x", "cycle_count_y", "cycle_count_z"},
                        8: {"pressure_min_pa", "pressure_max_pa", "pressure_part_number"}, 9: {"geophone_gain", "geophone_reference_v"}, **{i: set() for i in range(10, 18)}, **{i: {"cycle_count_x", "cycle_count_y", "cycle_count_z"} for i in (18,19,20)}}[sensor.sensor_id])
            supplied = {field.name for field, _ in sensor.ListFields() if field.number >= 5}
            require(supplied <= allowed, "settings incompatible with sensor")
            if sensor.enabled:
                require(allowed <= supplied, "enabled sensor settings required")
                if sensor.sensor_id <= 4:
                    require(sensor.acceleration_range_g in (2, 4, 8, 16) and sensor.angular_rate_range_dps in (125, 250, 500, 1000, 2000), "unsupported IMU range")
                elif sensor.sensor_id == 5:
                    require(1 <= sensor.tilt_mode <= 4, "invalid tilt mode")
                elif sensor.sensor_id in (7, 18, 19, 20):
                    require(all(1 <= getattr(sensor, field) <= 65535 for field in allowed), "invalid cycle count")
                elif sensor.sensor_id == 9:
                    require(sensor.geophone_gain == 64 and sensor.geophone_reference_v == 2.048 and sensor.period_ns == 3_030_303, "unsupported geophone profile")
                elif sensor.sensor_id == 17:
                    require(sensor.period_ns == 1_000_000_000, "unsupported SHT45 profile")
                elif sensor.sensor_id >= 10:
                    # Retain recorded v0.1.1 sessions (240 ms) as well as the
                    # faster v0.1.2 raw profile. Never relabel legacy cadence.
                    require(sensor.period_ns in ((32_000_000, 240_000_000) if sensor.sensor_id < 14 else (1_000_000_000,)), "unsupported Skylark profile")
                elif sensor.sensor_id == 8:
                    identifier(sensor.pressure_part_number)
                    require(math.isfinite(sensor.pressure_min_pa) and math.isfinite(sensor.pressure_max_pa)
                            and sensor.pressure_min_pa < sensor.pressure_max_pa, "invalid pressure range")
    elif kind == "status":
        require(0 <= body.sensor_id <= 20 and 1 <= body.code <= 6, "unknown status")
        require(len(body.detail.encode("utf-8")) <= 96 and all(ord(c) >= 32 for c in body.detail), "invalid status detail")
    elif kind == "batch":
        validate_batch(body)
    return message


def validate_batch(batch):
    sensor = batch.sensor_id
    require(1 <= sensor <= 20, "unknown sensor")
    require(batch.configuration_revision > 0, "batch configuration required")
    require(1 <= len(batch.samples) <= 4, "batch must contain 1..4 samples")
    identifier(batch.calibration_id, optional=True)
    expected = "imu" if sensor <= 4 else {5: "tilt", 6: "gnss", 7: "magnetic", 8: "pressure", 9: "geophone", **{i: "gas" for i in range(10, 14)}, 14: "particulate", 15: "climate", 16: "barometer", 17: "climate", 18: "magnetic", 19: "magnetic", 20: "magnetic"}[sensor]
    domain = 2 if sensor in (7, 8) or sensor >= 10 else 1
    previous = None
    for sample in batch.samples:
        require(sample.HasField("sequence") and sample.HasField("time"), "sequence/time required")
        time = sample.time
        require((time.domain in (1, 2) if sensor == 8 else time.domain == domain) and time.HasField("acquisition_ns"), "wrong or absent acquisition clock")
        require(time.HasField("utc_unix_ns") == time.HasField("utc_uncertainty_ns"), "UTC requires explicit uncertainty")
        if previous is not None:
            require(sample.sequence == previous.sequence + 1, "nonconsecutive sequence inside batch")
            require(time.acquisition_ns > previous.time.acquisition_ns, "acquisition time must increase")
        else:
            require(batch.dropped_before <= sample.sequence, "drop count exceeds sequence")
        previous = sample
        require(sample.quality in (1, 2, 3, 4), "quality required")
        if sample.HasField("magnetic_timing"):
            require(sensor in (7, 18, 19, 20), "magnetic timing on wrong sensor")
            timing = sample.magnetic_timing
            require(timing.HasField("cohort") and timing.cohort == sample.sequence, "magnetic cohort/sequence mismatch")
            if timing.HasField("trigger_ns"):
                require(timing.trigger_ns <= time.acquisition_ns, "trigger after read completion")
            if timing.HasField("ready_observed_ns"):
                require(timing.HasField("trigger_ns") and timing.trigger_ns <= timing.ready_observed_ns <= time.acquisition_ns, "invalid DRDY observation")
            if sample.quality != 2:
                require(timing.HasField("ready_observed_ns"), "usable magnetic sample requires DRDY evidence")
        raw = sample.WhichOneof("raw")
        if sample.quality == 2:
            require(raw is None and not sample.HasField("calibrated"), "missing sample cannot contain measurements")
            continue
        require(raw == expected, "wrong or absent raw measurement")
        if raw == "imu":
            vector(sample.imu.acceleration, 16)
            vector(sample.imu.angular_rate, 16)
            if sample.imu.HasField("temperature"):
                require(-32768 <= sample.imu.temperature <= 32767, "temperature count range")
        elif raw == "tilt":
            require(sample.tilt.HasField("acceleration") or sample.tilt.HasField("angle"), "tilt data required")
            for field in ("acceleration", "angle"):
                if sample.tilt.HasField(field): vector(getattr(sample.tilt, field), 16)
            if sample.tilt.HasField("temperature"):
                require(-32768 <= sample.tilt.temperature <= 32767, "temperature count range")
            require(sample.tilt.HasField("device_status") and sample.tilt.device_status <= 65535, "tilt status required")
        elif raw == "magnetic":
            vector(sample.magnetic.counts, 24)
        elif raw in ("geophone", "gas"):
            data = getattr(sample, raw)
            require(data.HasField("counts") and -8388608 <= data.counts <= 8388607, "ADC count range")
            require(data.HasField("conversion_counter") and data.conversion_counter <= 255, "ADC counter required")
        elif raw == "particulate":
            data = sample.particulate.response
            require(len(data) == 32 and data[:4] == b"\x42\x4d\x00\x1c", "PMS frame/header")
            require(sum(data[:30]) == int.from_bytes(data[30:], "big"), "PMS checksum")
            require(data[29] == 0 or sample.quality == 4, "PMS device error")
        elif raw == "climate":
            data = sample.climate.response
            require(len(data) == 6, "SHT response length")
            require(all(sht_crc(data[i:i+2]) == data[i+2] for i in (0, 3)), "SHT CRC")
        elif raw == "barometer":
            require(len(sample.barometer.response) == 6 and len(sample.barometer.calibration) == 21, "BMP raw/trim length")
        elif raw == "pressure":
            pressure = sample.pressure
            require(bool(pressure.response) != bool(pressure.sdp3x_response), "exactly one pressure response format")
            if pressure.sdp3x_response:
                data = pressure.sdp3x_response
                require(len(data) == 9, "SDP32 response must be nine bytes")
                require(all(sht_crc(data[i:i+2]) == data[i+2] for i in (0, 3, 6)), "SDP32 CRC")
                require(int.from_bytes(data[6:8], "big") == 240, "SDP32 scale")
            else:
                require(len(pressure.response) == 4, "pressure response must be four bytes")
                if sample.quality in (1, 3):
                    require(pressure.response[0] >> 6 == 0, "non-normal pressure status")
        else:
            require(len(sample.gnss.nav_pvt) == 92, "NAV-PVT payload must be 92 bytes")
        if sample.HasField("calibrated"):
            require(bool(batch.calibration_id) and sample.quality in (1, 3), "calibration identity/usable raw data required")
            allowed = {"imu": {"acceleration_m_s2", "angular_rate_rad_s", "temperature_k"},
                       "tilt": {"acceleration_m_s2", "angle_rad", "temperature_k"},
                       "magnetic": {"magnetic_t"}, "pressure": {"pressure_pa", "temperature_k"}, "gnss": set(), "geophone": {"geophone_input_v"}, "gas": set(), "particulate": set(), "climate": set(), "barometer": set()}[raw]
            fields = sample.calibrated.ListFields()
            require(bool(fields), "empty calibrated measurement")
            for field, value in fields:
                require(field.name in allowed, "calibrated field incompatible with sensor")
                if field.message_type: vector(value)
                else:
                    require(math.isfinite(value), "nonfinite calibrated value")
                    if field.name == "temperature_k": require(value >= 0, "negative absolute temperature")


def sht_crc(data):
    crc = 255
    for byte in data:
        crc ^= byte
        for _ in range(8): crc = ((crc << 1) ^ (0x31 if crc & 128 else 0)) & 255
    return crc
