"""Trim only KiCad-reported dangling copper, verifying connectivity after each pass."""
from hardware_require import require as _require_hardware
from pathlib import Path
from project_paths import board_dir
import subprocess,json,sys
from kicad_support import save_board
import pcbnew as p
ROOT=Path(__file__).resolve().parents[2]
for name in sys.argv[1:] or ['groundlark-field-head']:
    folder=board_dir(name);path=folder/(name+'.kicad_pcb');out=folder/'drc.json'
    for iteration in range(80):
        subprocess.run(['kicad-cli','pcb','drc','--format','json','-o',str(out),str(path)],check=True,stdout=subprocess.DEVNULL)
        r=json.loads(out.read_text())
        remove={i['uuid'] for v in r['violations'] if v['type'] in {'track_dangling','via_dangling'} for i in v['items']}
        # Removal of a connector can leave isolated branches. Only allow an
        # initial airwire whose two ends are themselves reported dangling.
        _require_hardware((all(all(i['description'].startswith(('Track [','Via [')) for i in v['items']) for v in r['unconnected_items'])), lambda: (r['unconnected_items']))
        if not remove:break
        b=p.LoadBoard(str(path));count=0
        for t in list(b.GetTracks()):
            if t.m_Uuid.AsString() in remove and not t.IsLocked():b.Delete(t);count+=1
        if not count:break
        p.ZONE_FILLER(b).Fill(b.Zones());save_board(str(path),b)
    print(name,'dangling trim passes',iteration)
    _require_hardware((not r['unconnected_items']), lambda: (r['unconnected_items']))
