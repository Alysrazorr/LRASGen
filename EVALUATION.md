# EVALUATION

How the quantitative results reported for RQ1, RQ2, and RQ3 are reproduced from the
archived outputs. This document describes the evaluation scripts, the matching rules they
apply, and which steps require an LLM or an API key.

Everything below describes what the scripts in `scripts/` do, as written.

## 1. What each step needs

| Step | Script | Requires an LLM or API key? |
|---|---|---|
| RQ1: LRASGen output vs. the enhanced ground truth (`GTa.xlsx`) | `scripts/evaluate_rq1.py` | No. Reads the archived pipeline output and `GTa.xlsx`; the comparison is local counting. |
| RQ2: LRASGen output vs. the developer-provided specifications | `scripts/evaluate_rq2.py` | No. Reads the archived pipeline output and `specs/developer_provided/`. |
| RQ3: LRASGen output vs. Respector output | `scripts/evaluate_rq3.py` | No. Reads the archived pipeline output and `specs/respector_generated/`, which ships with this package. |

Reproducing the RQ1, RQ2, and RQ3 comparisons from the archived outputs therefore costs
nothing and needs no credentials. Only a user who wants to regenerate the pipeline output
itself needs LLM API keys.

## 2. Inputs

| Input | Where it comes from |
|---|---|
| Generated endpoints | `output/lrasgen_generated/<API>/step3_endpoints.json` |
| Generated parameters, constraints and responses | `output/lrasgen_generated/<API>/step5_constraints.json` |
| Ground truth | `GTa.xlsx`, one sheet per API |
| Developer-provided specifications | `specs/developer_provided/<API>/*.json` |
| Respector output | `specs/respector_generated/<API>/*.json` |

The scripts read `step3_endpoints.json` and `step5_constraints.json` only. Every path above
has a command-line option that overrides it: `--output-root`, `--gt`, `--specs`,
`--respector`.

## 3. Matching keys

All three research questions align entities with the same keys. A key is evaluated after
normalization (Section 4).

| Entity | Matching key |
|---|---|
| Endpoint method | normalized path template + HTTP method |
| Endpoint parameter | endpoint (normalized path + method) + normalized parameter name + normalized type |
| Parameter constraint | endpoint + normalized parameter name + constraint kind |
| Endpoint response | endpoint + status code |


## 4. Normalization

**Path templates.** Every `{...}` placeholder collapses to `{}`, so `/{id}`, `/{path}` and
`/{path:.*}` are one template; the placeholder's name carries no meaning for matching. A
trailing slash and repeated separators are collapsed.

**Base prefix.** A generated path and a ground-truth path can differ by a leading segment, the
way `/api/v1/pets` and `/pets` do. For each API the script tries every leading segment that
appears in either side's paths, and keeps the one under which the two sides have the most
keys in common. `--strip-prefix` fixes the segment instead of searching for it.


**Parameter types.** Both sides are mapped into six kinds, with `object` the default for a
type that is not recognized.

| Kind | Types that map to it |
|---|---|
| `string` | `string`, `str`, `char`, `character`, `uuid`, `date`, `datetime`, `localdate`, `localdatetime`, `instant`, `timestamp`, `zoneddatetime`, `offsetdatetime`, `httpmethod`, `file`, `multipartfile` |
| `integer` | `int`, `integer`, `long`, `short`, `byte`, `biginteger` |
| `number` | `number`, `float`, `double`, `bigdecimal`, `decimal` |
| `boolean` | `bool`, `boolean` |
| `array` | `array`, `list`, `set`, `collection`, `iterable`, `arraylist`, `linkedlist`, `hashset`, `linkedhashset`, `treeset` |
| `object` | `object`, `map`, `dictionary`, `hashmap`, `linkedhashmap`, `treemap`, and anything else |

A parameter whose type resolves to `object` but which carries an `enum` is read as `string`,
because a list of permitted values says the parameter takes a value and not a structure.

**Constraint kinds.** The two sides name the same constraints differently, so both are mapped
into a shared set of kinds.

| `GTa.xlsx` | Pipeline output | Shared kind |
|---|---|---|
| `require`, `is_required`, `required` | `require` | `required` |
| `min_value` | `min` | `min_value` |
| `max_value` | `max` | `max_value` |
| `min_length` | `min_length` | `min_length` |
| `max_length` | `max_length` | `max_length` |
| `parameter_format`, `time_format` | `format` | `format` |
| `parameter_enum`, a bare value list | `enum` | `enum` |
| `parameter_dict` | `dictionary` | `dictionary` |

**Counting.** Each task's keys are held in a set, so a key written on more than one row counts
once. This applies to both sides.

## 5. RQ1: computing TP, FP, FN, precision, and recall

`scripts/evaluate_rq1.py` builds the key set of each side and takes the set intersection and
the two differences:

- **TP** -- keys in both the generated output and `GTa.xlsx`.
- **FP** -- keys in the generated output and not in `GTa.xlsx`.
- **FN** -- keys in `GTa.xlsx` and not in the generated output.

Precision is `TP / (TP + FP)` and recall is `TP / (TP + FN)`. **These counts are reported as
computed. No step of the script adjudicates them by hand, and no verdict feeds back into
them.**

What the script does provide for a human is `rq1_audit.csv`, one row per disagreement, with
the pipeline value, the ground-truth value, and the code anchor the pipeline recorded for the
entity. The `verdict` column is written empty. A reader who wants to check a disagreement
fills it in by reading the flagged source location; the audit is a reading aid and not an
input to the reported figures.

A parameter whose type differs between the two sides produces one FP and one FN, because the
type is part of the key and the two sides therefore hold different keys for the same
parameter. The audit shows the two rows side by side.

**Audit worksheet columns**

| Column | Meaning |
|---|---|
| `api` | subject API short name |
| `task` | `M`, `P`, `C` or `R` |
| `matching_key` | the key from Section 3, after normalization |
| `pipeline_value` | the generated entity, or empty if the pipeline did not report it |
| `gt_value` | the ground-truth entity, or empty if `GTa.xlsx` does not list it |
| `source_file` | code anchor recorded by the pipeline, on the pipeline's rows |
| `line_number` | code anchor recorded by the pipeline, on the pipeline's rows |
| `verdict` | empty; for a reader to fill in |

## 6. RQ2: comparison against the developer-provided specifications

`scripts/evaluate_rq2.py` is a pure counting comparison. It applies the same keys to both
sides and reports how many entities each one carries, per API and per task, with a total row
per task.

The headline figure the paper reports for RQ2 is the share of the ground truth that the
pipeline recovers and the developer specifications do not:

    (Ours - Dev) / GT*

The numerator is the difference between the two counts. The denominator is the ground
truth's own count for the task, `GTa.xlsx`'s totals, and not the developer's count: a
specification that lists nothing would make a ratio against it unbounded. The figure can be
negative, which says that the developer specifications carry more entities of that task than
the pipeline reported.

No true/false classification is involved, because the developer-provided specifications are a
comparison target and not a ground truth.

## 7. RQ3: comparison against Respector

`scripts/evaluate_rq3.py` is also a pure counting comparison. It applies the same keys to
both sides and reports how many entities each one carries.

Respector is a Java static-analysis tool and produces a result for 27 of the 53 subject APIs,
so those 27 are the APIs with a row. The headline figure is the share of the pipeline's own
entities that Respector did not report:

    (Ours - Resp) / Ours

The denominator is the pipeline's count over all 53 APIs and not over the 27 that Respector
covers. That is what makes the paper's "LRASGen applies to all 53 APIs, whereas Respector
applies to only 27" a statement about the same figure: Respector contributes nothing on the
APIs it cannot analyse, so the difference there is the whole of what the pipeline reported.

The comparison uses Respector's official replication package, with its default configuration
and unmodified (`https://zenodo.org/doi/10.5281/zenodo.10429765`); the run guide shipped with
that package documents how it is executed. The comparison output used in the original paper
was not retained, so we reran the package on the 27 subject APIs it supports. That rerun's
output ships with this package under `specs/respector_generated/`, one directory per API, and
the script reads it from there. Those 27 APIs are listed in Appendix A of the RCR report.

## 8. Ground truth

`GTa.xlsx` is the reference for RQ1, and its per-task totals are the denominator for RQ2.
