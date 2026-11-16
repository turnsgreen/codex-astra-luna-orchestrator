# GPT and Antigravity CLI

The Codex main session plans and integrates. The local `agy` MCP server calls
Antigravity CLI with Gemini 3.8 Flash for exploration, research, implementation,
and test analysis. A separate native Codex reviewer reads the actual diff.

## Install and run

1. Install a current local Codex CLI, Python 3.10+, and Antigravity CLI. Use
   `agy models` in your normal terminal to confirm you are signed in and can
   select `gemini-3.8-flash-medium`.
2. Run `setup.ps1` on Windows or `setup.sh` on macOS/Linux. Select **7** or
   `gpt-agy` for the target repository. For an existing Codex project, merge
   the settings you still need and remove older orchestration instructions
   that would route the same roles to native Codex agents.
3. In the target repository root, with your preferred Python environment active,
   install the bridge dependency and start Codex in that same environment.

   ```text
   python -m pip install -r .codex/agy/requirements.txt
   codex
   ```

   Trust the project when prompted after reviewing its local MCP configuration.
   For unattended use, arrange approval for `agy.run_role` in the intended
   trusted checkout. For example, for this smoke test use the temporary override
   `-c 'mcp_servers.agy.tools.run_role.approval_mode="approve"'` with `codex exec`.
   This allows the configured tool to edit the checkout and run its test suites.
4. Select any available GPT with Codex's model picker or `codex -m <model>`.
   The reviewer inherits the selected model and effort when neither the role,
   the spawn request, nor your `[agents]` defaults supply overrides. Set `model`
   in `.codex/agents/reviewer.toml` to select a separate GPT for review.

For a different Antigravity model or binary, set `AGY_MODEL` or `AGY_EXECUTABLE`
in the server's environment. You can add the following to `.codex/config.toml`
with values valid for your machine and account.

```toml
[mcp_servers.agy.env]
AGY_MODEL = "gemini-3.8-flash-medium"
```

## Tests and permissions

Put the test commands you want to make available in `.codex/agy/tests.json`.
Each command is an argument array run in the checkout with no shell expansion.

```json
{
  "unit": ["python", "-m", "unittest", "-v"]
}
```

The `tester` tool runs the named command locally and passes its recorded exit
status and output to Gemini for analysis. `test.status` and `test.exit_code`
report the test process outcome independently of Gemini's reply. Only configure
commands and test code you trust to execute locally. The test output is included
in the Gemini prompt, so use suites whose output you can share with Google.

The local worker applies edits in the checkout where the profile is installed.
Use a separate worktree for delegation when you have other pending edits. Keep
the bridge inside the checkout you intend to use. The bridge sets Antigravity's
per-session permissions to deny shell, external MCP and URL execution in all
roles, and file writes in read-only roles. The worker can use native file tools.
These are Antigravity tool permissions. An OS-level isolation boundary depends
on the local environment. Each bridge instance services one role call at a time.

## Shortest end-to-end check

In a disposable Git checkout, commit a small module with one known failing
unit test. Install this profile in that checkout and configure the test suite.
Start Codex from its root and use a bounded prompt such as:

```text
$gpt-agy
Delegate the fix to the agy worker. Change only the module under test.
Then use the agy tester with suite unit. Report the recorded exit code and
test count. Ask the native reviewer to inspect the actual Git diff in an
independent context, wait for its verdict, and summarize all three stages.
```

Confirm that the worker produced the expected diff, the recorded result is
`test.exit_code = 0`, and the independent reviewer inspected the changed code.
For a manual tool check, `codex mcp get agy` shows the loaded server configuration.
