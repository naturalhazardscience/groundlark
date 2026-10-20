"""Reproducible DAQHAT-01 design calculations. Analytical limits are not bench evidence."""
from hardware_require import require as _require_hardware
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "hw/groundlark-fpga-hat/boards/groundlark-daqhat-01"


def microstrip(width, height, thickness, er):
    """Hammerstad-Jensen quasi-static microstrip, dimensions in the same units.

    Finite copper thickness correction; uncoated homogeneous substrate. A solder
    mask, pads, vias and discontinuities require a field-solver/measurement check.
    Equations: Qucs technical documentation, Single microstrip line, node75.
    """
    if not (width > 0 and height > 0 and thickness >= 0 and er >= 1):
        raise ValueError("microstrip geometry")
    u, t = width / height, thickness / height
    du = t / math.pi * math.log(1 + 4 * math.e / (t * (1 / math.tanh(math.sqrt(6.517 * u))) ** 2)) if t else 0
    ur = u + du * (1 + 1 / math.cosh(math.sqrt(er - 1))) / 2
    u1 = u + du

    def air(v):
        f = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / v) ** .7528)
        return 376.730313668 / (2 * math.pi) * math.log(f / v + math.sqrt(1 + (2 / v) ** 2))

    a = 1 + math.log((ur ** 4 + (ur / 52) ** 2) / (ur ** 4 + .432)) / 49 + math.log(1 + (ur / 18.1) ** 3) / 18.7
    b = .564 * ((er - .9) / (er + 3)) ** .053
    ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / ur) ** (-a * b)
    # Z(ur)/sqrt(ee); effective permittivity corrected for thickness separately.
    return air(ur) / math.sqrt(ee), ee * (air(u1) / air(ur)) ** 2


def width_for(target, height, thickness, er):
    lo, hi = .001 * height, 100 * height
    for _ in range(70):
        mid = (lo + hi) / 2
        if microstrip(mid, height, thickness, er)[0] > target: lo = mid
        else: hi = mid
    return (lo + hi) / 2


def supply_range(setpoint, tolerance, resistance, current):
    if not (0 < setpoint and 0 <= tolerance < 1 and resistance >= 0 and current >= 0):
        raise ValueError("power budget")
    return setpoint * (1 - tolerance) - resistance * current, setpoint * (1 + tolerance)


def clearance(gap, port_height=16, connector_height=2.2, cable_allowance=0,
              stack_tolerance=1):
    return gap - port_height - connector_height - cable_allowance - stack_tolerance


POWER_PINS = {
    ('U41','1'):'PI_3V3', ('U41','23'):'SENS_3V3', ('U41','24'):'SENS_3V3',
    ('U42','1'):'PI_3V3', ('U42','23'):'SENS_3V3', ('U42','24'):'SENS_3V3',
    ('U41','22'):'SENSOR_OE_N', ('U42','22'):'SENSOR_OE_N',
    ('R50','1'):'SENSOR_OE_N', ('R50','2'):'PI_3V3',
    ('U43','1'):'SENS_3V3', ('U43','8'):'PI_3V3',
    ('U51','3'):'PI_3V3', ('U51','7'):'FPGA_3V3', ('U51','6'):'FPGA_IO_ENABLE',
    ('R62','1'):'FPGA_IO_ENABLE', ('R62','2'):'GND',
    ('Q1','1'):'FPGA_RESET_GATE', ('Q1','2'):'GND', ('Q1','3'):'FPGA_RESET_N',
    ('R66','1'):'FPGA_RESET_GATE', ('R66','2'):'GND',
    ('U52','1'):'GND', ('U52','2'):'FPGA_RESET_N', ('U52','3'):'FPGA_3V3',
    ('R64','1'):'FPGA_RESET_N', ('R64','2'):'FPGA_3V3',
    ('J83','1'):'EXT_12V', ('J83','2'):'GND', ('F80','1'):'EXT_12V', ('F80','2'):'FUSED_12V',
}


def power_interfaces(pins):
    for key, expected in POWER_PINS.items():
        if pins.get(key) != expected: raise ValueError(f'power isolation/bias mismatch: {key}')
    return len(POWER_PINS)


def main():
    import pcbnew as p
    spec = json.loads((ROOT / "hw/groundlark-fpga-hat/layout/placement.json").read_text())[BOARD.name]
    board = p.LoadBoard(str(BOARD / (BOARD.name + ".kicad_pcb")))
    pins = {(f.GetReference(), pad.GetNumber()):pad.GetNetname() for f in board.GetFootprints() for pad in f.Pads()}
    power_checks = power_interfaces(pins)
    for pin, net in {7:'PI_GEO_DRDY_N',13:'PI_IMU1_INT',15:'PI_IMU2_INT',16:'PI_IMU3_INT'}.items():
        _require_hardware((pins[('J1',str(pin))] == net), lambda: (('Pi acquisition IRQ mapping', pin)))
    from geophone_checks import verify
    geo_checks = verify(pins, {f.GetReference():(f.GetOrientationDegrees(), f.IsFlipped()) for f in board.GetFootprints()})
    from fpga_power_checks import budget, verify_board
    converter=verify_board(board,spec)
    bounds=converter['power_budget'];low,high=bounds["minimum_V"],bounds["maximum_V"]
    from assembly_fit import PI_GAP, RISER_COUNT
    gap = PI_GAP
    report = dict(
        geophone=dict(physical_pin_checks=geo_checks, sensor="Racotech RGI-4.5Hz vertical", adc="ADS122C04", axes="three aligned three-axis IMUs"),
        power=dict(interface_pin_checks=power_checks,converter=converter,**bounds),
        mechanical=dict(pi_to_hat_underside_mm=gap, riser="Samtec SSQ-120-02-G-D", riser_count=RISER_COUNT,
                        conservative_clearance_mm=clearance(gap),
                        limitations="1 mm seating tolerance plus 2.2 mm trimmed tail envelope; detailed selected cooler/support checks are in prefab-review.json"))
    _require_hardware((3.201 < low < high < 3.399), lambda: ('daqhat_01_engineering.py:98: hardware validation condition'))
    _require_hardware((clearance(gap) >= 3), lambda: ('daqhat_01_engineering.py:99: hardware validation condition'))
    (BOARD / "engineering.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()
