"""Independent Sensirion SDP3x digital v1.1 fixture, pages 4, 11 and 12.

Recommended land drawing is a top PCB view (mirror Y of the bottom pin view).
Three locating pegs, split die pad and an open center vent are required.
"""
MPN = 'SDP32-125PA-TR-250PCS'
PINS = {('U23', str(n)): 'GND' for n in (1, 2, 3, 6, 9, 10, 11, 17)}
PINS.update({('U23','5'):'I2C_SCL', ('U23','7'):'SENS_3V3', ('U23','8'):'I2C_SDA',
             ('C24','1'):'SENS_3V3', ('C24','2'):'GND'})
NC = (4, 12, 13, 14, 15, 16)
# Absolute board coordinates measured from upper left; independent drawing fixture.
PADS = {'1':[(3.175,28)], '2':[(3.175,29)], '3':[(3.175,30)],
        '4':[(4,31.075)], '5':[(5,31.075)], '6':[(6,31.075)],
        '7':[(7,31.075)], '8':[(8,31.075)], '9':[(8.825,30)],
        '10':[(8.825,29)], '11':[(8.825,28)], '12':[(8,26.925)],
        '13':[(7,26.925)], '14':[(6,26.925)], '15':[(5,26.925)],
        '16':[(4,26.925)], '17':[(6,28.15),(6,29.85)]}


def verify(pins, pads, pose, mpn, dnp):
    for key, net in PINS.items():
        if pins.get(key) != net:
            raise ValueError(f'SDP32 physical pin / supply mismatch: {key}')
    for n in NC:
        net = pins.get(('U23',str(n)))
        if not net or sum(value == net for value in pins.values()) != 1:
            raise ValueError('SDP32 IRQ/reserved pin must be deliberately unconnected')
    if mpn != MPN or dnp:
        raise ValueError('SDP32 must be the fitted +/-125 Pa variant')
    if pose != (0, False):
        raise ValueError('SDP32 top-view pin orientation changed')
    if set(pads) != set(PADS):
        raise ValueError('SDP32 numbered land set changed')
    for n, expected in PADS.items():
        actual = sorted(pads[n])
        if len(actual) != len(expected) or any(abs(a-b)>1e-5 for q,r in zip(actual,sorted(expected)) for a,b in zip(q,r)):
            raise ValueError('SDP32 numbered land geometry changed')
    for pin,net in {'18':'GNSS_PPS','31':'PI_SHUTDOWN_N','33':'PI_HALTED'}.items():
        if pins.get(('J1',pin)) != net:
            raise ValueError('Reserved GNSS/power-management GPIO changed')
    return dict(physical_pin_checks=len(PINS)+len(NC), i2c_address='0x21',
                existing_bus_addresses=['0x20','0x40','0x42'], additional_pi_pins=0,
                reserved_bcm=[6,13,24], maximum_continuous_current_mA=5.5,
                body_and_barbs_xy_mm=[1.75,26.25,10.25,31.75],
                minimum_module_xy_clearance_mm=19.75, physical_qualification=False)


def verify_mechanics(board):
    """Read-only checks of locating pegs, vent and split paste, independent of CAD generation."""
    import pcbnew as p
    f=next(f for f in board.GetFootprints() if f.GetReference()=='U23')
    xy=lambda a: tuple(round(v,6) for v in p.ToMM(a.GetPosition()-f.GetPosition()))
    holes=[a for a in f.Pads() if a.GetAttribute()==p.PAD_ATTRIB_NPTH]
    if {xy(a) for a in holes}!={(3.65,-2.15),(-3.65,2.15),(3.65,2.15)} or len(holes)!=3:
        raise ValueError('SDP32 locating peg pattern changed')
    if any(tuple(round(v,6) for v in p.ToMM(a.GetDrillSize()))!=(.7,.7) for a in holes):
        raise ValueError('SDP32 locating peg drill changed')
    die=[a for a in f.Pads() if a.GetNumber()=='17']
    paste=[a for a in f.Pads() if not a.GetNumber() and a.GetLayerSet().Contains(p.F_Paste)]
    for pads,size in ((die,(1.8,.9)),(paste,(1.6,.7))):
        if len(pads)!=2 or {xy(a) for a in pads}!={(0.,-.85),(0.,.85)}:
            raise ValueError('SDP32 split die/paste pattern changed')
        if any(tuple(round(v,6) for v in p.ToMM(a.GetSize()))!=size for a in pads):
            raise ValueError('SDP32 die/paste aperture dimensions changed')
        upper=next(a for a in pads if xy(a)[1]<0)
        if upper.GetChamferPositions()!=1 or abs(upper.GetChamferRectRatio()*size[1]-.3)>1e-6:
            raise ValueError('SDP32 pin-one die/paste chamfer changed')
    if any(a.GetLayerSet().Contains(p.F_Paste) for a in die):
        raise ValueError('SDP32 die pad must use separate reduced paste openings')
    zones=list(f.Zones())
    if len(zones)!=1 or not zones[0].GetIsRuleArea() or not zones[0].GetDoNotAllowCopperPour() or not zones[0].GetDoNotAllowTracks() or not zones[0].GetDoNotAllowVias():
        raise ValueError('SDP32 central vent keepout missing')
    return dict(locating_pegs=3,split_ground_lands=2,reduced_paste_apertures=2,open_center_gap_mm=.8)
