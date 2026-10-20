"""Small-signal acoustic RLC network and pre-sampling alias sweep.

Pressure is voltage, volume flow is current. Tubes use laminar resistance and
air-slug inertance; chamber compliance is V/(gamma*P). Finite sensor resistance
connects the sensing chamber to the reference volume. This is a parameterized
design model, not a manufacturer model of the SDP32's internal flow path.
"""
import itertools
import math
import json
from pathlib import Path
import numpy as np
from scipy.special import jve


def tube(length_m, diameter_m, viscosity=1.82e-5, density=1.2):
    if min(length_m,diameter_m,viscosity,density)<=0:raise ValueError('positive tube dimensions required')
    area=math.pi*diameter_m**2/4
    return 128*viscosity*length_m/(math.pi*diameter_m**4),density*length_m/area


def viscous_tube(frequencies, length_m, diameter_m, viscosity=1.82e-5, density=1.2,
                 end_correction_radii=1.7):
    """Oscillatory laminar circular-tube solution, including viscous boundary layer.

    Bessel functions use common exponential scaling, which cancels in the ratio.
    End inertance is an explicit two-end scenario, not a fitted filter pole.
    """
    tube(length_m,diameter_m,viscosity,density)
    omega=2*np.pi*np.asarray(frequencies,dtype=float)
    if np.any(~np.isfinite(omega)) or np.any(omega<=0):raise ValueError('positive frequencies required')
    r=diameter_m/2;area=np.pi*r*r
    z=np.sqrt(-1j*omega*density/viscosity)*r
    factor=1-2*jve(1,z)/(z*jve(0,z))
    return 1j*omega*density/area*(length_m/factor+end_correction_radii*r)


def transfer(frequencies, resistance, inertance, volumes_m3,
             sensor_resistance=1e9, reference_m3=.001, pressure_pa=101325, gamma=1.4,
             tube_impedances=None, reference_admittance=0):
    """Ambient -> tube -> chamber -> tube -> sensing chamber -> SDP -> reference.

    The optional independent vent connects ambient to the reference chamber.
    """
    if min(*resistance,*inertance,*volumes_m3,sensor_resistance,reference_m3,pressure_pa,gamma)<=0:
        raise ValueError('positive acoustic elements required')
    s=2j*np.pi*np.asarray(frequencies,dtype=float)
    if np.any(~np.isfinite(s)) or np.any(np.imag(s)<=0):raise ValueError('positive finite frequencies required')
    z1,z2=tube_impedances if tube_impedances is not None else (resistance[0]+s*inertance[0],resistance[1]+s*inertance[1])
    y1=1/z1;y2=1/z2;ys=1/sensor_resistance
    c1,c2=np.array(volumes_m3)/(gamma*pressure_pa);cr=reference_m3/(gamma*pressure_pa)
    a=np.zeros((len(s),3,3),complex)
    a[:,0,0]=y1+y2+s*c1;a[:,0,1]=a[:,1,0]=-y2
    a[:,1,1]=y2+ys+s*c2;a[:,1,2]=a[:,2,1]=-ys
    a[:,2,2]=ys+s*cr+reference_admittance
    b=np.zeros((len(s),3,1),complex);b[:,0,0]=y1;b[:,2,0]=reference_admittance
    p=np.linalg.solve(a,b)[:,:,0]
    return p[:,1]-p[:,2]


def averaging(frequencies, read_hz, conversion_hz=2000):
    # Only integer windows: corner rates 1800/2000/2200 divide 100/200 Hz.
    count=round(conversion_hz/read_hz)
    if count<1 or abs(count-conversion_hz/read_hz)>1e-9:raise ValueError('integer averaging window required')
    f=np.asarray(frequencies)
    return sum(np.exp(-2j*np.pi*f*i/conversion_hz) for i in range(count))/count


def evaluate(read_hz=200, diameter_mm=1.2, length_mm=10, volume_ml=320,
             sensor_resistance=1e9, reference_ml=4000, dimension_scale=1,
             temperature_c=20, pressure_pa=101325, gamma=1.4, conversion_hz=2000,
             sensor_tau_s=0, parallel=4, vent_diameter_mm=.3, vent_length_mm=10):
    """Two capillary banks, two chambers and an independently vented reference.

    Per-stage dimensions may be pairs, allowing independent tolerance faults.
    Parallel tubes reduce the source impedance without moving the filter poles
    when chamber volumes increase proportionally.
    """
    if type(parallel) is not int or parallel<1:raise ValueError('positive integer capillary count required')
    dimensions=np.broadcast_to(np.asarray(dimension_scale,dtype=float),(2,))
    volumes=np.broadcast_to(np.asarray(volume_ml,dtype=float),(2,))
    lengths=np.broadcast_to(np.asarray(length_mm,dtype=float),(2,))
    viscosity=(18.205+.0484*(temperature_c-20))*1e-6
    density=1.1885*(pressure_pa/1e5)*293.15/(273.15+temperature_c)
    elements=[tube(le/1000,diameter_mm/1000*di,viscosity,density) for le,di in zip(lengths,dimensions)]
    r,l=np.asarray(elements).T/parallel
    # All host-sampling images into 1..20 Hz through 4.4 kHz, including
    # images around the internal conversion clock; no internal LP credited.
    band=np.linspace(1,20,77)
    images=np.concatenate([k*read_hz+sign*band for k in range(1,math.ceil(4400/read_hz)+1) for sign in (-1,1)])
    def h(f):
        impedance=[viscous_tube(f,le/1000,diameter_mm/1000*di,viscosity,density)/parallel
                   for le,di in zip(lengths,dimensions)]
        vent=1/viscous_tube(f,vent_length_mm/1000,vent_diameter_mm/1000,viscosity,density)
        return transfer(f,r,l,volumes*1e-6,sensor_resistance,reference_ml*1e-6,pressure_pa,gamma,
                        impedance,vent)*averaging(f,read_hz,conversion_hz)/(1+2j*np.pi*f*sensor_tau_s)
    gain=np.abs(h(band));alias=np.abs(h(images))
    peak=int(np.argmax(alias))
    return dict(read_hz=read_hz,minimum_band_gain_db=float(20*np.log10(gain.min())),
                maximum_band_gain_db=float(20*np.log10(gain.max())),
                worst_alias_db=float(20*np.log10(alias[peak])),worst_alias_input_hz=float(images[peak]),
                bank_resistance_Pas_m3=r.tolist(),bank_inertance_Pas2_m3=l.tolist(),
                sensor_resistance_Pas_m3=sensor_resistance)


def report():
    source=Path(__file__).resolve().parents[1]/'mechanical/daqhat-01-pressure/network.json'
    design=json.loads(source.read_text())
    geometry=design['geometry']
    base=dict(diameter_mm=geometry['capillary_ID_mm'],length_mm=geometry['capillary_length_mm'],
              volume_ml=geometry['chamber_ml'],reference_ml=geometry['reference_ml'],
              parallel=geometry['capillaries_per_stage'],vent_diameter_mm=geometry['reference_vent_ID_mm'],
              vent_length_mm=geometry['reference_vent_length_mm'])
    cases=[]
    for rate,rs in itertools.product((100,200),(1e6,1e7,1e8,1e9,1e10,1e12)):
        cases.append(evaluate(rate,sensor_resistance=rs,**base))
    corners=[]
    for v1,v2,d1,d2,ref,vent,rs,temp,pressure,gamma,tau,clock in itertools.product(
            (.9,1.1),(.9,1.1),(.97,1.03),(.97,1.03),(.9,1.1),(.97,1.03),
            (1e7,1e12),(-10,40),(80000,105000),(1,1.4),(0,.003),(1800,2200)):
        inputs={**base,'volume_ml':[geometry['chamber_ml']*v for v in (v1,v2)],
                'dimension_scale':[d1,d2],'reference_ml':geometry['reference_ml']*ref,
                'vent_diameter_mm':geometry['reference_vent_ID_mm']*vent,
                'sensor_resistance':rs,'temperature_c':temp,'pressure_pa':pressure,
                'gamma':gamma,'sensor_tau_s':tau,'conversion_hz':clock}
        corners.append(dict(inputs=inputs,**evaluate(**inputs)))
    # Endpoints alone are insufficient for a resonant network. Sweep the
    # undocumented sensor resistance through the full interval as well.
    interior=[dict(inputs=dict(sensor_resistance=float(rs)),**evaluate(sensor_resistance=float(rs),**base))
              for rs in np.geomspace(1e7,1e12,101)]
    corners+=interior
    worst=dict(minimum_gain=min(corners,key=lambda r:r['minimum_band_gain_db']),
               maximum_gain=max(corners,key=lambda r:r['maximum_band_gain_db']),
               alias=max(corners,key=lambda r:r['worst_alias_db']))
    passed=(worst['minimum_gain']['minimum_band_gain_db']>=-6 and
            worst['maximum_gain']['maximum_band_gain_db']<=3 and worst['alias']['worst_alias_db']<=-40)
    return dict(scope='Robustness simulation; manufacturer flow estimates are not guaranteed small-signal bounds',
                topology='two parallel-capillary banks/chambers, SDP32, independently vented reference',
                geometry=geometry,source=source.relative_to(source.parents[3]).as_posix(),
                requirements=dict(band_hz=[1,20],minimum_gain_db=-6,maximum_gain_db=3,alias_limit_db=-40,
                                  note='Design allocations: retain at least half the band amplitude; not a landslide sensitivity specification'),
                cases=cases,corner_count=len(corners)-len(interior),interior_count=len(interior),
                corner_extrema=worst,conditional_design_pass=passed,
                manufacturer_evidence=design['sensor_flow_evidence'],
                validity=dict(sensor_resistance_Pas_m3=[1e7,1e12],manufacturer_resistance_bound_established=False,
                              capillary_diameter_tolerance_fraction=.03,
                              chamber_volume_tolerance_fraction=.1,temperature_c=[-10,40],pressure_pa=[80000,105000],
                              chamber_gamma=[1,1.4],sensor_first_order_tau_s=[0,.003],
                              sensor_response_note='First-order scenarios only; a step-time specification does not guarantee this transfer'),
                limitations=['External network dimensions are authored separately; not included in PCB Gerbers.',
                             'Sensor flow resistance robustness envelope is not a manufacturer guarantee.',
                             'Oscillatory viscous tubes include end inertance; omit compressible propagation, leaks, wind and sensor noise.',
                             'Aliasing sweep assumes uniform service; recorded timing bounds remain necessary.'])


if __name__=='__main__':
    import json
    from pathlib import Path
    result=report();output=Path('hw/groundlark-fpga-hat/simulation/pressure-pneumatics.json')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('geometry','corner_count','corner_extrema','conditional_design_pass')},indent=2))
    if not result['conditional_design_pass']:raise SystemExit('Pneumatic design envelope failed')
