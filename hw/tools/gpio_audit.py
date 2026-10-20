"""Audit all 158 ordinary TE0712-03-81I36-A I/Os against vendor page 6.

The module/ground CSVs are schematic transcriptions, not generated CAD netlists.
The host link uses nine ordinary I/Os; the remaining 149 are no-connects. Dedicated clocks,
Ethernet PHY pairs and GTP lanes must remain disconnected on this carrier.
"""
from hardware_require import require as _require_hardware
from collections import Counter
from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[2]
CARRIER = {'JM1': 'J80', 'JM2': 'J81', 'JM3': 'J82'}
HOST = {('JM2', 11): 'FPGA_UART_RX', ('JM2', 13): 'FPGA_UART_TX',
        ('JM2', 14): 'FPGA_RESET_N', ('JM2',22):'FPGA_LINK_SCLK',
        ('JM2',24):'FPGA_LINK_CS_N', ('JM2',21):'FPGA_LINK_DQ0',
        ('JM2',23):'FPGA_LINK_DQ1', ('JM2',25):'FPGA_LINK_DQ2',
        ('JM2',27):'FPGA_LINK_DQ3'}
CONTROL = {
 'JM1': {1:'FPGA_VIN',3:'FPGA_VIN',5:'FPGA_VIN',7:'FPGA_NOSEQ',9:'FPGA_3V3',
         11:'FPGA_3V3',13:'FPGA_VIN',14:'FPGA_3V3',15:'FPGA_VIN',28:'FPGA_EN1',
         30:'FPGA_PGOOD',32:'FPGA_MODE',89:'FPGA_JTAGEN'},
 'JM2': {1:'FPGA_3V3',2:'FPGA_VIN',3:'FPGA_3V3',4:'FPGA_VIN',6:'FPGA_VIN',
         7:'FPGA_3V3',8:'FPGA_VIN',9:'FPGA_3V3',10:'FPGA_3V3',12:'FPGA_3V3',
         18:'FPGA_CONFIG_RESET_N',91:'FPGA_3V3',93:'JTAG_TMS',95:'JTAG_TDI',
         97:'JTAG_TDO',99:'JTAG_TCK'}, 'JM3': {}}


def records(name):
    with (ROOT / 'docs' / name).open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def pad(module, number):
    return CARRIER[module], str(number + 1 if number % 2 else number - 1)


def check(pins):
    module = records('trenz-gpio-module.csv')
    grounds = records('trenz-ground-module.csv')
    _require_hardware((len(module) == 158), lambda: ('gpio_audit.py:40: hardware validation condition'))
    _require_hardware((Counter(int(r['bank']) for r in module) == {13:30,14:30,15:50,16:48}), lambda: ('gpio_audit.py:41: hardware validation condition'))
    _require_hardware((len({(r['module_connector'], r['module_pin']) for r in module}) == 158), lambda: ('gpio_audit.py:42: hardware validation condition'))
    degree = Counter(pins.values())
    expected = dict(HOST)
    for r in module:
        key = r['module_connector'], int(r['module_pin'])
        net = pins[pad(*key)]
        if key in HOST:
            _require_hardware((net == HOST[key]), lambda: ((key, net, HOST[key])))
        else:
            _require_hardware((net and degree[net] == 1), lambda: (('Unused GPIO connected', key, net)))
    for r in grounds:
        key = r['module_connector'], int(r['module_pin'])
        _require_hardware((key not in expected), lambda: ('gpio_audit.py:54: hardware validation condition'))
        expected[key] = 'GND'
    for connector, assignments in CONTROL.items():
        for number, net in assignments.items():
            _require_hardware(((connector, number) not in expected), lambda: ('gpio_audit.py:58: hardware validation condition'))
            expected[connector, number] = net
    for connector, count in [('JM1',100), ('JM2',100), ('JM3',60)]:
        for number in range(1,count+1):
            key = connector, number
            net = pins[pad(*key)]
            if key in expected:
                _require_hardware((net == expected[key]), lambda: ((key, net, expected[key])))
            else:
                _require_hardware((net and degree[net] == 1), lambda: (('Reserved or unused pin connected', key, net)))
        _require_hardware((pins[CARRIER[connector], str(count+1)] == 'GND'), lambda: ('gpio_audit.py:68: hardware validation condition'))
    _require_hardware((not any(ref in {f'J{i}' for i in range(84,90)} for ref, _ in pins)), lambda: ('External expansion/programming header remains'))
    # Trenz TE0712 CPLD v27 / firmware REV03: U3.13 MODE has an internal
    # pull-up. JM1.32 mates with carrier J80.31 and has no carrier load.
    # MODE is distinct from the carrier's JTAG/SPI switch mode select.
    _require_hardware((degree['FPGA_MODE']==1), lambda: ('MODE must remain unloaded for the documented REV03 pull-up'))
    for key,net in {('R80','1'):'FPGA_JTAGEN',('R80','2'):'GND',
                    ('R81','1'):'FPGA_NOSEQ',('R81','2'):'GND',
                    ('JP80','1'):'FPGA_EN1',('JP80','2'):'GND'}.items():
        _require_hardware((pins.get(key)==net), lambda: (('Trenz control bias/disable',key,net)))
    from host_link_checks import verify
    link_checks = verify(pins)
    return {'module_gpio_checks':158, 'module_contact_checks':260,
            'internal_user_gpio':9, 'unused_user_gpio':149, 'exposed_gpio':0,
            'host_link_pin_checks':link_checks, 'gpio_voltage_v':3.3}
