# WorkloadAnalyzer

A Windows desktop app to track work time by category and role.

## Features

- Manual time tracking with start/stop/pause controls
- System tray icon with category switching and pause/resume
- Floating always-on-top widget for quick category switching
- Role and category management via settings window
- CSV/XLSX export with configurable duration rounding
- Reports with donut chart visualization
- (Phase 2, planned) Outlook calendar auto-detection

## Requirements

- Python 3.11+
- Windows 10+

Install dependencies:

```
pip install -e ".[dev]"
```

## Quick Start

1. Clone the repository
2. Install dependencies: `pip install -e ".[dev]"`
3. Launch the app: `python -m workload_analyzer`

## Development

Run tests:

```
pytest tests/ -q
```

Lint:

```
ruff check src/
```

Format:

```
black src/ tests/
```

## Architecture

- **Layout**: src-layout with source in `src/workload_analyzer/`, tests in `tests/`
- **Database**: SQLite stored at `%APPDATA%\WorkloadAnalyzer\workload.db`, opened in
  autocommit mode with explicit `BEGIN`/`COMMIT` for atomic multi-step operations
- **Layers**: models → repository → tracker/export → UI (PyQt6)

## Project Status

MVP complete (Tasks 1–17). Phase 2 (Outlook calendar integration) is planned.
