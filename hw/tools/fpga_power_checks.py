"""Independent manufacturer pin fixtures and bounded FPGA input calculations.

Sources: TI TPSM53603 SNVSB77B pp. 3, 5, 12-13, 23; Same Sky PJ-102AH
2024-09-12 p. 2; Digilent Nexys Video reference manual, Power Supplies.
This does not model the converter control loop or qualify a fabricated board.
"""
from hardware_require import require as _require_hardware
from collections import Counter

PINS={
 ('J83','1'):'EXT_12V',('J83','2'):'GND',
 ('F80','1'):'EXT_12V',('F80','2'):'FUSED_12V',
 ('D80','1'):'PROTECTED_12V',('D80','2'):'FUSED_12V',
 ('D81','1'):'PROTECTED_12V',('D81','2'):'GND',
 ('U80','1'):'PROTECTED_12V',('U80','14'):'PROTECTED_12V',
 ('U80','2'):'BUCK_EN',('U80','3'):'GND',('U80','6'):'FPGA_EN1',
 ('U80','7'):'FPGA_VIN',('U80','8'):'FPGA_VIN',('U80','9'):'BUCK_FB',
 ('U80','10'):'GND',('U80','11'):'GND',('U80','12'):'GND',('U80','15'):'GND',
 ('R120','1'):'FPGA_VIN',('R120','2'):'BUCK_FB',
 ('R121','1'):'BUCK_FB',('R121','2'):'GND',
 ('R122','1'):'PROTECTED_12V',('R122','2'):'BUCK_EN',
 ('R123','1'):'BUCK_EN',('R123','2'):'GND',
 ('R124','1'):'FPGA_VIN',('R124','2'):'FPGA_EN1',
 ('SW80','1'):'GND',('SW80','2'):'BUCK_EN',
}
for ref in ('C86','C87','C88','C89'):
 PINS[ref,'1']='PROTECTED_12V';PINS[ref,'2']='GND'
for ref in ('C110','C111','C112'):
 PINS[ref,'1']='FPGA_VIN';PINS[ref,'2']='GND'
# Carrier numbering is the mating-view opposite parity of the vendor module.
for ref,nums in [('J80',(2,4,6,14,16)),('J81',(1,3,5,7))]:
 for num in nums:PINS[ref,str(num)]='FPGA_VIN'

def budget(top=10000,bottom=4300,resistor_tolerance=.001,loop_ohm=.015,current_a=3):
 if not 0<=current_a<=3:raise ValueError('Converter allocation exceeds 3 A')
 t=resistor_tolerance
 nominal=1+top/bottom
 # Full-temperature reference endpoints and maximum 50 nA FB bias.
 low=.985*(1+top*(1-t)/(bottom*(1+t)))-50e-9*top*(1+t)
 high=1.015*(1+top*(1+t)/(bottom*(1-t)))+50e-9*top*(1+t)
 return dict(setpoint_V=nominal,reference_and_divider_min_V=low,
     reference_and_divider_max_V=high,allocated_A=current_a,loop_ohm=loop_ohm,
     minimum_V=low-current_a*loop_ohm,maximum_V=high,
     adapter_V=12,adapter_tolerance=.05,adapter_rating_A=3,
     adapter_scenario_A=nominal*current_a/(11.4*.85),
     limitations='Reference/divider/DC-drop scenario only; line/load regulation, ripple, startup and transient margins require measurement. 85% efficiency is an input-sizing assumption.')

def verify(pins):
 for key,net in PINS.items():
  _require_hardware((pins.get(key)==net), lambda: (('FPGA power pin',key,pins.get(key),net)))
 counts=Counter(pins.values())
 for key in [('U80','4'),('U80','5'),('U80','13'),('J83','3'),('SW80','3')]:
  _require_hardware((pins.get(key) and counts[pins[key]]==1), lambda: (('Required isolated pin',key)))
 _require_hardware((len({pins['J1','1'],pins['J1','2'],pins['J83','1'],pins['U80','7']})==4), lambda: ('Pi and external supplies joined'))
 return len(PINS)

def verify_board(board,spec):
 import pcbnew as p
 fps={f.GetReference():f for f in board.GetFootprints()}
 pins={(f.GetReference(),q.GetNumber()):q.GetNetname() for f in board.GetFootprints() for q in f.Pads() if q.GetNumber()}
 checks=verify(pins);meta={x['ref']:x for x in spec['parts']}
 for ref,mpn in {'J83':'PJ-102AH','U80':'TPSM53603RDAR','F80':'0466002.NRHF','D80':'B340A-13-F','D81':'SMAJ15A-13-F','R120':'RT0603BRD0710KL','R121':'RT0603BRD074K3L'}.items():
  _require_hardware((meta[ref]['mpn']==mpn and not fps[ref].IsDNP()), lambda: (('Fitted power part',ref)))
 _require_hardware((fps['R120'].GetValue()=='10k' and fps['R121'].GetValue()=='4.30k'), lambda: ('fpga_power_checks.py:63: hardware validation condition'))
 _require_hardware((fps['J83'].GetOrientationDegrees()%360==180 and not fps['J83'].IsFlipped()), lambda: ('fpga_power_checks.py:64: hardware validation condition'))
 # Same Sky top-view drawing: 6 mm center/sleeve spacing and 4.7/3 mm switch offset.
 expected={'1':(95,14.1),'2':(95,8.1),'3':(90.3,11.1)}
 for q in fps['J83'].Pads():
  x,y=expected[q.GetNumber()];xy=q.GetPosition()
  _require_hardware((abs(p.ToMM(xy.x)-50-x)<.001 and abs(p.ToMM(xy.y)-50-y)<.001), lambda: ('fpga_power_checks.py:69: hardware validation condition'))
 # -Y jack mouth and +Y geophone mating directions are opposite; tall parts
 # stay to the right of the vendor module envelope x=30..80, y=8..48.
 _require_hardware((p.ToMM(fps['J90'].GetPosition().y)>p.ToMM(fps['J83'].GetPosition().y)), lambda: ('fpga_power_checks.py:72: hardware validation condition'))
 for ref in ('J83','U80','C89'):
  _require_hardware((p.ToMM(fps[ref].GetBoundingBox(False,False).GetLeft())>130), lambda: ('fpga_power_checks.py:74: hardware validation condition'))
 thermal=[t for t in board.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND' and
          144<=p.ToMM(t.GetPosition().x)<=146 and 81<=p.ToMM(t.GetPosition().y)<=83]
 _require_hardware((len(thermal)>=9), lambda: ('Converter thermal/return through-vias missing'))
 output=[t for t in board.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetNetname()=='FPGA_VIN' and
         142<=p.ToMM(t.GetPosition().x)<=148 and 84.8<=p.ToMM(t.GetPosition().y)<=86.2]
 _require_hardware((len(output)>=8), lambda: ('Parallel converter output through-vias missing'))
 for t in thermal+output:_require_hardware((t.GetViaType()==p.VIATYPE_THROUGH), lambda: ('fpga_power_checks.py:81: hardware validation condition'))
 from copper_resistance import fpga_loop
 copper=fpga_loop(board,board.GetFileName())
 b=budget(loop_ohm=copper['copper_with_reserve_ohm']+copper['contact_allocation_ohm'])
 _require_hardware((b['minimum_V']>3.201 and b['maximum_V']<3.399), lambda: ('FPGA voltage envelope'))
 return dict(pin_checks=checks,thermal_vias=len(thermal),output_vias=len(output),
             jack_mating_direction='-Y; opposite geophone +Y',power_budget=b,copper_extraction=copper,physical_qualification=False)
