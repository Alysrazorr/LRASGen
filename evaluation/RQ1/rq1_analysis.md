# RQ1: accuracy against the enhanced ground truth

`scripts/evaluate_rq1.py` reads the pipeline output under `output/lrasgen_generated` and the enhanced ground truth in `GTa.xlsx`, applies the same four keys to both sides, and matches them entity by entity.

## Summary

LRASGen identifies 2,510 of 2,516 (99.8%) endpoint methods, 11,661 of 11,807 (98.8%) endpoint parameters, 10,741 of 10,917 (98.4%) parameter constraints, and 6,009 of 6,154 (97.6%) endpoint responses against the enhanced ground truth (GT*).

## Per task

| Task | GT | Ours | TP | FP | FN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| Endpoint Methods | 2,516 | 2,510 | 2,501 | 9 | 15 | 0.9964 | 0.9940 |
| Endpoint Parameters | 11,807 | 11,661 | 11,338 | 323 | 469 | 0.9723 | 0.9603 |
| Parameter Constraints | 10,917 | 10,741 | 10,603 | 138 | 314 | 0.9872 | 0.9712 |
| Endpoint Responses | 6,154 | 6,009 | 5,970 | 39 | 184 | 0.9935 | 0.9701 |

## Reading

The ground truth is the reference for this comparison, so a false negative is an entity it lists and the pipeline did not report, and a false positive is one the pipeline reported and it does not list. Precision and recall both follow from those two counts, and neither is meaningful on its own: a task can reach a high recall by reporting every path it saw and a high precision by reporting almost nothing.

The full list of disagreements is in `rq1_audit.csv` beside this file, one row per entity, with the pipeline value, the ground truth value, and the source file the pipeline read.
