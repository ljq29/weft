# Changelog

## Unreleased

## [0.1.0] - 2026-11-04

### Added

- Workflow DAG engine, frozen Runs, typed ports, caching, loops and isolated Worker pools.
- React canvas, REST/WS execution, Excel integration and real CSV closed loops.
- LLMProxy, LLM Call, Agent Loop, authorized NodeTool, chat and audit traces.
- NoneSandbox controlled shadow tools, change review, conflict detection and approval.
- Sandboxie-Plus isolated Runs, network restrictions, host COM isolation and audited approvals.
- Schedule/file/HTTP triggers, HTTP Response and trigger health.
- Portable pack/unpack with secret scanning, preflight and safe extraction.
- Metanode editing, comments, Markdown notes, run history and retention cleanup.
- Memory nodes, Rule Engine, trusted Worker Shell Command and Excel Run Macro with real return-value validation.
- Resource preflight, user settings, rotating JSON logs, doctor and owned cleanup.
- Production SPA serving from `weft serve`.
- Windows-only GitHub Actions CI and tag-driven GitHub Release with three wheel assets.

### Verified

- GitHub Actions run `41788943113`: lint/type checks, 181 backend unit tests, 36 integration tests, 23 frontend tests, 11 Playwright E2E tests and wheel builds passed on Windows.
- Twelve `win_real` tests passed with real Excel and Sandboxie; successful Excel Macro return values and missing-macro errors were both verified, with no Excel or test Box left running.
- Real OpenAI-compatible model calls, Agent Loop tool calls and the Pi/LLMProxy sandbox path passed without exposing the original API key.
- Controlled same-machine Excel, Arrow, scheduler, WebSocket, cold-start and cache-materialization benchmarks passed.

### Remaining v1 acceptance boundaries

- This release does not mark `T7.10` complete: second-machine handoff, timed manual UI checks, migration of at least three real scripts and adoption by at least one colleague remain tracked separately.
