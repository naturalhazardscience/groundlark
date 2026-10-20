"""Rebuild native DAQHAT-01 copper from authored placement + complete SES in a temp tree."""
from hardware_require import require as _require_hardware
from pathlib import Path
from project_paths import board_dir
import collections
import json
import shutil
import subprocess
import sys
import tempfile
import pcbnew as p

ROOT=Path(__file__).resolve().parents[2]
NAME='groundlark-daqhat-01'
FOLDER=board_dir(NAME)

def copper(board):
    records=[]
    for t in board.GetTracks():
        if isinstance(t,p.PCB_VIA):
            q=t.GetPosition()
            records.append(('via',t.GetNetname(),q.x,q.y,t.GetWidth(t.TopLayer()),
                            t.GetDrillValue(),t.GetViaType(),t.TopLayer(),t.BottomLayer(),t.IsLocked(),t.GetIsFree()))
        else:
            a,z=t.GetStart(),t.GetEnd()
            records.append(('track',t.GetNetname(),t.GetLayer(),t.GetWidth(),
                            *sorted([(a.x,a.y),(z.x,z.y)]),t.IsLocked()))
    return collections.Counter(records)

def main():
    with tempfile.TemporaryDirectory(prefix='groundlark-replay-') as tmp:
        dst=Path(tmp)
        for folder in ['hw/tools','hw/shared/elec','hw/shared/libraries','hw/groundlark-fpga-hat/layout/trenz_hat']:
            shutil.copytree(ROOT/folder,dst/folder)
        f=board_dir(NAME, dst);f.mkdir(parents=True)
        (dst/'hw/logs').mkdir()
        shutil.copy2(ROOT/'hw/groundlark-fpga-hat/layout/placement.json',dst/'hw/groundlark-fpga-hat/layout/placement.json')
        shutil.copy2(FOLDER/(NAME+'.ses'),f/(NAME+'.ses'))
        for args in [['assemble_pcb.py','--trenz'],['import_routes.py',NAME],['trenz_power.py']]:
            subprocess.run([sys.executable,str(dst/'hw/tools'/args[0]),*args[1:]],check=True)
        subprocess.run(['kicad-cli','pcb','drc','--format','json','-o',str(f/'replay-drc.json'),
                        str(f/(NAME+'.kicad_pcb'))],check=True)
        drc=json.loads((f/'replay-drc.json').read_text())
        a=copper(p.LoadBoard(str(FOLDER/(NAME+'.kicad_pcb'))))
        b=copper(p.LoadBoard(str(f/(NAME+'.kicad_pcb'))))
        report=dict(tracks_and_vias=sum(a.values()),copper_identical=a==b,
                    drc_violations=len(drc['violations']),unconnected_items=len(drc['unconnected_items']))
        (FOLDER/'replay.json').write_text(json.dumps(report,indent=2)+'\n')
        print(report)
        for row in drc['violations']:print(row['type'],[(i['description'],i.get('pos')) for i in row['items']])
        _require_hardware((a==b and not drc['violations'] and not drc['unconnected_items']), lambda: (report))

if __name__=='__main__':main()
