"""Bounded passive interface and DC input-budget checks; not FPGA simulation."""
from hardware_require import require as _require_hardware
from pathlib import Path
import subprocess,re,json,itertools
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'hw/groundlark-fpga-hat/simulation/trenz';OUT.mkdir(exist_ok=True)
from fpga_power_checks import budget
bounds=budget()
source_limits=[bounds["reference_and_divider_min_V"],bounds["reference_and_divider_max_V"]]
results=[]
def run(name,body):
    path=OUT/(name+'.cir');path.write_text('Groundlark Trenz support check: '+name+'\n'+body+'\n.end\n')
    r=subprocess.run(['ngspice','-b',str(path)],capture_output=True,text=True);log=r.stdout+r.stderr;(OUT/(name+'.log')).write_text(log)
    _require_hardware((r.returncode==0), lambda: (log))
    return {k:float(v) for k,v in re.findall(r'^([a-z][a-z0-9_]*)\s*=\s*([-+0-9.eE]+)',log,re.M)}
for vin,load in itertools.product(source_limits,[.1,1.5,3.0]):
    # Ideal source at U80 output using reference/divider corners. The 15 mOhm
    # budget includes output copper and module contacts/return, not 12 V wiring.
    m=run(f'dc_{vin}_{load}',f'Vsource src 0 {vin}\nRpath src module 0.015\nIload module 0 {load}\nCbulk module 0 26.4u\n.tran 1u 100u\n.measure tran vmodule FIND v(module) AT=99u')
    _require_hardware((3.201<=m['vmodule']<=3.399), lambda: (m))
    results.append(dict(case=f'dc_{vin}_{load}',measured=m,pass_check=True))
# Negative case: excessive wiring resistance must be recognized as unsafe.
m=run('reject_long_power_lead','Vsource src 0 3.267\nRpath src module 0.10\nIload module 0 3\n.tran 1u 100u\n.measure tran vmodule FIND v(module) AT=99u')
_require_hardware((m['vmodule']<3.201), lambda: ('simulate_trenz.py:22: hardware validation condition'));results.append(dict(case='reject_long_power_lead',measured=m,undervoltage_detected=True))
for cap in [25,100,200]:
    m=run(f'uart_{cap}pf',f'Vdrive src 0 PULSE(0 3.201 100n 5n 5n 500n 1u)\nRdriver src driver 25\nRseries driver rx 47\nCload rx 0 {cap}p\n.tran .5n 900n\n.measure tran rise TRIG v(rx) VAL=0.9603 RISE=1 TARG v(rx) VAL=2.2407 RISE=1\n.measure tran sample FIND v(rx) AT=350n')
    _require_hardware((m['rise']<50e-9 and m['sample']>2.31), lambda: (m))
    results.append(dict(case=f'uart_{cap}pf',measured=m,pass_check=True))
for vin,inductance in itertools.product(source_limits,[50,200]):
    m=run(f'load_step_{vin}_{inductance}n',f'''Vsource src 0 {vin}
Rpath src wire .015
Lpath wire module {inductance}n
Resr module cap .020
Cbulk cap 0 26.4u
Iload module 0 PULSE(.1 3 1m 100u 100u 1m 3m)
.tran .1u 4m
.measure tran vmin MIN v(module) FROM=.5m TO=4m
.measure tran vmax MAX v(module) FROM=.5m TO=4m''')
    _require_hardware((3.201 <= m['vmin'] and m['vmax'] <= 3.399), lambda: (m))
    results.append(dict(case=f'load_step_{vin}_{inductance}n',measured=m,pass_check=True))
(OUT/'results.json').write_text(json.dumps({'cases':results,'scope':'6 DC budgets, expected undervoltage rejection, 3 UART RC checks, 4 bounded 0.1-to-3 A / 100 us load steps with 50/200 nH loop inductance and 26.4 uF effective capacitance. Ideal converter-output source only. No regulator control loop, fast FPGA load edge, startup inrush or thermal qualification.'},indent=2));print('PASS:',len(results),'bounded support-circuit cases')
