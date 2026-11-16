import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from test_profiles import run_installer


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "gpt-agy"
SERVER = PROFILE / "codex" / "agy" / "server.py"


class GPTAGYProfileTests(unittest.TestCase):
    def test_root_model_is_selectable_and_reviewer_pins_sol_medium(self):
        config = tomllib.loads((PROFILE / "codex" / "config.toml").read_text())
        self.assertNotIn("model", config)
        self.assertNotIn("default_subagent_model", config["agents"])
        reviewer = tomllib.loads((PROFILE / "codex" / "agents" / "reviewer.toml").read_text())
        self.assertEqual(reviewer["model"], "gpt-6.1-sol")
        self.assertEqual(reviewer["model_reasoning_effort"], "medium")
        self.assertEqual(reviewer["sandbox_mode"], "read-only")

    def test_installers_install_the_bridge_and_profile_instructions(self):
        installers = []
        if shutil.which("sh"):
            installers.append(["sh", str(ROOT / "setup.sh")])
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell:
            installers.append([powershell, "-NoProfile", "-File", str(ROOT / "setup.ps1")])
        if not installers:
            self.skipTest("no supported shell available")
        for installer in installers:
            with self.subTest(installer=installer[0]), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "project"
                target.mkdir()
                exit_code, stdout, stderr = run_installer(installer, target, "7")
                self.assertEqual(exit_code, 0, stdout + stderr)
                self.assertEqual((target / "AGENTS.md").read_text(), (PROFILE / "AGENTS.md").read_text())
                self.assertEqual((target / ".codex/agy/server.py").read_text(), SERVER.read_text())
                self.assertTrue((target / ".agents/skills/gpt-agy/SKILL.md").is_file())


@unittest.skipUnless(importlib.util.find_spec("mcp"), "install the bridge dependencies")
class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("agy_bridge_under_test", SERVER)
        cls.bridge = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.bridge
        with patch.dict(os.environ):
            os.environ.pop("AGY_MODEL", None)
            spec.loader.exec_module(cls.bridge)

    def mock_agy_result(self, **fields):
        result = {"status": "SUCCESS", "response": "Gemini reply", **fields}
        output = json.dumps({"event": "result", "result": result})
        return subprocess.CompletedProcess([], 0, stdout=output, stderr="")

    def test_tester_preserves_an_actual_failure_even_when_gemini_replies(self):
        evidence = {"status": "failed", "exit_code": 3}
        with patch.object(self.bridge, "run_test_suite", return_value=evidence), patch.object(
            self.bridge.subprocess, "run", return_value=self.mock_agy_result()
        ) as run:
            result = self.bridge.invoke_agy("tester", "Inspect the failure.", "unit")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["test"], evidence)
        self.assertEqual(result["requested_model"], "gemini-3.8-flash-high")
        message = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(message["event"], "user")
        self.assertIn('"exit_code": 3', message["message"]["content"])

    def test_reports_denied_actions_even_when_agy_exits_zero(self):
        denied = [{"tool": "write_to_file"}]
        with patch.object(self.bridge.subprocess, "run", return_value=self.mock_agy_result(denied_actions=denied)):
            result = self.bridge.invoke_agy("explorer", "Inspect a file.", None)
        self.assertEqual(result["status"], "denied_actions")
        self.assertEqual(result["denied_actions"], denied)

    def test_test_suite_has_its_own_process_exit_code(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(self.bridge, "BRIDGE", Path(directory)):
            config = Path(directory) / "tests.json"
            config.write_text(json.dumps({"fails": [sys.executable, "-c", "raise SystemExit(7)"]}))
            result = self.bridge.run_test_suite("fails")
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual(result["status"], "failed")
