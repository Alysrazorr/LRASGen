# RQ2: comparison against the developer-provided specifications

`scripts/evaluate_rq2.py` reads the developer-provided specifications under `specs/developer_provided` and the pipeline output under `output/lrasgen_generated`, applies the same four keys to both sides, and counts how many entities each one carries.

## Summary

LRASGen recovers entities missing from developer-provided specifications: 13.75% more endpoint methods, 21.66% more parameters, 75.92% more parameter constraints, and 2.14% fewer responses (27.30% more entities on average).

## Per task

| Task | Ours | Developer | Difference | Relative to the ground truth |
|---|---:|---:|---:|---:|
| Endpoint Methods | 2,509 | 2,163 | +346 | 13.75% |
| Endpoint Parameters | 11,661 | 9,104 | +2,557 | 21.66% |
| Parameter Constraints | 10,741 | 2,453 | +8,288 | 75.92% |
| Endpoint Responses | 6,007 | 6,139 | -132 | -2.14% |

The relative column divides the difference by the ground truth's own count for the task (2,516 methods, 11,807 parameters, 10,917 constraints, 6,154 responses in total), which is the quantity the paper reports. It does not divide by the developer's count, because a specification that lists nothing would make that ratio unbounded.

## Reading

The developer-provided specifications are a comparison target and not a ground truth, so no entity on either side is classified as right or wrong here. A developer who leaves an entity out has documented less, not made a mistake, and a positive difference counts what the pipeline reports and the specification does not mention.
