# GPT and Antigravity orchestration

For multi-step coding tasks that benefit from delegation, use the `gpt-agy`
skill. The Codex main session owns task decomposition, integration, and final
verification. Use the `agy` MCP tool for execution roles and the Codex
`reviewer` agent for an independent review of the actual diff.
