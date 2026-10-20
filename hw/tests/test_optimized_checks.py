"""Faults must still fail when the interpreter removes Python assertions."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest

TOOLS=Path(__file__).resolve().parents[1]/'tools'


class OptimizedChecks(unittest.TestCase):
    def test_no_optimization_sensitive_hardware_conditions(self):
        remaining=[]
        for path in TOOLS.glob('*.py'):
            remaining.extend(f'{path.name}:{node.lineno}' for node in ast.walk(ast.parse(path.read_text(encoding='utf-8')))
                             if isinstance(node,ast.Assert))
        self.assertEqual(remaining,[])

    def test_optimized_fault_and_lazy_message(self):
        code='''
from hardware_require import require
from fpga_power_checks import verify
require(True, lambda: 1/0)
try:
    require(False, lambda: 'injected geometry fault')
except AssertionError as error:
    if str(error) != 'injected geometry fault': raise RuntimeError('wrong diagnostic')
else: raise RuntimeError('condition disabled')
try:
    verify({})
except AssertionError: pass
else: raise RuntimeError('invalid power pins accepted')
'''
        result=subprocess.run([sys.executable,'-O','-c',code],cwd=TOOLS,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
