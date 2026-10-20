"""Place small supporting parts within the Pi outline using real courtyards.

Large components and connectors are fixed by the reviewed mechanical layout.
This modifies placement only, never electrical connectivity.
"""
from hardware_require import require as _require_hardware
from pathlib import Path
import json,math
import pcbnew as p
ROOT=Path(__file__).resolve().parents[2];path=ROOT/'hw/groundlark-fpga-hat/layout/placement.json';data=json.loads(path.read_text());spec=data['groundlark-daqhat-01']
parts=spec['parts'];by={m['ref']:m for m in parts}
by['JP1'].update(xy=[23,53],angle=90)
by['F80'].update(xy=[17,8.5],angle=0)
fixed={m['ref'] for m in parts if m['ref'].startswith(('U','J','H','Q','F'))}
desired={}
for i,u in enumerate(['U11','U12','U13','U14']):
    x,y=by[u]['xy'];desired[f'C{12+2*i}']=[x-3.2,y+.1];desired[f'C{13+2*i}']=[x+1.6,y+2.4];desired[f'R{11+i}']=[x+3.7,y-1.2]
desired.update({'C1':[73,29],'C2':[59,8],'C3':[65,8],'R1':[72,18],'R2':[76,18],'R3':[24,51],
 'C20':[42,22],'C21':[46,22],'C22':[42,34],'C23':[46,34],'R20':[43,36],
 'C24':[5,43],'C25':[5,46],'C26':[5,49],
 'C40':[70,30],'C41':[74,30],'C42':[70,42],'C43':[74,41],
 'C44':[55,17],'C45':[65,17],'C46':[55,29],'C47':[65,29],
 'R50':[66,24],'R51':[48,34],'C48':[39,16],'C49':[45,18],
 'R52':[29,23],'R53':[29,25],'TP1':[29,52],'TP2':[26,52],'TP4':[12,52],
 'C75':[19,9],'C76':[24,9],'R61':[22,17],'R62':[18,17],'R63':[26,17],
 'C77':[42,38],'R64':[47,35],'R65':[50,33],'R66':[51,35],
 'C80':[55,51],'C81':[43,8],'C82':[50,8],'C83':[53,8],
 'C84':[43,16],'C85':[56,39],'R80':[73,16],'R81':[39,40]})
def bounds(m,xy=None,angle=None):
    f=p.FootprintLoad(str(ROOT/'hw/shared/elec'),m['local_fp']);x,y=xy or m['xy'];f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));f.SetOrientationDegrees(m['angle'] if angle is None else angle)
    rects=[s.GetBoundingBox() for s in f.GraphicalItems() if s.GetLayer()==p.F_CrtYd]
    if not rects:rects=[f.GetBoundingBox(False,False)]
    return (min(p.ToMM(r.GetX()) for r in rects),min(p.ToMM(r.GetY()) for r in rects),max(p.ToMM(r.GetRight()) for r in rects),max(p.ToMM(r.GetBottom()) for r in rects))
def overlap(a,b):return a[0]<b[2]+.08 and a[2]+.08>b[0] and a[1]<b[3]+.08 and a[3]+.08>b[1]
placed=[]
for ref in fixed:
    bb=bounds(by[ref]);bad=[r for r,b in placed if overlap(bb,b)]
    if bad:raise ValueError(('Fixed placement overlap',ref,bad,bb))
    _require_hardware((bb[0]>=.1 and bb[1]>=.1 and bb[2]<=84.9 and bb[3]<=55.9), lambda: ((ref,bb)))
    placed.append((ref,bb))
for m in sorted([m for m in parts if m['ref'] not in fixed],key=lambda m:(0 if m['ref'].startswith('C') else 1,m['ref'])):
    want=desired.get(m['ref'],[50,30]);base=bounds(m,[0,0],0);w=base[2]-base[0];h=base[3]-base[1]
    candidates=[]
    for angle in [0,90]:
        for dx in range(-32,33):
            for dy in range(-24,25):
                x=round(want[0]+dx*.5,3);y=round(want[1]+dy*.5,3)
                if x<1 or x>84 or y<1 or y>55:continue
                # Compute translated AABB without repeated pcbnew loading.
                a=bounds(m,[0,0],angle) if dx==-32 and dy==-24 else None
                candidates.append((dx*dx+dy*dy+(0.1 if angle else 0),x,y,angle))
    zeros={a:bounds(m,[0,0],a) for a in [0,90]}
    for _,x,y,angle in sorted(candidates):
        bb=zeros[angle];bb=(bb[0]+x,bb[1]+y,bb[2]+x,bb[3]+y)
        if bb[0]<.45 or bb[1]<.45 or bb[2]>84.55 or bb[3]>55.55:continue
        if any(overlap(bb,b) for _,b in placed):continue
        m['xy']=[x,y];m['angle']=angle;placed.append((m['ref'],bb));break
    else:raise ValueError(('No room',m['ref']))
path.write_text(json.dumps(data,indent=2));print('Packed',len(parts),'courtyard-checked components in 85 x 56 mm')
