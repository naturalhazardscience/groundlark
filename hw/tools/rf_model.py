"""Conservative Coilcraft 0402HP/HPH display envelope, not a supplier solid.

Dimensions include optional solder: Coilcraft Doc 526-1, 2023.
https://www.coilcraft.com/getmedia/54459dcc-b821-4a9d-b91e-0416ea86a9b2/0402hp.pdf
Run with CadQuery; local Z=0 is the mounting surface.
"""
from pathlib import Path

import cadquery as cq


if __name__ == "__main__":
    model = cq.Assembly(name="Coilcraft_0402HP_HPH_envelope")
    model.add(
        cq.Workplane("XY").box(1.17, .71, .82, centered=(True, True, False)),
        name="maximum_package_envelope",
        color=cq.Color(.17, .14, .11),
    )
    model.save(str(Path(__file__).resolve().parents[1] /
                   "shared/models/Coilcraft_0402HP_envelope.step"))
