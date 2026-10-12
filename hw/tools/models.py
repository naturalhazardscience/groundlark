"""Attach real stock package models plus explicit simplified module envelopes.

Custom VRMLs represent dimensions, not qualified supplier STEP geometry.
"""
from pathlib import Path
from project_paths import board_dir
import pcbnew as p
ROOT=Path(__file__).resolve().parents[2];DEST=ROOT/'hw/shared/models';DEST.mkdir(exist_ok=True)
def box(x,y,z,w,d,h,color):
    return f'Transform {{ translation {x/2.54} {y/2.54} {z/2.54} children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry Box {{ size {w/2.54} {d/2.54} {h/2.54} }} }} ] }}\n'
def write(name,geometry): (DEST/(name+'.wrl')).write_text('#VRML V2.0 utf8\n# Simplified mechanical envelope; dimensions in 0.1 inch model units.\n'+geometry)
write('SCL3300',box(0,0,1.5,7.6,8.6,3,'0.12 0.13 0.15'))
write('MAX_M10S',box(0,0,.4,9.7,10.1,.8,'0.06 0.14 0.22')+box(0,0,1.7,8.3,8.7,1.8,'0.65 0.66 0.68'))
write('PTC1812',box(0,0,.6,4.5,3.2,1.2,'0.63 0.53 0.21'))
write('PNI14190',box(0,0,2,25.4,25.4,1,'0.05 0.23 0.1')+box(0,-8,4,18,3.2,3,'0.22 0.13 0.055')+box(-8,0,4,3.2,18,3,'0.22 0.13 0.055')+box(7,7,5.5,4,4,6,'0.22 0.13 0.055')+box(1,1,3,4,4,1,'0.1 0.1 0.1'))
# Correct bottom-mounted socket envelope aligned to the PTH pad array. The
# cavities are separate dark boxes over a gold contact row, not a solid header.
socket=box(1.27,-24.13,-5.5,5.1,50.8,8,'0.055 0.055 0.06')
for i in range(20):
    for x in [0,2.54]:
        socket+=box(x,-i*2.54,-9.55,1.25,1.25,.15,'0.01 0.01 0.012')
        socket+=box(x,-i*2.54,.5,.64,.64,2,'0.65 0.52 0.22')
write('Pi_bottom_socket',socket)
for name in ['groundlark-field-head']:
    path=board_dir(name)/(name+'.kicad_pcb');b=p.LoadBoard(str(path))
    custom={'U2':'PNI14190','U7':'PNI14190','U8':'PNI14190','U9':'PNI14190','F1':'PTC1812'}
    missing=[]
    for fp in b.GetFootprints():
        if fp.GetReference() in custom:
            fp.Models().clear();m=p.FP_3DMODEL();m.m_Filename='${KIPRJMOD}/../../../shared/models/'+custom[fp.GetReference()]+'.wrl';m.m_Show=True;fp.Models().push_back(m)
        else:
            for model in fp.Models():
                model.m_Filename=model.m_Filename.replace('${KICAD7_3DMODEL_DIR}','${KICAD9_3DMODEL_DIR}')
                check=model.m_Filename.replace('${KICAD9_3DMODEL_DIR}','/usr/share/kicad/3dmodels')
                if not Path(check).exists():missing.append((fp.GetReference(),check))
    p.SaveBoard(str(path),b);print(name,'unresolved stock model paths:',missing)
