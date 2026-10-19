"""Independent physical-pin and orientation fixture for DAQHAT-01.

Pin maps: TI ADS122C04 SBAS751B PW package, TPD2E2U06-Q1 SLLSEJ9E DCK
(same numbered pins as the replaced TPD2E2U06 SLLSEG9C DCK).
ADC analog inputs/reference pins 6..9 intentionally float per TI section 9.1.3.
"""
PINS = {
    ('U22','1'):'GND', ('U22','2'):'GND', ('U22','3'):'SENS_3V3',
    ('U22','4'):'GND', ('U22','5'):'GND', ('U22','10'):'GEO_AIN_N',
    ('U22','11'):'GEO_AIN_P', ('U22','12'):'GEO_AVDD', ('U22','13'):'SENS_3V3',
    ('U22','14'):'GEO_DRDY_N', ('U22','15'):'I2C_SDA', ('U22','16'):'I2C_SCL',
    ('J90','1'):'GEO_P', ('J90','2'):'GEO_N', ('J90','3'):'GND',
    ('D90','1'):'GEO_P', ('D90','2'):'GEO_N', ('D90','3'):'GND',
    ('R90','1'):'GEO_P', ('R90','2'):'GEO_AIN_P',
    ('R91','1'):'GEO_N', ('R91','2'):'GEO_AIN_N',
    ('R92','1'):'GEO_AIN_P', ('R92','2'):'GEO_VCM',
    ('R93','1'):'GEO_AIN_N', ('R93','2'):'GEO_VCM',
    ('R94','1'):'GEO_AVDD', ('R94','2'):'GEO_VCM',
    ('R95','1'):'GEO_VCM', ('R95','2'):'GND',
    ('C90','1'):'GEO_AIN_P', ('C90','2'):'GEO_AIN_N',
    ('C91','1'):'GEO_AIN_P', ('C91','2'):'GND',
    ('C92','1'):'GEO_AIN_N', ('C92','2'):'GND',
    ('C93','1'):'GEO_VCM', ('C93','2'):'GND',
    ('R96','1'):'SENS_3V3', ('R96','2'):'GEO_AVDD',
    ('C94','1'):'GEO_AVDD', ('C94','2'):'GND',
    ('C95','1'):'GEO_AVDD', ('C95','2'):'GND',
    ('C96','1'):'SENS_3V3', ('C96','2'):'GND',
    ('R97','1'):'GEO_DRDY_N', ('R97','2'):'SENS_3V3',
    ('U42','16'):'GEO_DRDY_N', ('U42','8'):'PI_GEO_DRDY_N', ('J1','7'):'PI_GEO_DRDY_N',
}


def verify_connector(pads, orientation, footprint):
    """Independent outward-facing fixture; positions use board-outline origin.

    Phoenix 1803280 drawing: 3.81 mm pitch, 1.2 mm PCB holes, local +Y entry.
    Numbered pads must retain polarity when replacing the former vertical part.
    """
    if orientation != (0, False) or not footprint.endswith('MC_1,5_3-G-3.81_1x03_P3.81mm_Horizontal'):
        raise ValueError('J90 must be the outward-facing horizontal 1803280')
    expected={'1':(10.38,50.9,1.2),'2':(14.19,50.9,1.2),'3':(18,50.9,1.2)}
    if set(pads)!=set(expected) or any(any(abs(a-b)>1e-5 for a,b in zip(pads[n],xyz)) or len(pads[n])!=3 for n,xyz in expected.items()):
        raise ValueError('J90 numbered pad / hole geometry mismatch')
    return 3


def verify(pins, orientations):
    for key, net in PINS.items():
        if pins.get(key) != net: raise ValueError(f'geophone physical pin mismatch: {key}')
    for ref in ('U11','U12','U13'):
        if orientations.get(ref) != (0,False):
            raise ValueError(f'{ref}: package axes changed; explicit software remapping required')
    if any(ref in orientations for ref in ('U14','C18','C19','R14')):
        raise ValueError('removed fourth IMU circuitry remains')
    if any(ref in orientations for ref in ('U20','C20','C21','C22','C23','R20')) or any('TILT' in net for net in pins.values()):
        raise ValueError('removed inclinometer circuitry remains')
    return len(PINS)
