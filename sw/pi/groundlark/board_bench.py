"""Board-specific experiments through the shared acquisition/recording path."""
from hashlib import sha256
from .workbench import Workbench


def run_bench(board="hat"):
    if board == "hat":
        from .hat_signals import run_bench as hat_bench
        data, report = hat_bench()
        report["scope"] += "; no physical HAT connected"
        return data, report
    if board not in ("burrowlark", "skylark"):
        raise ValueError("Board test is unavailable")
    e = Workbench(board=board)
    initial = ({"so2_ppm": 1, "h2s_ppm": 2, "pm25_ug_m3": 37,
                "temperature_c": 25, "humidity_percent": 50, "ambient_pressure_pa": 101325}
               if board == "skylark" else {"magnetic_ut": [-10, 0, 20],
                                          "temperature_c": -10, "humidity_percent": 0})
    e.controls(initial)
    def advance(ms):
        e.running = True
        for _ in range(ms // 100): e.advance(100)
        e.pause()
    checks = []
    def check(name, passed, detail): checks.append(dict(name=name, passed=bool(passed), detail=detail))
    advance(2000)
    sid = 10 if board == "skylark" else 7
    snap = e.snapshot(sid)
    check("Inventory", all(snap["latest"].values()) and not e.error, f"{len(snap['latest'])} active streams")
    if board == "skylark":
        values = snap["latest"]
        check("Gas channels", values[10]["primary"][0] == 4328522 and values[11]["primary"][0] == 4194304
              and values[12]["primary"][0] == 4422474 and values[13]["primary"][0] == 4194304,
              "Independent 2.5 V ADC expectation for nominal stimulus; no cell calibration")
        check("Particulate", values[14]["primary"] == [22, 37, 48], "Atmospheric PM1/2.5/10: 22 / 37 / 48 ug/m3")
        check("Climate", abs(values[15]["primary"][0]-25)<.003 and abs(values[15]["secondary"][0]-50)<.003,
              "SHT40 inverse transfer, CRC-preserved frame")
        check("Barometer", values[16]["primary"][0] == 101325 and values[16]["secondary"][0] == 25,
              "Factory compensation of synthetic trim: 101325 Pa, 25 C")
    else:
        check("Four magnetometers", set(snap["latest"]) == {7, 18, 19, 20, 17} and
              all(snap["latest"][sensor]["primary"] == [-750, 0, 1500] for sensor in (7, 18, 19, 20)),
              "Four distinct streams; independent nominal 75 counts/uT expectation, signed axes")
        climate = snap["latest"][17]
        check("SHT45 cold/dry", abs(climate["primary"][0]+10)<.003 and
              abs(climate["secondary"][0])<.003, "Negative temperature and zero RH remain valid; both CRC words retained")
        e.controls({"temperature_c": 35, "humidity_percent": 85})
        advance(1000)
        climate = e.snapshot(17)["latest"][17]
        check("SHT45 stimulus", abs(climate["primary"][0]-35)<.003 and
              abs(climate["secondary"][0]-85)<.003, "Independent warm/humid transfer expectation")
    e.controls({"sensor_faults": {str(sid): "timeout"}})
    advance(1000)
    snap = e.snapshot(sid)
    check("Fault isolation", snap["latest"][sid]["quality"] == "Missing" and
          snap["latest"][14 if board == "skylark" else 17]["quality"] == "Valid",
          "Missing stays distinct from zero; independent environmental stream continues")
    if board == "burrowlark":
        check("Modeled lane isolation", all(snap["latest"][sensor]["quality"] == "Valid" for sensor in (18, 19, 20)),
              "Ideal independent drivers continue; target firmware instead latches the whole array on a magnetic fault")
    e.controls({"sensor_faults": {str(sid): "none"}})
    advance(5000 if board == "skylark" else 1000)
    if board == "burrowlark":
        e.controls({"sensor_faults": {"17": "timeout"}})
        advance(1000)
        values = e.snapshot(17)["latest"]
        check("SHT45 fault isolation", values[17]["quality"] == "Missing" and
              all(values[sensor]["quality"] == "Valid" for sensor in (7, 18, 19, 20)),
              "Climate failure leaves all four magnetic streams running")
        e.controls({"sensor_faults": {"17": "none"}})
        advance(3000)
        check("SHT45 recovery", e.snapshot(17)["latest"][17]["quality"] == "Valid",
              "Bounded retry restores heater-off climate acquisition")
    data = e.finish()
    before = e.snapshot(sid)["latest"]
    end = e.now / 1e9
    e.load_recording(data);e.seek(end)
    check("Replay", e.snapshot(sid)["latest"] == before, "Checked recording reproduces final raw values, gaps and timestamps")
    return data, dict(passed=all(c["passed"] for c in checks), checks=checks,
                     samples=e.samples, recording_sha256=sha256(data).hexdigest(),
                     scope="Ideal sensor stimulus through shared acquisition and replay; " +
                     ("Skylark C firmware fault tests run separately in the portable suite" if board=='skylark'
                      else "Burrowlark B1 C timing/fault tests run separately; physical coherence and noise remain unqualified"))
