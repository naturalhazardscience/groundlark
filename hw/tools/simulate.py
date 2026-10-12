"""Run explicit, bounded ngspice support-circuit simulations.

These are behavioral/passive models, not vendor LDO or sensor silicon models.
See hw/shared/simulation/README.md for model scope, assumptions and acceptance criteria.
"""
from pathlib import Path
import subprocess,json,re,itertools,math
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'hw/shared/simulation';OUT.mkdir(exist_ok=True)
results=[]
def run(name,body,checks):
    deck='Groundlark supporting circuit: '+name+'\n'+body+'\n.end\n'
    (OUT/(name+'.cir')).write_text(deck)
    proc=subprocess.run(['ngspice','-b',str(OUT/(name+'.cir'))],capture_output=True,text=True)
    log=proc.stdout+proc.stderr;(OUT/(name+'.log')).write_text(log)
    if proc.returncode: raise RuntimeError(name+'\n'+log)
    measured={k:float(v) for k,v in re.findall(r'^([a-z][a-z0-9_]*)\s*=\s*([-+0-9.eE]+)',log,re.M)}
    failures=[f'{key}={measured.get(key)} outside [{lo}, {hi}]' for key,(lo,hi) in checks.items() if key not in measured or not lo<=measured[key]<=hi]
    results.append({'case':name,'measured':measured,'acceptance':checks,'failures':failures})
    if failures:raise AssertionError(failures)

for rail,derating,rs in itertools.product([3.18,3.42],[.4,1.0],[.05,.2]):
    name=f'power_{rail}_{derating}_{rs}'.replace('.','p')
    run(name,f'''Vreg source 0 {rail}
Rsource source feed {rs}
Ltrace feed board 500n
Rbulk board bulk 0.03
Cbulk bulk 0 {22e-6*derating}
Rlocal board local 0.04
Clocal local 0 1u
Iload board 0 PULSE(0.02 0.20 100u 1u 1u 200u 500u)
.tran 100n 800u
.measure tran vmin MIN v(board) FROM=90u TO=800u
.measure tran vmax MAX v(board) FROM=90u TO=800u
''',{'vmin':(3.0,3.6),'vmax':(3.0,3.6)})

# USB 5 V cable/PTC budget, behavioral LDO and sensor switch on resistance.
# The LDO is an ideal bounded source: this does not model its control loop.
for vin,load in itertools.product([4.75,5.25],[.025,.08]):
    run(f'usb_supply_{vin}_{load}'.replace('.','p'),f'''Vhost host 0 {vin}
Rcable host fused 2
Rptc fused input 1
Cin input 0 2.2u
Iload input 0 {load}
Bldo reg 0 V=min(3.234,v(input)-0.4)
Cout reg 0 4.7u
Rswitch reg sensor 0.5
Isensor sensor 0 PULSE(0.001 0.055 100u 2u 2u 200u 500u)
Csensor sensor 0 500n
.tran 100n 800u
.measure tran input_min MIN v(input) FROM=90u TO=800u
.measure tran sensor_min MIN v(sensor) FROM=90u TO=800u
''',{'input_min':(4.35,5.25),'sensor_min':(3.20,3.366)})

for tolerance in [-.01,.01]:
    run(f'usb_cc_{tolerance}'.replace('.','p'),f'''Vhost src 0 5
Rrp src cc 56000
Rrd cc 0 {5100*(1+tolerance)}
Ccc cc 0 100p
.tran 1n 20u
.measure tran cc_voltage FIND v(cc) AT=19u
''',{'cc_voltage':(.40,.43)})

for c in [50e-12,100e-12,200e-12]:
    run(f'i2c_{round(c*1e12)}pf',f'''Vcc vcc 0 3.3
Vctl ctl 0 PULSE(1 0 5u 1n 1n 5u 10u)
Rpull vcc bus 4747
Cbus bus 0 {c}
Sdrive bus 0 ctl 0 SW
.model SW SW(Ron=20 Roff=1e12 Vt=0.5 Vh=0)
.tran 1n 9u
.measure tran rise TRIG v(bus) VAL=0.99 RISE=1 TARG v(bus) VAL=2.31 RISE=1
.measure tran low FIND v(bus) AT=4u
''',{'rise':(0,1e-6),'low':(0,.4)})

# UART 2 Mbaud: 500 ns bit period. 47 ohm source damping, 25 ohm driver,
# 100 pF lumped load. This is not a transmission-line/IBIS simulation.
run('uart_service', '''Vdrive src 0 PULSE(0 3.135 100n 5n 5n 500n 1u)
Rdriver src out 25
Rseries out receiver 47
Cload receiver 0 100p
.tran 0.5n 900n
.measure tran rise TRIG v(receiver) VAL=0.9405 RISE=1 TARG v(receiver) VAL=2.1945 RISE=1
.measure tran sampled FIND v(receiver) AT=350n
''',{'rise':(0,50e-9),'sampled':(2.31,3.465)})

# Conservative budget envelope, to be replaced with measured worst-case currents.
budget={'input_max_v':5.25,'regulated_min_v':3.18,'sensor_budget_a':.2,'ambient_max_c':60,'assumed_theta_ja_c_per_w':100}
budget['ldo_dissipation_w']=(budget['input_max_v']-budget['regulated_min_v'])*budget['sensor_budget_a']
budget['junction_estimate_c']=budget['ambient_max_c']+budget['assumed_theta_ja_c_per_w']*budget['ldo_dissipation_w']
assert budget['junction_estimate_c']<125
report={'simulator':subprocess.run(['ngspice','--version'],capture_output=True,text=True).stdout,'cases':results,'power_budget':budget,'status':'PASS — supporting-circuit behavioral models only'}
(OUT/'results.json').write_text(json.dumps(report,indent=2))
print(len(results),'ngspice cases PASS; estimated LDO junction',budget['junction_estimate_c'],'C under stated assumptions')
