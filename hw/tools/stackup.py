"""Write the recorded supplier stock stack without requesting custom lamination.

Nominal ordering/mechanical thickness and the supplier's copper/dielectric sum
are distinct. Mask thickness is a CAD visualization assumption, not a fab spec.
"""
from hardware_require import require as _require_hardware
from pathlib import Path

def block_span(text, token):
    start=text.index(token);depth=0;quoted=False;escaped=False
    for end in range(start,len(text)):
        char=text[end]
        if escaped:escaped=False;continue
        if char=='\\' and quoted:escaped=True;continue
        if char=='"':quoted=not quoted;continue
        if quoted:continue
        if char=='(':depth+=1
        elif char==')':
            depth-=1
            if not depth:return start,end+1
    raise ValueError('Unbalanced KiCad block')

def apply_stackup(path,spec):
    if 'stackup' not in spec:return
    profile=spec['stackup'];copper=profile['copper_thickness_mm'];dielectric=profile['dielectric_thickness_mm'];mask=profile['mask_thickness_mm']
    _require_hardware((len(copper)==spec['copper_layers'] and len(dielectric)==len(copper)-1), lambda: ('stackup.py:25: hardware validation condition'))
    _require_hardware((abs(sum(copper)+sum(dielectric)-profile['stock_copper_dielectric_total_mm'])<1e-6), lambda: ('stackup.py:26: hardware validation condition'))
    names=['F.Cu',*[f'In{i}.Cu' for i in range(1,len(copper)-1)],'B.Cu']
    parts=['(stackup','(layer "F.SilkS" (type "Top Silk Screen"))','(layer "F.Paste" (type "Top Solder Paste"))',f'(layer "F.Mask" (type "Top Solder Mask") (color "Green") (thickness {mask}) (epsilon_r 3.5) (loss_tangent 0.01))']
    for i,(name,thickness) in enumerate(zip(names,copper)):
        parts.append(f'(layer "{name}" (type "copper") (thickness {thickness}))')
        if i<len(dielectric):
            kind=profile['dielectric_types'][i]
            parts.append(f'(layer "dielectric {i+1}" (type "{kind}") (thickness {dielectric[i]}) (material "FR4 {profile["stock_id"]}") (epsilon_r 4.3) (loss_tangent 0.02))')
    parts.extend([f'(layer "B.Mask" (type "Bottom Solder Mask") (color "Green") (thickness {mask}) (epsilon_r 3.5) (loss_tangent 0.01))','(layer "B.Paste" (type "Bottom Solder Paste"))','(layer "B.SilkS" (type "Bottom Silk Screen"))','(copper_finish "ENIG")','(dielectric_constraints no)',')'])
    path=Path(path);text=path.read_text();a,z=block_span(text,'(stackup');path.write_text(text[:a]+'\n'.join(parts)+text[z:],encoding='utf-8')
