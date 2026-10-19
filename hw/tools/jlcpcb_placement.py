"""Resolve supplier zero orientation by fitting numbered pads, never ref offsets.

Coordinates are mm, X right/Y up. This is a catalog-footprint check, not a
claim that JLC's private feeder/model library or an order has been approved.
Bottom parts require an explicit part-specific coordinate-projection entry;
never infer a generic bottom-side mirror/rotation from a top-side mapping.
"""
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from jlcpcb_smd_placement import register_smd

ROOT = Path(__file__).resolve().parents[2]
MAPPINGS = ROOT / 'hw/assembly/groundlark-fpga-hat/daqhat-01-jlcpcb-placement.json'


def load_mappings(path=MAPPINGS):
    data = json.loads(path.read_text(encoding='utf-8'))
    validate_mappings(data)
    return data


def validate_mappings(data):
    if data['schema_version'] != 1:
        raise ValueError('Unsupported placement mapping version')
    refs = [ref for entry in data['footprints']+data.get('unverified',[]) for ref in entry['designators']]
    if len(refs) != len(set(refs)):
        raise ValueError('Duplicate placement mapping')


def require_verified_placements(audit):
    """Release gate: review exports may retain exceptions, production may not."""
    missing = [a['reference'] for a in audit if 'pads_checked' not in a]
    if missing:
        raise ValueError(f'{len(missing)} unverified supplier placements: {", ".join(missing)}')
    if not audit:
        raise ValueError('Empty supplier placement audit')


def supplier_pads(entry):
    """EasyEDA Std PAD fields: x=2, y=3, number=8; units are 10 mil."""
    ox, oy = entry['origin_easyeda']
    aliases = entry.get('pad_aliases', {})
    pads = []
    for shape in entry['pad_shapes']:
        fields = shape.split('~')
        if fields[0] != 'PAD' or not fields[8]:
            raise ValueError('Expected numbered supplier PAD')
        number = fields[8]
        number = str(int(number)) if number.isdecimal() else number
        number = aliases.get(number, number)
        pads.append((number, (float(fields[2])-ox)*.254,
                     -(float(fields[3])-oy)*.254))
    return pads


def fit_pads(source, target, tolerance=.01):
    """Rigid 2D fit with exact pin identities and multiplicities; no scaling.

    Common-number mounting pads fit by group centroid, then EACH physical pad
    is checked. Thus merging S1/S2 into native GND cannot hide a wrong offset.
    """
    if Counter(p[0] for p in source) != Counter(p[0] for p in target):
        raise ValueError('Supplier/native pad identities or counts differ')
    if len(source) < 2 or any(not math.isfinite(v) for p in source+target for v in p[1:]):
        raise ValueError('Invalid pad geometry')
    groups = []
    for pads in (source, target):
        by_number = defaultdict(list)
        for number, x, y in pads: by_number[number].append((x, y))
        groups.append({n:(sum(x for x,y in pts)/len(pts), sum(y for x,y in pts)/len(pts))
                       for n,pts in by_number.items()})
    a, b = groups
    n = len(a)
    ax, ay = (sum(p[i] for p in a.values())/n for i in (0,1))
    bx, by = (sum(p[i] for p in b.values())/n for i in (0,1))
    dot = cross = spread = 0
    for key in a:
        x,y = a[key][0]-ax, a[key][1]-ay
        u,v = b[key][0]-bx, b[key][1]-by
        dot += x*u+y*v; cross += x*v-y*u; spread += x*x+y*y
    if spread < 1e-9 or math.hypot(dot,cross) < 1e-9:
        raise ValueError('Ambiguous supplier orientation')
    angle = math.atan2(cross,dot)
    # These reviewed connector patterns are orthogonal. Quantization avoids
    # artificial 270.00004 angles from rounded catalog coordinates.
    degrees = math.degrees(angle)
    orthogonal = round(degrees/90)*90
    if abs(degrees-orthogonal) < .001: angle = math.radians(orthogonal)
    c,s = math.cos(angle),math.sin(angle)
    tx,ty = bx-c*ax+s*ay, by-s*ax-c*ay
    remaining = list(target); errors=[]
    for number,x,y in source:
        px,py = tx+c*x-s*y, ty+s*x+c*y
        matches=[(math.hypot(px-u,py-v),i) for i,(key,u,v) in enumerate(remaining) if key==number]
        error,index=min(matches)
        errors.append(error); remaining.pop(index)
    if max(errors) > tolerance:
        raise ValueError(f'Supplier pad fit exceeds {tolerance} mm: {max(errors):.6f} mm')
    return dict(x_mm=tx,y_up_mm=ty,rotation_deg=math.degrees(angle)%360,
                max_pad_error_mm=max(errors),pads_checked=len(source))


def correct_placements(placements, geometry, selections, mappings=None):
    mappings = load_mappings() if mappings is None else mappings
    validate_mappings(mappings)
    lookup = {ref:entry for entry in mappings['footprints'] for ref in entry['designators']}
    unverified = {ref:entry for entry in mappings.get('unverified',[]) for ref in entry['designators']}
    rows = {row['Designator']:row for row in placements}
    geo = {item['reference']:item for item in geometry}
    if len(rows)!=len(placements) or len(geo)!=len(geometry):
        raise ValueError('Duplicate placement geometry')
    if not set(lookup)<=set(rows):
        raise ValueError('Mapped connector missing from placement export')
    if mappings.get('require_complete_coverage') and set(rows)!=set(lookup)|set(unverified):
        raise ValueError('Incomplete supplier placement audit coverage')
    output=[]; audit=[]
    for original in placements:
        row=dict(original); ref=row['Designator']
        if ref not in lookup:
            exception=unverified.get(ref)
            if exception and (selections[ref]['mpn'],selections[ref]['lcsc'],selections[ref]['source_footprint'])!=(exception['mpn'],exception['lcsc'],exception['source_footprint']):
                raise ValueError(f'Stale placement exception: {ref}')
            output.append(row)
            audit.append(dict(reference=ref,status='UNVERIFIED supplier zero; retain native placement',
                              reason=exception['reason'] if exception else 'No supplier mapping'))
            continue
        entry=lookup[ref]; part=selections[ref]; item=geo[ref]
        if (part['mpn'],part['lcsc']) != (entry['mpn'],entry['lcsc']):
            raise ValueError(f'Stale supplier placement identity: {ref}')
        if part['source_footprint'] not in entry['source_footprints']:
            raise ValueError(f'Stale supplier placement footprint: {ref}')
        side=entry.get('side','Top')
        if row['Layer']!=side or item['side']!=side:
            raise ValueError(f'Unqualified side/bottom-side supplier mapping: {ref}')
        mode=entry.get('fit_method','rigid_centres')
        projection=entry.get('bottom_projection')
        allowed_projection='mirror_local_x_then_ccw' if mode=='smd_pad_overlap' else 'unmirrored_catalog_board_xy'
        if side=='Bottom' and (projection!=allowed_projection
                               or not entry.get('bottom_basis')):
            raise ValueError(f'Missing bottom-side projection basis: {ref}')
        if side not in ('Top','Bottom'):
            raise ValueError(f'Invalid supplier side: {ref}')
        target=[(a['number'],a['xy_mm'][0],-a['xy_mm'][1]) for a in item['pads']]
        if mode=='rigid_centres':
            fit=fit_pads(supplier_pads(entry),target)
        elif mode=='smd_pad_overlap':
            fit=register_smd(entry,item)
        else:
            raise ValueError('Unsupported placement fit method')
        row.update(MidX=f'{fit["x_mm"]:.6f}mm',MidY=f'{fit["y_up_mm"]:.6f}mm',
                   Rotation=f'{fit["rotation_deg"]:.6f}')
        output.append(row)
        status=('CATALOG BOARD-PROJECTION FIT; bottom-side model/pin-1 preview required'
                if side=='Bottom' else 'CATALOG PAD FIT; order preview review still required')
        audit.append(dict(reference=ref,status=status,side=side,fit_method=mode,
                          coordinate_projection=entry.get('bottom_projection','top_catalog_board_xy'),
                          mpn=part['mpn'],lcsc=part['lcsc'],footprint_uuid=entry['footprint_uuid'],
                          before=original,after=row,**fit))
    return output,audit


def board_geometry(board):
    import pcbnew as p
    return [dict(reference=f.GetReference(),side='Bottom' if f.IsFlipped() or f.GetReference()=='J1' else 'Top',
                 footprint_origin_mm=list(p.ToMM(f.GetPosition())),rotation_deg=f.GetOrientationDegrees()%360,
                 pads=[dict(number=a.GetNumber(),xy_mm=list(p.ToMM(a.GetPosition())))
                       |dict(size_mm=list(p.ToMM(a.GetSize())),rotation_deg=a.GetOrientationDegrees())
                       for a in f.Pads() if a.GetNumber()]) for f in board.GetFootprints()]
