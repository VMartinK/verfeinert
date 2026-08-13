# User Documentation

These guides show reproducible researcher workflows built on public
`verfeinert` APIs.

## Official Examples

- `cx01_reproduction.md`: CX-01 reproduction workflow with a fast smoke profile
  and documented full scientific settings.
- `mixt5g_reproduction.md`: MIXT-5G strict-Pareto evolution reproduction with a
  bounded smoke profile and documented full schedule.

Both examples write artifacts only under caller-provided output roots. Expensive
scientific metrics remain explicit opt-in workflows.

For a minimal new campaign, start from the canonical `workflow` section used by
the examples: choose `campaign_type`, declare `scientific_execution`, add
optional `postprocessing`, and provide either generated candidates, persisted
artifacts, or a public candidate factory such as `InsertGateMutationFactory`.
