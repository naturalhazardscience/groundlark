"""Read-only Pi/mating-connector audit independent of enclosure coordinates.

Reference: preserved KiCad Raspberry Pi HAT template, Raspberry Pi 4 mechanical
drawing, vendor Trenz pin transcriptions and frozen numbered supplier pads.
Native PCB coordinates are top-view X right/Y down; CPL uses Y up. Neither is
an instruction to reflect an imported physical 3D component.
"""
from hardware_require import require as _require_hardware
import argparse
import csv
import hashlib
import json
from pathlib import Path

import pcbnew as p
from gpio_audit import check as check_module
from geophone_checks import verify as check_geophone, verify_connector
from jlcpcb_bom import resolve
from jlcpcb_placement import board_geometry, correct_placements, require_verified_placements

ROOT=Path(__file__).resolve().parents[2]


def header_coordinates(board,ref):
    bounds=board.GetBoardEdgesBoundingBox()
    ox,oy=p.ToMM(bounds.GetLeft()),p.ToMM(bounds.GetTop())
    footprint=next(f for f in board.GetFootprints() if f.GetReference()==ref)
    return {q.GetNumber():(p.ToMM(q.GetPosition().x)-ox,p.ToMM(q.GetPosition().y)-oy)
            for q in footprint.Pads() if q.GetNumber()}


def check_header(actual,expected):
    if set(actual)!=set(expected) or len(actual)!=40:
        raise ValueError('Pi header must have all 40 numbered contacts')
    for number,xy in expected.items():
        if max(abs(a-b) for a,b in zip(actual[number],xy))>.06:
            raise ValueError(f'Pi physical header position/handedness mismatch: pin {number}')
    return 40


def audit(require_supplier_complete=True):
    reference=ROOT/'hw/shared/reference/raspberrypi_hat.kicad_pcb'
    template=p.LoadBoard(str(reference))
    header=next(f for f in template.GetFootprints()
                if {str(i) for i in range(1,41)}<={q.GetNumber() for q in f.Pads()})
    expected=header_coordinates(template,header.GetReference())
    report={'physical_qualification':False,'Pi_template_sha256':hashlib.sha256(reference.read_bytes()).hexdigest(),'boards':{}}
    for product,name in [('groundlark-fpga-hat','groundlark-daqhat-01')]:
        source=ROOT/f'hw/{product}/boards/{name}/{name}.kicad_pcb'
        before=hashlib.sha256(source.read_bytes()).hexdigest();board=p.LoadBoard(str(source))
        count=check_header(header_coordinates(board,'J1'),expected)
        fps={f.GetReference():f for f in board.GetFootprints()}
        pins={(f.GetReference(),q.GetNumber()):q.GetNetname() for f in fps.values() for q in f.Pads() if q.GetNumber()}
        for n in (1,17):_require_hardware((pins['J1',str(n)]=='PI_3V3'), lambda: ('pcb_handedness.py:53: hardware validation condition'))
        for n in (2,4):_require_hardware((pins['J1',str(n)]=='PI_5V'), lambda: ('pcb_handedness.py:54: hardware validation condition'))
        for n in (6,9,14,20,25,30,34,39):_require_hardware((pins['J1',str(n)]=='GND'), lambda: ('pcb_handedness.py:55: hardware validation condition'))
        result={'source_sha256':before,'pi_numbered_positions':count,
                'pi_power_and_ground_contacts':12,'odd_row':'board interior','even_row':'board edge'}
        if name=='groundlark-daqhat-01':
            result['Trenz']=check_module(pins)
            orientations={r:(f.GetOrientationDegrees(),f.IsFlipped()) for r,f in fps.items()}
            result['geophone_pin_checks']=check_geophone(pins,orientations)
            pads={q.GetNumber():(p.ToMM(q.GetPosition().x)-50,p.ToMM(q.GetPosition().y)-50,p.ToMM(q.GetDrillSize().x)) for q in fps['J90'].Pads()}
            result['J90_numbered_geometry']=verify_connector(pads,orientations['J90'],str(fps['J90'].GetFPID().GetLibItemName()))
            with source.with_name('bom.csv').open(newline='') as stream:selections=resolve(list(csv.DictReader(stream)))
            geometry=[g for g in board_geometry(board) if g['reference'] in selections]
            placements=[{'Designator':g['reference'],'Layer':g['side'],'MidX':str(g['footprint_origin_mm'][0]),'MidY':str(-g['footprint_origin_mm'][1]),'Rotation':str(g['rotation_deg'])} for g in geometry]
            rows,checks=correct_placements(placements,geometry,selections)
            if require_supplier_complete:require_verified_placements(checks)
            sides={row['Designator']:row['Layer'] for row in rows}
            _require_hardware((sides['J1']=='Bottom' and all(sides[r]=='Top' for r in ('J80','J81','J82','J90'))), lambda: ('pcb_handedness.py:70: hardware validation condition'))
            result['supplier_numbered_placements']=sum('pads_checked' in c for c in checks)
            result['supplier_placement_candidates']=len(checks)
            result['supplier_release_gate_checked']=require_supplier_complete
            result['assembly_sides']={r:sides[r] for r in ('J1','J80','J81','J82','J90')}
            result['J1_convention']='Through-hole footprint drawn on front in native CAD; selected socket body and assembly CPL explicitly below PCB. Board-view hole numbers are retained.'
        _require_hardware((hashlib.sha256(source.read_bytes()).hexdigest()==before), lambda: ('Audit changed CAD'))
        report['boards'][name]=result
    report['status']='PASS: native header handedness, power/ground, module contacts and available supplier-side mappings'
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path)
    args=parser.parse_args();text=json.dumps(audit(),indent=2)+'\n'
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text)
    print(text)
