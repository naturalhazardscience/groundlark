"""Print the fitted SDP32 profile's ideal averaging response and alias limits."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'pi'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'interfaces/python'))
from groundlark.pressure_response import report

if __name__ == '__main__':
    print(json.dumps(report(), indent=2, allow_nan=False))
