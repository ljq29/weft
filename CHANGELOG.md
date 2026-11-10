# Changelog

## Unreleased

## [0.5.0] - 2026-11-10

### Added

- Add `weft serve --gui` to host the same authenticated SPA in a Microsoft Edge WebView2 desktop window through pywebview, with loopback-only startup and graceful service shutdown when the window closes.
- Report the optional WebView2 Runtime in `weft doctor` and include the Windows GUI dependency in locked wheel and portable installations.
- Add declaration-driven upstream output selection and a visible Test up to this node action to the node inspector.
- Add a current-Run output workspace with node, port, type and table-shape summaries alongside the existing log and history views.

### Changed

- Include immutable per-Run `ValueRef` outputs and cache provenance in `node.finished` events, and restore the same output references from REST snapshots and reconnect baselines.
- Keep connection validation and execution rules in the backend; the upstream picker only presents compatible, acyclic candidates.
- Update the built-in demos to locked same-version Worker and SDK wheels.

### Verified

- Five focused desktop/CLI tests, eight engine scheduler tests and 65 frontend Vitest tests passed during implementation.
- `poe check` passed with 245 backend unit/contract tests and 65 frontend tests; 37 integration and 26 Playwright E2E tests also passed.
- Seventeen Windows real/benchmark tests passed with Excel, Sandboxie and pi.
- WebView2 opened the authenticated UI and closed with graceful lifespan shutdown in both the development environment and the portable bundle; startup tokens were absent from server logs.
- Portable clean bootstrap, cached offline workflow/repair, authenticated service API and SPA acceptance passed without host Python or uv.
- This entry does not mark T7.10 or its remaining manual adoption gates complete.

## [0.4.0] - 2026-11-05

### Added

- Add Chinese supplementary names for all built-in nodes, bilingual search and generated node specifications.
- Add recursive schema-driven parameter controls for enums, nested objects, record arrays, key-value maps and common built-in nodes.
- Add OpenAI-compatible provider presets, draft connection testing, model discovery and structured runtime settings.
- Add a visible WebSocket connection indicator with authenticated reconnection, backoff, immediate retry and REST baseline recovery.

### Changed

- Establish readable typography, spacing, control and panel sizing tokens, and split styles by UI region without changing canvas zoom semantics.
- Connect every built-in demo from Trigger through all business nodes; safely replace only a matching demo copy after staged environment synchronization.
- Split editor document, command, canvas and overlay orchestration into focused hooks and replace native browser dialogs with accessible Weft dialogs.
- Preserve local edits on revision conflicts until the user explicitly reloads, and apply backend validation without overwriting execution state.
- Remove the unused TanStack Query dependency and retain the lightweight API client with structured errors.

### Fixed

- Synchronize React Flow handle measurements so loaded demo edges render reliably.
- Format Arrow BigInt values safely in inline tables and write Run metadata atomically for concurrent history readers.
- Preserve the selected node when reloading the same workflow so the inspector remains synchronized.

### Verified

- `poe check` passed with 240 backend unit/contract tests and 64 frontend tests; 37 backend integration tests also passed.
- All 26 Playwright E2E tests passed, including demo replacement, structured forms, dialogs, 401/409 recovery and real WebSocket reconnection with baseline restoration.
- Windows real Excel/Sandboxie/pi tests were not rerun for this UI-focused release; existing `win_real` acceptance remains recorded in earlier releases.

## [0.3.0] - 2026-11-05

### Added

- Add a built-in demo gallery with independent CSV sales, table transformation and LLM text workflows, including portable data, locked dependencies and local Worker/SDK wheels.
- Synchronize a demo's isolated environment before opening it so the CSV and table examples can run immediately.

### Fixed

- Use left-button drag for node marquee selection and middle-button drag for canvas panning while retaining Space+drag navigation.
- Force Worker JSON-RPC standard streams to UTF-8 so Chinese node parameters and table values survive real subprocess execution on Windows.

### Verified

- GitHub Release run `41982811856` and main CI run `41982726654` passed all automated gates, including full integration tests, 15 Playwright E2E tests and clean portable acceptance.
- `poe check` passed with 186 backend unit tests and 23 frontend tests.
- Four Playwright tests passed for mouse navigation, demo creation, real CSV/table execution and LLM placeholder setup.
- CSV and table demo ZIPs passed fresh unpack, environment synchronization and real execution; demo resources were also loaded directly from a built wheel.
- Seventeen local Windows real/benchmark tests passed with real Excel, Sandboxie and pi.
- The portable ZIP passed clean bootstrap without host Python/uv, cached offline execution, authenticated service and frontend acceptance.
- All four downloaded Release assets matched their API SHA-256 hashes; the downloaded Windows ZIP also passed local bootstrap, offline CSV, service and frontend acceptance.
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
