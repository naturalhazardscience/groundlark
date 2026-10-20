import sys
import unittest
import subprocess
import tempfile
import math
from unittest.mock import patch
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from simulate_signal_integrity import transmission,scattering,rf_network,shunt,choke_impedance,inductor_impedance


class RFTests(unittest.TestCase):
    def test_murata_terminal_tolerances_and_nonoverlapping_land_faults(self):
        from rf_substitution import terminal_overlap
        result=terminal_overlap(.96,.56,.62)
        self.assertAlmostEqual(result['minimum_axial_overlap_mm'],.1)
        self.assertFalse(result['supplier_placement_verified'])
        for dims in ((1.6,.56,.62),(.96,.2,.62),(.96,.56,.3),(0,.56,.62)):
            with self.subTest(dims=dims),self.assertRaises(ValueError):terminal_overlap(*dims)

    def test_unmodeled_assembly_substitution_is_rejected(self):
        import pcbnew as p
        from simulate_signal_integrity import rf_review
        from project_paths import board_dir
        from jlcpcb_bom import load_registry
        board=p.LoadBoard(str(board_dir('groundlark-daqhat-01')/'groundlark-daqhat-01.kicad_pcb'))
        registry=load_registry()
        next(r for r in registry['parts'] if 'L140' in r['designators'])['mpn']='UNREVIEWED-56NH'
        with patch('jlcpcb_bom.load_registry',return_value=registry),self.assertRaisesRegex(ValueError,'assembly selection L140'):
            rf_review(board)

    def test_matched_line_and_shunt_analytical_reference(self):
        s11,s21=scattering(transmission(50,3.2,100,1.57542e9))
        self.assertLess(abs(s11),1e-14);self.assertAlmostEqual(abs(s21),1)
        y=1j*.01;s11,s21=scattering(shunt(y))
        self.assertAlmostEqual(abs(s11),abs(-y*50/(2+y*50)))
        self.assertAlmostEqual(abs(s11)**2+abs(s21)**2,1)

    def test_nominal_network_and_high_capacitance_fault(self):
        args=(1.57542e9,46.2,3.425,
              {'GNSS_ANT':1.36,'GNSS_MATCH':1.057,'GNSS_RF':1.863,'BIAS':1.02,'ESD':.8},
              {'GNSS_ANT':.133,'GNSS_MATCH':.266,'GNSS_RF':.685,'BIAS':.133,'ESD':.138})
        nominal=rf_network(*args,diode_pf=.4)
        self.assertGreater(nominal['return_loss_db'],10)
        self.assertLess(nominal['insertion_loss_db'],.5)
        fault=rf_network(*args,diode_pf=5)
        self.assertLess(fault['return_loss_db'],10)
        self.assertGreater(fault['insertion_loss_db'],1)
        old=rf_network(*args,match_nh=0)
        self.assertLess(old['return_loss_db'],10)
        long_stubs={**args[3],'BIAS':3.82,'ESD':4.8}
        self.assertLess(rf_network(*args[:3],long_stubs,args[4])['return_loss_db'],10)

    def test_inductor_surrogate_limits_and_independent_resonance(self):
        # Independently specified RL limit and lossless parallel-LC identity.
        f=1.57542e9;w=2*np.pi*f
        z=choke_impedance(f,srf_ghz=None,q=None)
        self.assertAlmostEqual(z.real,.996)
        self.assertAlmostEqual(z.imag,w*56e-9)
        for f in (100e6,1.57542e9,2.5e9):
            z=inductor_impedance(f,56,2.9,None,0)
            self.assertAlmostEqual(z.imag,2*np.pi*f*56e-9/(1-(f/2.9e9)**2))
        self.assertGreater(abs(choke_impedance(1.559e9,56*.93,None,None)),500)
        # The old 27 nH choke must not inherit the 56 nH isolation result.
        self.assertLess(abs(choke_impedance(1.559e9,27,None,None)),500)

    def test_native_envelope_is_an_acceptance_gate(self):
        import pcbnew as p
        from simulate_signal_integrity import rf_review
        from project_paths import board_dir
        r=rf_review(p.LoadBoard(str(board_dir('groundlark-daqhat-01')/'groundlark-daqhat-01.kicad_pcb')))
        self.assertTrue(r['all_corners_meet_targets'])
        self.assertEqual(r['circuit_cases'],196608)
        self.assertEqual(r['dense_frequency_cases'],771)
        self.assertEqual(r['assembly_mpns'],{'L140':'LQW15AN56NG80D','L141':'LQW15AN3N6G80D'})

    def test_independent_ngspice_network(self):
        f=1.57542e9;w=2*np.pi*f
        lengths={'GNSS_ANT':1.36,'GNSS_MATCH':1.057,'GNSS_RF':1.863,'BIAS':1.02,'ESD':.8}
        pads={'GNSS_ANT':.133,'GNSS_MATCH':.266,'GNSS_RF':.685,'BIAS':.133,'ESD':.138}
        def line(name,a,b,mm):return f'T{name} {a} 0 {b} 0 Z0=46.2 TD={mm*1e-3*np.sqrt(3.425)/299792458}'
        # Literal three-node RF circuit, separately assembled for ngspice.
        # Literal Murata sensitivity surrogate, not a vendor model. DCR/SRF
        # come from JELF243A_0100K-01; Q 30/60 are L1 scenario assumptions.
        text=['RF matching independent reference','Vsrc source 0 AC 2','Rsrc source port 50',
          'Lconnector port junction .8n','Cconnector junction 0 .3p',
          line('bias','junction','bias',lengths['BIAS']),'Cbiaspad bias 0 .133p',
          f'Rchoke bias c1 {.996+w*56e-9/30}','Lchoke c1 c4 56n',
          f'Cres bias c4 {1/((2*np.pi*2.9e9)**2*56e-9)}',
          'Rbypass c4 b1 .1','Lbypass b1 b2 1n','Cbypass b2 0 10n',
          line('esd','junction','esd',lengths['ESD']),'Cesdpad esd 0 .138p',
          'Lesd esd d1 .2n',
          'Cesd d1 0 .55p',line('antenna','junction','ant',lengths['GNSS_ANT']),
          'Cantpad ant 0 .133p','Rblock ant bc1 .1','Lblock bc1 bc2 .2n','Cblock bc2 bc3 47p',
          line('match','bc3','match',lengths['GNSS_MATCH']),'Cmatchpad match 0 .266p',
          f'Rmatch match m1 {.03+w*3.6e-9/60}','Lmatch m1 m2 3.6n',
          f'Cmatch match m2 {1/((2*np.pi*10e9)**2*3.6e-9)}',
          line('receiver','m2','out',lengths['GNSS_RF']),'Crfpad out 0 .685p','Rload out 0 50',
          '.control','set wr_singlescale','set wr_vecnames',f'ac lin 1 {f} {f}',
          'let reflection=v(port)-1','wrdata rf.txt reflection v(out)','quit','.endc','.end']
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);(path/'rf.cir').write_text('\n'.join(text)+'\n')
            subprocess.run(['ngspice','-b','rf.cir'],cwd=path,check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            row=np.loadtxt(path/'rf.txt',skiprows=1)
        result=rf_network(f,46.2,3.425,lengths,pads,branch_z=46.2,branch_epsilon=3.425)
        for key,columns in [('return_loss_db',(1,2)),('insertion_loss_db',(3,4))]:
            independent=-20*math.log10(math.hypot(row[columns[0]],row[columns[1]]))
            self.assertAlmostEqual(result[key],independent,delta=.001)

    def test_passivity_across_frequency(self):
        for f in np.geomspace(1e6,4e9,50):
            result=rf_network(f,46,3.4,{'GNSS_ANT':1.92,'GNSS_RF':1.87},{'GNSS_ANT':.4,'GNSS_RF':.68})
            self.assertGreaterEqual(result['insertion_loss_db'],0)

    def test_native_component_change_cannot_reuse_old_model(self):
        import pcbnew as p
        from simulate_signal_integrity import rf_review
        from project_paths import board_dir
        board=p.LoadBoard(str(board_dir('groundlark-daqhat-01')/'groundlark-daqhat-01.kicad_pcb'))
        next(f for f in board.GetFootprints() if f.GetReference()=='C148').SetValue('4.7p')
        with self.assertRaisesRegex(ValueError,'native C148'):rf_review(board)
