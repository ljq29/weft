# Changelog

## Unreleased

### Added

- Workflow DAG engine, frozen Runs, typed ports, caching, loops and isolated Worker pools.
- React canvas, REST/WS execution, Excel integration and real CSV closed loops.
- LLMProxy, LLM Call, Agent Loop, authorized NodeTool, chat and audit traces.
- NoneSandbox controlled shadow tools, change review, conflict detection and approval.
- Schedule/file/HTTP triggers, HTTP Response and trigger health.
- Portable pack/unpack with secret scanning, preflight and safe extraction.
- Metanode editing, comments, Markdown notes, run history and retention cleanup.
- Memory nodes, Rule Engine, trusted Worker Shell Command and Excel Run Macro.
- Resource preflight, user settings, rotating JSON logs, doctor and owned cleanup.
- Production SPA serving from `weft serve`.

### Validation boundaries

- Sandboxie win_real and real-model manual checks remain required before release.
- Excel Run Macro still needs a real successful macro invocation check.
- A formal release requires all roadmap release gates; this entry does not declare a version or claim those gates are complete.
