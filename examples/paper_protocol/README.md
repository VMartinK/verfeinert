# Manuscript-protocol family evaluation for n qubits

`config/tfim_paper_protocol_n6.yaml` evaluates the 19 Sanz19 templates with
`L = 1, 2, 3` layers using the exact sampling protocol of the manuscript
(10 000 fidelity pairs / 75 equal-mass bins for expressibility, 3 000 gradient
samples for trainability, 5 independent trials, `Expr' x Train` ranking and the
IBM Heron r2 cost weights).

Change the qubit count, the Hamiltonian, its parameters or the number of trials
from the CLI:

```bash
verfeinert validate examples/paper_protocol/config/tfim_paper_protocol_n6.yaml \
  --n-qubits 8 --hamiltonian heisenberg --hamiltonian-param Jz=1.5 --trials 3

verfeinert run examples/paper_protocol/config/tfim_paper_protocol_n6.yaml \
  --output-root outputs/paper-n8 --n-qubits 8 --hamiltonian heisenberg \
  --hamiltonian-param Jz=1.5 --trials 3
```

`--protocol paper` (or `fast`) can be applied to any other workflow file to
inject the same sampling preset. Each metric record stores the per-trial values
under `metadata.trials`, and the mean / sample standard deviation under
`value.expressibility`, `value.expressibility_std`, `value.trainability` and
`value.trainability_std`.

A single 4-qubit circuit takes about one second with the full protocol; the
cost grows with `2**n_qubits` and the number of parameters (see
`PROPUESTA METRICAS.pdf` for scaling strategies).
