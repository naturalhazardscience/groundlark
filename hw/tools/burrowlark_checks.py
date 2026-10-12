"""Burrowlark population boundary, independent of placement/BOM generation."""


def population(references):
    references = set(references)
    removed = references & {'U3', 'C5'}
    if removed:
        raise ValueError(f'Burrowlark retains removed infrasound parts: {sorted(removed)}')
    if not {'U6', 'C10'} <= references:
        raise ValueError('Burrowlark requires SHT45 U6 and bypass C10')
    if not {'U2', 'U7', 'U8', 'U9', 'C4', 'C11', 'C12', 'C13', 'R9'} <= references:
        raise ValueError('Burrowlark requires four RM3100 modules, local bypasses and CS pull-up')


def array_pins(pins):
    """Independent PNI 14190 numbered-pad and STM32F042K6 package fixture."""
    from collections import Counter
    degree = Counter(pins.values())
    for lane, (ref, cap) in enumerate(zip(('U2', 'U7', 'U8', 'U9'), ('C4', 'C11', 'C12', 'C13'))):
        expected = {1: 'MAG_SCK', 2: f'MAG_MISO{lane}', 3: 'MAG_MOSI',
                    4: 'MAG_CSN', 5: f'MAG_DRDY{lane}', 7: 'GND', 10: 'GND',
                    12: 'V3_SENSOR', 13: 'V3_SENSOR', 14: 'GND'}
        for pin, net in expected.items():
            if pins.get((ref, str(pin))) != net:
                raise ValueError(f'{ref}.{pin} must connect to {net}')
        for pin in (6, 8, 9, 11):
            net = pins.get((ref, str(pin)))
            if (ref, str(pin)) not in pins or (net and degree[net] != 1):
                raise ValueError(f'{ref}.{pin} must be a deliberate no-connect')
        for pin, net in ((1, 'V3_SENSOR'), (2, 'GND')):
            if pins.get((cap, str(pin))) != net:
                raise ValueError(f'{cap}.{pin} must connect to {net}')
    mcu = {7: 'MAG_SCK', 8: 'MAG_MOSI', 9: 'MAG_CSN',
           10: 'MAG_MISO0', 11: 'MAG_MISO1', 12: 'MAG_MISO2', 13: 'MAG_MISO3',
           14: 'MAG_DRDY0', 15: 'MAG_DRDY1', 26: 'MAG_DRDY2', 27: 'MAG_DRDY3'}
    for pin, net in mcu.items():
        if pins.get(('U1', str(pin))) != net:
            raise ValueError(f'U1.{pin} must connect to {net}')
    if pins.get(('R9', '1')) != 'MAG_CSN' or pins.get(('R9', '2')) != 'V3_SENSOR':
        raise ValueError('CS pull-up must use the switched sensor supply')


def array_geometry(parts, size):
    """Check actual PCB geometry or placement independently of array metadata."""
    if tuple(size) != (96, 70):
        raise ValueError('Burrowlark B1 outline must be 96 x 70 mm')
    expected = {'U2': (20, 20), 'U7': (50, 20), 'U8': (20, 50), 'U9': (50, 50)}
    for ref, xy in expected.items():
        part = parts[ref]
        if any(abs(a-b) > .001 for a, b in zip(part['xy'], xy)) or abs(part['angle']) > .001 or part.get('side', 'front') != 'front':
            raise ValueError(f'{ref} must preserve the 30 mm aligned square grid')


def climate_pins(pins):
    expected = {('U6', '1'): 'SDA', ('U6', '2'): 'SCL',
                ('U6', '3'): 'V3_SENSOR', ('U6', '4'): 'GND',
                ('C10', '1'): 'V3_SENSOR', ('C10', '2'): 'GND'}
    for pin, net in expected.items():
        if pins.get(pin) != net:
            raise ValueError(f'SHT45 pin {pin} must connect to {net}')


def array_layout(board):
    """Read actual local bypass copper and filled-plane intersections."""
    import pcbnew as p
    from imu_layout import Copper
    fps={f.GetReference():f for f in board.GetFootprints()}
    def pad(ref,num):return next(q for q in fps[ref].Pads() if q.GetNumber()==num)
    layer=board.GetLayerID('In1.Cu')
    planes=[z.GetFilledPolysList(layer) for z in board.Zones() if z.GetNetname()=='GND' and z.IsOnLayer(layer)]
    stitches=[t.GetPosition() for t in board.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND'
              and any(poly.Contains(t.GetPosition()) for poly in planes)]
    supply,ground=Copper(board,'V3_SENSOR'),Copper(board,'GND')
    rows=[]
    for ref,cap in zip(('U2','U7','U8','U9'),('C4','C11','C12','C13')):
        assert not fps[cap].IsDNP() and fps[cap].GetValue() in ('100nF','100n','0.1uF'),f'{cap}: fitted 100 nF required'
        feed=supply.between(pad(ref,'13'),pad(cap,'1'))
        back=ground.to_stitch(pad(cap,'2'),stitches)
        assert feed<=4.0,f'{cap}: local supply path {feed:.3f} mm exceeds 4 mm'
        assert back<=2.0,f'{cap}: ground return {back:.3f} mm exceeds 2 mm'
        rows.append(dict(module=ref,capacitor=cap,supply_path_mm=round(feed,4),ground_stitch_path_mm=round(back,4)))
    return dict(bypasses=rows,scope='Native copper geometry; not supply-noise or magnetic cross-talk qualification')
