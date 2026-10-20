"""Record DAQHAT-01 artifacts while checking preservation of the original circuits."""
from hardware_require import require as _require_hardware
from pathlib import Path
import hashlib,json,datetime
ROOT=Path(__file__).resolve().parents[2];path=ROOT/'docs/artifact-manifest.json';j=json.loads(path.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
protected=['hw/burrowlark-usb/elec/field_head.ato','hw/burrowlark-usb/layout/placement.json',
 'hw/burrowlark-usb/boards/groundlark-field-head/groundlark-field-head.kicad_pcb']
for name in protected:
    if name in j['sha256']:_require_hardware((sha(ROOT/name)==j['sha256'][name]), lambda: (name+' unexpectedly changed'))
files=[ROOT/'hw/ato.yaml',ROOT/'hw/groundlark-fpga-hat/layout/placement.json',ROOT/'hw/groundlark-fpga-hat/elec/hat_trenz.ato',ROOT/'hw/groundlark-fpga-hat/elec/trenz_parts.ato',ROOT/'docs/trenz-pin-map.json',ROOT/'docs/trenz-hat.md']
for pattern in ['hw/shared/libraries/Groundlark.pretty/*.kicad_mod','sw/pi/groundlark/*.py','sw/tests/*.py','sw/ui/assets/*','sw/ui/main.py','docs/geophone-input.md','hw/groundlark-fpga-hat/elec/geophone_parts.ato','hw/groundlark-fpga-hat/elec/host_link_parts.ato','hw/shared/elec/symbols/LINK*.kicad_sym','sw/fpga/rtl/*.sv','sw/fpga/tests/*.sv','sw/fpga/*.py','sw/fpga/*.xdc','sw/fpga/*.tcl','sw/fpga/verification/*','sw/tools/fpga.py','sw/pi/deploy/*.cfg','sw/pi/deploy/*.dts','docs/fpga-host-link*.md','hw/groundlark-fpga-hat/simulation/host-link/*','hw/shared/elec/symbols/GEO*.kicad_sym','hw/shared/elec/Connector_Phoenix_MC*.kicad_mod','hw/shared/elec/Package_SO__TSSOP*.kicad_mod','hw/shared/elec/Package_TO_SOT_SMD*.kicad_mod','docs/geophone-input.md','hw/groundlark-fpga-hat/simulation/geophone/*','hw/tools/*.py','hw/tests/*.py','docs/trenz-*.csv','hw/shared/elec/TZ_*.kicad_mod','hw/shared/elec/symbols/TZ*.kicad_sym','hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/*','hw/groundlark-fpga-hat/simulation/trenz/*','hw/shared/models/trenz/*','hw/shared/models/FFC_*.wrl','hw/shared/models/Pi4_stack_concept.wrl','environment/lab.py','docs/stack-assembly.md','docs/pre-fab-acquisition-stress.json','hw/groundlark-fpga-hat/simulation/geophone-review/*','hw/shared/models/DAQHAT_01_service_envelopes.wrl']:
    files.extend(p for p in ROOT.glob(pattern) if p.is_file() and p.suffix not in ['.log','.lck','.kicad_prl'])
j['sha256']={name:digest for name,digest in j['sha256'].items() if (ROOT/name).is_file()}
files.extend(ROOT/name for name in j['sha256'])
for p in files:j['sha256'][p.relative_to(ROOT).as_posix()]=sha(p)
j['trenz_update_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
validation=json.loads((ROOT/'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/validation.json').read_text())
_require_hardware((all(validation[k]==0 for k in ['drc_violations','unconnected_items','erc_violations'])), lambda: ('Cannot record a passing board before native checks close'))
j['trenz_status']='DAQHAT-01 Pi-outline 6-layer through-via prototype; internal SPI6/QSPI reservation, UART and switched JTAG; native CAD, loopback RTL and portable checks; physical qualification pending'
path.write_text(json.dumps(j,indent=2)+'\n',encoding='utf-8',newline='\n');print('DAQHAT-01 artifacts recorded; USB head circuit/layout hashes preserved')
