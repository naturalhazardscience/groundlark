"""Bounded switch truth-table and lumped RC checks, not TI transistor models."""
from hardware_require import require as _require_hardware
from pathlib import Path
import itertools
import json
import re
import subprocess

OUT=Path(__file__).resolve().parents[1]/'groundlark-fpga-hat/simulation/host-link'
OUT.mkdir(parents=True,exist_ok=True)
results=[]

def run(name,body):
    path=OUT/(name+'.cir')
    path.write_text('DAQHAT-01 internal link: '+name+'\n'+body+'\n.end\n')
    r=subprocess.run(['ngspice','-b',str(path)],capture_output=True,text=True,timeout=30)
    log=r.stdout+r.stderr
    (OUT/(name+'.log')).write_text(log)
    _require_hardware((r.returncode==0), lambda: (log))
    return {k:float(v) for k,v in re.findall(r'^([a-z][a-z0-9_]*)\s*=\s*([-+0-9.eE]+)',log,re.M)}

# Truth table at valid rail endpoints. The 3.0 V supervisor release and 200 ms
# delay are abstracted to settled GOOD states; no brownout-ramp guarantee.
for pi,fpga,request,arm,select in itertools.product((0,1),repeat=5):
    name=f'power_{pi}{fpga}_request_{request}_arm_{arm}_jtag_{select}'
    enabled=bool(pi and fpga and request and arm)
    m=run(name,f'''Vpi pi 0 {3.3*pi}
Vfpga fpga 0 {3.3*fpga}
Vrequest request 0 {3.3*request*pi}
Varm arm 0 {3.3*arm*pi}
Vselect select 0 {3.3*select*pi}
Vsignal signal 0 3.3
Bapp appctrl 0 V=(v(pi)>3 && v(fpga)>3 && v(request)>2 && v(arm)>2 && v(select)<1) ? 1 : 0
Bjtag jtagctrl 0 V=(v(pi)>3 && v(fpga)>3 && v(request)>2 && v(arm)>2 && v(select)>2) ? 1 : 0
Sapp signal app appctrl 0 LINK
Sjtag signal jtag jtagctrl 0 LINK
.model LINK SW(Ron=10 Roff=1e12 Vt=.5 Vh=0)
Rapp app 0 100k
Rjtag jtag 0 100k
.tran 1u 10u
.measure tran app FIND v(app) AT=9u
.measure tran jtag FIND v(jtag) AT=9u''')
    _require_hardware(((m['app']>3.2)==(enabled and not select)), lambda: (m))
    _require_hardware(((m['jtag']>3.2)==(enabled and bool(select))), lambda: (m))
    if not enabled:_require_hardware((max(m.values())<.001), lambda: (m))
    results.append(dict(case=name,measured=m,passed=True))

for direction,driver in [('pi_to_fpga',25),('fpga_to_pi',40)]:
    for load in (25,100,200):
        name=f'{direction}_{load}pf'
        m=run(name,f'''Vdrive source 0 PULSE(0 3.201 100n 5n 5n 500n 1u)
Rdriver source damp {driver}
Rseries damp sw 22
Rswitch sw receiver 10
Cload receiver 0 {load}p
.tran .5n 900n
.measure tran rise TRIG v(receiver) VAL=.9603 RISE=1 TARG v(receiver) VAL=2.2407 RISE=1
.measure tran sample FIND v(receiver) AT=350n''')
        _require_hardware((m['rise']<50e-9 and m['sample']>2.31), lambda: (m))
        results.append(dict(case=name,measured=m,passed=True))

(OUT/'results.json').write_text(json.dumps(dict(cases=results,scope=
    '32 settled rail/arm/request/mode cases and six lumped RC cases. Ideal behavioral '
    'switch logic, conservative 10-ohm on resistance, 22-ohm damping, 25/40-ohm '
    'drivers and 25-200 pF load. No transistor-level power-ramp, supervisor delay '
    'tolerance, PCB extraction, ringing, crosstalk or clock-rate qualification.'),indent=2)+'\n')
print('PASS:',len(results),'bounded internal-link support cases')
