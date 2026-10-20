"""Bounded input-pulse, overload-removal and bias startup SPICE checks.

ADC is not present in this model: recovery assertions concern passive nodes.
"""
from hardware_require import require as _require_hardware
from pathlib import Path
import itertools
import json
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def main():
    out=ROOT/'hw/groundlark-fpga-hat/simulation/geophone-review';out.mkdir(exist_ok=True)
    cases=[]
    for number,(rail,cap,amplitude) in enumerate(itertools.product((3.135,3.465),(8e-6,12e-6),(.002,.050))):
        deck=f'''Geophone passive startup and pulse recovery; no ADC overload model
Vsupply supply 0 PWL(0 0 1m {rail})
R96 supply avdd 22
Iadc avdd 0 500u
C94 avdd 0 {cap}
C95 avdd 0 100n
R94 avdd vcm 10.1k
R95 vcm 0 9.9k
C93 vcm 0 {cap}
Vcoil coilp coilm PULSE(0 {amplitude} .4 10u 10u .02 1)
Rcoil coilp leadp 414.75
R90 leadp ainp 1.01k
R91 coilm ainm .99k
R92 ainp vcm 1.01meg
R93 ainm vcm .99meg
C90 ainp ainm 105n
C91 ainp 0 1.05n
C92 ainm 0 .95n
Ileakp leadp 0 10n
Ileakn coilm 0 0
.control
tran 20u .5
let differential = v(ainp)-v(ainm)
let commonmode = (v(ainp)+v(ainm))/2
meas tran baseline FIND differential AT=.39
meas tran pulse FIND differential AT=.419
meas tran recovered FIND differential AT=.425
meas tran bias_start FIND commonmode AT=.3
meas tran bias_final FIND commonmode AT=.5
quit
.endc
.end
'''
        path=out/f'pulse-{number}.cir';path.write_text(deck)
        run=subprocess.run(['ngspice','-b',str(path)],capture_output=True,text=True)
        log=run.stdout+run.stderr;(out/f'pulse-{number}.log').write_text(log)
        if run.returncode:raise RuntimeError(log)
        values={key:float(value) for key,value in re.findall(r'^(baseline|pulse|recovered|bias_start|bias_final)\s*=\s*([-+0-9.eE]+)',log,re.M)}
        _require_hardware((len(values)==5), lambda: (log))
        _require_hardware((abs((values['pulse']-values['baseline'])/amplitude-1)<.003), lambda: (values))
        _require_hardware((abs(values['recovered']-values['baseline'])<.5e-6), lambda: (values))
        _require_hardware((values['bias_start']>.44 and values['bias_start']<rail-.44), lambda: (values))
        _require_hardware((abs(values['bias_start']-values['bias_final'])<.015), lambda: (values))
        cases.append(dict(rail_v=rail,bulk_cap_f=cap,pulse_v=amplitude,**values,passed=True))
    (out/'results.json').write_text(json.dumps(dict(cases=cases,
        scope='8 passive transient checks with asymmetric resistors/caps and leakage',
        limitations='No ADC clipping dynamics, sensor mechanics, PCB coupling or ESD pulse model'),indent=2)+'\n')
    print('PASS: 8 passive startup, pulse and post-overload settling cases')


if __name__=='__main__':main()
