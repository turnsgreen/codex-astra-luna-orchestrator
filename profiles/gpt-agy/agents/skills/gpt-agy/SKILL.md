---
name: gpt-agy
description: Delegate bounded code exploration, research, implementation and test analysis to local Antigravity CLI, then review changes with a separate Codex reviewer. Use for multi-step coding work or explicit requests to use agy.
---

# GPT and Antigravity orchestration

The Codex main session plans, delegates, reviews the evidence, and integrates
the result. Invoke the `agy` MCP tool directly for these roles:

- `explorer` maps the implementation and tests and cites files and symbols.
- `researcher` checks version-specific facts and cites sources it can access.
- `worker` implements a bounded change in the current checkout. Before it
  runs, check the Git status and use an isolated worktree when other changes
  are present or multiple workers need to write in parallel. Assign files and
  acceptance criteria explicitly.
- `tester` analyzes the results of a configured test suite. Pass its name as
  `test_suite`. The bridge runs the configured command before asking Gemini to
  analyze the real output. Check `test.exit_code` and `test.status` yourself.

Give each call the relevant objective, file scope, and expected result. Check
the actual resulting diff and report tool errors or denials. Use the native
Codex `reviewer` role in a fresh context after implementation. Give it the
requirements and diff scope and wait for its findings before integrating.
Resolve material findings and rerun affected tests before finishing.
