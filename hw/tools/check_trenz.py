"""Independent Trenz carrier pin/geometry checks plus KiCad DRC/ERC.

Critical module pin fixture is transcribed from vendor revision-03 schematic
page 6 and mechanical drawing, independently of the atopile authoring script.
"""
from pathlib import Path
from collections import Counter
import csv,json,subprocess,xml.etree.ElementTree as ET
import pcbnew as p
from gpio_audit import check as check_gpio
ROOT=Path(__file__).resolve().parents[2];F=ROOT/'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01';N=F.name
board=p.LoadBoard(str(F/(N+'.kicad_pcb')));compiled=p.LoadBoard(str(ROOT/'hw/groundlark-fpga-hat/layout/trenz_hat/trenz_hat.kicad_pcb'))
def pins(b):
    result={}
    for f in b.GetFootprints():
        for q in f.Pads():
            if not q.GetNumber():continue
            key=(f.GetReference(),q.GetNumber());net=q.GetNetname()
            assert key not in result or result[key]==net,('Inconsistent repeated pad number',key)
            result[key]=net
    return result
bp,cp=pins(board),pins(compiled);assert all(bp.get(k)==n for k,n in cp.items()),'Compiled circuit changed during layout'
fixture={
 'J80':{1:'FPGA_VIN',3:'FPGA_VIN',5:'FPGA_VIN',13:'FPGA_VIN',15:'FPGA_VIN',9:'FPGA_3V3',11:'FPGA_3V3',14:'FPGA_3V3',28:'FPGA_EN1',89:'FPGA_JTAGEN'},
 'J81':{2:'FPGA_VIN',4:'FPGA_VIN',6:'FPGA_VIN',8:'FPGA_VIN',1:'FPGA_3V3',3:'FPGA_3V3',7:'FPGA_3V3',9:'FPGA_3V3',10:'FPGA_3V3',12:'FPGA_3V3',91:'FPGA_3V3',11:'FPGA_UART_RX',13:'FPGA_UART_TX',14:'FPGA_RESET_N',18:'FPGA_CONFIG_RESET_N',93:'JTAG_TMS',95:'JTAG_TDI',97:'JTAG_TDO',99:'JTAG_TCK'}}
gpio_report=check_gpio(bp)
check_gpio(cp)
spec=json.loads((ROOT/'hw/groundlark-fpga-hat/layout/placement.json').read_text())[N]
from host_link_checks import verify_parts
with (F/'bom.csv').open(newline='',encoding='utf8') as stream:
    gpio_report['host_link_component_checks']=verify_parts(spec,list(csv.DictReader(stream)),board)
assert board.GetCopperLayerCount()==spec['copper_layers']==6
assert abs(p.ToMM(board.GetDesignSettings().GetBoardThickness())-1.6)<1e-6
planes={board.GetLayerName(z.GetLayer()) for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND'}
assert planes=={'F.Cu','In1.Cu','In4.Cu'} and set(spec['ground_layers'])=={'In1.Cu','In4.Cu'}
microvias=[t for t in board.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetViaType()==p.VIATYPE_MICROVIA]
from fabrication_audit import inspect
process=inspect(F/(N+'.kicad_pcb'))
assert not process['standard_process_issues'],process['standard_process_issues']
(F/'fabrication-audit.json').write_text(json.dumps(process,indent=2)+'\n')
checks=0
for ref,m in fixture.items():
    for modulepin,net in m.items():
        carrierpin=modulepin+1 if modulepin%2 else modulepin-1
        assert bp[(ref,str(carrierpin))]==net,(ref,modulepin,net);checks+=1
for pin,net in {1:'PI_3V3',2:'PI_5V',4:'PI_5V',8:'PI_UART_TX',10:'PI_UART_RX',11:'FPGA_RESET_GPIO',22:'FPGA_IO_ENABLE'}.items():assert bp[('J1',str(pin))]==net
assert bp[('U51','3')]=='PI_3V3' and bp[('U51','7')]=='FPGA_3V3'
assert bp[('R62','1')]=='FPGA_IO_ENABLE' and bp[('R62','2')]=='GND'
from fpga_power_checks import verify_board
gpio_report['fpga_power']=verify_board(board,spec)
from pi_power_checks import verify_board as verify_pi_power
gpio_report['pi_power']=verify_pi_power(board,spec)
from calibration_checks import verify_board as verify_calibration
gpio_report['calibration']=verify_calibration(board)
from gnss_checks import verify_board as verify_gnss
gpio_report['gnss']=verify_gnss(board)
assert len({'PI_5V','PI_3V3','EXT_12V','FPGA_VIN','FPGA_3V3'} & set(bp.values()))==5
from sensor_pin_checks import verify as verify_sensor_pins
gpio_report['shared_sensor_pin_checks']=verify_sensor_pins(bp)
verify_sensor_pins(cp)
fps={f.GetReference():f for f in board.GetFootprints()}
from infrasound_checks import verify as verify_infrasound
pressure=next(part for part in spec['parts'] if part['ref']=='U23')
pressure_pads={}
for q in fps['U23'].Pads():
    if q.GetNumber():
        pressure_pads.setdefault(q.GetNumber(), []).append((p.ToMM(q.GetPosition().x)-50,p.ToMM(q.GetPosition().y)-50))
gpio_report['infrasound']=verify_infrasound(bp,
    pressure_pads,
    (fps['U23'].GetOrientationDegrees()%360,fps['U23'].IsFlipped()),pressure['mpn'],fps['U23'].IsDNP())
assert not fps['C24'].IsDNP() and fps['C24'].GetValue()=='100n'
assert fps['C24'].IsFlipped(), 'SDP32 bypass belongs beneath the supply escape'
from infrasound_checks import verify_mechanics
gpio_report['infrasound']['assembly_geometry']=verify_mechanics(board)
assert {ref for ref,fp in fps.items() if fp.GetValue()=='LSM6DSOTR'}=={'U11','U12','U13'}, 'Expected exactly three XYZ IMUs'
assert not {'U14','C18','C19','R14'} & fps.keys(), 'Fourth IMU circuitry remains'
assert bp[('U41','8')]==bp[('U41','9')]==bp[('U42','17')]=='GND', 'Unused buffer inputs must not float'
for key in [('U41','16'),('U42','7'),('U41','15')]:
    net=bp[key]
    assert sum(n==net for n in bp.values())==1, ('Removed sensor pin must be NC',key)
assert not {'U20','C20','C21','C22','C23','R20'} & fps.keys(), 'Inclinometer circuitry remains'
assert not any('TILT' in net for net in bp.values()), 'Inclinometer net remains'
assert not any('IMU4' in net for net in bp.values()), 'Removed IMU4 GPIO net remains'
# Bypass placement metadata must reproduce the reviewed native layout.
for meta in spec['parts']:
    if meta['ref'] not in {'C12','C13','C14','C15','C16','C17'}:continue
    fp=fps[meta['ref']];q=fp.GetPosition()
    assert abs(p.ToMM(q.x)-50-meta['xy'][0])<.001 and abs(p.ToMM(q.y)-50-meta['xy'][1])<.001,meta['ref']
    assert abs((fp.GetOrientationDegrees()-meta['angle']+180)%360-180)<.001,meta['ref']
pad_ids=[q.m_Uuid.AsString() for f in board.GetFootprints() for q in f.Pads()]
assert len(pad_ids)==len(set(pad_ids)),'Duplicate pad UUIDs corrupt KiCad report item references'
for ref,xy in {'J80':(55,44),'J81':(55,12),'J82':(34,28),'H80':(33,11),'H81':(77,11),'H82':(33,45),'H83':(77,45),'H1':(3.5,3.5),'H2':(61.5,3.5),'H3':(3.5,52.5),'H4':(61.5,52.5)}.items():
    q=fps[ref].GetPosition();assert abs(p.ToMM(q.x)-50-xy[0])<.001 and abs(p.ToMM(q.y)-50-xy[1])<.001,ref
for ref in [f'U{i}' for i in range(100,107)]:
    meta=next(item for item in spec['parts'] if item['ref']==ref)
    xy,angle=meta['xy'],meta['angle']
    f=fps[ref];q=f.GetPosition()
    assert f.IsFlipped() and f.GetLayer()==p.B_Cu,(ref,'must be underside')
    assert abs(p.ToMM(q.x)-50-xy[0])<.001 and abs(p.ToMM(q.y)-50-xy[1])<.001,ref
    assert (f.GetOrientationDegrees()-angle)%360<.001,ref
    # Internal link components stay inside the outline; DRC checks overlap.
    box=f.GetBoundingBox(False,False)
    assert box.GetLeft()>p.FromMM(50) and box.GetRight()<p.FromMM(135),ref
    assert box.GetTop()>p.FromMM(50) and box.GetBottom()<p.FromMM(106),ref
edge=board.GetBoardEdgesBoundingBox();assert abs(p.ToMM(edge.GetWidth())-140)<.1 and abs(p.ToMM(edge.GetHeight())-56)<.1
for num,xy in {'1':(8.38,4.77),'2':(8.38,2.23),'39':(56.64,4.77),'40':(56.64,2.23)}.items():
    q=next(q for q in fps['J1'].Pads() if q.GetNumber()==num).GetPosition()
    assert abs(p.ToMM(q.x)-50-xy[0])<.001 and abs(p.ToMM(q.y)-50-xy[1])<.001
subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(F/'schematic-netlist.xml'),str(F/(N+'.kicad_sch'))],check=True,stdout=subprocess.DEVNULL)
tree=ET.parse(F/'schematic-netlist.xml');sp={}
for net in tree.findall('.//nets/net'):
    for node in net.findall('node'):sp[(node.get('ref'),node.get('pin'))]=net.get('name')
degree=Counter(bp.values())
for k,n in bp.items():
    if degree[n]>1:assert sp.get(k)==n,(k,n,sp.get(k))
for kind,extension,check in [('pcb','kicad_pcb','drc'),('sch','kicad_sch','erc')]:
    subprocess.run(['kicad-cli',kind,check,'--format','json','-o',str(F/(check+'.json')),str(F/(N+'.'+extension))],check=True,stdout=subprocess.DEVNULL)
drc=json.loads((F/'drc.json').read_text());erc=json.loads((F/'erc.json').read_text())
er=[v for s in erc['sheets'] for v in s['violations']]
report={'status':'DAQHAT-01 engineering prototype; not fabrication released','outline_mm':[140,56],**gpio_report,'compiled_pin_checks':len(cp),'critical_module_pin_checks':checks,'drc_violations':len(drc['violations']),'unconnected_items':len(drc['unconnected_items']),'erc_violations':len(er),'tracks_and_vias':len(board.GetTracks()),'copper_layers':6,'microvias':len(microvias),'fabrication_process':'standard-six-layer-through-via','limits':['Stock six-layer stack includes epoxy-filled/capped through-vias; include ADC supply pad through-vias in fabrication notes','No FPGA bitstream port or hardware test performed','External regulated 3.3 V supply required; confirm 3.201â€“3.399 V at module under startup/load','Copper resistance, heating, sensor thermal drift, EMI and physical mating remain unqualified','Internal-link timing and signal integrity remain unqualified; see fpga-host-link.md','Pi rendering is conceptual; Trenz rendering uses vendor generic revision-03 STEP']}
report['limits'] = [
 'Fabrication process approval is owned by the project owner; stock JLC06161H-3313 is recorded; no controlled impedance is claimed',
 'Single Racotech geophone input; analog noise, cable coupling and ADC timing require physical qualification',
 'J83: 12 V +/-5% center-positive, 3 A adapter; U80 output allocation 3 A, output hot loop <=15 milliohms; measure startup/load/thermal behavior',
 'J130: 8-18 V protected battery/controller DC input; U130 TI supervisor and 3 A combined Pi/HAT supply; MCU firmware and battery policy qualification pending',
 'Pi4 conceptual stack uses Megastar J1 and two SSQ-120-02-G-D risers; selected cooler, cables and mating need physical fit verification',
 'Loopback bitstream built separately; no physical sensor/rail/thermal/EMI/high-speed GPIO tests performed',
 'Pi FIFO/IRQ and geophone polling are tested on modeled buses; GNSS/PPS capture is implemented; sample timing and RF performance require physical qualification',
 'Trenz rendering uses vendor generic revision-03 STEP']
(F/'validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
assert not drc['violations'] and not drc['unconnected_items'] and not er
