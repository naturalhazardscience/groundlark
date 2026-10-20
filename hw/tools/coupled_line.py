"""Passive multiconductor LC ladder; voltage is relative to the quiet rail.

Uses field-extracted Maxwell C and partial L, not a fitted crosstalk percentage.
Both polarities have the same excursion in this linear small-signal model.
"""
import numpy as np
from scipy.signal import lsim, StateSpace


def step(capacitance, inductance, length_mm, rise_ns=.5, driver_ohm=20,
         victim_ohm=4700, load_pf=2, sections=6, dt_ns=.01, duration_ns=12):
    if min(length_mm,rise_ns,driver_ohm,victim_ohm,load_pf,dt_ns)>0 and sections>=2:
        pass
    else:raise ValueError('positive line parameters and at least two sections required')
    c,l=np.asarray(capacitance),np.asarray(inductance)
    for matrix in (c,l):
        if matrix.shape!=(2,2) or not np.allclose(matrix,matrix.T,rtol=1e-8,atol=1e-24) or np.linalg.eigvalsh(matrix).min()<=0:
            raise ValueError('passive reciprocal two-line matrices required')
    size=2*(sections+1);length=length_mm*1e-3/sections
    cn=np.zeros((size,size));g=np.zeros_like(cn)
    incidence=np.zeros((size,2*sections))
    for i in range(sections+1):
        cn[2*i:2*i+2,2*i:2*i+2]=c*length*(.5 if i in (0,sections) else 1)
    # Receiver capacitance at far ends, source/package capacitance at near ends.
    cn[:2,:2]+=np.eye(2)*load_pf*1e-12
    cn[-2:,-2:]+=np.eye(2)*load_pf*1e-12
    g[0,0]=1/driver_ohm;g[1,1]=1/victim_ohm
    for i in range(sections):
        incidence[2*i:2*i+2,2*i:2*i+2]=np.eye(2)
        incidence[2*i+2:2*i+4,2*i:2*i+2]=-np.eye(2)
    linv=np.kron(np.eye(sections),np.linalg.inv(l*length))
    cinv=np.linalg.inv(cn)
    # 10 mOhm per section damps numerical ideal-loop modes; its value is not
    # credited as a design remedy. Near-end source resistances dominate.
    a=np.block([[-cinv@g,-cinv@incidence],
                [linv@incidence.T,-linv*.01]])
    b=np.zeros(size+2*sections);b[:size]=cinv[:,0]/driver_ohm
    observe=np.zeros((2,len(b)));observe[0,1]=1;observe[1,size-1]=1
    t=np.arange(0,duration_ns+dt_ns/2,dt_ns)*1e-9
    stimulus=3.465*np.minimum(t/(rise_ns*1e-9),1)
    _,voltage,_=lsim(StateSpace(a,b[:,None],observe,np.zeros((2,1))),stimulus,t)
    return dict(near_peak_V=float(np.max(np.abs(voltage[:,0]))),
                far_peak_V=float(np.max(np.abs(voltage[:,1]))))
