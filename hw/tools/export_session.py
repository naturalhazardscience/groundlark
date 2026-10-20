"""Record all native copper, including HDI microvias, for lossless project replay.

This restricted SES snapshot is consumed by import_routes.py. The native KiCad
board remains authoritative; this is not an autorouter or a fabrication export.
"""
from hardware_require import require as _require_hardware
from pathlib import Path
from project_paths import board_dir
import sys,collections
import pcbnew as p
import sexpdata as sx
ROOT=Path(__file__).resolve().parents[2]
S=sx.Symbol

def main(name):
    folder=board_dir(name);b=p.LoadBoard(str(folder/(name+'.kicad_pcb')))
    ordered=[p.F_Cu,*[b.GetLayerID(f'In{i}.Cu') for i in range(1,b.GetCopperLayerCount()-1)],p.B_Cu]
    placement=[S('placement'),[S('resolution'),S('um'),1000]]
    for f in sorted(b.GetFootprints(),key=lambda f:f.GetReference()):
        q=f.GetPosition();placement.append([S('component'),str(f.GetFPID().GetLibNickname())+':'+str(f.GetFPID().GetLibItemName()),[S('place'),f.GetReference(),q.x,-q.y,S('back' if f.IsFlipped() else 'front'),f.GetOrientationDegrees()]])
    nets=collections.defaultdict(list);stacks={}
    for t in b.GetTracks():
        kind=[S('type'),S('protect' if t.IsLocked() else 'route')]
        if isinstance(t,p.PCB_VIA):
            top,bottom=t.TopLayer(),t.BottomLayer();a,z=ordered.index(top),ordered.index(bottom)
            micro=t.GetViaType()==p.VIATYPE_MICROVIA
            _require_hardware((micro or t.GetViaType()==p.VIATYPE_THROUGH), lambda: ('Unsupported blind/buried via'))
            width=t.GetWidth(top);drill=t.GetDrillValue();_require_hardware((width%1000==drill%1000==0), lambda: ('export_session.py:27: hardware validation condition'))
            via=f'{"MicroVia" if micro else "Via"}[{a}-{z}]_{width//1000}:{drill//1000}_um'
            q=t.GetPosition();record=[S('via'),via,q.x,-q.y,kind]
            if t.GetIsFree():record.append([S('free'),S('yes')])
            nets[t.GetNetname()].append(record)
            stacks[via]=[S('padstack'),via,*[[S('shape'),[S('circle'),b.GetLayerName(layer),width]] for layer in ordered[a:z+1]],[S('attach'),S('off')]]
        else:
            _require_hardware((t.GetClass()=='PCB_TRACK'), lambda: ('Arc snapshot support must be implemented explicitly'))
            a,z=t.GetStart(),t.GetEnd();nets[t.GetNetname()].append([S('wire'),[S('path'),b.GetLayerName(t.GetLayer()),t.GetWidth(),a.x,-a.y,z.x,-z.y],kind])
    routes=[S('routes'),[S('resolution'),S('um'),1000],[S('library_out'),*stacks.values()],[S('network_out'),*[[S('net'),net,*nets[net]] for net in sorted(nets)]]]
    session=[S('session'),name+'.native-full',[S('base_design'),name],placement,routes]
    (folder/(name+'.ses')).write_text(sx.dumps(session)+'\n')
    print('Recorded complete native copper:',name,len(b.GetTracks()),'tracks/vias')

if __name__=='__main__':main(sys.argv[1])

