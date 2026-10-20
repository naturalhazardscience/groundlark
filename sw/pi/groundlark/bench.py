"""Executable bench checklist; arithmetic/evidence checks, not instrument control."""
import hashlib
from pathlib import Path
import math

# id: unit, lower, upper, application-target key (if required)
CHECKS = {
    'module_min_v': ('V', 3.201, None, None),
    'module_max_v': ('V', None, 3.399, None),
    'hot_loop_resistance': ('ohm', 0, .015, None),
    'pi_hot_loop_resistance': ('ohm', 0, .050, None),
    'power_sequence': ('boolean', True, True, None),
    'partial_power_isolation': ('boolean', True, True, None),
    'fpga_jtag_programming': ('boolean', True, True, None),
    'fpga_mode_handoff': ('boolean', True, True, None),
    'trenz_cpld_revision': ('count', 3, 3, None),
    'trenz_mode_pull_up': ('boolean', True, True, None),
    'shared_bus_signal_integrity': ('boolean', True, True, None),
    'gnss_rf_performance': ('boolean', True, True, None),
    'fpga_loopback_errors': ('count', 0, 0, None),
    'fpga_spi_clock_max': ('Hz', 1000, 1_000_000, None),
    'fpga_sclk_high_min': ('ns', 500, None, None),
    'fpga_sclk_low_min': ('ns', 500, None, None),
    'fpga_cs_setup_min': ('ns', 1000, None, None),
    'fpga_cs_hold_min': ('ns', 1000, None, None),
    'fpga_cs_inactive_min': ('ns', 1000, None, None),
    'connector_cable_cooler_fit': ('boolean', True, True, None),
    'irq_fifo_fault_recovery': ('boolean', True, True, None),
    'unexpected_missing_samples': ('count', 0, 0, None),
    'geophone_polarity_response': ('boolean', True, True, None),
    'max_geophone_input_noise_rms': ('V', 0, None, 'max_geophone_input_noise_rms_v'),
    'max_geophone_timing_error': ('ns', 0, None, 'max_geophone_timing_error_ns'),
    'max_inter_imu_skew': ('ns', 0, None, 'max_inter_imu_skew_ns'),
    'max_acceleration_noise_rms': ('m/s^2', 0, None, 'max_acceleration_noise_rms_m_s2'),
    'max_acceleration_bias_change': ('m/s^2', 0, None, 'max_acceleration_bias_change_m_s2'),
    'max_fpga_noise_ratio': ('ratio', 0, None, 'max_fpga_noise_ratio'),
    'pressure_port_response': ('boolean', True, True, None),
    'pressure_gap_recovery': ('boolean', True, True, None),
    'max_pressure_gain_error': ('dB', 0, None, 'max_pressure_gain_error_db'),
    'max_pressure_phase_error': ('degree', 0, None, 'max_pressure_phase_error_deg'),
    'max_pressure_noise_rms': ('Pa', 0, None, 'max_pressure_noise_rms_pa'),
    'max_pressure_alias_rms': ('Pa', 0, None, 'max_pressure_alias_rms_pa'),
}


def template():
    return dict(version=4, scope='physical-bench', operator=None, date_utc=None,
                hardware_revision=None, board_serial=None, software_commit=None,
                pi_and_kernel=None, geophone_serial=None, fpga_image=None,
                conditions=dict(temperature_range_c=None, noise_band_hz=None, sample_rates_hz=None,
                                mounting=None, cooling=None, power_load_cases=None,
                                pressure_band_hz=[1,20], pressure_tubing=None,
                                pressure_reference=None, trenz_cpld_image=None,
                                signal_integrity_corner_cases=None, gnss_test_setup=None),
                equipment=[], targets={v[3]:None for v in CHECKS.values() if v[3]},
                checks={key:dict(value=None, unit=values[0], evidence=[], notes='') for key, values in CHECKS.items()})


def finite(value): return type(value) in (int, float) and math.isfinite(value)


def evidence(path, root):
    root, path = Path(root).resolve(), Path(path).resolve()
    if not path.is_relative_to(root) or not path.is_file(): raise ValueError('evidence must be a file inside the report folder')
    if path.stat().st_size > 64 * 1024 * 1024: raise ValueError('evidence file exceeds 64 MiB')
    with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=path.relative_to(root).as_posix(), sha256=digest)


def evaluate(report, root):
    if report.get('version') != 4 or report.get('scope') != 'physical-bench': raise ValueError('bench report version/scope')
    if set(report.get('checks', {})) != set(CHECKS): raise ValueError('bench check inventory')
    results, missing = {}, []
    for key in ('operator','date_utc','hardware_revision','board_serial','software_commit','pi_and_kernel','geophone_serial','fpga_image'):
        if not isinstance(report.get(key), str) or not report[key].strip(): missing.append(key)
    for key in template()['conditions']:
        if not report.get('conditions', {}).get(key): missing.append('conditions.' + key)
    if report.get('conditions', {}).get('pressure_band_hz') != [1,20]:
        raise ValueError('pressure qualification requires the complete 1-20 Hz band')
    if not report.get('equipment'): missing.append('equipment with calibration/reference details')
    for key, (unit, lo, hi, target) in CHECKS.items():
        row = report['checks'][key]
        if row.get('unit') != unit: raise ValueError('wrong unit: ' + key)
        value = row.get('value')
        if value is None: results[key] = 'incomplete'; continue
        if unit == 'boolean':
            if type(value) is not bool: raise ValueError('expected boolean: ' + key)
        elif not finite(value) or (unit == 'count' and type(value) is not int):
            raise ValueError('expected finite measurement: ' + key)
        if target:
            hi = report.get('targets', {}).get(target)
            if hi is None: results[key] = 'incomplete'; continue
            if not finite(hi) or hi <= 0: raise ValueError('positive application limit required: ' + target)
        if not row.get('evidence'): results[key] = 'incomplete'; continue
        for item in row['evidence']:
            try: actual = evidence(Path(root)/item['path'], root)
            except (OSError, ValueError, KeyError): results[key] = 'invalid-evidence'; break
            if actual != item: results[key] = 'invalid-evidence'; break
        else:
            results[key] = 'fail' if (lo is not None and value < lo) or (hi is not None and value > hi) else 'pass'
    status = ('fail' if any(v in ('fail', 'invalid-evidence') for v in results.values()) else
              'incomplete' if missing or 'incomplete' in results.values() else 'pass')
    return dict(status=status, checks=results, missing_context=missing,
                scope='supplied physical evidence and limits; not a fabrication release')
