"""Widen routed power tracks where native KiCad DRC permits, retaining neck-downs.

This is geometric cleanup, not an ampacity or voltage-drop signoff. Each trial
uses real DRC; every implicated trial segment returns to its previous width.
"""
from hardware_require import require as _require_hardware
from pathlib import Path
from project_paths import board_dir
import json,subprocess,collections,sys
from kicad_support import save_board
import pcbnew as p
ROOT=Path(__file__).resolve().parents[2]
power={'PI_5V','PI_3V3','SENS_3V3','USB_VBUS','USB_5V','V3_SENSOR','V3','FPGA_VIN','FPGA_3V3','EXT_3V3','EXT_12V','FUSED_12V','PROTECTED_12V'}
if 'skylark-usb' in sys.argv: power |= {'PM_5V','VA'}
for name in sys.argv[1:] or ['groundlark-field-head']:
    folder=board_dir(name);path=folder/(name+'.kicad_pcb')
    b=p.LoadBoard(str(path));trials={}
    for width in ([1.2,.8,.6,.4,.3,.25,.2] if name=='groundlark-daqhat-01' else [.4,.3,.25,.2]):
        changed={}
        for t in b.GetTracks():
            if t.GetClass()=='PCB_TRACK' and t.GetNetname() in power and t.GetWidth()<p.FromMM(width):
                changed[t.m_Uuid.AsString()]=(t,t.GetWidth());t.SetWidth(p.FromMM(width))
        reverted=set()
        # KiCad caps large violation lists. Recheck after each rollback until
        # every remaining trial is clean, including freshly filled zone copper.
        while True:
            p.ZONE_FILLER(b).Fill(b.Zones());save_board(str(path),b)
            out=ROOT/'hw/logs'/f'widen-{name}-{width}.json'
            subprocess.run(['kicad-cli','pcb','drc','--format','json','-o',str(out),str(path)],check=True,stdout=subprocess.DEVNULL)
            report=json.loads(out.read_text())
            if not report['violations'] and not report['unconnected_items']:break
            undo=set()
            for violation in report['violations']+report['unconnected_items']:
                for item in violation['items']:
                    key=item['uuid']
                    if key in changed and key not in reverted:undo.add(key)
            _require_hardware((undo), lambda: ('DRC failure is unrelated to remaining width trials; inspect saved report'))
            for key in undo:
                t,old=changed[key];t.SetWidth(old)
            reverted.update(undo)
        trials[str(width)]={'attempted':len(changed),'retained':len(changed)-len(reverted)}
    p.ZONE_FILLER(b).Fill(b.Zones());save_board(str(path),b)
    lengths=collections.defaultdict(float)
    for t in b.GetTracks():
        if t.GetClass()=='PCB_TRACK' and t.GetNetname() in power:lengths[(t.GetNetname(),round(p.ToMM(t.GetWidth()),3))]+=p.ToMM(t.GetLength())
    report={'trial_counts':trials,'track_length_mm':[{'net':net,'width_mm':w,'length_mm':round(l,3)} for (net,w),l in sorted(lengths.items())],'scope':'Width cleanup checked by DRC; not current/thermal signoff'}
    (folder/'power-widths.json').write_text(json.dumps(report,indent=2));print(name,trials)
    project=folder/(name+'.kicad_pro');data=json.loads(project.read_text());settings=data['net_settings']
    settings['classes']=[x for x in settings['classes'] if x['name']!='Power']
    rule=dict(settings['classes'][0]);rule.update(name='Power',track_width=.4);settings['classes'].append(rule)
    settings['netclass_patterns']=[{'netclass':'Power','pattern':net} for net in sorted(power) if net in b.GetNetsByName()]
    project.write_text(json.dumps(data,indent=2))
