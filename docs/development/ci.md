# Continuous Integration

Verfeinert CI validates the standalone repository checkout, where
`pyproject.toml`, `verfeinert/`, `schemas/`, `examples/`, and `tests/` live at
the repository root.

## Base Validation

The base matrix runs on Python 3.11 and 3.12. It installs `.[dev]`, parses all root JSON Schemas, checks public imports and packaged schemas, runs the full `unittest` suite, runs `pytest`, and executes CX-01 and MIXT-5G smoke examples with output roots under the GitHub runner temp directory.

Scientific metric reference tests run in the base job because NumPy and PennyLane are required runtime dependencies after Phase 8.0.1.

## Visualization Validation

The visualization job installs `.[dev,visualization]` and runs the visualization test slice. Plotting remains optional for users, but the optional package path is validated in CI.

## Local Equivalent

From the repository root:

```bash
python -m pip install ".[dev]"
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib-verfeinert python -m unittest discover -s tests -q
python -m pytest tests -q
```

Contributors should keep generated outputs, local environments, caches, and
notebook execution artifacts out of commits. Example workflows should use
caller-owned output roots.
