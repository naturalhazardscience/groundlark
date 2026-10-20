"""Explicit numeric solve for manual atomic parts in atopile 0.15.9.

The stock picker skips solving when there are no auto-picked components. This
entrypoint runs the upstream full solver after graph setup, including bus aliases.
No installed package is patched and no check is disabled.
"""
from hardware_require import require as _require_hardware
import os,sys,subprocess
from pathlib import Path
os.environ['CI']='1';os.environ['FBRK_FULL_SOLVER']='1'
from atopile.config import config
from atopile.buildutil import build
from faebryk.core.solver import Solver
import faebryk.core.node as fabll
import faebryk.library._F as F
ROOT=Path(__file__).resolve().parents[2]
# Match atopile's worker working directory when resolving per-build layout paths.
os.chdir(ROOT/'hw')
negative='--negative' in sys.argv
if not negative and '--target' not in sys.argv:
    for name in ['field_head','trenz_hat','skylark']:
        subprocess.run([sys.executable,__file__,'--target',name],check=True)
    sys.exit(0)
entry=str(ROOT/'hw/tests/overvoltage.ato')+':InvalidVoltage' if negative else str(ROOT/'hw')
selected=[] if negative else [sys.argv[sys.argv.index('--target')+1]]
config.apply_options(entry=entry,standalone=negative,selected_builds=selected,include_targets=['post-instantiation-design-check'])
for name in config.selected_builds:
    with config.select_build(name):
        app=build()
        try:
            params=[node.get_trait(F.Parameters.is_parameter) for node in app.get_children(direct_only=False,types=fabll.Node,required_trait=F.Parameters.is_parameter) if node.get_full_name().split('.')[-1] in {'voltage','resistance','capacitance','rated_voltage'}]
            _require_hardware((params), lambda: ('No numeric electrical constraints found'))
            Solver().simplify_for(*params,terminal=True)
        except Exception as error:
            if negative and 'contradiction' in (type(error).__name__+' '+str(error)).lower():
                print('PASS: upstream solver rejected 5V on the 3.6V IMU:',type(error).__name__)
                continue
            raise
        if negative:raise AssertionError('Unsafe voltage was not rejected')
        print('PASS: explicit upstream constraint solve',name)
