"""Independent circuit invariants against the actual atopile-compiled PCB."""
from pathlib import Path
from project_paths import compiled_dir, load_layout
from burrowlark_checks import population, array_pins, array_geometry
import argparse,json,re
import pcbnew as p
ROOT=Path(__file__).resolve().parents[2]
def require(pins,ref,expected):
    for pin,net in expected.items():
        assert pins.get((ref,str(pin)))==net,(ref,pin,pins.get((ref,str(pin))),net)
def main(boards=('groundlark-field-head',)):
    metadata=load_layout(*boards);source=(ROOT/'hw/shared/elec/parts.ato').read_text() + '\n' + (ROOT/'hw/shared/elec/burrowlark.ato').read_text()
    blocks={m[1]:m[2] for m in re.finditer(r'^component (\w+):\n(.*?)(?=^component |\Z)',source,re.M|re.S)}
    reports=[]
    for name,meta in metadata.items():
        target='field_head';b=p.LoadBoard(str(compiled_dir(target)/(target+'.kicad_pcb')))
        pins={(f.GetReference(),pad.GetNumber()):pad.GetNetname() for f in b.GetFootprints() for pad in f.Pads() if pad.GetNumber()}
        for part in meta['parts']:
            if not part['type']:continue
            block=blocks[part['type']]
            assert f'partnumber="{part["mpn"]}"' in block,(part['ref'],'BOM/source MPN mismatch')
            assert f'footprint="{part["local_fp"]}.kicad_mod"' in block,(part['ref'],'BOM/source footprint mismatch')
        array_pins(pins)
        array_geometry({part['ref']:part for part in meta['parts']}, meta['size'])
        population(f.GetReference() for f in b.GetFootprints())
        population(part['ref'] for part in meta['parts'])
        require(pins,'U1',{1:'V3',5:'V3',16:'GND',17:'V3',32:'GND',4:'NRST',6:'SENSOR_EN',21:'USB_DM',22:'USB_DP',23:'SWDIO',24:'SWCLK',29:'SCL',30:'SDA',31:'BOOT0'})
        require(pins,'J1',{'A5':'USB_CC1','B5':'USB_CC2','A6':'USB_DP','B6':'USB_DP','A7':'USB_DM','B7':'USB_DM','A4':'USB_VBUS','A9':'USB_VBUS','B4':'USB_VBUS','B9':'USB_VBUS','A1':'GND','A12':'GND','B1':'GND','B12':'GND','S1':'GND'})
        require(pins,'R1',{1:'USB_CC1',2:'GND'});require(pins,'R2',{1:'USB_CC2',2:'GND'})
        require(pins,'F1',{1:'USB_VBUS',2:'USB_5V'})
        require(pins,'U4',{1:'USB_5V',2:'GND',3:'USB_5V',5:'V3'})
        require(pins,'U5',{1:'V3',2:'GND',3:'SENSOR_EN',5:'V3_SENSOR',6:'V3_SENSOR'})
        require(pins,'R5',{1:'SENSOR_EN',2:'GND'})
        require(pins,'C1',{1:'USB_5V',2:'GND'})
        require(pins,'C8',{1:'NRST',2:'GND'})
        for n in [2,3,6,7,9]:require(pins,f'C{n}',{1:'V3',2:'GND'})
        require(pins,'C4',{1:'V3_SENSOR',2:'GND'})
        from burrowlark_checks import climate_pins
        climate_pins(pins)
        reports.append({'board':name,'compiled_pins':len(pins),'source_bom_agreement':'PASS','circuit_invariants':'PASS'})
    result={'boards':reports,'negative_mutations':[]}
    (ROOT/'hw/shared/simulation/circuit-checks.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board',choices=('groundlark-field-head',))
    args=parser.parse_args()
    main((args.board,) if args.board else ('groundlark-field-head',))
