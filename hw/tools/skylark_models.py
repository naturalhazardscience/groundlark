"""Generate portable dimension-envelope models and attach them to Skylark.

These are simplified authored models, not supplier STEP files. The routed PCB
and its footprints supply positions and rotations. No circuit/copper is edited.
"""
from hardware_require import require as _require_hardware
import math, json, hashlib
from pathlib import Path
import pcbnew as p
from project_paths import ROOT, board_dir
from kicad_support import save_board

DEST=ROOT/'hw/skylark-usb/models'
def box(x,y,z,w,d,h,color):
    return f'Transform {{ translation {x/2.54} {y/2.54} {z/2.54} children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry Box {{ size {w/2.54} {d/2.54} {h/2.54} }} }} ] }}\n'

def cylinder(x,y,z,r,h,color,n=96):
    # Explicit mesh: KiCad's VRML reader does not render Cylinder primitives.
    pts=[(x+r*math.cos(2*math.pi*i/n),y+r*math.sin(2*math.pi*i/n),zz) for zz in (z,z+h) for i in range(n)]
    faces=[list(reversed(range(n))),list(range(n,2*n))]+[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)]
    return 'Shape { appearance Appearance { material Material { diffuseColor '+color+' } } geometry IndexedFaceSet { solid FALSE coord Coordinate { point [ '+', '.join(' '.join(f'{q/2.54:.6f}' for q in pt) for pt in pts)+' ] } coordIndex [ '+', '.join(' '.join(map(str,f))+', -1' for f in faces)+' ] } }\n'

def main():
    DEST.mkdir(exist_ok=True)
    shapes={}
    # SO2 and H2S share the DS-0685/DS-0681 31.5 x 15.5 mm envelope.
    # Mill-Max 0322 upper rim is 4.88 mm above the PCB seating surface.
    for kind,col in [('SO2','0.86 0.87 0.88'),('H2S','0.83 0.86 0.89')]:
        s=cylinder(0,0,4.88,15.75,15.3,col)
        s+=cylinder(0,0,20.20,13.5,.08,'0.23 0.25 0.27')
        s+=cylinder(0,0,20.29,10.5,.08,'0.78 0.79 0.76')
        for x,y in [(0,8.5),(6.010408,6.010408),(-6.010408,6.010408),(0,-8.5)]:
            s+=cylinder(x,y,-3.18,1.08,3.18,'0.72 0.55 0.20',24)
            s+=cylinder(x,y,0,1.59,.81,'0.72 0.55 0.20',24)
            s+=cylinder(x,y,.81,1.155,4.07,'0.72 0.55 0.20',24)
        shapes[kind]=s
    for kind,w,d,h in [('MCU',7,7,1.6),('ADC',4.4,5,1.2),('OPA2',3,3,1.1),('OPA1',1.6,2.9,1.1),('ESD',1.6,2.9,1.1),('SWITCH',1.6,2.9,1.1),('AnalogSwitch',1.6,2.9,1.1),('LDO',1.6,2.9,1.1),('REF',1.3,2.9,1.1),('JFET',1.3,2.9,1.1),('MOS',1.3,2.9,1.1),('ClampNPN',1.3,2.9,1.1),('GateDiode',1.3,2.9,1.1)]:
        shapes[kind]=box(0,0,.15+h/2,w,d,h,'0.075 0.08 0.09')
    shapes['SHT']=box(0,0,.25,1.5,1.5,.5,'0.72 0.73 0.7')+box(0,0,.55,1.1,1.1,.12,'0.93 0.93 0.91')
    shapes['BMP']=box(0,0,.375,2,2,.75,'0.68 0.7 0.72')+cylinder(.4,.4,.75,.14,.03,'0.05 0.05 0.05',24)
    # USB receptacle opens toward the bottom edge (-Y in model coordinates).
    shapes['USB']=box(0,0,.25,8.94,7.35,.5,'0.68 0.7 0.73')+box(0,0,3.0,8.94,7.35,.3,'0.68 0.7 0.73')
    for x in (-4.3,4.3):shapes['USB']+=box(x,0,1.55,.3,7.35,2.5,'0.68 0.7 0.73')
    shapes['USB']+=box(0,-.8,1.6,6.3,4.2,.6,'0.08 0.08 0.085')
    shapes['PMS']=box(0,0,.3,13.7,5.2,.6,'0.9 0.89 0.84')
    for x in (-6.5,6.5):shapes['PMS']+=box(x,0,2.2,.7,5.2,3.8,'0.9 0.89 0.84')
    for y in (-2.3,2.3):shapes['PMS']+=box(0,y,2.2,13.7,.6,3.8,'0.9 0.89 0.84')
    shapes['DebugHeader']=box(.635,-2.54,1.27,3.43,6.35,2.54,'0.055 0.055 0.06')
    for i in range(5):
        for x in (0,1.27):shapes['DebugHeader']+=box(x,-i*1.27,2,.41,.41,7,'0.7 0.55 0.22')
    shapes['BUTTON']=box(0,0,.8,6,6,1.6,'0.55 0.57 0.59')+cylinder(0,0,1.6,1.4,1,'0.13 0.13 0.14',32)
    shapes['FUSE']=box(0,0,.6,3.2,1.6,1.2,'0.60 0.50 0.20')
    shapes['StatusLED']=box(0,0,.4,1.6,.8,.8,'0.45 0.7 0.22')
    def passive(w,d,h,color):
        return box(0,0,h/2,w-.4,d,h,color)+box(-(w-.2)/2,0,h/2,.2,d,h,'0.72 0.73 0.75')+box((w-.2)/2,0,h/2,.2,d,h,'0.72 0.73 0.75')
    shapes['R']=passive(1.6,.8,.45,'0.11 0.12 0.13')
    shapes['C0603']=passive(1.6,.8,.8,'0.60 0.42 0.23')
    shapes['C1206']=passive(3.2,1.6,1.3,'0.60 0.42 0.23')
    shapes['C0805']=passive(2,1.25,1.25,'0.60 0.42 0.23')
    for k,s in shapes.items():(DEST/(k+'.wrl')).write_text('#VRML V2.0 utf8\n# Simplified dimension envelope; model units = 2.54 mm.\n'+s)
    path=board_dir('skylark-usb')/'skylark-usb.kicad_pcb';b=p.LoadBoard(str(path))
    meta=json.loads((path.parent/'electrical.json').read_text())
    kinds={x['ref']:x for x in meta['parts']}
    for fp in b.GetFootprints():
        entry=kinds[fp.GetReference()];kind=entry['type']
        if not kind or kind=='TP':continue
        if kind.startswith('R_'):kind='R'
        if kind.startswith('C_'):kind='C1206' if '1206' in entry['local_fp'] else 'C0805' if '0805' in entry['local_fp'] else 'C0603'
        _require_hardware((kind in shapes), lambda: (kind))
        fp.Models().clear();m=p.FP_3DMODEL();m.m_Filename='${KIPRJMOD}/../../models/'+kind+'.wrl';m.m_Show=True;fp.Models().push_back(m)
    save_board(str(path),b)
    (DEST/'provenance.json').write_text(json.dumps({'generator':'hw/tools/skylark_models.py','kind':'simplified dimension envelopes, not supplier STEP','cell_body_mm':[31.5,15.5],'socket_rim_above_pcb_mm':4.88,'board_mm':[90,100,1.6],'qualification':'Physical mating, retention, airflow and enclosure fit not qualified.','models':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DEST.glob('*.wrl'))}},indent=2)+'\n')
    print('Attached portable Skylark models; no copper changed')

if __name__=='__main__':main()
