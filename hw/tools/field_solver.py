"""2-D quasi-static capacitance extraction on a conforming rectangular mesh.

Solves div(epsilon grad(V))=0 with grounded outer boundaries. Conductors and
dielectric interfaces are exact mesh lines. Edge fluxes give Maxwell C, and a
second vacuum solve gives L = inv(C0)/c**2 for quasi-TEM transmission lines.
Dimensions are mm; returned matrices are F/m and H/m. Not a 3-D full-wave model.
"""
import math
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import splu

EPS0 = 8.8541878128e-12
C0 = 299792458.


def axis(low, high, breaks, pitch):
    edges=sorted({low,high,*[v for v in breaks if low<v<high]})
    return np.concatenate([np.linspace(a,b,max(1,math.ceil((b-a)/pitch))+1)[:-1]
                           for a,b in zip(edges,edges[1:])]+[np.array([high])])


def capacitance(bounds, conductors, dielectrics, pitch=.01):
    """rectangles=(xmin,ymin,xmax,ymax); dielectric bands=(bottom,top,er).

    Conductor rectangles must be disjoint and inside the grounded box. All
    unspecified dielectric is air. Every conductor is independently excited.
    """
    xmin,ymin,xmax,ymax=bounds
    if not (0<pitch<=.1 and xmin<xmax and ymin<ymax and conductors):
        raise ValueError('invalid field-solver geometry')
    for a,b,c,d in conductors:
        if not (xmin<a<c<xmax and ymin<=b<d<ymax):raise ValueError('conductor outside domain')
    if any(not (a<b and er>=1 and math.isfinite(er)) for a,b,er in dielectrics):
        raise ValueError('invalid dielectric')
    xs=axis(xmin,xmax,[v for r in conductors for v in (r[0],r[2])],pitch)
    ys=axis(ymin,ymax,[v for r in conductors for v in (r[1],r[3])]+
            [v for a,b,_ in dielectrics for v in (a,b)],pitch)
    nx,ny=len(xs),len(ys);n=nx*ny
    xx,yy=np.meshgrid(xs,ys);labels=np.zeros((ny,nx),dtype=int)
    for index,(a,b,c,d) in enumerate(conductors,1):
        mask=(xx>=a-1e-12)&(xx<=c+1e-12)&(yy>=b-1e-12)&(yy<=d+1e-12)
        if np.any(labels[mask]):raise ValueError('overlapping conductors')
        labels[mask]=index
    if np.any(labels[[0,-1],:]) or np.any(labels[:,[0,-1]]):raise ValueError('conductor touches domain boundary')
    dx,dy=np.diff(xs),np.diff(ys)
    mid=(ys[:-1]+ys[1:])/2;er=np.ones(ny-1)
    for a,b,value in dielectrics:er[(mid>=a)&(mid<b)]=value
    # Flux through dual-cell faces. The interface is a mesh line; tangential
    # half-faces add in parallel, normal edges stay in one dielectric.
    hy=np.r_[0,er*dy/2]+np.r_[er*dy/2,0]
    wx=np.r_[0,dx/2]+np.r_[dx/2,0]
    ids=np.arange(n).reshape(ny,nx)
    a=np.r_[ids[:,:-1].ravel(),ids[:-1,:].ravel()]
    b=np.r_[ids[:,1:].ravel(),ids[1:,:].ravel()]
    g=EPS0*np.r_[(hy[:,None]/dx).ravel(),((er/dy)[:,None]*wx).ravel()]
    lap=coo_matrix((np.r_[g,g,-g,-g],(np.r_[a,b,a,b],np.r_[a,b,b,a])),shape=(n,n)).tocsr()
    fixed=labels!=0;fixed[[0,-1],:]=True;fixed[:,[0,-1]]=True
    free=np.flatnonzero(~fixed.ravel());fixed=np.flatnonzero(fixed)
    excitation=(labels.ravel()[:,None]==np.arange(1,len(conductors)+1)).astype(float)
    voltage=excitation.copy()
    solve=splu(lap[free][:,free].tocsc())
    voltage[free]=solve.solve(-(lap[free][:,fixed]@excitation[fixed]))
    charge=lap@voltage
    matrix=np.array([charge[labels.ravel()==i].sum(axis=0) for i in range(1,len(conductors)+1)])
    if not np.allclose(matrix,matrix.T,rtol=1e-7,atol=1e-20) or np.min(np.linalg.eigvalsh(matrix))<=0:
        raise ValueError('non-passive or nonreciprocal capacitance solve')
    return matrix


def line(bounds, conductors, dielectrics, pitch=.01):
    c=capacitance(bounds,conductors,dielectrics,pitch)
    vacuum=capacitance(bounds,conductors,[],pitch)
    inductance=np.linalg.inv(vacuum)/C0**2
    return dict(capacitance_F_m=c,inductance_H_m=inductance,
                impedance_ohm=np.sqrt(np.diag(inductance)/np.diag(c)),
                vacuum_F_m=vacuum)


def microstrip(width=.17,height=.0994,thickness=.035,er=4.3,mask=.01,mask_er=3.5,
               coplanar_gap=None,pitch=.005,extent=10):
    half=max(extent*height,width*2);top=height+thickness+extent*height
    rectangles=[(-width/2,height,width/2,height+thickness)]
    if coplanar_gap is not None:
        # Keep ground rails as independent conductors, grounded in the signal
        # excitation. Their outer edges stop short of the domain boundary.
        edge=width/2+coplanar_gap
        if edge>=half-pitch:raise ValueError('coplanar rail outside domain')
        rectangles += [(-half+pitch,height,-edge,height+thickness),
                       (edge,height,half-pitch,height+thickness)]
    result=line((-half,0,half,top),rectangles,
                [(0,height,er),(height,height+thickness+mask,mask_er)] if mask else [(0,height,er)],pitch)
    c=result['capacitance_F_m'][0,0];c0=result['vacuum_F_m'][0,0]
    # Grounded coplanar rails carry return current: scalar C00/C0_00, not
    # the diagonal of an inverse multiconductor matrix with floating rails.
    return dict(z_ohm=1/(C0*math.sqrt(c*c0)),epsilon_effective=c/c0,
                capacitance_F_m=float(c),inductance_H_m=float(1/(C0*C0*c0)))


def broadside(width1=.125,width2=.125,gap=.1088,outer_gap=.55,thickness=.0152,
              offset=0,er=4.3,pitch=.01):
    y=outer_gap;z=y+thickness+gap;top=z+thickness+outer_gap
    half=max(2.,abs(offset)+max(width1,width2)+top)
    return line((-half,0,half,top),[(-width1/2,y,width1/2,y+thickness),
                (offset-width2/2,z,offset+width2/2,z+thickness)],[(0,top,er)],pitch)
