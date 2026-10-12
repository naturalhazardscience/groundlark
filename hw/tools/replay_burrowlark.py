"""Read-only B1 native SES replay in a temporary checkout; never reroute authoring CAD."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import pcbnew as p
from project_paths import ROOT, board_dir
from replay_trenz import copper
from burrowlark_checks import array_geometry, array_pins, population


def main():
    name='groundlark-field-head';source=board_dir(name)
    with tempfile.TemporaryDirectory(prefix='burrowlark-replay-') as tmp:
        root=Path(tmp)
        for relative in ('hw/tools','hw/shared/elec','hw/shared/libraries','hw/burrowlark-usb/layout'):
            shutil.copytree(ROOT/relative,root/relative)
        dest=board_dir(name,root);dest.mkdir(parents=True)
        (root/'hw/logs').mkdir()
        shutil.copy2(source/(name+'.ses'),dest/(name+'.ses'))
        for script,args in (('assemble_pcb.py',[]),('import_routes.py',[name])):
            subprocess.run([sys.executable,str(root/'hw/tools'/script),*args],check=True)
        a=p.LoadBoard(str(source/(name+'.kicad_pcb')));b=p.LoadBoard(str(dest/(name+'.kicad_pcb')))
        population(f.GetReference() for f in b.GetFootprints())
        array_pins({(f.GetReference(),pad.GetNumber()):pad.GetNetname() for f in b.GetFootprints() for pad in f.Pads() if pad.GetNumber()})
        array_geometry({f.GetReference():dict(xy=[p.ToMM(f.GetPosition().x)-50,p.ToMM(f.GetPosition().y)-50],
            angle=f.GetOrientationDegrees(),side='back' if f.IsFlipped() else 'front') for f in b.GetFootprints()},(96,70))
        subprocess.run(['kicad-cli','pcb','drc','--format','json','-o',str(dest/'drc.json'),str(dest/(name+'.kicad_pcb'))],check=True)
        drc=json.loads((dest/'drc.json').read_text())
        report=dict(copper_identical=copper(a)==copper(b),tracks_and_vias=len(a.GetTracks()),
                    violations=len(drc['violations']),unconnected_items=len(drc['unconnected_items']),
                    scope='Native copper replay and geometry only; physical coherence/noise unqualified')
        (source/'replay.json').write_text(json.dumps(report,indent=2)+'\n')
        print(report)
        assert report['copper_identical'] and not report['violations'] and not report['unconnected_items'],report


if __name__=='__main__':main()
