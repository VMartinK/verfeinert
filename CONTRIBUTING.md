# Contributing

Verfeinert is an open-source research framework for the generation, analysis,
and evolution of physics-informed variational quantum ansätze.

Contributions should preserve the JSON-first architecture, public namespace,
and strict separation between framework code and research artifacts.

## Rules

- Keep public APIs under the `verfeinert` namespace.
- Do not introduce dependencies on legacy development artifacts, thesis-specific notebooks, or external research folders.
- Do not commit generated outputs, experiment artifacts, executed notebooks,
  bytecode caches, build directories, or temporary validation artifacts.
- Keep campaign-specific logic in examples or configuration, not framework
  modules.
- Keep canonical exchange as JSON; tables and plots are derived outputs.
- Do not weaken required scientific dependencies for convenience.

## Development workflow

For new features:

1. Discuss significant changes through an issue before implementation.
2. Keep changes focused and documented.
3. Add tests for new functionality.
4. Update documentation when public APIs change.

## Validation

Before submitting changes, run the test suite to verify that the
framework remains functional:

``` bash
pytest tests -q
```

Changes affecting public APIs, data schemas, workflows, or scientific
functionality should include appropriate tests.

For release-oriented changes, additionally validate the package from an
external installation environment:

``` bash
python scripts/validate_external_install.py --output-root /tmp/verfeinert-external-validation
```

This validation checks that Verfeinert can be installed and executed
without depending on the development repository structure.

## Scientific contributions

Changes affecting scientific methods, metrics, or reproducibility should include
a clear explanation of the methodological impact and validation performed.