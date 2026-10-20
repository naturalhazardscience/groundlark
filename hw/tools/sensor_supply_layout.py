"""Read-only supply/bias return limits for the DAQHAT sensor circuitry.

These are project geometry goals, not measured impedance or noise guarantees.
"""
from hardware_require import require as _require_hardware
from imu_layout import Copper, shortest

RETURNS = [('C40','2'), ('C41','2'), ('C42','2'), ('C43','2'),
           ('C93','2'), ('C94','2'), ('U41','12'), ('U41','13'),
           ('U42','12'), ('U42','13')]


def review(board):
    import pcbnew as p
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    def pad(ref, number):
        return next(q for q in fps[ref].Pads() if q.GetNumber() == number)
    layer = board.GetLayerID('In1.Cu')
    planes = [z.GetFilledPolysList(layer) for z in board.Zones()
              if z.GetNetname() == 'GND' and z.IsOnLayer(layer)]
    stitches = [t.GetPosition() for t in board.GetTracks()
                if isinstance(t, p.PCB_VIA) and t.GetNetname() == 'GND'
                and t.IsOnLayer(p.F_Cu) and t.IsOnLayer(layer)
                and any(poly.Contains(t.GetPosition()) for poly in planes)]
    ground = Copper(board, 'GND')
    returns = {}
    for ref, pin in RETURNS:
        q = pad(ref, pin)
        _require_hardware((q.GetNetname() == 'GND'), lambda: (f'{ref}.{pin}: ground net'))
        length = ground.to_stitch(q, stitches)
        _require_hardware((length <= 2.0), lambda: (f'{ref}.{pin}: ground return {length:.3f} mm exceeds 2 mm'))
        returns[ref+'.'+pin] = round(length, 4)
    supply = Copper(board, 'SENS_3V3')
    # The output tab and small lead are the same silicon terminal. Measure
    # from either physical output pad, without inventing a PCB track between them.
    sources = [k for q in fps['U40'].Pads() if q.GetNumber() == '2'
               for k in supply.at_pad(q)]
    _require_hardware((not fps['C43'].IsDNP() and fps['C43'].GetValue() in ('100nF','100n','0.1uF')), lambda: ('sensor_supply_layout.py:37: hardware validation condition'))
    _require_hardware((pad('C43','1').GetNetname() == 'SENS_3V3'), lambda: ('sensor_supply_layout.py:38: hardware validation condition'))
    length = shortest(supply.graph, sources, set(supply.at_pad(pad('C43','1'))))
    _require_hardware((length <= 4.0), lambda: (f'C43: output bypass path {length:.3f} mm exceeds 4 mm'))
    return dict(ground_track_to_plane_via_mm=returns, c43_supply_xy_mm=round(length,4),
                ground_limit_mm=2, c43_supply_limit_mm=4,
                scope='Connected copper graph and filled In1.Cu; excludes via barrel, plane impedance and measured noise')
