"""Read-only source, charge and dissipation budgets from the native boards.

Allocated currents, source impedance, ramp time and thermal resistance are
engineering envelopes, not measured loads or guaranteed silicon maxima.
"""
from hardware_require import require as _require_hardware
import argparse
import hashlib
import json
import math
from pathlib import Path
from signal_response import value
from project_paths import board_dir

ROOT=Path(__file__).resolve().parents[2]


def pm_limit(resistance):
    """TI TPS2553 equations 1-3, resistance in kohm, result in ampere."""
    r=resistance/1000
    if not 15<=r<=232:raise ValueError('TPS2553 ILIM resistor outside supported range')
    return dict(minimum=25.230/(r*1.01)**1.016,
                nominal=23.950/r**.977,maximum=22.980/(r*.99)**.94)


def load_voltage(source,loop_ohm,current):
    if min(source,loop_ohm,current)<0:raise ValueError('invalid source budget')
    return source-loop_ohm*current


def charge_current(capacitance,voltage,ramp_s):
    if ramp_s<=0 or min(capacitance,voltage)<0:raise ValueError('invalid ramp')
    return capacitance*voltage/ramp_s


def ldo_heat(vin,vout,current,iq,theta,ambient):
    if vin<vout or min(current,iq,theta)<0:raise ValueError('invalid regulator envelope')
    power=(vin-vout)*current+vin*iq
    return dict(dissipation_W=power,scenario_junction_C=ambient+power*theta,
                assumed_theta_JA_C_W=theta,assumed_ambient_C=ambient)


def native(name):
    import pcbnew
    path=board_dir(name)/(name+'.kicad_pcb')
    b=pcbnew.LoadBoard(str(path))
    parts={f.GetReference():f.GetValue() for f in b.GetFootprints()}
    pins={(f.GetReference(),p.GetNumber()):p.GetNetname() for f in b.GetFootprints() for p in f.Pads()}
    def cap(net):
        return sum(value(parts[r]) for r in parts if r.startswith('C')
                   and {pins.get((r,'1')),pins.get((r,'2'))}=={net,'GND'})
    return parts,pins,cap,hashlib.sha256(path.read_bytes()).hexdigest()


def build_report():
    s,sp,sc,sh=native('skylark-usb');g,gp,gc,gh=native('groundlark-daqhat-01')
    for key,net in {('U2','1'):'USB_5V',('U2','5'):'V3',('U3','1'):'USB_5V',
                    ('U3','6'):'PM_5V',('U13','1'):'V3',('U13','6'):'VA_SW'}.items():
        _require_hardware((sp[key]==net), lambda: (('Skylark supply topology',key)))
    for key,net in {('J1','2'):'PI_5V',('J1','4'):'PI_5V',('J1','1'):'PI_3V3',
                    ('U40','3'):'PI_5V',('U40','2'):'SENS_3V3',
                    ('J83','1'):'EXT_12V',('F80','2'):'FUSED_12V',('U80','7'):'FPGA_VIN'}.items():
        _require_hardware((gp[key]==net), lambda: (('Groundlark supply topology',key)))
    from fpga_power_checks import verify, budget
    verify(gp)
    import gnss_checks, pi_power_checks
    gnss_checks.verify(gp)
    pi_power_checks.verify(gp)
    limits=pm_limit(value(s['R3']))
    # Explicit allocations. Excess becomes a qualification failure, not an
    # excuse to increase a source's rating. STM32 at 48 MHz; SHT heater off.
    skylark_mA={'MCU_and_USB':32,'analog_rail':8,'SHT40':1,'BMP388':1,
                'ADC_digital':.5,'I2C_pullups':1.5,'clamp_LED_monitor':2,
                'regulator_and_switch_quiescent':.2,'reserve':3.8}
    overhead=sum(skylark_mA.values())/1000
    _require_hardware((math.isclose(overhead,.050)), lambda: ('power_review.py:75: hardware validation condition'))
    configured=limits['maximum']+overhead
    _require_hardware((configured<.500), lambda: ('USB configured allocation exceeded'))
    # At attach only the digital rail and directly connected capacitance charge.
    # 20% high-capacitance case, no DC-bias derating credit; LDO transfers charge.
    attach_charge=1.2*(sc('USB_5V')*5.25+sc('V3')*3.366+sc('NRST')*3.366+sc('VBUS_SENSE')*2.625)
    _require_hardware((attach_charge<50e-6), lambda: ('USB attach charge needs inrush limiting review'))
    ground_5v_mA={'three_IMUs':3,'ADS122C04':2,'ISO1640_side1':10,
                  'translators_switching':10,'bias_and_pullups':5,'LDO_Iq':.5,'SDP32_continuous_max':5.5,'reserve':14,'GNSS_antenna':20,'antenna_LDO_and_reserve':5}
    ground_3v3_mA={'ISO1640_side2':10,'translators_and_muxes':10,'EEPROM_expander_logic':5,
                   'bias_and_pullups':10,'reserve':15,'MAX_M10S_acquisition':100}
    ground_5v=sum(ground_5v_mA.values())/1000
    ground_3v3=sum(ground_3v3_mA.values())/1000
    # ILIM tied to IN selects the fixed 50..100 mA limit. These are
    # sustained DC envelopes: overshoot, thermal cycling and recovery need a bench.
    antenna_fault=dict(limit_A=[.05,.1],choke_rating_A=.28,
        additional_pi_5V_A=.1-ground_5v_mA['GNSS_antenna']/1000,
        pi_5V_fault_allocation_A=ground_5v+.1-ground_5v_mA['GNSS_antenna']/1000,
        limiter_short_dissipation_W=3.366*.1,
        ldo_fault=ldo_heat(5.25,3.234,.1,.000005,200,85),
        fault_telemetry=False,transient_qualified=False)
    _require_hardware((antenna_fault['limit_A'][1]<antenna_fault['choke_rating_A']), lambda: ('power_review.py:96: hardware validation condition'))
    # Capacitive current scenarios are C*dV/dt, NOT simulated regulator startup.
    ramps=[]
    for t in (.0001,.001,.01):
        ramps.append(dict(ramp_s=t,
            pi_5V_A=ground_5v+charge_current(1.2*gc('PI_5V'),5.25,t)+charge_current(1.2*(gc('SENS_3V3')+gc('GNSS_BIAS')+gc('GNSS_LDO')),3.366,t),
            pi_3V3_A=ground_3v3+charge_current(1.2*gc('PI_3V3'),3.366,t)))
    cables=[]
    for source in (4.35,4.75,5.0,5.1):
        for resistance in (.25,.5,1):
            # Allocated cable + connector + fuse round-trip resistance; switch
            # and PM lead additional 0.25 ohm must also be verified physically.
            pms=load_voltage(source,resistance,configured)-limits['maximum']*.25
            cables.append(dict(source_V=source,source_loop_ohm=resistance,pms_V=pms,pms_4p5V_met=pms>=4.5))
    refcap=sc('REF_2V5')
    rtop,rbot=value(s['R20']),value(s['R21'])
    tau=(rtop*rbot/(rtop+rbot))*sc('VMID')
    _require_hardware((refcap*1.2<=10e-6), lambda: ('Reference output capacitor review required'))
    _require_hardware((tau*1.21*math.log(1000)<.15), lambda: ('Reference divider startup exceeds 150 ms'))
    _require_hardware((value(s['R75'])>=100), lambda: ('Guard capacitive-load isolation'))
    return dict(physical_qualification=False,pcb_sha256={'skylark':sh,'groundlark':gh},
        skylark=dict(allocation_mA=skylark_mA,pm_limit_A=limits,configured_A=configured,
            unconfigured_allocated_A=overhead,usb_allocation_A=.5,attach_charge_C=attach_charge,
            suspend_measured_A=None,suspend_limit_A=.0025,
            ldo=ldo_heat(5.25,3.234,overhead,.00008,250,85),
            cable_scenarios=cables,pm_lead_and_switch_assumed_ohm=.25),
        groundlark=dict(pi_5V_allocations_mA=ground_5v_mA,pi_3V3_allocations_mA=ground_3v3_mA,
            pi_5V_allocated_A=ground_5v,pi_3V3_allocated_A=ground_3v3,
            antenna_short=antenna_fault,
            ldo=ldo_heat(5.25,3.234,.05,.0005,150,85),startup_scenarios=ramps,
            fpga_separate_source=budget(),
            pi_supervisor_source=pi_power_checks.budget(),
            powered_from_pi_header_only=False),
        analog=dict(reference_capacitance_F=refcap,divider_load_A=2.5/(rtop+rbot),
            divider_tau_s=tau,divider_0p1pct_settle_corner_s=tau*1.21*math.log(1000),
            guard_isolation_ohm=value(s['R75']),cell_loop_stability=None,
            scope='Reference/divider checks exclude IC slew, rail ramp, cell settling and capacitor discharge/backfeed.'),
        limits=['Allocations are design ceilings to measure, not datasheet worst-case sums.',
                'USB current limit is steady-state; fault response, inrush overshoot and suspend require measurements.',
                'PMS cannot operate across the entire allowed USB cable-voltage range without a boost supply.',
                'Pi source budget includes Pi workload, cooling, other USB devices and HATs; header power is not GPIO drive current.',
                'Groundlark FPGA supply is separate; do not connect J83 to Pi 5V or Pi 3V3.',
                'Regulator thermal scenarios exclude mutual heating and enclosure airflow; effective capacitance/ESR and startup remain unqualified.'],
        sources=['https://www.ti.com/lit/ds/symlink/tps2553.pdf',
                 'https://www.diodes.com/datasheet/download/AP2112.pdf',
                 'https://www.st.com/resource/en/datasheet/ldl1117.pdf',
                 'https://www.raspberrypi.com/documentation/computers/raspberry-pi.html',
                 'https://www.ti.com/lit/ds/symlink/ref3025.pdf'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'hw/shared/simulation/power-review/results.json')
    args=parser.parse_args();report=build_report()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Power budgets checked; source-voltage restrictions and physical qualification remain explicit.')


if __name__=='__main__':main()
