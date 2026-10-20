"""Read-only Skylark circuit/geometry invariants plus native KiCad DRC/ERC.

Expected pin functions below are independent manufacturer pin-map fixtures.
CAD checks do not establish gas detection limits or outdoor qualification.
"""
from hardware_require import require as _require_hardware
from pathlib import Path
import collections, json, math, subprocess, xml.etree.ElementTree as ET
import pcbnew as p
from skylark_analog import review as analog_review
from skylark_fabrication import review as fabrication_review, stackup as review_stackup
from project_paths import ROOT, board_dir, compiled_dir, load_layout

NAME='skylark-usb'
def pins(board):
    return {(f.GetReference(),x.GetNumber()):x.GetNetname() for f in board.GetFootprints() for x in f.Pads() if x.GetNumber()}

def review(board):
    actual=pins(board);fps={f.GetReference():f for f in board.GetFootprints()}
    def require(ref,mapping):
        for pin,net in mapping.items():_require_hardware((actual.get((ref,str(pin)))==net), lambda: ((ref,pin,net,actual.get((ref,str(pin))))))
    require('U1',{1:'V3',7:'NRST',8:'GND',9:'V3',10:'VBUS_SENSE',12:'UART_TX',13:'UART_RX',14:'PM_EN',15:'PM_FAULT_N',16:'PM_SLEEP',17:'PM_RESET',18:'ADC_DRDY_N',19:'ADC_RESET_N',23:'GND',24:'V3',25:'ANA_EN',26:'CLAMP_HOLD',32:'USB_DM',33:'USB_DP',34:'SWDIO',35:'GND',36:'V3',37:'SWCLK',39:'STATUS',42:'SCL',43:'SDA',44:'BOOT0',47:'GND',48:'V3'})
    require('U2',{1:'USB_5V',2:'GND',3:'USB_5V',5:'V3'})
    require('U3',{1:'USB_5V',2:'GND',3:'PM_EN',4:'PM_ILIM',5:'PM_FAULT_N',6:'PM_5V'})
    require('U13',{1:'V3',2:'GND',3:'ANA_EN',4:'ANA_CT',5:'VA_SW',6:'VA_SW'})
    require('Q7',{1:'CLAMP_BASE',2:'VZERO',3:'CLAMP_GATE'})
    require('R74',{1:'CLAMP_HOLD',2:'CLAMP_BASE'})
    require('D4',{1:'USB_5V',3:'GATE_SUPPLY'})
    require('R75',{1:'VZERO',2:'GUARD'})
    _require_hardware((fps['Q7'].GetValue()=='MMBT3904LT1G'), lambda: ('Reference-following clamp driver'))
    _require_hardware((fps['D4'].GetValue()=='BAT54LT1G'), lambda: ('Clamp supply isolation'))
    for ref in ('Q1','Q2','Q3','Q4'):_require_hardware((fps[ref].GetValue()=='MMBFJ270'), lambda: ('Low-leakage electrode clamp'))
    for ref,el in [(f'C{i}','WE' if i<84 else 'AE') for i in range(80,88)]:
        require(ref,{1:'H2S_'+el+'_SUM',2:'H2S_'+el+'_OUT'})
    require('R72',{1:'ANA_EN',2:'GND'});require('R73',{1:'V3',2:'CLAMP_HOLD'})
    require('C73',{1:'V3',2:'GND'});require('C74',{1:'ANA_CT',2:'GND'})
    require('U4',{1:'VA',2:'REF_2V5',3:'GND'})
    require('U5',{1:'VZERO',2:'GND',3:'VMID',4:'VZERO',5:'VA'})
    require('U6',{1:'GND',2:'GND',3:'ADC_RESET_N',4:'GND',5:'GND',6:'H2S_AE_ADC',7:'H2S_WE_ADC',8:'GND',9:'REF_2V5',10:'SO2_AE_ADC',11:'SO2_WE_ADC',12:'VA',13:'V3',14:'ADC_DRDY_N',15:'SDA',16:'SCL'})
    require('U11',{1:'SDA',2:'SCL',3:'V3',4:'GND'})
    require('U12',{1:'V3',2:'SCL',3:'GND',4:'SDA',5:'GND',6:'V3',8:'GND',9:'GND',10:'V3'})
    require('J1',{'A1B12':'GND','B1A12':'GND','S1':'GND','A4B9':'USB_VBUS','B4A9':'USB_VBUS','A5':'CC1','B5':'CC2','A6':'USB_DP','B6':'USB_DP','A7':'USB_DM','B7':'USB_DM'})
    require('D1',{1:'USB_DP',2:'GND',3:'USB_DM',4:'USB_DM',5:'USB_VBUS',6:'USB_DP'})
    require('D2',{1:'CC1',2:'GND',3:'CC2',4:'CC2',5:'USB_VBUS',6:'CC1'})
    require('J2',{1:'PM_5V',2:'GND',3:'PM_SET_N',4:'PM_RX',5:'PM_TX',6:'PM_RESET_N','MP':'GND'})
    require('J3',{1:'V3',2:'SWDIO',3:'GND',4:'SWCLK',5:'GND',9:'GND',10:'NRST'})
    require('Q5',{1:'PM_SLEEP',2:'GND',3:'PM_SET_N'});require('Q6',{1:'PM_RESET',2:'GND',3:'PM_RESET_N'})
    for ref,a,z in [('F1','USB_VBUS','USB_5V'),('R1','CC1','GND'),('R2','CC2','GND'),('R3','PM_ILIM','GND'),('R4','PM_EN','GND'),('R8','UART_TX','PM_RX'),('R9','PM_TX','UART_RX'),('R19','VA_SW','VA'),('R20','REF_2V5','VMID'),('R21','VMID','GND'),('R70','GATE_SUPPLY','CLAMP_GATE'),('R71','CLAMP_GATE','VZERO')]:require(ref,{1:a,2:z})
    for index,gas,base,gain in [(0,'SO2',30,100000),(1,'H2S',50,20000)]:
        cell=f'GS{index+1}';require(cell,{x:gas+'_'+x for x in ['WE','RE','CE','AE']})
        require(f'U{7+2*index}',{1:gas+'_WE_OUT',2:gas+'_WE_SUM',3:'VZERO',4:'GND',5:'VZERO',6:gas+'_AE_SUM',7:gas+'_AE_OUT',8:'VA'})
        require(f'U{8+2*index}',{1:gas+'_CE_DRV',2:'GND',3:'VZERO',4:gas+'_RE_FB',5:'VA'})
        for j,el in enumerate(['WE','AE']):
            require(f'Q{1+2*index+j}',{1:gas+'_'+el,2:gas+'_RE',3:'CLAMP_GATE'})
            require(f'R{base+3*j}',{1:gas+'_'+el,2:gas+'_'+el+'_SUM'})
            require(f'R{base+3*j+1}',{1:gas+'_'+el+'_SUM',2:gas+'_'+el+'_OUT'})
            require(f'C{base+3*j}',{1:gas+'_'+el+'_SUM',2:gas+'_'+el+'_OUT'})
            require(f'R{base+3*j+2}',{1:gas+'_'+el+'_OUT',2:gas+'_'+el+'_ADC'})
            require(f'C{base+3*j+1}',{1:gas+'_'+el+'_ADC',2:'GND'})
            _require_hardware((fps[f'R{base+3*j}'].GetValue()=='20R'), lambda: ('Electrode load'))
            _require_hardware((fps[f'R{base+3*j+1}'].GetValue()==f'{gain:g}R'), lambda: ('TIA gain'))
        require(f'R{base+6}',{1:gas+'_RE',2:gas+'_RE_FB'})
        require(f'R{base+7}',{1:gas+'_CE_DRV',2:gas+'_CE'})
        require(f'C{base+6}',{1:gas+'_CE_DRV',2:gas+'_RE_FB'})
        # Manufacturer drawing is a bottom view. Mirror X to obtain PCB top.
        f=fps[cell];_require_hardware((not f.IsFlipped()), lambda: ('Cells must face the hood air space'))
        for x in f.Pads():
            xy=x.GetPosition()-f.GetPosition();expected={'WE':(0,-8.5),'RE':(6.010408,-6.010408),'CE':(-6.010408,-6.010408),'AE':(0,8.5)}[x.GetNumber()]
            _require_hardware((math.dist((p.ToMM(xy.x),p.ToMM(xy.y)),expected)<.001), lambda: ('Gas socket pin geometry'))
            _require_hardware((abs(p.ToMM(x.GetDrillSize().x)-2.35)<.001), lambda: ('Socket hole'))
    degrees=collections.Counter(actual.values())
    nc={'D4':['2'],'J1':['A8','B8'],'J2':['7','8'],'J3':['6','7','8'],'U2':['4'],'U12':['7'],'U1':['2','3','4','5','6','11','20','21','22','27','28','29','30','31','38','40','41','45','46']}
    for ref,nums in nc.items():
        for num in nums:_require_hardware((degrees[actual[(ref,num)]]==1), lambda: (('Deliberate NC connected',ref,num)))
    for ref,value in [('R1','5100R'),('R2','5100R'),('R3','82000R'),('R70','10000R'),('R71','100000R'),('R74','10000R'),('R75','100R')]:_require_hardware((fps[ref].GetValue()==value), lambda: ((ref,value)))
    _require_hardware((len(fps)==132 and not any(f.IsDNP() for f in fps.values())), lambda: ('check_skylark.py:75: hardware validation condition'))
    _require_hardware((board.GetCopperLayerCount()==4), lambda: ('check_skylark.py:76: hardware validation condition'))
    # USB signal copper must remain on top, with no signal vias or long stub.
    usb={net:[t for t in board.GetTracks() if t.GetNetname()==net] for net in ['USB_DP','USB_DM']}
    lengths={}
    for net,items in usb.items():
        _require_hardware((items and all(t.GetClass()=='PCB_TRACK' and t.GetLayer()==p.F_Cu for t in items)), lambda: ('USB route layer/via'))
        lengths[net]=sum(p.ToMM(t.GetLength()) for t in items)
        _require_hardware((lengths[net]<22), lambda: ('USB excessive length/duplicate copper'))
    _require_hardware((abs(lengths['USB_DP']-lengths['USB_DM'])<2), lambda: ('USB branch length difference'))
    # Low heat conduction: no inner/bottom copper or vias on the sensor finger.
    for t in board.GetTracks():
        if any(p.ToMM(q.x)>131 and p.ToMM(q.y)>139 for q in (t.GetStart(),t.GetEnd())):
            _require_hardware((t.GetClass()=='PCB_TRACK' and t.GetLayer()==p.F_Cu), lambda: ('Thermal finger copper'))
    r=82.0
    limits={'min_mA':25230/(r*1.01)**1.016,'nominal_mA':23950/r**.977,'max_mA':22980/(r*.99)**.94}
    _require_hardware((limits['max_mA']+50<500), lambda: ('USB configured power budget'))
    return {'independent_pin_invariants':'passed','contacts':len(actual),'usb_total_copper_length_mm':lengths,'pms_current_limit':limits,'mechanical_mm':[90,100,1.6],'analog':analog_review(board),'construction':fabrication_review(board)}

def main():
    folder=board_dir(NAME);path=folder/(NAME+'.kicad_pcb');board=p.LoadBoard(str(path))
    result=review(board)
    result['construction'].update(review_stackup(path.read_text()))
    compiled=p.LoadBoard(str(compiled_dir('skylark')/'skylark.kicad_pcb'))
    _require_hardware((pins(compiled)==pins(board)), lambda: ('Compiled/native contacts differ'))
    spec=load_layout(NAME)[NAME];fps={f.GetReference():f for f in board.GetFootprints()}
    for part in spec['parts']:
        f=fps[part['ref']];xy=f.GetPosition()
        _require_hardware((math.dist((p.ToMM(xy.x)-50,p.ToMM(xy.y)-50),part['xy'])<.001), lambda: ('Placement metadata'))
        _require_hardware((abs((f.GetOrientationDegrees()-part['angle']+180)%360-180)<.001), lambda: ('Placement angle'))
        _require_hardware((f.GetValue()==part['value']), lambda: ('Native/placement value mismatch'))
    for mode,suffix,output in [('pcb','.kicad_pcb','drc'),('sch','.kicad_sch','erc')]:
        subprocess.run(['kicad-cli',mode,output,'--format','json','-o',str(folder/(output+'.json')),str(folder/(NAME+suffix))],check=True)
    drc=json.loads((folder/'drc.json').read_text());erc=json.loads((folder/'erc.json').read_text())
    errors=[x for x in drc['violations'] if x['severity']=='error']
    _require_hardware((not errors and not drc['unconnected_items']), lambda: ((errors,drc['unconnected_items'])))
    findings=[x for sheet in erc['sheets'] for x in sheet['violations']]
    _require_hardware((not findings), lambda: (findings))
    subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(folder/'schematic-netlist.xml'),str(folder/(NAME+'.kicad_sch'))],check=True)
    sch={(n.get('ref'),n.get('pin')):net.get('name') for net in ET.parse(folder/'schematic-netlist.xml').findall('.//nets/net') for n in net.findall('node')}
    actual=pins(board);degrees=collections.Counter(actual.values())
    for key,net in actual.items():
        if degrees[net]>1:_require_hardware((sch.get(key)==net), lambda: (('Review schematic',key,net,sch.get(key))))
    result.update(drc_errors=0,unconnected_items=0,erc_findings=0,drc_warnings=[x['type'] for x in drc['violations']],status='ENGINEERING PROTOTYPE; not fabrication released',limits=['Physical USB enumeration/suspend/eye testing pending','Gas bias must be confirmed for exact SGX AQ variants; noise, calibration and cross-sensitivity not qualified','Physical socket fit, retention, outdoor exposure and enclosure airflow untested','SGX specified pressure range starts at 800 mbar; high-altitude operation requires qualification'])
    (folder/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
