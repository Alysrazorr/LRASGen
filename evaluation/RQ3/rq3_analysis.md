# RQ3: comparison against Respector

`scripts/evaluate_rq3.py` reads Respector's output under `specs/respector_generated` and the pipeline output under `output/lrasgen_generated`, applies the same four keys to both sides, and counts how many entities each one carries.

## Summary

LRASGen outperforms Respector by 54.30% (methods), 27.72% (parameters), 93.79% (constraints), and 72.37% (responses), and applies to all 53 APIs, whereas Respector applies to only 27.

## Per task

| Task | Ours (53 APIs) | Ours (the 27) | Respector | Outperforms by |
|---|---:|---:|---:|---:|
| Endpoint Methods | 2,510 | 1,171 | 1,147 | 54.30% |
| Endpoint Parameters | 11,661 | 8,456 | 8,428 | 27.72% |
| Parameter Constraints | 10,741 | 8,515 | 667 | 93.79% |
| Endpoint Responses | 6,009 | 2,970 | 1,660 | 72.37% |

The share is the pipeline's count over all 53 APIs minus Respector's count, divided by the pipeline's count. The denominator covers every API because the pipeline covers every API: Respector contributes nothing on the APIs it cannot analyse, so its column is empty there and the difference is the whole of what the pipeline reported on those.

## The APIs Respector covers

Respector is a Java static-analysis tool. It produced a result for 27 of the 53 subject APIs:

- Actuator, CWA, Cassandra, CatWatch, Digdag, ECommerce
- ERC20, Faults, Features-Service, Genome, Gestao, Gravitee
- Kafka, Market, OCVN, Ohsome, Piggy, ProxyPrint
- Quartz, RESTcountries, Scout, Senzing, Session, UM
- Ur-Codebin, YTM, enviroCar

## Reading

Respector's output is a comparison target and not a ground truth, so no entity on either side is classified as right or wrong here. A result Respector omits is one it could not derive from the source it analyses, and the gap on the APIs it does cover is where the two approaches read the same code differently. The constraint column is the widest gap, which follows from what each side can see: Respector derives constraints from what the project compiles into the API, and the pipeline reads them off the handler, the annotations, and the classes the request names.
