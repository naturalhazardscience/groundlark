"""Cleanup and staging failure modes, tested in disposable temporary directories."""
import json
import os
from pathlib import Path
import tempfile
import unittest
import subprocess
from unittest.mock import patch
from lab import MARKER, clean, lab_lock, managed_runs, source_files, write_json, commands
from lab import run_steps


class LabSafetyTests(unittest.TestCase):
    def test_failures_and_timeouts_do_not_hide_remaining_checks(self):
        steps=[('registry',['check']),('timeout',['slow']),('missing',['missing']),('simulation',['sim'])]
        record={'steps':[],'status':'running'}
        results=[subprocess.CompletedProcess(['check'],1),
                 subprocess.TimeoutExpired(['slow'],600),FileNotFoundError('missing tool'),
                 subprocess.CompletedProcess(['sim'],0)]
        with patch('lab.subprocess.run',side_effect=results) as run:
            failures=run_steps(steps,self.root,self.root,record)
        self.assertEqual(failures,['registry','timeout','missing'])
        self.assertEqual(run.call_count,4)
        self.assertEqual([s['exit_code'] for s in record['steps']],[1,1,1,0])
        saved=json.loads((self.root/'run.json').read_text())
        self.assertEqual(saved['steps'],record['steps'])
        self.assertIn('timed out',(self.root/'timeout.log').read_text())

    def test_product_sources_are_staged_without_generated_packages(self):
        inputs = [
            'hw/groundlark-fpga-hat/elec/hat_trenz.ato',
            'hw/burrowlark-usb/elec/field_head.ato',
            'hw/shared/elec/parts.ato',
            'hw/shared/reference/raspberrypi_hat.kicad_pcb',
        ]
        excluded = [
            'hw/releases/groundlark-fpga-hat/example.ato',
            'hw/groundlark-fpga-hat/build/example.ato',
        ]
        for rel in inputs + excluded:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture')
        staged = source_files(self.root)
        for rel in inputs:
            self.assertIn(self.root / rel, staged)
        for rel in excluded:
            self.assertNotIn(self.root / rel, staged)

    def test_native_custom_rules_are_in_validation_snapshot(self):
        board=self.root/'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01'
        board.mkdir(parents=True)
        rule=board/'groundlark-daqhat-01.kicad_dru'
        rule.write_text('(version 1)')
        self.assertIn(rule,source_files(self.root))

    def test_foreign_run_owner_is_rejected(self):
        marker = self.root / '.groundlark-lab'
        marker.write_text(MARKER)
        path = self.run_folder(0)
        data = json.loads((path / 'run.json').read_text())
        data['owner'] = 'unrecognized-project-v1'
        write_json(path / 'run.json', data)
        with lab_lock(self.root):
            with self.assertRaises(RuntimeError):
                clean(self.root, keep=0, apply=True)
        self.assertEqual(marker.read_text(), MARKER)
        self.assertTrue(path.exists())

    def test_active_soak_counts_towards_five_and_cannot_be_pruned(self):
        paths=[self.run_folder(i) for i in range(7)]
        marker=paths[0]/'run.json';data=json.loads(marker.read_text())
        data['active_soak']=True;write_json(marker,data)
        clean(self.root,keep=5,apply=True)
        self.assertEqual(len(managed_runs(self.root)),5)
        self.assertTrue(paths[0].exists())
        with self.assertRaises(RuntimeError):clean(self.root,keep=0,apply=True)

    def symlink(self, link, target, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except OSError as error:
            if getattr(error, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege unavailable; exercised inside Linux container")
            raise

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "lab"
        self.root.mkdir()

    def run_folder(self, number):
        ident = f"20260923T1200{number:02d}Z-00000000"
        path = self.root / "runs" / ident
        path.mkdir(parents=True)
        write_json(path / "run.json", {"id": ident, "owner": MARKER})
        (path / "evidence.log").write_text("evidence")
        return path

    def test_preview_and_retention(self):
        paths = [self.run_folder(i) for i in range(7)]
        clean(self.root, keep=5)
        self.assertTrue(all(p.exists() for p in paths))
        clean(self.root, keep=5, apply=True)
        self.assertEqual(set(managed_runs(self.root)), set(paths[2:]))

    def test_unknown_folder_refuses_all_deletion(self):
        known = self.run_folder(0)
        (self.root / "runs" / "user-notes").mkdir()
        with self.assertRaises(RuntimeError):
            clean(self.root, keep=0, apply=True)
        self.assertTrue(known.exists())

    def test_marker_mismatch_refuses_all_deletion(self):
        known = self.run_folder(0)
        bad = self.run_folder(1)
        write_json(bad / "run.json", {"owner": MARKER, "id": "../../outside"})
        with self.assertRaises(RuntimeError):
            clean(self.root, keep=0, apply=True)
        self.assertTrue(known.exists())

    def test_nested_symlink_preserves_external_file(self):
        known = self.run_folder(0)
        outside = Path(self.temp.name) / "design.ato"
        outside.write_text("preserve me")
        self.symlink(known / "link", outside)
        with self.assertRaises(RuntimeError):
            clean(self.root, keep=0, apply=True)
        self.assertEqual(outside.read_text(), "preserve me")

    def test_linked_runs_directory_is_refused(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        self.symlink(self.root / "runs", outside, directory=True)
        with self.assertRaises(RuntimeError):
            clean(self.root, keep=0, apply=True)

    def test_nonempty_unmarked_lab_is_not_adopted(self):
        (self.root / "keep.txt").write_text("keep")
        with self.assertRaises(RuntimeError):
            with lab_lock(self.root):
                self.fail("Should not acquire ownership")

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_windows_junction_is_refused(self):
        import _winapi
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        _winapi.CreateJunction(str(outside), str(self.root / "runs"))
        with self.assertRaises(RuntimeError):
            clean(self.root, keep=0, apply=True)
        self.assertTrue(outside.exists())

    def test_lock_blocks_concurrent_cleanup(self):
        with lab_lock(self.root):
            with self.assertRaises(RuntimeError):
                with lab_lock(self.root):
                    self.fail("Concurrent lock was granted")

    def test_all_removes_runs_only(self):
        with lab_lock(self.root):
            self.run_folder(0)
            clean(self.root, keep=0, apply=True)
            self.assertEqual(managed_runs(self.root), [])
            self.assertEqual((self.root / ".groundlark-lab").read_text(), MARKER)
            self.assertTrue((self.root / ".lock").exists())

    def test_input_allowlist_excludes_generated_trees(self):
        source = Path(self.temp.name) / "source"
        source.mkdir()
        for rel in (".local/legacy/.venv/lib/fake.py", ".lab/runs/report.json", "hw/shared/models/large.step", "hw/logs/old.log", "hw/build/cache.py", "sw/build/schema.binpb", "sw/build/generated.py"):
            path = source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not an input")
        selected = source_files(source)
        self.assertFalse(any(p.exists() for p in selected))

    def test_software_contract_inputs_are_staged(self):
        source = Path(self.temp.name) / "source"
        expected = ["sw/interfaces/buf.yaml", "sw/interfaces/baseline.binpb",
                    "sw/interfaces/proto/groundlark/sensor/v1/sensor.proto",
                    "sw/interfaces/python/groundlark_contract/framing.py",
                    "sw/tests/fixtures/magnetic_boundary.json", "sw/tools/check_interfaces.py",
                    "sw/pi/groundlark/runtime.py", "sw/pi/profiles/daqhat-01.example.json"]
        for rel in expected:
            path = source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture")
        self.assertTrue({source / rel for rel in expected} <= set(source_files(source)))

    def test_hardware_profiles_replay_authored_routing(self):
        for profile in ('full','quick','simulation'):
            self.assertIn('routing-replay',dict(commands(profile)))
        root=Path(self.temp.name)
        self.assertIn(root/'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/groundlark-daqhat-01.ses',source_files(root))

    def test_simulation_excludes_only_explicit_procurement_gate(self):
        from hardware_regressions import without_procurement,PROCUREMENT_GATE
        class Fixture(unittest.TestCase):
            def __init__(self,name):super().__init__();self.name=name
            def id(self):return self.name
        selected,excluded=without_procurement(unittest.TestSuite([
            Fixture('native.geometry'),unittest.TestSuite([Fixture(PROCUREMENT_GATE),Fixture('supplier.pad_fault')])]))
        self.assertEqual([x.id() for x in selected],['native.geometry','supplier.pad_fault'])
        self.assertEqual(excluded,[PROCUREMENT_GATE])
        with self.assertRaises(RuntimeError):without_procurement(unittest.TestSuite([Fixture('native.geometry')]))
        full=dict(commands('full'));simulation=dict(commands('simulation'))
        self.assertEqual(set(full),set(simulation))
        self.assertIn('unittest',full['hardware-regressions'])
        self.assertTrue(simulation['hardware-regressions'][-1].endswith('hardware_regressions.py'))

    def test_assembly_regression_inputs_are_staged_without_release_archives(self):
        source=Path(self.temp.name)/'assembly-source'
        expected=['hw/assembly/groundlark-fpga-hat/daqhat-01-jlcpcb-parts.json',
                  'hw/assembly/groundlark-fpga-hat/daqhat-01-jlcpcb-placement.json',
                  'hw/groundlark-fpga-hat/boards/groundlark-daqhat-01/verification.json',
                  'hw/tests/test_jlcpcb_export_integration.py']
        excluded=['hw/releases/old/BOM-review.csv','.local/placement-review/old.json']
        for rel in expected+excluded:
            path=source/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
        staged=set(source_files(source))
        self.assertTrue({source/rel for rel in expected}<=staged)
        self.assertFalse({source/rel for rel in excluded}&staged)

    def test_skylark_firmware_inputs_exclude_generated_builds(self):
        source=Path(self.temp.name)/'firmware-source'
        expected=['sw/skylark/firmware/core.c','sw/skylark/firmware/platform.h',
                  'sw/skylark/firmware/stm32f072cb.ld','sw/skylark/firmware/Makefile',
                  'sw/skylark/tests/native.c','sw/skylark/tests/boot.c','sw/tests/test_skylark.py']
        excluded=['sw/skylark/build/native.c','sw/skylark/build/firmware.json','sw/skylark/build/skylark.elf']
        for rel in expected+excluded:
            path=source/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
        staged=set(source_files(source))
        self.assertTrue({source/rel for rel in expected}<=staged)
        self.assertFalse({source/rel for rel in excluded}&staged)


if __name__ == "__main__":
    unittest.main()
