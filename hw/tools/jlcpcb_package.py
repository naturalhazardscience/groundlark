"""Read-only KiCad 9 export for a DAQHAT-01 JLCPCB engineering-review package.

Run with a Python that can import pcbnew (the portable lab or WSL). Never
rewrites the routed board, fills zones, substitutes components, or releases an
order. PDF generation and independent Gerber inspection are separate steps.
"""
import argparse
import csv
import hashlib
import json
import re
import subprocess
import zipfile
from collections import Counter
from pathlib import Path
from jlcpcb_bom import REGISTRY, build_bom, check_upload_roundtrip, load_registry, require_single_hat, sourcing_status
from jlcpcb_placement import MAPPINGS, correct_placements

ROOT = Path(__file__).resolve().parents[2]
BOARD_DIR = ROOT / 'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01'
BOARD = BOARD_DIR / 'groundlark-daqhat-01.kicad_pcb'
LAYERS = ['F.Cu', *[f'In{i}.Cu' for i in range(1, 5)], 'B.Cu',
          'F.Paste', 'B.Paste', 'F.SilkS', 'B.SilkS', 'F.Mask', 'B.Mask', 'Edge.Cuts']
EXTENSIONS = {'gtl', 'g1', 'g2', 'g3', 'g4', 'gbl',
              'gtp', 'gbp', 'gto', 'gbo', 'gts', 'gbs', 'gm1'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def natural(ref):
    return re.sub(r'\d+', lambda m: m[0].zfill(6), ref)


def assembly_process(has_smd, has_pth):
    if has_smd and has_pth:
        return 'Mixed SMT/THT'
    if has_smd:
        return 'SMT'
    if has_pth:
        return 'THT'
    raise ValueError('Component has no assembly contacts')


def physical(ref):
    return not re.fullmatch(r'(H|TP)\d+', ref)


def check_reference_sets(bom, placements):
    a = [r for row in bom for r in row['Designator'].split(',')]
    b = [row['Designator'] for row in placements]
    if len(set(a)) != len(a) or len(set(b)) != len(b):
        raise ValueError('Duplicate assembly designator')
    if set(a) != set(b):
        raise ValueError(f'BOM/CPL mismatch: {sorted(set(a) ^ set(b))}')


def check_drills(expected, actual, tolerance=0.001001):
    """Match each hit once, allowing KiCad's 1 um Excellon quantization."""
    remaining = list(actual)
    for x, y, diameter in expected:
        match = next((i for i, (ax, ay, ad) in enumerate(remaining)
                      if abs(x-ax) <= tolerance and abs(y-ay) <= tolerance
                      and abs(diameter-ad) < 1e-6), None)
        if match is None:
            raise ValueError(f'Missing drill: {(x, y, diameter)}')
        remaining.pop(match)
    if remaining:
        raise ValueError(f'Unexpected drills: {remaining}')


def validate_plot_inventory(folder):
    present = {p.suffix[1:] for p in folder.iterdir() if p.is_file()}
    if not EXTENSIONS <= present:
        raise ValueError(f'Missing manufacturing layers: {sorted(EXTENSIONS - present)}')
    if present - EXTENSIONS - {'drl', 'gbrjob'}:
        raise ValueError('Unexpected manufacturing layer or file')
    drills = list(folder.glob('*.drl'))
    if len(drills) != 2:
        raise ValueError('Expected separate PTH and NPTH through-drill files only')
    spans = []
    for path in drills:
        text = path.read_text()
        if 'METRIC' not in text:
            raise ValueError('Drill units must be millimetres')
        line = next((s for s in text.splitlines() if 'TF.FileFunction' in s), '')
        spans.append(line)
    expected = ['NonPlated,1,6,NPTH', 'Plated,1,6,PTH']
    for value in expected:
        if not any(value in line for line in spans):
            raise ValueError(f'Missing drill layer attribution: {value}; got {spans}')


def run(*args):
    result = subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def source_commit(root=ROOT):
    # Portable lab/source archives intentionally omit .git. Content hashes are
    # authoritative; never fabricate a commit or inherit a parent repository.
    if not (root/'.git').exists():
        return None
    return run('git','-C',root,'rev-parse','HEAD')


def export(out, quantity):
    require_single_hat(quantity)
    import pcbnew as p
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output must be new or empty; preserve earlier packages')
    out.mkdir(parents=True, exist_ok=True)
    source_paths = [BOARD, BOARD.with_suffix('.kicad_pro'), BOARD.with_suffix('.kicad_dru'), ROOT/'hw/groundlark-fpga-hat/layout/placement.json', BOARD_DIR / 'bom.csv',
                    BOARD_DIR / 'verification.json']
    before = {str(f.relative_to(ROOT)): sha(f) for f in source_paths}
    validated = json.loads((BOARD_DIR / 'verification.json').read_text())['input_sha256']
    for source in source_paths[:-1]:
        key = str(source.relative_to(ROOT))
        if validated.get(key) != sha(source):
            raise ValueError(f'Source differs from recorded validation: {key}')
    # Procurement inputs are separately hashed; electrical validation predates
    # this ordering-code clarification and remains bound to the unchanged CAD.
    source_paths.append(REGISTRY)
    before[REGISTRY.relative_to(ROOT).as_posix()] = sha(REGISTRY)
    source_paths.append(MAPPINGS)
    before[MAPPINGS.relative_to(ROOT).as_posix()] = sha(MAPPINGS)
    b = p.LoadBoard(str(BOARD))
    from fabrication_audit import inspect
    process=inspect(BOARD)
    if process['standard_process_issues']:
        raise ValueError(process['standard_process_issues'])
    stackup=json.loads((ROOT/'hw/groundlark-fpga-hat/layout/placement.json').read_text())[BOARD_DIR.name]['stackup']
    refs = {f.GetReference(): f for f in b.GetFootprints()}
    with (BOARD_DIR / 'bom.csv').open(newline='', encoding='utf-8') as stream:
        source = list(csv.DictReader(stream))
    if len(source) != len(refs) or {r['Reference'] for r in source} != set(refs):
        raise ValueError('Source BOM does not match PCB footprints')
    if any(r['DNP'] != 'False' and not re.fullmatch(r'(H|TP)\d+', r['Reference']) for r in source):
        raise ValueError('New DNP variant requires explicit assembly review')
    registry = load_registry()
    bom, procurement, selections = build_bom(source, quantity, registry)
    plots = out / 'gerbers'; plots.mkdir()
    evidence = out / 'review'; evidence.mkdir()
    write_json(evidence/'assembly-selections.json', registry)
    write_json(evidence/'fabrication-audit.json',process)
    run('kicad-cli', 'pcb', 'drc', BOARD, '--format', 'json', '--severity-all',
        '--exit-code-violations', '-o', evidence / 'drc.json')
    drc = json.loads((evidence / 'drc.json').read_text())
    for key in ('violations', 'unconnected_items', 'schematic_parity'):
        if drc.get(key):
            raise ValueError(f'Native DRC failed: {key}')
    run('kicad-cli', 'pcb', 'export', 'gerbers', BOARD, '-o', str(plots) + '/',
        '-l', ','.join(LAYERS), '--subtract-soldermask', '--precision', '6')
    run('kicad-cli', 'pcb', 'export', 'drill', BOARD, '-o', str(plots) + '/',
        '--format', 'excellon', '--drill-origin', 'absolute', '--excellon-units', 'mm',
        '--excellon-zeros-format', 'decimal', '--excellon-oval-format', 'alternate',
        '--excellon-separate-th', '--generate-report', '--report-path', evidence / 'drill-report.txt')
    validate_plot_inventory(plots)
    for side, layers in [('top', 'F.Fab,F.SilkS,Edge.Cuts'), ('bottom', 'B.Fab,B.SilkS,Edge.Cuts')]:
        extra = ['--mirror'] if side == 'bottom' else []
        run('kicad-cli', 'pcb', 'export', 'svg', BOARD, '-o', evidence / f'cad-fab-{side}.svg',
            '-l', layers, '--mode-single', '--fit-page-to-board', '--exclude-drawing-sheet',
            '--sketch-pads-on-fab-layers', '--black-and-white', *extra)
    placements, review = [], []
    geometry = []
    for row in sorted(source, key=lambda r: natural(r['Reference'])):
        ref = row['Reference']; f = refs[ref]
        pads = [pad for pad in f.Pads() if pad.GetNumber()]
        if not physical(ref):
            continue
        if not pads:
            raise ValueError(f'Physical component without numbered pads: {ref}')
        tht = any(pad.GetAttribute() == p.PAD_ATTRIB_PTH for pad in pads)
        smd = any(pad.GetAttribute() == p.PAD_ATTRIB_SMD for pad in pads)
        process_name = assembly_process(smd, tht)
        side = 'Bottom' if f.IsFlipped() or ref == 'J1' else 'Top'
        # Standard SMD footprints are body-centred. Pin-1-anchored THT packages
        # need a body-centre estimate; use the pad pattern for review only.
        x, y = p.ToMM(f.GetPosition())
        method = 'KiCad SMD body origin; confirm against feeder definition'
        if tht and not smd:
            xs, ys = zip(*(p.ToMM(pad.GetPosition()) for pad in pads))
            x, y = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            method = 'THT pad-pattern centre; manual assembly drawing controls'
        if smd and tht:
            method += '; SMT contacts with plated mounting features; confirm both assembly processes'
        placement = dict(Designator=ref, MidX=f'{x:.6f}mm', MidY=f'{-y:.6f}mm',
                         Layer=side, Rotation=f'{f.GetOrientationDegrees() % 360:.6f}')
        placements.append(placement)
        part = selections[ref]
        mpn, code, url = part['mpn'], part['lcsc'], part['evidence_url']
        hold = sourcing_status(part)
        review.append(dict(Designator=ref, MPN=mpn, Manufacturer=part['manufacturer'],
                           Source_MPN=row['MPN'], CAD_Footprint=row['Footprint'],
                           Ordering_code_resolution=part['resolution'], Process=process_name,
                           Side=side, Position_basis=method, Rotation_status='REVIEW REQUIRED',
                           Sourcing_status=hold, Catalog_URL=url))
        pin1 = next((pad for pad in pads if pad.GetNumber() == '1'), None)
        geometry.append(dict(reference=ref, side=side, process=process_name,
                             footprint_origin_mm=list(p.ToMM(f.GetPosition())),
                             x_mm=x, y_mm=y, rotation_deg=f.GetOrientationDegrees() % 360,
                             pin1_mm=list(p.ToMM(pin1.GetPosition())) if pin1 else None,
                             pads=[dict(number=a.GetNumber(), xy_mm=list(p.ToMM(a.GetPosition())),
                                        size_mm=list(p.ToMM(a.GetSize())),rotation_deg=a.GetOrientationDegrees()) for a in pads]))
    placements, placement_audit = correct_placements(placements, geometry, selections)
    fitted = {a['reference']:a for a in placement_audit if 'pads_checked' in a}
    for row in review:
        if row['Designator'] in fitted:
            row['Rotation_status'] = fitted[row['Designator']]['status']
            row['Position_basis'] = ('Native SMT body origin retained; catalog pin-envelope registration'
                if fitted[row['Designator']]['fit_method']=='smd_pad_overlap'
                else 'Supplier footprint origin fitted to native numbered pads')
    write_json(evidence / 'supplier-placement-audit.json', placement_audit)
    write_json(evidence / 'supplier-placement-mappings.json', json.loads(MAPPINGS.read_text()))
    check_reference_sets(bom, placements)
    write_csv(out / 'BOM-review.csv', list(bom[0]), bom)
    check_upload_roundtrip(out / 'BOM-review.csv', bom)
    write_csv(out / 'CPL-review.csv', list(placements[0]), placements)
    write_csv(evidence / 'assembly-review.csv', list(review[0]), review)
    write_csv(out / 'procurement.csv', list(procurement[0]), procurement)
    # Conservative full via-fill callout: every through-via is resin filled and
    # copper capped. The process audit rejects every non-through via. This
    # avoids omissions where a via barrel only partly overlaps a solder pad.
    vias = []
    for track in b.GetTracks():
        if not isinstance(track, p.PCB_VIA): continue
        x, y = p.ToMM(track.GetPosition())
        vias.append(dict(X_mm=x, Y_mm=-y, Type='through',
                         From=b.GetLayerName(track.TopLayer()), To=b.GetLayerName(track.BottomLayer()),
                         Drill_mm=p.ToMM(track.GetDrillValue()), Pad_mm=p.ToMM(track.GetWidth(track.TopLayer())),
                         Fill='resin filled / copper capped'))
    vias.sort(key=lambda v: (v['X_mm'], v['Y_mm']))
    write_csv(out / 'via-processing.csv', list(vias[0]), vias)
    write_json(evidence / 'placement-geometry.json', geometry)
    if before != {str(f.relative_to(ROOT)): sha(f) for f in source_paths}:
        raise ValueError('Source changed during export')
    with zipfile.ZipFile(out / 'DAQHAT-01-Gerbers-REVIEW.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(plots.iterdir()):
            if path.suffix[1:] in EXTENSIONS | {'drl', 'gbrjob'}:
                archive.write(path, path.name)
    manifest = {
        'status': 'ENGINEERING REVIEW ONLY - NOT RELEASED FOR MANUFACTURE',
        'requested_assembled_HATs': quantity,
        'requested_fabricated_HATs': quantity,
        'boards_per_gerber_design': 1,
        'panelized': False,
        'supplier_placement_complete': all('pads_checked' in a for a in placement_audit),
        'unverified_placements': [a['reference'] for a in placement_audit if 'pads_checked' not in a],
        'published_standard_PCBA_minimum': 2,
        'source_commit': source_commit(),
        'kicad': run('kicad-cli', 'version'), 'source_sha256': before,
        'board_mm': [140, 56], 'nominal_thickness_mm': 1.6,
        'copper_layers': LAYERS[:6], **stackup,
        'stack_status': 'Stock six-layer FR4 JLC06161H-3313 reference; no custom lamination',
        'counts': {'physical_placements': len(placements), 'BOM_lines': len(bom),
                   'catalog_mapped_BOM_lines': sum(bool(r['JLCPCB Part #']) for r in bom),
                   'excluded_holes_testpads': len(source) - len(placements),
                   'vias': dict(Counter(v['Type'] for v in vias)),
                   'assembly': dict(Counter(f"{r['Side']} {r['Process']}" for r in review))},
        'coordinate_convention': 'Absolute KiCad origin; X right, Y up; mm. CPL/Excellon/Gerber same origin. Bottom NOT mirrored.',
        'release_holds': [
            'ONE fabricated and assembled HAT only. Supplier must accept quantity 1; no increase to 2 or 5 is authorized. Set both website quantities to 1.',
            'Confirm standard six-layer FR4, 1.6mm nominal, 1oz outer/0.5oz inner, 0.3/0.4mm through-drills and POFV; no HDI or custom stack.',
            'JLC Standard assembly frame/rails and fiducials; 140x56 board is below 70mm minimum dimension.',
            f'J1 {selections["J1"]["mpn"]} / {selections["J1"]["lcsc"]}: {selections["J1"]["sourcing_note"]}',
            'Verify every rotation and centroid against JLC component definitions; J1 is bottom-mounted THT.',
            f'{len(placements)-len(fitted)} placements lack frozen numbered supplier pads; retain as manufacturing holds until verified.',
            'U23 SDP32: install in the final reflow only, maximum 260 C and at most 150 seconds above 200 C; protect ports and never wash the assembled sensor.',
            'Approve mixed SMT/THT assembly, reflow constraints and sensor handling; do not substitute parts.',
            'Review panelized Gerbers, drill spans, polarity/pin 1 and assembly preview before payment.',
        ],
    }
    write_json(out / 'manifest.json', manifest)
    print(json.dumps(manifest['counts'], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--quantity', type=int, choices=[1], default=1,
                        help='One fabricated and assembled HAT only; batch quantities are prohibited')
    args = parser.parse_args()
    export(args.output.resolve(), args.quantity)
