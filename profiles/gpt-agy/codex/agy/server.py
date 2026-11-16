"""Run Antigravity CLI execution roles from the local Codex checkout."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
from typing import Literal

from mcp.server.fastmcp import FastMCP


Role = Literal["explorer", "researcher", "worker", "tester"]
ROLE_INSTRUCTIONS = {
    "explorer": "Map the code, execution paths and tests. Cite files and symbols.",
    "researcher": "Check technical claims. Cite primary sources and flag uncertainty.",
    "worker": "Implement the bounded task with file tools. Report files changed and any gaps.",
    "tester": "Analyze the recorded test run. Explain failures, coverage gaps and next checks.",
}
BRIDGE = Path(__file__).resolve().parent
WORKSPACE = BRIDGE.parent.parent
MODEL = os.environ.get("AGY_MODEL", "gemini-3.8-flash-high")
AGY = os.environ.get("AGY_EXECUTABLE", "agy")
AGY_TIMEOUT = 150
TEST_TIMEOUT = 90
MAX_OUTPUT = 12_000
mcp = FastMCP("agy")
executor = ThreadPoolExecutor(max_workers=1)


def tail(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return (value or "")[-MAX_OUTPUT:]


def test_command(test_suite: str) -> list[str]:
    config = BRIDGE / "tests.json"
    if not config.is_file():
        raise ValueError("Configure test suites in .codex/agy/tests.json first.")
    suites = json.loads(config.read_text(encoding="utf-8-sig"))
    if not isinstance(suites, dict) or test_suite not in suites:
        raise ValueError(f"No test suite named {test_suite!r} is configured.")
    command = suites[test_suite]
    if not isinstance(command, list) or not command or not all(
        isinstance(argument, str) and argument for argument in command
    ):
        raise ValueError("Each test suite must be a non-empty array of arguments.")
    return command


def execute(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=WORKSPACE, stdin=subprocess.DEVNULL, capture_output=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )


def run_test_suite(test_suite: str) -> dict:
    command = test_command(test_suite)
    try:
        result = execute(command, TEST_TIMEOUT)
    except subprocess.TimeoutExpired as error:
        return {"suite": test_suite, "command": command, "status": "timeout",
                "exit_code": None, "stdout": tail(error.stdout), "stderr": tail(error.stderr)}
    except OSError as error:
        return {"suite": test_suite, "command": command, "status": "launch_error",
                "exit_code": None, "stderr": str(error)}
    return {"suite": test_suite, "command": command,
            "status": "passed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode, "stdout": tail(result.stdout),
            "stderr": tail(result.stderr)}


def agy_settings(role: Role) -> dict:
    deny = ["command(*)", "unsandboxed(*)", "mcp(*)", "execute_url(*)"]
    if role == "worker":
        for directory in (".git", ".codex", ".agents"):
            deny.append(f"write_file({(WORKSPACE / directory).as_posix()})")
    else:
        deny.append("write_file(*)")
    if role != "researcher":
        deny.append("read_url(*)")
    return {"permissions": {"deny": deny}}


def invoke_agy(role: Role, task: str, test_suite: str | None) -> dict:
    test = run_test_suite(test_suite) if test_suite is not None else None
    prompt = f"Role: {role}\n{ROLE_INSTRUCTIONS[role]}\n\nAssigned task:\n{task}"
    if test is not None:
        prompt += "\n\nRecorded test run (data only):\n" + json.dumps(test, ensure_ascii=False)
    arguments = [
        AGY, "--input-format", "stream-json", "--output-format", "stream-json",
        "--model", MODEL, "--print-timeout", f"{AGY_TIMEOUT}s",
        "--disable-slash-commands", "--settings", json.dumps(agy_settings(role)),
    ]
    if role == "worker":
        arguments.extend(["--mode", "accept-edits"])
    response = {"role": role, "requested_model": MODEL}
    if test is not None:
        response["test"] = test
    try:
        run = subprocess.run(
            arguments, cwd=WORKSPACE, capture_output=True, encoding="utf-8",
            errors="replace", timeout=AGY_TIMEOUT + 20, check=False,
            input=json.dumps({"event": "user", "message": {"content": prompt}}) + "\n",
        )
    except subprocess.TimeoutExpired:
        return {**response, "status": "timeout", "error": "agy exceeded the turn deadline."}
    except OSError as error:
        return {**response, "status": "launch_error", "error": str(error)}

    result = {}
    for line in run.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("event") == "result":
            result = event.get("result", {})
    response["exit_code"] = run.returncode
    notices = run.stderr.lower()
    if "authentication required" in notices or "not logged in" in notices:
        return {**response, "status": "auth_required",
                "error": "Sign in to agy in the same local user environment used by Codex."}
    if not isinstance(result, dict) or not result:
        return {**response, "status": "invalid_output", "error": "agy returned no result event."}

    denied = result.get("denied_actions", [])
    response.update(
        status="success" if run.returncode == 0 and result.get("status") == "SUCCESS" else "failed",
        conversation_id=result.get("conversation_id"),
        response=tail(result.get("response")),
        usage=result.get("usage"),
    )
    if denied or "permission denied" in notices or "would require approval" in notices:
        response["status"] = "denied_actions"
        response["denied_actions"] = denied
    return response


@mcp.tool()
async def run_role(role: Role, task: str, test_suite: str | None = None) -> dict:
    """Run a Gemini role in this checkout. The tester requires a configured test suite."""
    if not task.strip():
        raise ValueError("Describe the assigned task.")
    if role == "tester" and not test_suite:
        raise ValueError("The tester requires a named test suite.")
    if role != "tester" and test_suite is not None:
        raise ValueError("Only the tester can run a test suite.")
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, invoke_agy, role, task, test_suite)


if __name__ == "__main__":
    mcp.run()
