# Data And Output Policy

Verfeinert separates framework source code from experiment inputs and
experiment outputs. This is essential for an open-source scientific framework:
package code should be reusable without depending on a particular experiment
workspace.

## Caller-Owned Roots

Public APIs must not assume local paths. Experiment roots are supplied by
the caller through validated configuration:

- `input_root`: externally managed experiment inputs, reference data, or
  campaign material;
- `output_root`: generated run outputs, exports, reports, metadata, or logs.

The package does not provide default experiment roots. Tests may use temporary
directories, but source modules must not hard-code `tmp/`, `outputs/`,
`analysis_exports/`, `analysis_results/`, project-specific postprocessing folders, or
absolute local paths.

## Path Guards

Core path validation rejects output roots that are the same as, nested within,
or parents of input roots. It also rejects output roots that overlap package
source. The goal is to prevent accidental mixing of source files, external
inputs, and generated artifacts.

Output directories may be created only after a caller has explicitly supplied
the target root and it has passed validation.

## Serialization

Reusable JSON and YAML helpers convert records to JSON-safe structures before
writing. Supported shared values include dataclasses, paths, enums, dates,
datetimes, mappings, sequences, sets, and scalar values. Non-finite floats and
unknown objects are rejected rather than silently producing unstable metadata.

## Provenance

Run metadata records include the effective configuration, execution mode,
worker count, random seed, input hashes, schema version, Verfeinert version,
timestamp, Git commit when available, and truthful execution flags. Metadata
collection must not fail solely because Git is absent or the working directory
is not a Git repository.

Generated outputs are not source code. They belong under caller-provided output
roots and should not be committed into the framework package.
