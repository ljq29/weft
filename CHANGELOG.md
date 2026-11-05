# Changelog

## Unreleased

## [0.3.0] - 2026-11-05

### Added

- Add a built-in demo gallery with independent CSV sales, table transformation and LLM text workflows, including portable data, locked dependencies and local Worker/SDK wheels.
- Synchronize a demo's isolated environment before opening it so the CSV and table examples can run immediately.

### Fixed

- Use left-button drag for node marquee selection and middle-button drag for canvas panning while retaining Space+drag navigation.
- Force Worker JSON-RPC standard streams to UTF-8 so Chinese node parameters and table values survive real subprocess execution on Windows.

### Verified

- `poe check` passed with 186 backend unit tests and 23 frontend tests.
- Four Playwright tests passed for mouse navigation, demo creation, real CSV/table execution and LLM placeholder setup.
- CSV and table demo ZIPs passed fresh unpack, environment synchronization and real execution; demo resources were also loaded directly from a built wheel.
- Seventeen local Windows real/benchmark tests passed with real Excel, Sandboxie and pi.
- The portable ZIP passed clean bootstrap without host Python/uv, cached offline execution, authenticated service and frontend acceptance.
- Real LLM execution remains subject to user-supplied OpenAI-compatible settings; no API key is bundled.

## [0.2.2] - 2026-11-05

### Fixed

- Serve the new SVG logo and favicon as image assets instead of the SPA HTML fallback in packaged installations.
- Extend portable acceptance to validate both brand assets and their MIME types.

### Verified

- GitHub Release run `41962241669` and main CI run `41962239168` passed all automated gates, including integration tests, Playwright E2E and clean portable acceptance.
- Seventeen local Windows real/benchmark tests passed with real Excel, Sandboxie and pi.
- Downloaded Release assets matched their API SHA-256 hashes; the three wheels matched local builds, and the downloaded ZIP passed bootstrap, offline CSV, service and browser UI acceptance with visible SVG branding.

## [0.2.1] - 2026-11-05

### Added

- Add an original woven Weft logo, SVG favicon and a dependency-free interface icon system with categorized node icons.

### Changed

- Restyle the workflow editor with a Dify-inspired light workspace, refined node cards, dot-grid canvas and responsive three-column layout.
- Unify parameter forms, run logs, history, chat, settings, port previews, audit trails, confirmations and change review with consistent spacing, states and accessible controls.
- Cap the initial canvas fit at 100% zoom and preserve all existing workflow interactions and API contracts.

## [0.2.0] - 2026-11-05

### Changed

- Replace the Nuitka standalone executable and duplicated bundled Python with pure-Python wheels and a CMD bootstrap launcher.
- Use the bundled uv to download managed CPython and locked production dependencies into versioned environments under `%LOCALAPPDATA%/Weft` on first run.
- Reduce `weft-windows-x64.zip` from approximately 292 MiB to 15 MB before bootstrap; Python and locked dependencies are downloaded once and reused.
- Add `--china` with Tsinghua PyPI and gh-proxy Python downloads, custom package/Python mirrors, cached `--offline` execution and `--repair` bootstrap options.
- Run clean bootstrap, real CSV, cached offline, authenticated service and frontend acceptance in both CI and the tag-driven Release workflow.

### Removed

- Remove the Nuitka build dependency, compiled service executable, bundled CPython and duplicate Polars/Arrow runtime files from the distribution.

## [0.1.1] - 2026-11-04

### Added

- Nuitka standalone `weft.exe` and `weft-windows-x64.zip` portable distribution.
- Bundled Python workflow runtime, `uv.exe` and same-version local wheels for machines without a Python development environment.
- Portable acceptance that executes a real CSV workflow and validates the authenticated service and frontend with no host Python or uv on PATH.

### Changed

- ExcelWorker, Sandboxie helpers, doctor and workflow environment setup now select the bundled Python and uv when running from the portable distribution.

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
