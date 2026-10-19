"""Immutable, explicit affine SI calibration in package axes; raw is retained."""
import hashlib
import json
import math
from groundlark_contract.validation import require, validate, identifier

VECTORS = {"acceleration_m_s2": "acceleration", "angular_rate_rad_s": "angular_rate",
           "angle_rad": "angle", "magnetic_t": "counts"}
FIELDS = {**{i: {"acceleration_m_s2", "angular_rate_rad_s", "temperature_k"} for i in range(1, 5)},
          5: {"angle_rad", "temperature_k"}, **{i: {"magnetic_t"} for i in (7,18,19,20)},
          8: {"pressure_pa", "temperature_k"}, 9: {"geophone_input_v"}}


def raw_values(sample, name):
    """Return original counts, never previously calibrated values."""
    raw = getattr(sample, sample.WhichOneof("raw"))
    if sample.WhichOneof("raw") == "pressure" and raw.sdp3x_response:
        require(name in ("pressure_pa", "temperature_k"), "SDP32 calibration field")
        offset = 0 if name == "pressure_pa" else 3
        return [int.from_bytes(raw.sdp3x_response[offset:offset+2], "big", signed=True)]
    if name in VECTORS:
        source = VECTORS[name]
        require(source in raw.DESCRIPTOR.fields_by_name and raw.HasField(source), "raw calibration input missing")
        return [getattr(getattr(raw, source), axis) for axis in ("x", "y", "z")]
    if name == "pressure_pa":
        require(sample.WhichOneof("raw") == "pressure", "pressure input missing")
        return [int.from_bytes(raw.response[:2], "big") & 0x3fff]
    source = "counts" if name == "geophone_input_v" else "temperature"
    require(source in raw.DESCRIPTOR.fields_by_name and raw.HasField(source), "raw calibration input missing")
    return [getattr(raw, source)]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def configuration_hash(configuration):
    return hashlib.sha256(configuration.SerializeToString(deterministic=True)).hexdigest()


class Calibrations:
    def __init__(self, records=()):
        self.records = {}
        for record in records:
            self.add(record)

    def add(self, record):
        require(len(self.records) < 16, "calibration capacity exhausted")
        data = canonical(record)
        require(len(data) <= 2048, "calibration too large")
        keys = {"sensor_id", "configuration_sha256", "provenance", "fields"}
        if "version" in record:
            require(record["version"] == 2, "calibration version")
            keys |= {"version", "device_id", "evidence_sha256", "method", "raw_limits"}
            identifier(record["device_id"])
            require(record["method"] == "static-affine", "calibration method")
            require(isinstance(record["evidence_sha256"], str) and len(record["evidence_sha256"]) == 64 and
                    all(c in "0123456789abcdef" for c in record["evidence_sha256"]), "evidence digest")
        require(set(record) == keys, "calibration keys")
        require(type(record["sensor_id"]) is int and record["sensor_id"] in FIELDS, "calibration sensor")
        require(isinstance(record["provenance"], str) and 0 < len(record["provenance"]) <= 256, "calibration provenance")
        require(len(record["configuration_sha256"]) == 64 and all(c in "0123456789abcdef" for c in record["configuration_sha256"]), "configuration digest")
        require(1 <= len(record["fields"]) <= 3, "calibration fields")
        if "version" in record:
            require(set(record["raw_limits"]) == set(record["fields"]), "calibration range fields")
        for name, coefficients in record["fields"].items():
            require(name in FIELDS[record["sensor_id"]], "calibration field incompatible with sensor")
            require(set(coefficients) == {"scale", "offset"}, "calibration coefficient keys")
            count = 3 if name in VECTORS else 1
            if "version" in record:
                limits = record["raw_limits"][name]
                require(isinstance(limits, list) and len(limits) == count and all(
                    isinstance(pair, list) and len(pair) == 2 and all(type(v) in (int, float) and math.isfinite(v) for v in pair)
                    and pair[0] < pair[1] for pair in limits), "calibration raw limits")
            for key in ("scale", "offset"):
                values = coefficients[key]
                require(isinstance(values, list) and len(values) == count and all(type(v) in (int, float) and math.isfinite(v) for v in values), "calibration coefficient shape")
        ident = "cal-" + hashlib.sha256(data).hexdigest()[:28]
        self.records[ident] = json.loads(data)
        return ident

    def verify(self, ident, sensor, cfg, device=None):
        r = self.records.get(ident)
        require(r is not None and r["sensor_id"] == sensor and r["configuration_sha256"] == configuration_hash(cfg), "calibration/configuration mismatch")
        require("device_id" not in r or r["device_id"] == device, "calibration/device mismatch")
        return r

    def apply(self, message, ident, cfg):
        record = self.verify(ident, message.batch.sensor_id, cfg, message.device_id)
        copy = type(message)()
        copy.CopyFrom(message)
        for sample in copy.batch.samples:
            sample.ClearField("calibrated")
            if sample.quality not in (1, 3): continue
            for name, c in record["fields"].items():
                values = raw_values(sample, name)
                if "raw_limits" in record and not all(lo <= value <= hi for value, (lo, hi)
                                                        in zip(values, record["raw_limits"][name])):
                    continue
                if name in VECTORS:
                    for i, axis in enumerate(("x", "y", "z")):
                        setattr(getattr(sample.calibrated, name), axis, values[i] * c["scale"][i] + c["offset"][i])
                else:
                    setattr(sample.calibrated, name, values[0] * c["scale"][0] + c["offset"][0])
            copy.batch.calibration_id = ident
        return validate(copy)
