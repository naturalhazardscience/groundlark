"""Independent CAD consistency checks and genuine KiCad PCB DRC.

This does not perform analog simulation, SI/PI signoff or bench validation.
"""
from pathlib import Path
from project_paths import board_dir, compiled_dir
from burrowlark_checks import population, array_pins, array_geometry, array_layout
from collections import Counter
import argparse,json,subprocess,xml.etree.ElementTree as ET
import pcbnew as pcb

ROOT=Path(__file__).resolve().parents[2]
def main(boards=('groundlark-field-head',)):
    board_failures=[]
    for folder in map(board_dir, boards):
        name=folder.name
        subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(folder/'schematic-netlist.xml'),str(folder/(name+'.kicad_sch'))],check=True)
        tree=ET.parse(folder/'schematic-netlist.xml')
        expected=json.loads((folder/'electrical.json').read_text())
        sch={}
        for net in tree.findall('.//nets/net'):
            for node in net.findall('node'): sch[(node.get('ref'),node.get('pin'))]=net.get('name')
        board=pcb.LoadBoard(str(folder/(name+'.kicad_pcb')))
        actual={(fp.GetReference(),pad.GetNumber()):pad.GetNetname() for fp in board.GetFootprints() for pad in fp.Pads() if pad.GetNumber()}
        array_pins(actual)
        array_geometry({f.GetReference():dict(xy=[pcb.ToMM(f.GetPosition().x)-50,pcb.ToMM(f.GetPosition().y)-50],angle=f.GetOrientationDegrees(),side='back' if f.IsFlipped() else 'front') for f in board.GetFootprints()}, [round(pcb.ToMM(board.GetBoardEdgesBoundingBox().GetWidth())),round(pcb.ToMM(board.GetBoardEdgesBoundingBox().GetHeight()))])
        degree=Counter(actual.values())
        target='field_head'
        compiled=pcb.LoadBoard(str(compiled_dir(target)/(target+'.kicad_pcb')))
        if target=='field_head':
            for refs in (
                (f.GetReference() for f in board.GetFootprints()),
                (f.GetReference() for f in compiled.GetFootprints()),
                (part['ref'] for part in expected['parts']),
                (node.get('ref') for node in tree.findall('.//components/comp')),
            ):
                population(refs)
        compiler_pins={(fp.GetReference(),pad.GetNumber()):pad.GetNetname() for fp in compiled.GetFootprints() for pad in fp.Pads() if pad.GetNumber()}
        failures=[];checks=0
        for key,net in compiler_pins.items():
            if actual.get(key)!=net:failures.append(f'Atopile/PCB mismatch {key}: {actual.get(key)} != {net}')
        for part in expected['parts']:
            for num,net in part['pins'].items():
                key=part['ref'],num;checks+=1
                if net:
                    if actual.get(key)!=net: failures.append(f'PCB {key}: {actual.get(key)} != {net}')
                    if sch.get(key)!=net: failures.append(f'SCH {key}: {sch.get(key)} != {net}')
                elif degree[actual.get(key,'')]>1: failures.append(f'NC connected {key}')
        subprocess.run(['kicad-cli','pcb','drc','--format','json','-o',str(folder/'drc.json'),str(folder/(name+'.kicad_pcb'))],check=True)
        subprocess.run(['kicad-cli','sch','erc','--format','json','-o',str(folder/'erc.json'),str(folder/(name+'.kicad_sch'))],check=True)
        drc=json.loads((folder/'drc.json').read_text());erc=json.loads((folder/'erc.json').read_text())
        findings=drc['violations']+drc['unconnected_items'];erc_findings=[x for sheet in erc['sheets'] for x in sheet['violations']]
        types=Counter(x['type'] for x in findings)
        errors=[x for x in findings if x['severity']=='error']
        result={'pin_checks':checks,'atopile_pin_checks':len(compiler_pins),'connectivity_errors':failures,'drc_findings_by_type':dict(types),'drc_errors':len(errors),'erc_findings':len(erc_findings),'unconnected_items':len(drc['unconnected_items']),'tracks_and_vias':len(board.GetTracks()),'status':'B1 PROTOTYPE - NOT FABRICATION RELEASED','limits':['Prototype USB sensor firmware is implemented; physical enumeration, suspend and USB signal integrity are unvalidated','No bench, magnetic-noise, RF impedance, EMC or mechanical stack validation','SPICE models are supporting-circuit behavioral/passive models, not full sensor silicon models']}
        result['array_layout']=array_layout(board)
        (folder/'validation.json').write_text(json.dumps(result,indent=2))
        print(name,json.dumps(result,indent=2))
        if failures or errors or erc_findings:board_failures.append({'board':name,'connectivity':failures,'drc':dict(types),'erc':len(erc_findings)})
    if board_failures:raise AssertionError(board_failures)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board',choices=('groundlark-field-head',))
    args=parser.parse_args()
    main((args.board,) if args.board else ('groundlark-field-head',))
