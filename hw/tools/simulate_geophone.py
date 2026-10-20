"""Passive AFE + nominal Racotech mechanical model in ngspice.

No vendor transistor ADC/TVS model; no ESD, ADC noise, EMC or sub-hertz
performance qualification. Component tolerances and sensor damping are swept.
"""
from hardware_require import require as _require_hardware
from pathlib import Path
import json, math, re, subprocess
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'hw/groundlark-fpga-hat/simulation/geophone'


def main():
    OUT.mkdir(exist_ok=True);rows=[]
    for damping,coil,cap,rail in ((.7,395,100e-9,3.3),(.63,375.25,95e-9,3.135),(.77,414.75,105e-9,3.465)):
        for hz in (.5,4.5,10,27,1000):
            name=f'ac_{damping}_{hz}'
            # RLC voltage across L has s²/(s²+2*zeta*wn*s+wn²) transfer.
            body=f'''Geophone nominal mechanical and passive electrical model
Vmotion motion 0 DC 0 AC 0.0001
Cm motion damp {1/(2*math.pi*4.5)**2}
Rm damp hp {2*damping*2*math.pi*4.5}
Lm hp 0 1
Egeo coilp coilm hp 0 23.4
Rcoil coilp leadp {coil}
R90 leadp ainp 1000
R91 coilm ainm 1000
R92 ainp vcm 1meg
R93 ainm vcm 1meg
C90 ainp ainm {cap}
C91 ainp 0 1n
C92 ainm 0 1n
Vsupply supply 0 {rail}
R96 supply avdd 22
Iadc avdd 0 0.0005
C94 avdd 0 10u
C95 avdd 0 100n
R94 avdd vcm 10k
R95 vcm 0 10k
C93 vcm 0 10u
Eout out 0 ainp ainm 1
.control
op
print v(avdd) v(vcm)
ac lin 1 {hz} {hz}
let amplitude = mag(v(out))
print amplitude
quit
.endc
.end
'''
            path=OUT/(name+'.cir');path.write_text(body)
            r=subprocess.run(['ngspice','-b',str(path)],capture_output=True,text=True)
            log=r.stdout+r.stderr;(OUT/(name+'.log')).write_text(log)
            if r.returncode:raise RuntimeError(log)
            values={k:float(v) for k,v in re.findall(r'^(v\(avdd\)|v\(vcm\)|amplitude)\s*=\s*([-+0-9.eE]+)',log,re.M)}
            omega=2*math.pi*hz;wn=2*math.pi*4.5
            mechanical=omega**2/math.hypot(wn**2-omega**2,2*damping*wn*omega)
            resistance=coil+2000;load=2e6/(2e6+resistance)
            expected=.0001*23.4*mechanical*load/math.sqrt(1+(omega*resistance*(cap+.5e-9)*load)**2)
            _require_hardware((abs(values['amplitude']/expected-1)<1e-4), lambda: (values))
            _require_hardware((1.55 < values['v(vcm)'] < 1.75), lambda: ('simulate_geophone.py:60: hardware validation condition'))
            _require_hardware((abs(values['v(avdd)']/2-values['v(vcm)'])<1e-5), lambda: ('simulate_geophone.py:61: hardware validation condition'))
            # PGA64 worst full-scale output still fits the specified 0.2V rail margin.
            _require_hardware((values['v(vcm)']-1.024 > .2 and values['v(vcm)']+1.024 < values['v(avdd)']-.2), lambda: ('simulate_geophone.py:63: hardware validation condition'))
            rows.append(dict(case=name,**values,expected_v=expected,passed=True))
    report=dict(cases=rows,scope='15 AC/mechanical/tolerance cases and DC common-mode/PGA headroom checks',
                limitations='Nominal passive model; ADC digital filter/noise, TVS leakage/ESD, package microphonics, cable EMI and physical installation need measurement.')
    (OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: 15 geophone mechanical/RC response and bias/headroom cases')


if __name__=='__main__':main()
