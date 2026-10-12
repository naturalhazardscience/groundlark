# Python sensor workbench

From the repository root, run `./setup-ui.ps1 -Check`, then `./ui.ps1`.
On Linux/macOS, use `sh ./setup-ui.sh --check`, then `sh ./ui.sh`.
Open `http://127.0.0.1:8080`; Ctrl+C in the terminal stops the server.
See the [beginner walkthrough](../../docs/sensor-workbench.md).

The same app serves `/station` for persistent simulation or live acquisition.
Set the UI service's `GROUNDLARK_STATION_TOKEN` to match the local station service;
the browser never receives that API credential. Use the
[deployment guide](../pi/deploy/README.md) for station setup, storage, LAN login
and source profiles. Closing `/station` leaves capture running. Pause/resume,
completed-recording downloads and validated configuration editing are local.

Rerun `./ui.ps1 -Check` / `sh ./ui.sh --check` for the HTTP and scene tests.
The full acquisition/controller tests use the portable software profile.

- `main.py`: Python page construction, charts, board scene and user callbacks.
- `geophone_scene.py`: selectable external geophone and illustrative leads.
- `test_geophone_scene.py`: geometry and shared ADC/can selection regression.
- `test_skylark_scene.py`: exported cell dimensions, position and shared working/auxiliary selection.
- `style.css`: visual styling and responsive layout; dark by default.
- `pyproject.toml`, `uv.lock`: isolated, reproducible optional UI environment.
- `check.py`: page-construction/asset-delivery smoke check.
- `assets/`: checked display assets and provenance, separate from editable CAD.
- `build_wordmark.py`: compose the original favicon and outlined UI lettering
  for the shared README/header asset; see `assets/README.md` for regeneration.
- [workbench.py](../pi/groundlark/workbench.py): bounded framework-independent
  simulation/recording/replay controller.
- [test_workbench.py](../tests/test_workbench.py): controller regression tests.
- [hat_signals.py](../pi/groundlark/hat_signals.py): measured HAT signal regression
  behind the **Test selected board** button, using production drivers on modeled buses.

The UI is authored in Python. NiceGUI supplies bundled browser components based
on Vue, Quasar, Three.js and ECharts. There is no custom JavaScript application,
Node dependency install, npm build, or separate frontend server in this project.

The board selector switches experiments and models between the FPGA HAT,
Burrowlark and Skylark. `skylark_scene.py` adds
selectable gas/climate/PM targets to the native PCB/package GLB.
`build_skylark_model.py` is build-only tooling; its dependencies are separate
from the locked UI environment. See [asset provenance](assets/README.md).

Burrowlark B1 includes four RM3100 modules (IDs 7/18/19/20) in a 2×2 grid
and SHT45 sensor 17. Each magnetic module has its own selectable raw chart.
The ideal model does not establish physical coherence or noise performance.
Select its enclosure-climate
channel to adjust temperature and humidity, inject faults and inspect both plots.
**Test selected board** verifies independent faults, recovery and recording/replay.
`build_burrowlark_model.py` merges the native KiCad export with the authored
PNI/PTC/SHT45 envelopes; see `assets/README.md` for regeneration.
