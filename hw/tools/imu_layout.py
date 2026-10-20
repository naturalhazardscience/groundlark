"""Read-only IMU bypass geometry screen; not a parasitic or noise simulation."""
from hardware_require import require as _require_hardware
import heapq

PAIRS = [('U11','5','C12'),('U11','8','C13'),
         ('U12','5','C14'),('U12','8','C15'),
         ('U13','5','C16'),('U13','8','C17')]


def shortest(graph, sources, goals):
    queue = [(0, key) for key in sources]
    heapq.heapify(queue)
    seen = set()
    while queue:
        distance, key = heapq.heappop(queue)
        if key in seen:
            continue
        if key in goals:
            return distance
        seen.add(key)
        for other, length in graph.get(key, ()):
            heapq.heappush(queue, (distance + length, other))
    raise ValueError('No copper-only path')


class Copper:
    def __init__(self, board, net):
        import pcbnew as p
        self.p = p
        self.graph, self.positions = {}, {}
        def node(v, layer):
            key = (v.x, v.y, layer)
            self.positions[key] = v
            self.graph.setdefault(key, [])
            return key
        def link(a, b, length):
            self.graph[a].append((b, length))
            self.graph[b].append((a, length))
        for t in board.GetTracks():
            if t.GetNetname() != net:
                continue
            if isinstance(t, p.PCB_VIA):
                layers = [l for l in board.GetEnabledLayers().CuStack() if t.IsOnLayer(l)]
                for a, b in zip(layers, layers[1:]):
                    link(node(t.GetPosition(), a), node(t.GetPosition(), b), 0)
            else:
                link(node(t.GetStart(), t.GetLayer()), node(t.GetEnd(), t.GetLayer()), p.ToMM(t.GetLength()))
        # Include conductive pad interiors; lengths exclude pad spreading.
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname() != net:
                    continue
                keys = self.at_pad(pad)
                for other in keys[1:]:
                    link(keys[0], other, 0)

    def at_pad(self, pad):
        return [key for key, v in self.positions.items()
                if pad.IsOnLayer(key[2]) and pad.HitTest(v)]

    def between(self, a, b):
        return shortest(self.graph, self.at_pad(a), set(self.at_pad(b)))

    def to_stitch(self, pad, stitches):
        goals = {(v.x, v.y, self.p.F_Cu) for v in stitches}
        return shortest(self.graph, self.at_pad(pad), goals)


def review(board):
    import pcbnew as p
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    def pad(ref, number):
        return next(q for q in fps[ref].Pads() if q.GetNumber() == number)
    supply, ground = Copper(board, 'SENS_3V3'), Copper(board, 'GND')
    layer = board.GetLayerID('In1.Cu')
    planes = [z.GetFilledPolysList(layer) for z in board.Zones()
              if z.GetNetname() == 'GND' and z.IsOnLayer(layer)]
    stitches = [t.GetPosition() for t in board.GetTracks()
                if isinstance(t, p.PCB_VIA) and t.GetNetname() == 'GND'
                and t.IsOnLayer(p.F_Cu) and t.IsOnLayer(layer)
                and any(poly.Contains(t.GetPosition()) for poly in planes)]
    rows = []
    for imu, pin, cap in PAIRS:
        _require_hardware((not fps[cap].IsDNP()), lambda: (f'{cap}: bypass capacitor DNP'))
        _require_hardware((fps[cap].GetValue() in ('100nF','100n','0.1uF')), lambda: (f'{cap}: expected 100 nF'))
        a, b, g = pad(imu, pin), pad(cap, '1'), pad(cap, '2')
        _require_hardware((a.GetNetname() == b.GetNetname() == 'SENS_3V3'), lambda: (f'{cap}: supply net'))
        _require_hardware((g.GetNetname() == 'GND'), lambda: (f'{cap}: ground net'))
        length = supply.between(a, b)
        return_length = ground.to_stitch(g, stitches)
        # Project layout goals, not ST limits and not noise-performance claims.
        limit = 4.0 if pin == '5' else 2.0
        _require_hardware((length <= limit), lambda: (f'{cap}: supply path {length:.3f} mm exceeds {limit} mm'))
        _require_hardware((return_length <= 2.0), lambda: (f'{cap}: ground stitch path {return_length:.3f} mm exceeds 2 mm'))
        rows.append(dict(imu=imu, pin=pin, capacitor=cap,
                         supply_xy_mm=round(length,4), supply_limit_mm=limit,
                         ground_track_to_plane_via_mm=round(return_length,4)))
    returns = {ref+'.'+pin: round(ground.to_stitch(pad(ref,pin), stitches),4)
               for ref in ('U11','U12','U13') for pin in ('6','7')}
    _require_hardware((max(returns.values()) <= 2.5), lambda: (f'IMU ground return exceeds 2.5 mm: {returns}'))
    return dict(bypass_paths=rows, imu_ground_pins_to_plane_via_mm=returns,
                method='Native track endpoint graph, pad-interior bridges, ground via intersects filled In1.Cu GND',
                limits=['XY centerline lengths exclude via barrels, pad spreading and plane impedance',
                        'No field solver, thermal/stress model, or measured noise qualification'])
