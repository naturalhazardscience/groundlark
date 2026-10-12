"""Calibrated quartet reduction. Raw envelopes remain the acquisition record.

No default calibration or skew tolerance: both must be supplied from the
experiment's documented calibration and timing policy. This is a derived
equal-weight field estimate, not cancellation of shared interference.
"""
from dataclasses import dataclass
import math
from .calibration import configuration_hash
from groundlark_contract.validation import validate, require, identifier

SENSORS = (7, 18, 19, 20)  # U2, U7, U8, U9; top-left, top-right, bottom-left, bottom-right


@dataclass(frozen=True)
class ArrayField:
    device: str
    boot: int
    revision: int
    cohort: int
    trigger_ns: int
    ready_skew_ns: int
    magnetic_t: tuple[float, float, float]
    lane_fields_t: tuple
    calibration_id: str


def average_cohort(envelopes, configuration, calibration, *, max_ready_skew_ns):
    """Reduce exactly four valid, independently calibrated and aligned readings.

    calibration: id, device_id, configuration_sha256, provenance, lanes. Each
    lane (string sensor ID) has matrix_t_per_count (3x3 into common board axes)
    and offset_t (3). Calibration is explicit and configuration-bound; callers
    must retain the calibration record and qualify its temperature/time range.
    Raises ValueError rather than averaging a partial or mismatched cohort.
    """
    require(type(max_ready_skew_ns) is int and 0 <= max_ready_skew_ns <= 50_000_000,
            'explicit bounded DRDY skew policy required')
    require(len(envelopes) == 4, 'complete quartet required')
    require(set(calibration) == {'id', 'device_id', 'configuration_sha256', 'provenance', 'lanes'},
            'array calibration fields')
    identifier(calibration['id']);identifier(calibration['device_id'])
    require(isinstance(calibration['provenance'], str) and 0 < len(calibration['provenance']) <= 256,
            'calibration provenance required')
    validate(configuration)
    require(configuration.WhichOneof('body') == 'configuration', 'configuration envelope required')
    require(calibration['configuration_sha256'] == configuration_hash(configuration.configuration),
            'array calibration/configuration mismatch')
    require(set(calibration['lanes']) == {str(s) for s in SENSORS}, 'four lane calibrations required')
    configs = {s.sensor_id: s for s in configuration.configuration.sensors}
    require(set(SENSORS) <= set(configs), 'four magnetic configurations required')
    settings = [(configs[i].enabled, configs[i].period_ns, configs[i].cycle_count_x,
                 configs[i].cycle_count_y, configs[i].cycle_count_z, configs[i].register_config) for i in SENSORS]
    require(all(s == settings[0] and s[0] for s in settings), 'array settings differ or disabled')
    lanes = {}
    keys = set()
    for m in envelopes:
        validate(m)
        require(m.WhichOneof('body') == 'batch' and len(m.batch.samples) == 1, 'single-lane sample envelope required')
        sid = m.batch.sensor_id
        require(sid in SENSORS and sid not in lanes, 'duplicate or wrong array lane')
        sample = m.batch.samples[0]
        require(sample.quality == 1 and sample.HasField('magnetic_timing'), 'valid timed magnetic sample required')
        timing = sample.magnetic_timing
        require(timing.HasField('trigger_ns') and timing.HasField('ready_observed_ns'), 'trigger and DRDY evidence required')
        require(m.device_id == configuration.device_id == calibration['device_id'] and
                m.boot_id == configuration.boot_id and
                m.batch.configuration_revision == configuration.configuration.revision,
                'array identity/configuration mismatch')
        keys.add((timing.cohort, timing.trigger_ns))
        lane = calibration['lanes'][str(sid)]
        require(set(lane) == {'matrix_t_per_count', 'offset_t'}, 'lane calibration fields')
        matrix, offset = lane['matrix_t_per_count'], lane['offset_t']
        require(isinstance(matrix, (list, tuple)) and len(matrix) == 3 and
                all(isinstance(row, (list, tuple)) and len(row) == 3 for row in matrix) and
                isinstance(offset, (list, tuple)) and len(offset) == 3, 'calibration shape')
        require(all(type(v) in (int, float) and math.isfinite(v) for row in matrix for v in row) and
                all(type(v) in (int, float) and math.isfinite(v) for v in offset), 'finite calibration required')
        # Reject a collapsed axis transformation; units may legitimately be tiny.
        determinant = sum(matrix[0][i] * (matrix[1][(i+1)%3]*matrix[2][(i+2)%3] -
                                         matrix[1][(i+2)%3]*matrix[2][(i+1)%3]) for i in range(3))
        require(math.isfinite(determinant) and determinant != 0, 'singular calibration matrix')
        counts = tuple(getattr(sample.magnetic.counts, axis) for axis in 'xyz')
        field = tuple(math.fsum(row[i]*counts[i] for i in range(3)) + bias for row, bias in zip(matrix, offset))
        require(all(math.isfinite(v) for v in field), 'calibrated field overflow')
        lanes[sid] = (timing.ready_observed_ns, field)
    require(len(keys) == 1, 'mixed magnetic cohorts/triggers')
    ready = [lanes[s][0] for s in SENSORS]
    skew = max(ready)-min(ready)
    require(skew <= max_ready_skew_ns, 'DRDY skew exceeds experiment policy')
    fields = tuple(lanes[s][1] for s in SENSORS)
    mean = tuple(math.fsum(v[i]/4 for v in fields) for i in range(3))
    cohort, trigger = keys.pop()
    return ArrayField(configuration.device_id, configuration.boot_id, configuration.configuration.revision,
                      cohort, trigger, skew, mean, fields, calibration['id'])
