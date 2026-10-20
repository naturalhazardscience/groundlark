"""Independent electrostatic identities and deliberately bad line fixtures."""
import sys
import unittest
import shutil
import subprocess
import tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from field_solver import capacitance, microstrip, broadside, C0
from coupled_line import step


class FieldSolverTests(unittest.TestCase):
    def test_uniform_dielectric_scaling_and_tem_identity(self):
        bounds=(-.7,0,.7,.7);wires=[(-.15,.2,-.05,.22),(.05,.4,.15,.42)]
        air=capacitance(bounds,wires,[],.02)
        dielectric=capacitance(bounds,wires,[(0,.7,4)],.02)
        np.testing.assert_allclose(dielectric,4*air,rtol=1e-9)
        np.testing.assert_allclose(dielectric@np.linalg.inv(air)/C0**2,np.eye(2)*4/C0**2,atol=1e-25)
        self.assertLess(air[0,1],0)
        np.testing.assert_allclose(air,air.T,rtol=1e-9)

    def test_microstrip_independent_formula_and_mesh_convergence(self):
        from daqhat_01_engineering import microstrip as hammerstad
        reference,_=hammerstad(.17,.0994,.035,4.3)
        coarse=microstrip(mask=0,pitch=.01)['z_ohm']
        fine=microstrip(mask=0,pitch=.005)['z_ohm']
        self.assertAlmostEqual(fine,reference,delta=reference*.025)
        self.assertLess(abs(fine-coarse),.5)
        self.assertLess(microstrip(pitch=.005)['z_ohm'],fine)

    def test_offset_reduces_broadside_coupling(self):
        near=broadside(pitch=.02)['capacitance_F_m']
        far=broadside(offset=.5,pitch=.02)['capacitance_F_m']
        self.assertLess(abs(far[0,1]),abs(near[0,1])/2)

    def test_ladder_zero_coupling_and_length_fault(self):
        c=np.array([[120,-70],[-70,120]])*1e-12
        l=np.array([[600,350],[350,600]])*1e-9
        quiet=step(np.diag(np.diag(c)),np.diag(np.diag(l)),5)
        self.assertLess(max(quiet.values()),1e-10)
        short=step(c,l,2);long=step(c,l,20)
        self.assertGreater(max(long.values()),max(short.values())*2)
        fine=step(c,l,2,sections=12,dt_ns=.005)
        self.assertAlmostEqual(max(short.values()),max(fine.values()),delta=.003)
        with self.assertRaises(ValueError):step(c,-l,2)
        asymmetric=c.copy();asymmetric[0,1]*=.5
        with self.assertRaises(ValueError):step(asymmetric,l,2)

    def test_bad_geometry_rejected(self):
        for wires in ([(-1,.1,0,.2)],[(0,.1,.2,.2),(.1,.1,.3,.2)]):
            with self.assertRaises(ValueError):capacitance((-.5,0,.5,1),wires,[])

    @unittest.skipUnless(shutil.which('ngspice'),'ngspice is installed in the portable lab')
    def test_ladder_matches_independent_spice_transient(self):
        # Explicit capacitors to ground and between wires, and mutually
        # coupled inductors: independent MNA implementation in ngspice.
        c=np.array([[120,-70],[-70,120]])*1e-12
        l=np.array([[600,350],[350,600]])*1e-9
        count=6;dx=.005/count
        lines=['Coupled line independent fixture','Vstep src 0 PWL(0 0 .5n 3.465 12n 3.465)',
               'Ra src a0 20','Rb b0 0 4700']
        for i in range(count+1):
            scale=dx*(.5 if i in (0,count) else 1)
            for net in ('a','b'):
                lines.append(f'Cg{net}{i} {net}{i} 0 {50e-12*scale+(2e-12 if i in (0,count) else 0)}')
            lines.append(f'Cm{i} a{i} b{i} {70e-12*scale}')
        for i in range(count):
            for net in ('a','b'):
                lines += [f'R{net}{i} {net}{i} {net}x{i} .01',f'L{net}{i} {net}x{i} {net}{i+1} {600e-9*dx}']
            lines.append(f'K{i} La{i} Lb{i} {350/600}')
        lines += ['.control','set wr_vecnames','set wr_singlescale','tran .005n 12n',
                  'wrdata wave.txt v(b0) v(b6)','quit','.endc','.end']
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'line.cir').write_text('\n'.join(lines)+'\n')
            subprocess.run(['ngspice','-b','line.cir'],cwd=path,check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            waveform=np.loadtxt(path/'wave.txt',skiprows=1)
        independent=float(np.max(np.abs(waveform[:,1:])))
        model=max(step(c,l,5,dt_ns=.005).values())
        self.assertAlmostEqual(model,independent,delta=.005)


if __name__=='__main__':unittest.main()
