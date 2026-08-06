# Verfeinert

Verfeinert is an open-source scientific framework for quantum ansatz generation,
analysis, evolution, and reproducible workflow orchestration.

## Authors
Developed by Víctor Martín Kruglova

## Citation
If you use Verfeinert in academic work, please cite the software according to the citation metadata provided in `CITATION.cff`.
[View citation information](CITATION.cff)

The citation file is also available through GitHub's "Cite this repository" functionality.

## Namespace

```text
verfeinert
  core
  ansatz_generator
  ansatz_analyzer
  ansatz_evolver
  workflow
```

## Current Capabilities

- canonical JSON schemas for candidates, staged packages, analysis results,
  experiments, and evolution runs;
- packaged schema resources available after installation;
- standardized ansatz generation and canonical Candidate/StagedPackage export;
- analyzer structural cost, Pareto/ranking foundations, and v1-aligned
  expressibility/trainability metric implementations;
- reference-based evolver population, mutation, selection, and EvolutionRun
  export foundations;
- workflow runner and researcher-facing CX-01 and MIXT-5G reproducibility
  examples.

## Install For Development

From this directory:

```bash
python -m pip install -e ".[dev]"
```

The scientific metric reference implementation requires NumPy and PennyLane as
runtime dependencies. Visualization support is optional:

```bash
python -m pip install -e ".[dev,visualization]"
```

## Validate

```bash
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib-verfeinert python -m unittest discover -s tests -q
python -m pytest tests -q
```

`pytest` is part of the dev extra and is required in CI. If it is not installed
in a local environment, the stdlib `unittest` suite is the minimum supported
check.

## Examples

```bash
python examples/CX01_reproduction/scripts/run_cx01_reproduction.py \
  --profile smoke \
  --output-root /tmp/verfeinert-cx01

python examples/MIXT5G_reproduction/scripts/run_mixt5g_reproduction.py \
  --profile smoke \
  --output-root /tmp/verfeinert-mixt5g
```

Generated artifacts must be written under caller-provided output roots and
should not be committed.

## External Validation

```bash
python scripts/validate_external_install.py \
  --output-root /tmp/verfeinert-external-validation
```

This creates a temporary virtual environment, installs the package, checks
public imports and packaged schemas, and runs both smoke reproduction examples.

## License

Verfeinert is licensed under the Apache License, Version 2.0. See
[`LICENSE`](LICENSE).
