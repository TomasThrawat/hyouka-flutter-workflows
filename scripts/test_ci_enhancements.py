#!/usr/bin/env python3
"""Offline regression coverage for CI helper tools; standard library only."""
import importlib.util, json, tempfile, unittest, zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location("ci_enhancements",Path(__file__).with_name("ci_enhancements.py"))
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class ImpactTests(unittest.TestCase):
 def test_push_uses_full_suite(self): self.assertEqual(mod.change_impact(["lib/math.dart"],event="push",targeted=True)["mode"],"full")
 def test_related_test_is_selected(self):
  with tempfile.TemporaryDirectory() as d:
   t=Path(d)/"test"; t.mkdir(); (t/"math_test.dart").write_text("")
   r=mod.change_impact(["lib/math.dart"],event="pull_request",targeted=True,test_root=t)
   self.assertEqual(r["mode"],"targeted"); self.assertEqual(r["target_tests"],["test/math_test.dart"])
 def test_unknown_mapping_is_full_suite(self):
  with tempfile.TemporaryDirectory() as d: self.assertEqual(mod.change_impact(["lib/orphan.dart"],event="pull_request",targeted=True,test_root=Path(d))["mode"],"full")
 def test_lockfile_change_is_full_suite(self): self.assertEqual(mod.change_impact(["pubspec.lock"],event="pull_request",targeted=True)["mode"],"full")
 def test_workflow_change_is_full_suite(self): self.assertEqual(mod.change_impact([".github/workflows/ci.yml"],event="pull_request",targeted=True)["mode"],"full")
 def test_docs_only_can_skip(self): self.assertEqual(mod.change_impact(["README.md","docs/usage.md"],event="pull_request",targeted=True)["mode"],"skip")
 def test_coverage_gate_forces_full_suite(self): self.assertEqual(mod.change_impact(["lib/math.dart"],event="pull_request",targeted=True,force_full=True)["mode"],"full")
 def test_unmapped_runtime_file_is_full(self): self.assertEqual(mod.change_impact(["lib/data.dart"],event="pull_request",targeted=True,test_root=Path("/nonexistent"))["mode"],"full")

class LogTests(unittest.TestCase):
 def test_signatures_deduplicate_locations_and_ignore_known_noise(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"x.log"; p.write_text("warning: lib/a.dart:3:4: lint\nwarning: lib/a.dart:9:2: lint\nCaught exception: Already watching path: /tmp/android\n")
   sig=mod.warning_signatures([p]); self.assertEqual(len(sig),1); self.assertNotIn("Already watching",sig[0])
 def test_logs_classified(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d); (r/"x.log").write_text("::error::oops\nwarning: noisy\ninfo • use const\nCould not resolve host\nCaught exception: Already watching path: /x/android\n")
   import argparse
   out=r/"out"; self.assertEqual(mod.cmd_logs(argparse.Namespace(log_root=d,output_dir=str(out),baseline="",fail_on_new_warnings=False)),0)
   data=json.loads((out/"log-analysis.json").read_text())
   self.assertEqual(data["counts"]["errors"],1); self.assertEqual(data["counts"]["warnings"],1); self.assertEqual(data["counts"]["info_lints"],1)
   self.assertEqual(data["counts"]["infrastructure"],1); self.assertEqual(data["counts"]["known_flutter_tool_noise"],1)
 def test_new_warnings_gate_only_after_baseline(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d); (r/"x.log").write_text("warning: new thing\n")
   import argparse
   args=argparse.Namespace(log_root=d,output_dir=str(r/"out"),baseline=str(r/"missing.json"),fail_on_new_warnings=True)
   self.assertEqual(mod.cmd_logs(args),0)
   base=r/"baseline.json"; base.write_text('{"signatures":[]}')
   args.baseline=str(base); args.output_dir=str(r/"out2"); self.assertEqual(mod.cmd_logs(args),1)

class ApkTests(unittest.TestCase):
 def _make(self,path):
  with zipfile.ZipFile(path,"w") as z:
   z.writestr("lib/arm64-v8a/libapp.so",b"binary"); z.writestr("classes.dex",b"dex"); z.writestr("assets/large.dat",b"x"*1000)
 def test_metadata_permissions_and_abi(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); apk=root/"app.apk"; self._make(apk); badging=root/"badging.txt"
   badging.write_text("package: name='com.example' versionCode='4' versionName='1.2'\nsdkVersion:'23'\ntargetSdkVersion:'35'\nuses-permission: name='android.permission.INTERNET'\n")
   import argparse
   a=argparse.Namespace(apk=str(apk),badging=str(badging),expected_abi="arm64-v8a",max_size_mb=0,max_entry_size_mb=0,forbid_permissions="",output_dir=str(root/"out"))
   self.assertEqual(mod.cmd_apk(a),0); data=json.loads((root/"out"/"apk-metadata.json").read_text())
   self.assertEqual(data["metadata"]["application_id"],"com.example"); self.assertEqual(data["native_abis"],["arm64-v8a"])
   self.assertIn("android.permission.INTERNET",data["permissions"])
 def test_wrong_abi_fails(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); apk=root/"app.apk"; self._make(apk)
   import argparse
   self.assertEqual(mod.cmd_apk(argparse.Namespace(apk=str(apk),badging="",expected_abi="x86_64",max_size_mb=0,max_entry_size_mb=0,forbid_permissions="",output_dir=str(root/"out")),),1)
 def test_forbidden_permission_fails(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); apk=root/"app.apk"; self._make(apk); badging=root/"badging.txt"
   badging.write_text("package: name='com.example' versionCode='4' versionName='1.2'\n" + "uses-permission: name='android.permission.CAMERA'\n")
   import argparse
   a=argparse.Namespace(apk=str(apk),badging=str(badging),expected_abi="arm64-v8a",max_size_mb=0,max_entry_size_mb=0,forbid_permissions="android.permission.CAMERA",output_dir=str(root/"out"))
   self.assertEqual(mod.cmd_apk(a),1)
 def test_missing_native_abi_fails_expected_abi_gate(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); apk=root/"app.apk"
   with zipfile.ZipFile(apk,"w") as z: z.writestr("classes.dex",b"dex")
   import argparse
   a=argparse.Namespace(apk=str(apk),badging="",expected_abi="arm64-v8a",max_size_mb=0,max_entry_size_mb=0,forbid_permissions="",output_dir=str(root/"out"))
   self.assertEqual(mod.cmd_apk(a),1)
 def test_invalid_archive_fails(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); apk=root/"bad.apk"; apk.write_bytes(b"not zip")
   import argparse
   self.assertEqual(mod.cmd_apk(argparse.Namespace(apk=str(apk),badging="",expected_abi="",max_size_mb=0,max_entry_size_mb=0,forbid_permissions="",output_dir=str(root/"out")),),2)

class QualityTests(unittest.TestCase):
 def test_coverage_gate_fails_below_threshold(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); (root/"coverage.json").write_text('{"coverage_percent":74.5}')
   import argparse
   a=argparse.Namespace(output_dir=str(root/"out"),coverage_json=str(root/"coverage.json"),apk=str(root/"missing.apk"),log_analysis="",min_coverage=75,max_apk_size=0,fail_on_new_warnings=False)
   self.assertEqual(mod.cmd_quality(a),1)
 def test_zero_threshold_disables_missing_coverage(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); import argparse
   a=argparse.Namespace(output_dir=str(root/"out"),coverage_json=str(root/"missing.json"),apk=str(root/"missing.apk"),log_analysis="",min_coverage=0,max_apk_size=0,fail_on_new_warnings=False)
   self.assertEqual(mod.cmd_quality(a),0)

if __name__=="__main__": unittest.main(verbosity=2)
