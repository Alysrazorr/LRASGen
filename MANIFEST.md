# MANIFEST

Correspondence table between the 53 subject APIs and the files that represent them in the
replication package. Each API is listed against its source folder, its pipeline output
directory, and the three specifications the RCR report compares: the one LRASGen
generated, the one the developer provided, and Respector's.

## 53 subject APIs

Every path below is relative to the package root, and `<br>` separates multiple entries for
one API.

The package arranges the material by the API's short name, which is the name used in
Table 1 of the RCR report and in `scripts/run_all_apis.py`:

    api-sources/<short name>/...             the project as it was obtained, unmodified
    output/lrasgen_generated/<short name>/   the pipeline's run
    specs/lrasgen_generated/<short name>/    the specification the pipeline produced
    specs/developer_provided/<short name>/   the developer-provided specification
    specs/respector_generated/<short name>/  the Respector output, where one exists

A pipeline output directory holds the five step files that record what the pipeline did at
each stage, together with a copy of the specification it produced. `specs/` collects the
three specifications side by side, so that the comparison the report describes can be read
from one place. The copy under `specs/lrasgen_generated/` is byte-identical to the one in
the API's own output directory.

| # | Short name | Full name | Source folder | Pipeline output | LRASGen-generated spec | Developer-provided spec | Respector output |
|---|---|---|---|---|---|---|---|
| 1 | Digdag | Digdag | `api-sources/Digdag/digdag/digdag-server` | `output/lrasgen_generated/Digdag/` | `specs/lrasgen_generated/Digdag/generated_oas.json` | `specs/developer_provided/Digdag/digdag.json` | `specs/respector_generated/Digdag/digdag.json` |
| 2 | enviroCar | enviroCar | `api-sources/enviroCar/enviroCar-server` | `output/lrasgen_generated/enviroCar/` | `specs/lrasgen_generated/enviroCar/generated_oas.json` | `specs/developer_provided/enviroCar/envirocar-server.json` | `specs/respector_generated/enviroCar/enviro.json` |
| 3 | Features-Service | Features-Service | `api-sources/Features-Service/features-service` | `output/lrasgen_generated/Features-Service/` | `specs/lrasgen_generated/Features-Service/generated_oas.json` | `specs/developer_provided/Features-Service/features-service.json` | `specs/respector_generated/Features-Service/feature_service.json` |
| 4 | Gravitee | Gravitee.io | `api-sources/Gravitee/gravitee-api-management` | `output/lrasgen_generated/Gravitee/` | `specs/lrasgen_generated/Gravitee/generated_oas.json` | `specs/developer_provided/Gravitee/gravitee-api.json` | `specs/respector_generated/Gravitee/gravitee_manage_v4.json` |
| 5 | Kafka | Kafka REST Proxy | `api-sources/Kafka/kafka-rest` | `output/lrasgen_generated/Kafka/` | `specs/lrasgen_generated/Kafka/generated_oas.json` | `specs/developer_provided/Kafka/kafka-rest.json` | `specs/respector_generated/Kafka/kafka.json` |
| 6 | Cassandra | Management API for Apache Cassandra | `api-sources/Cassandra/management-api-for-apache-cassandra` | `output/lrasgen_generated/Cassandra/` | `specs/lrasgen_generated/Cassandra/generated_oas.json` | `specs/developer_provided/Cassandra/management-api-for-apache-cassandra.json` | `specs/respector_generated/Cassandra/cassandra.json` |
| 7 | RESTcountries | RESTCountries | `api-sources/RESTcountries/restcountries` | `output/lrasgen_generated/RESTcountries/` | `specs/lrasgen_generated/RESTcountries/generated_oas.json` | `specs/developer_provided/RESTcountries/restcountries.json` | `specs/respector_generated/RESTcountries/restcountries.json` |
| 8 | Senzing | Senzing | `api-sources/Senzing/senzing-api-server` | `output/lrasgen_generated/Senzing/` | `specs/lrasgen_generated/Senzing/generated_oas.json` | `specs/developer_provided/Senzing/senzing-api-server.json` | `specs/respector_generated/Senzing/senzing.json` |
| 9 | Petstore | Swagger Petstore | `api-sources/Petstore/swagger-petstore` | `output/lrasgen_generated/Petstore/` | `specs/lrasgen_generated/Petstore/generated_oas.json` | `specs/developer_provided/Petstore/swagger-petstore.json` | not applicable |
| 10 | Payments | Payments Public API | `api-sources/Payments/pay-publicapi` | `output/lrasgen_generated/Payments/` | `specs/lrasgen_generated/Payments/generated_oas.json` | `specs/developer_provided/Payments/pay-publicapi.json` | not applicable |
| 11 | Scout | Scout-API | `api-sources/Scout/scout-api` | `output/lrasgen_generated/Scout/` | `specs/lrasgen_generated/Scout/generated_oas.json` | `specs/developer_provided/Scout/scout-api.json` | `specs/respector_generated/Scout/Scout.json` |
| 12 | Languagetool | Languagetool | `api-sources/Languagetool/languagetool` | `output/lrasgen_generated/Languagetool/` | `specs/lrasgen_generated/Languagetool/generated_oas.json` | `specs/developer_provided/Languagetool/languagetool.json` | not applicable |
| 13 | CatWatch | CatWatch | `api-sources/CatWatch/catwatch` | `output/lrasgen_generated/CatWatch/` | `specs/lrasgen_generated/CatWatch/generated_oas.json` | `specs/developer_provided/CatWatch/catwatch.json` | `specs/respector_generated/CatWatch/catwatch.json` |
| 14 | CWA | CWA Verification Server | `api-sources/CWA/cwa-verification-server` | `output/lrasgen_generated/CWA/` | `specs/lrasgen_generated/CWA/generated_oas.json` | `specs/developer_provided/CWA/cwa-verification.json` | `specs/respector_generated/CWA/cwa.json` |
| 15 | OCVN | OCVN | `api-sources/OCVN/ocvn` | `output/lrasgen_generated/OCVN/` | `specs/lrasgen_generated/OCVN/generated_oas.json` | `specs/developer_provided/OCVN/ocvn.json` | `specs/respector_generated/OCVN/ocvn.json` |
| 16 | Ohsome | Ohsome | `api-sources/Ohsome/ohsome-api` | `output/lrasgen_generated/Ohsome/` | `specs/lrasgen_generated/Ohsome/generated_oas.json` | `specs/developer_provided/Ohsome/ohsome-api-aggregation.json`<br>`specs/developer_provided/Ohsome/ohsome-api-extraction.json`<br>`specs/developer_provided/Ohsome/ohsome-api-metadata.json` | `specs/respector_generated/Ohsome/ohsome.json` |
| 17 | ProxyPrint | ProxyPrint | `api-sources/ProxyPrint/proxyprint-kitchen` | `output/lrasgen_generated/ProxyPrint/` | `specs/lrasgen_generated/ProxyPrint/generated_oas.json` | `specs/developer_provided/ProxyPrint/proxyprint.json` | `specs/respector_generated/ProxyPrint/proxyprint.json` |
| 18 | Quartz | Quartz Manager | `api-sources/Quartz/quartz-manager` | `output/lrasgen_generated/Quartz/` | `specs/lrasgen_generated/Quartz/generated_oas.json` | `specs/developer_provided/Quartz/quartz-manager.json` | `specs/respector_generated/Quartz/quartz.json` |
| 19 | Ur-Codebin | Ur-Codebin API | `api-sources/Ur-Codebin/Ur-Codebin-API` | `output/lrasgen_generated/Ur-Codebin/` | `specs/lrasgen_generated/Ur-Codebin/generated_oas.json` | `specs/developer_provided/Ur-Codebin/ur-codebin-api.json` | `specs/respector_generated/Ur-Codebin/ur_codebin.json` |
| 20 | SCS | SCS | `api-sources/SCS/scs` | `output/lrasgen_generated/SCS/` | `specs/lrasgen_generated/SCS/generated_oas.json` | `specs/developer_provided/SCS/rest-scs.json` | not applicable |
| 21 | Session | Session Service | `api-sources/Session/session-service` | `output/lrasgen_generated/Session/` | `specs/lrasgen_generated/Session/generated_oas.json` | `specs/developer_provided/Session/session-service.json` | `specs/respector_generated/Session/Session.json` |
| 22 | Actuator | Spring-actuator-demo | `api-sources/Actuator/spring-actuator-demo` | `output/lrasgen_generated/Actuator/` | `specs/lrasgen_generated/Actuator/generated_oas.json` | `specs/developer_provided/Actuator/spring-actuator-demo.json` | `specs/respector_generated/Actuator/Actuator.json` |
| 23 | Batch | Spring-batch-rest | `api-sources/Batch/spring-batch-rest` | `output/lrasgen_generated/Batch/` | `specs/lrasgen_generated/Batch/generated_oas.json` | `specs/developer_provided/Batch/spring-batch-rest.json` | not applicable |
| 24 | SBRAE | Spring Boot Restful API Example | `api-sources/SBRAE/spring-rest-example` | `output/lrasgen_generated/SBRAE/` | `specs/lrasgen_generated/SBRAE/generated_oas.json` | `specs/developer_provided/SBRAE/spring-rest-example.json` | not applicable |
| 25 | ECommerce | Spring ECommerce | `api-sources/ECommerce/spring-ecommerce` | `output/lrasgen_generated/ECommerce/` | `specs/lrasgen_generated/ECommerce/generated_oas.json` | `specs/developer_provided/ECommerce/spring-ecommerce.json` | `specs/respector_generated/ECommerce/ECommerce.json` |
| 26 | Tiltak | Tiltaksgjennomforing | `api-sources/Tiltak/tiltaksgjennomforing` | `output/lrasgen_generated/Tiltak/` | `specs/lrasgen_generated/Tiltak/generated_oas.json` | `specs/developer_provided/Tiltak/tiltaksgjennomforing.json` | not applicable |
| 27 | UM | User Management | `api-sources/UM/user-management` | `output/lrasgen_generated/UM/` | `specs/lrasgen_generated/UM/generated_oas.json` | `specs/developer_provided/UM/user-management.json` | `specs/respector_generated/UM/UM.json` |
| 28 | WebGoat | WebGoat | `api-sources/WebGoat/webgoat` | `output/lrasgen_generated/WebGoat/` | `specs/lrasgen_generated/WebGoat/generated_oas.json` | `specs/developer_provided/WebGoat/webgoat.json` | not applicable |
| 29 | YTM | YouTubeMock | `api-sources/YTM/youtube-mock` | `output/lrasgen_generated/YTM/` | `specs/lrasgen_generated/YTM/generated_oas.json` | `specs/developer_provided/YTM/youtube-mock.json` | `specs/respector_generated/YTM/YTM.json` |
| 30 | PetClinic | PetClinic | `api-sources/PetClinic/spring-petclinic-rest-master` | `output/lrasgen_generated/PetClinic/` | `specs/lrasgen_generated/PetClinic/generated_oas.json` | `specs/developer_provided/PetClinic/petclinic-openapi.json` | not applicable |
| 31 | Piggy | Piggy Metrics | `api-sources/Piggy/piggymetrics-master` | `output/lrasgen_generated/Piggy/` | `specs/lrasgen_generated/Piggy/generated_oas.json` | `specs/developer_provided/Piggy/piggy-account.json`<br>`specs/developer_provided/Piggy/piggy-auth.json`<br>`specs/developer_provided/Piggy/piggy-metrics-openapi.json`<br>`specs/developer_provided/Piggy/piggy-notification.json`<br>`specs/developer_provided/Piggy/piggy-statistics.json` | `specs/respector_generated/Piggy/Piggy-account.json`<br>`specs/respector_generated/Piggy/Piggy-auth.json`<br>`specs/respector_generated/Piggy/Piggy-notification.json`<br>`specs/respector_generated/Piggy/Piggy-statistics.json` |
| 32 | Faults | REST Faults | `api-sources/Faults/rest-faults-master` | `output/lrasgen_generated/Faults/` | `specs/lrasgen_generated/Faults/generated_oas.json` | `specs/developer_provided/Faults/rest-faults-openapi.json` | `specs/respector_generated/Faults/Faults.json` |
| 33 | Bibliothek | Bibliothek | `api-sources/Bibliothek/bibliothek` | `output/lrasgen_generated/Bibliothek/` | `specs/lrasgen_generated/Bibliothek/generated_oas.json` | `specs/developer_provided/Bibliothek/bibliothek.json` | not applicable |
| 34 | Blog | Blog | `api-sources/Blog/blogapi` | `output/lrasgen_generated/Blog/` | `specs/lrasgen_generated/Blog/generated_oas.json` | `specs/developer_provided/Blog/blogapi.json` | not applicable |
| 35 | ERC20 | ERC20 Rest Service | `api-sources/ERC20/erc20-rest-service` | `output/lrasgen_generated/ERC20/` | `specs/lrasgen_generated/ERC20/generated_oas.json` | `specs/developer_provided/ERC20/erc20-rest-service.json` | `specs/respector_generated/ERC20/ERC20.json` |
| 36 | Genome | Genome Nexus | `api-sources/Genome/genome-nexus` | `output/lrasgen_generated/Genome/` | `specs/lrasgen_generated/Genome/generated_oas.json` | `specs/developer_provided/Genome/genome-nexus.json` | `specs/respector_generated/Genome/Genome.json` |
| 37 | Gestao | Gestao Hospital | `api-sources/Gestao/gestaohospital` | `output/lrasgen_generated/Gestao/` | `specs/lrasgen_generated/Gestao/generated_oas.json` | `specs/developer_provided/Gestao/gestaohospital.json` | `specs/respector_generated/Gestao/Gestao.json` |
| 38 | HTTPPatch | HTTP Patch Spring | `api-sources/HTTPPatch/http-patch-spring` | `output/lrasgen_generated/HTTPPatch/` | `specs/lrasgen_generated/HTTPPatch/generated_oas.json` | `specs/developer_provided/HTTPPatch/http-patch-spring.json` | not applicable |
| 39 | Market | Market | `api-sources/Market/market` | `output/lrasgen_generated/Market/` | `specs/lrasgen_generated/Market/generated_oas.json` | `specs/developer_provided/Market/market.json` | `specs/respector_generated/Market/Market.json` |
| 40 | Microcks | Microcks | `api-sources/Microcks/microcks` | `output/lrasgen_generated/Microcks/` | `specs/lrasgen_generated/Microcks/generated_oas.json` | `specs/developer_provided/Microcks/microcks.json` | not applicable |
| 41 | NCS | NCS | `api-sources/NCS/ncs` | `output/lrasgen_generated/NCS/` | `specs/lrasgen_generated/NCS/generated_oas.json` | `specs/developer_provided/NCS/rest-ncs.json` | not applicable |
| 42 | Person | Person Controller | `api-sources/Person/person-controller` | `output/lrasgen_generated/Person/` | `specs/lrasgen_generated/Person/generated_oas.json` | `specs/developer_provided/Person/person-controller.json` | not applicable |
| 43 | PTS | Project Tracking System | `api-sources/PTS/tracking-system` | `output/lrasgen_generated/PTS/` | `specs/lrasgen_generated/PTS/generated_oas.json` | `specs/developer_provided/PTS/tracking-system.json` | not applicable |
| 44 | Reservations | Reservations API | `api-sources/Reservations/reservations-api` | `output/lrasgen_generated/Reservations/` | `specs/lrasgen_generated/Reservations/generated_oas.json` | `specs/developer_provided/Reservations/reservations-api.json` | not applicable |
| 45 | News | News | `api-sources/News/news` | `output/lrasgen_generated/News/` | `specs/lrasgen_generated/News/generated_oas.json` | `specs/developer_provided/News/rest-news.json` | not applicable |
| 46 | Familie | Familie Ba Sak | `api-sources/Familie/familie-ba-sak` | `output/lrasgen_generated/Familie/` | `specs/lrasgen_generated/Familie/generated_oas.json` | `specs/developer_provided/Familie/familie-ba-sak.json` | not applicable |
| 47 | Poke | Poke API | `api-sources/Poke/pokeapi-master` | `output/lrasgen_generated/Poke/` | `specs/lrasgen_generated/Poke/generated_oas.json` | `specs/developer_provided/Poke/poke.json` | not applicable |
| 48 | Gramps | Gramps Web API | `api-sources/Gramps/gramps-web-api-master` | `output/lrasgen_generated/Gramps/` | `specs/lrasgen_generated/Gramps/generated_oas.json` | `specs/developer_provided/Gramps/gramps.json` | not applicable |
| 49 | Jupyter | Jupyter Server | `api-sources/Jupyter/jupyter_server-main` | `output/lrasgen_generated/Jupyter/` | `specs/lrasgen_generated/Jupyter/generated_oas.json` | `specs/developer_provided/Jupyter/jupyter.json` | not applicable |
| 50 | Mlmmj | Mlmmjadmin | `api-sources/Mlmmj/mlmmjadmin-master` | `output/lrasgen_generated/Mlmmj/` | `specs/lrasgen_generated/Mlmmj/generated_oas.json` | `specs/developer_provided/Mlmmj/mlmmj.json` | not applicable |
| 51 | Bitwarden | Bitwarden Server | `api-sources/Bitwarden/bitwarden-server-main/src/Api/Public`<br>`api-sources/Bitwarden/bitwarden-server-main/src/Api/AdminConsole/Public`<br>`api-sources/Bitwarden/bitwarden_clients-main/apps/cli/src`<br>`api-sources/Bitwarden/bitwarden_clients-main/bitwarden_license/bit-cli/src` | `output/lrasgen_generated/Bitwarden/` | `specs/lrasgen_generated/Bitwarden/api-adminconsole-public.json`<br>`specs/lrasgen_generated/Bitwarden/api-public.json`<br>`specs/lrasgen_generated/Bitwarden/cli-licensed.json`<br>`specs/lrasgen_generated/Bitwarden/cli-oss.json` | `specs/developer_provided/Bitwarden/bitwarden-public-api.json`<br>`specs/developer_provided/Bitwarden/bitwarden-vault-management-api.json` | not applicable |
| 52 | Cyclotron | Cyclotron | `api-sources/Cyclotron/cyclotron-master` | `output/lrasgen_generated/Cyclotron/` | `specs/lrasgen_generated/Cyclotron/generated_oas.json` | `specs/developer_provided/Cyclotron/cyclotron-openapi.json` | not applicable |
| 53 | Realworld | Realworld App | `api-sources/Realworld/nestjs-realworld-example-app-master` | `output/lrasgen_generated/Realworld/` | `specs/lrasgen_generated/Realworld/generated_oas.json` | `specs/developer_provided/Realworld/realworld-app-openapi.json` | not applicable |

## Counts by folder

| Folder | Directories | Files | Subject APIs with no entry |
|---|---|---|---|
| `api-sources/` | 53 | 34,257 | none |
| `output/lrasgen_generated/` | 53 | 341 | none |
| `specs/lrasgen_generated/` | 53 | 56 | none |
| `specs/developer_provided/` | 53 | 60 | none |
| `specs/respector_generated/` | 27 | 30 | 26 |

A file count is not an API count. Some subject APIs are represented by more than one
document on a side, and all of them are kept: Ohsome supplied three developer-provided
documents, Piggy five, and Bitwarden two; Piggy's Respector run produced four; and
Bitwarden's pipeline run produced four, one per entry point (see below).

## Notes

**Bitwarden.** This API's source spans two upstream repositories and four entry points, so
the pipeline was run once per entry point and its output was merged into one. The merged
result is what the four top-level step files in `output/lrasgen_generated/Bitwarden/`
hold, and the four run directories beneath it are the runs that were merged. A
specification is generated per run, so the merged directory carries no specification of its
own; the four are collected in `specs/lrasgen_generated/Bitwarden/`, each named after the
run directory it came from.

**Respector.** Respector is a Java static-analysis tool, and it produced a result for 27 of
the 53 subject APIs. The other 26 are marked `not applicable` above. The subset is the one
listed in Appendix A of the RCR report.
