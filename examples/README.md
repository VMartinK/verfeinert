# Examples

This directory contains official reproducible examples for Verfeinert.

## Official Examples

- `CX01_reproduction/`: CX-01 reproduction with a fast smoke profile,
  documented full scientific settings, and a declarative full-lite CLI workflow
  at `config/cx01_full_lite_workflow.yaml`.
- `MIXT5G_reproduction/`: mixed-gate five-generation strict-Pareto reproduction
  with a bounded smoke profile, documented full schedule, and a declarative
  multi-generation full-lite CLI workflow at
  `config/mixt5g_full_lite_workflow.yaml`.
- `publication_visualization.py`: compact headless publication-figure export
  from synthetic, already-prepared semantic visualization data.

CX-01 demonstrates an `individual` workflow. MIXT-5G demonstrates an
`evolutionary` workflow. The full-lite configs can be run without writing
campaign-specific Python:

```bash
verfeinert run examples/CX01_reproduction/config/cx01_full_lite_workflow.yaml --output-root outputs/cx01-full-lite
verfeinert run examples/MIXT5G_reproduction/config/mixt5g_full_lite_workflow.yaml --output-root outputs/mixt5g-full-lite
```

Generated artifacts must be written under the configured example output root
and should not be committed.
