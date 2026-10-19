"""Render models: stock bodies, vendor TE0712 STEP, and labelled Pi envelope.

The Pi model is conceptual; the HAT geometry is the actual KiCad PCB. Run after
routing. Does not change the circuit or create a fictitious routed board.
"""
from pathlib import Path
import math
from kicad_support import save_board
import pcbnew as p
from assembly_fit import PI_TOP, PI_GAP, J1_BODY, RISER_BODY, RISER_COUNT
ROOT=Path(__file__).resolve().parents[2];M=ROOT/'hw/shared/models'
F=ROOT/'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01';NAME='groundlark-daqhat-01'
def box(x,y,z,w,d,h,color):
    return f'Transform {{ translation {x/2.54} {y/2.54} {z/2.54} children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry Box {{ size {w/2.54} {d/2.54} {h/2.54} }} }} ] }}\n'
def cylinder(x,y,z,r,h,color):
    return f'Transform {{ translation {x/2.54} {y/2.54} {z/2.54} rotation 1 0 0 1.570796 children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry Cylinder {{ radius {r/2.54} height {h/2.54} }} }} ] }}\n'

def z_cylinder_mesh(x,y,z,r,h,color):
    # KiCad's VRML renderer omits Cylinder primitives; explicit faces retain ports.
    n=32
    pts=[((x+r*math.cos(i*2*math.pi/n))/2.54,(y+r*math.sin(i*2*math.pi/n))/2.54,(z+dz)/2.54)
         for dz in (-h/2,h/2) for i in range(n)]
    faces=[list(reversed(range(n))),list(range(n,2*n))]
    faces += [[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)]
    vertices=', '.join(' '.join(f'{v:.7f}' for v in q) for q in pts)
    indices=', '.join(' '.join(map(str,face+[-1])) for face in faces)
    return f'Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry IndexedFaceSet {{ coord Coordinate {{ point [ {vertices} ] }} coordIndex [ {indices} ] }} }}\n'
def write(name,s):
    (M/(name+'.wrl')).write_text('#VRML V2.0 utf8\n# Conceptual geometry, millimetres converted to KiCad VRML units.\n'+s)
def model(fp,path,offset=(0,0,0)):
    fp.Models().clear();m=p.FP_3DMODEL();m.m_Filename=path;m.m_Show=True
    m.m_Offset.x,m.m_Offset.y,m.m_Offset.z=offset;fp.Models().push_back(m)
def add(b,ref,path,xy,offset=(0,0,0)):
    f=p.FOOTPRINT(b);f.SetReference(ref);f.SetValue('Visualization only');f.SetPosition(p.VECTOR2I(*(p.FromMM(t) for t in xy)));f.Reference().SetVisible(False);f.Value().SetVisible(False);b.Add(f);model(f,path,offset)
socket=box(1.27,-24.13,-1.6-J1_BODY/2,5.1,50.8,J1_BODY,'0.04 0.045 0.055')
for i in range(20):
    for x in [0,2.54]:socket+=box(x,-i*2.54,1.15,.64,.64,2.3,'0.73 0.57 0.22')
write('Pi_Megastar_2x20',socket)
# DS-0300 Rev J E1BS: upright SIP, four 2.54 mm leads; two side barbs.
# Conservative display envelope, not a certified manufacturer solid.
dlvr=box(3.62,2.8,9.375,12.7,4.88,15.75,'0.15 0.15 0.17')
for y,z in [(2.12,7.95),(7.03,11.3)]:
    dlvr+=box(11.025,y,z,2.11,2.24,2.24,'0.15 0.15 0.17')
for i in range(4):dlvr+=box(i*2.54,0,0,.51,.25,3,'0.72 0.72 0.72')
write('DLVR_E1BS',dlvr)
# Sensirion SDP3x digital v1.1 drawing envelope; not a vendor solid.
sdp32=box(0,0,1.1,8.5,5.5,2.2,'0.15 0.15 0.17')
for x in [-2.15,2.15]:sdp32+=z_cylinder_mesh(x,.65,3.3,1,2.2,'0.15 0.15 0.17')
for x,y in [(3.65,2.15),(-3.65,-2.15),(3.65,-2.15)]:sdp32+=z_cylinder_mesh(x,y,-.375,.295,.75,'0.15 0.15 0.17')
write('SDP32_envelope',sdp32)
# Datasheet-derived display envelopes for parts absent from the stock 3D set.
# PJ-102AH body 9 x 14.4 x 11 mm; mouth at local PCB +Y (VRML -Y).
jack=box(0,-6.5,5.5,9,14.4,11,'0.055 0.055 0.065')
for r,y,h,color in [(3.25,-13.76,.16,'0.5 0.52 0.54'),(2.8,-13.86,.12,'0.018 0.018 0.021'),(1,-13.94,.12,'0.7 0.7 0.7')]:
    jack+=f'Transform {{ translation 0 {y/2.54} {6.5/2.54} children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry Cylinder {{ radius {r/2.54} height {h/2.54} }} }} ] }}\n'
for x,y in [(0,0),(0,-6),(4.7,-3)]:jack+=box(x,y,-.8,1,1.6,3,'0.65 0.65 0.65')
write('PJ_102AH_envelope',jack)
write('TPSM53603_envelope',box(0,0,2,5,5.5,4,'0.12 0.12 0.14')+cylinder(-1.8,1.8,4.01,.23,.02,'0.8 0.8 0.8'))
for n in [50,30]:
    s=box(0,0,2,(n-1)*.5+5.7,4.6,4,'0.08 0.09 0.1')
    for i in range(n):
        for y in [-1.85,1.85]:s+=box((i-(n-1)/2)*.5,y,.3,.2,1.1,.6,'0.72 0.58 0.25')
    write(f'LSHM_{n}_4mm',s)
b=p.LoadBoard(str(F/(NAME+'.kicad_pcb')))
title=b.GetTitleBlock();title.SetRevision('DAQHAT-01 6L');title.SetDate('2026-10-19');b.SetTitleBlock(title)
custom={'J1':'Pi_Megastar_2x20','J80':'LSHM_50_4mm','J81':'LSHM_50_4mm','J82':'LSHM_30_4mm','U23':'SDP32_envelope','J83':'PJ_102AH_envelope','U80':'TPSM53603_envelope','U132':'TPSM53603_envelope'}
for fp in b.GetFootprints():
    if fp.GetReference()=='J140':model(fp,'${KIPRJMOD}/../../../shared/models/HL_SMA_KWE_02.step')
    elif fp.GetReference()=='U21':model(fp,'${KIPRJMOD}/../../../shared/models/MAX_M10S_envelope.step')
    elif fp.GetReference() in custom:model(fp,'${KIPRJMOD}/../../../shared/models/'+custom[fp.GetReference()]+'.wrl')
    else:
        for m in fp.Models():m.m_Filename=m.m_Filename.replace('${KICAD7_3DMODEL_DIR}','${KICAD9_3DMODEL_DIR}')
# Mark each underside bank without covering the fine-pitch pads.
for item in list(b.GetDrawings()):
    if isinstance(item,p.PCB_TEXT) and item.GetText()=='OFF   ON':item.SetText('FPGA ON/OFF')
    if isinstance(item,p.PCB_TEXT) and (item.GetText().startswith('GPIO J8') or item.GetText() in ('JTAG','PI / FPGA LINK')):b.Delete(item)
save_board(str(F/(NAME+'.kicad_pcb')),b)
# Actual carrier + manufacturer's module geometry; separate assembly view file.
add(b,'MODEL_TE0712','${KIPRJMOD}/../../../shared/models/trenz/STP-TE0712-03-No Variations.step',(80,98),(0,0,9.6099917))
st=''
for x,y in [(33,11),(77,11),(33,45),(77,45)]:
    st+=cylinder(x,-y,4,2.5,8,'0.7 0.72 0.74')
write('Trenz_spacers',st);add(b,'MODEL_SPACERS','${KIPRJMOD}/../../../shared/models/Trenz_spacers.wrl',(50,50))
save_board(str(F/'trenz-mounted.kicad_pcb'),b)
# Pi 4 concept with two unmounted SSQ-120-02-G-D sockets used as 1:1 risers.
# Its 8.51 mm body adds clearance; 4.93 mm square tails mate into HAT J1.
z=PI_TOP
pi=box(42.5,-28,z-.8,85,56,1.6,'0.04 0.28 0.15')
pi+=box(32.5,-3.5,z+1.27,51,5.1,2.54,'0.045 0.045 0.055')
for i in range(20):
    for y in [2.23,4.77]:pi+=box(8.38+i*2.54,-y,z+5,.64,.64,6,'0.75 0.6 0.25')
for level in range(RISER_COUNT):
    base=z+2.54+level*RISER_BODY
    pi+=box(32.51,-3.5,base+RISER_BODY/2,51.31,4.95,RISER_BODY,'0.08 0.085 0.095')
    for i in range(20):
        for y in [2.23,4.77]:pi+=box(8.38+i*2.54,-y,base+RISER_BODY+4.93/2,.64,.64,4.93,'0.75 0.6 0.25')
pi+=box(31,-28,z+1.4,15,15,2.8,'0.16 0.17 0.18')
# Pi 4 Case Fan kit's 18 x 18 x 10 mm heatsink only; fan not installed.
# Allow 0.5 mm adhesive thickness in the conservative envelope.
pi+=box(31,-28,z+2.8+.5+5,18,18,10,'0.27 0.29 0.32')
pi+=box(50,-31,z+.7,11,14,1.4,'0.055 0.06 0.07')
# Approximate connector clearance envelopes, not certified vendor geometry.
for x,y,w,d,h in [(76,-10.5,21,16,15.5),(76,-29,21,15,16),(76,-47,21,15,16),(11,-54,9,6,3.2),(26,-54,7,6,3),(39,-54,7,6,3)]:
    pi+=box(x,y,z+h/2,w,d,h,'0.6 0.64 0.67')
for x,y in [(3.5,3.5),(61.5,3.5),(3.5,52.5),(61.5,52.5)]:
    pi+=cylinder(x,-y,(z-1.6)/2,2.4,PI_GAP,'0.69 0.7 0.72')
for x,y in [(12,11),(20,42),(45,15),(57,43),(62,20)]:pi+=box(x,-y,z+.5,4,3,1,'0.12 0.13 0.14')
write('Pi4_stack_concept',pi);add(b,'MODEL_PI4','${KIPRJMOD}/../../../shared/models/Pi4_stack_concept.wrl',(50,50))
save_board(str(F/'pi-trenz-stack-concept.kicad_pcb'),b)
# Separate service-envelope view: bounding volumes, not exact mated solids.
# The ordinary stack remains uncluttered and does not imply flex fit approval.
# Conservative plug envelope starts at the header mouth; no insertion overlap
# is credited without a supplier mated solid. Cables leave toward board +Y.
service=box(14.19,-(58.9+16.1/2),11.1/2,12.22,16.1,11.1,'0.12 0.5 0.23')
service+=box(95,14.6,6.5,12,30,12,'0.16 0.18 0.22')
write('DAQHAT_01_service_envelopes',service)
add(b,'MODEL_SERVICE','${KIPRJMOD}/../../../shared/models/DAQHAT_01_service_envelopes.wrl',(50,50))
save_board(str(F/'stack-service-envelopes.kicad_pcb'),b)
for fp in list(b.GetFootprints()):
    if fp.GetReference() in ('MODEL_SERVICE',):b.Delete(fp)
# Exploded view separates assemblies; spacer bodies are hidden intentionally.
for fp in list(b.GetFootprints()):
    if fp.GetReference()=='MODEL_TE0712':model(fp,'${KIPRJMOD}/../../../shared/models/trenz/STP-TE0712-03-No Variations.step',(0,0,27.6099917))
    elif fp.GetReference()=='MODEL_PI4':model(fp,'${KIPRJMOD}/../../../shared/models/Pi4_stack_concept.wrl',(0,0,-20))
    elif fp.GetReference()=='MODEL_SPACERS':b.Delete(fp)
save_board(str(F/'stack-exploded.kicad_pcb'),b)
print('Models attached; actual HAT, mounted Trenz and conceptual Pi stack saved')
