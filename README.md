# LRASGen — LLM-based RESTful API Specification Generation

LRASGen generates an OpenAPI Specification (OAS) directly from RESTful API source code
using Large Language Models. It needs neither compilation nor a runtime environment, and
it works across six programming languages and thirteen frameworks.
[LRASGen: LLM-based RESTful API Specification Generation (TOSEM 2026).](https://dl.acm.org/doi/10.1145/3810241)

## Repository Structure

```
.
├── README.md                     # This file
├── EVALUATION.md                 # How the RQ1–RQ3 figures are reproduced
├── EXTENDING.md                  # Adding a new LLM/model or a new REST API framework
├── MANIFEST.md                   # The 53 APIs: source folder, output, specifications
├── GTa.xlsx                      # Enhanced ground truth
├── LICENSE / NOTICE
├── src/                          # Pipeline source code
│   ├── main.py                   # Entry point — single-API pipeline orchestrator
│   ├── config.py                 # Endpoints and models the pipeline calls
│   ├── llm.py                    # LLM communication, cross-validation, usage accounting
│   ├── logger.py                 # Progress logger
│   ├── frameworks.py             # Framework knowledge base
│   ├── normalize.py              # Entity keys and the shared type/kind vocabulary
│   ├── apis.yaml                 # The 53 APIs, as a readable list
│   ├── requirements.txt          # Pinned dependencies
│   ├── step1.py                  # Endpoint entry-file discovery
│   ├── step2.py                  # Dependency resolution & code extraction
│   ├── step3.py                  # Endpoint method identification (LLM)
│   ├── step4.py                  # Parameter & response identification (LLM)
│   ├── step5.py                  # Parameter constraint identification (LLM)
│   └── step6.py                  # OAS assembly & validation
├── scripts/                      # Every entry point other than main.py
│   ├── run_all_apis.py           # Batch run — all 53 APIs
│   ├── evaluate_rq1.py           # RQ1: pipeline output vs. GTa.xlsx
│   ├── evaluate_rq2.py           # RQ2: pipeline output vs. developer-provided specs
│   ├── evaluate_rq3.py           # RQ3: pipeline output vs. Respector
│   └── cost_table.py             # Runtime / token / cost table
├── api-sources/                  # API source trees (see Setup)
├── specs/                        # Specifications, one directory per subject API
│   ├── lrasgen_generated/
│   ├── developer_provided/
│   └── respector_generated/
├── output/                       # Pipeline output (written at runtime)
└── evaluation/                   # RQ1–RQ3 results (written by the evaluation scripts)
```

`output/` and `api-sources/` each hold 54 entries: 53 correspond one-to-one with the
subject APIs, and the extra one is a second run for Bitwarden, whose source spans two
upstream repositories (`bitwarden-server` and `bitwarden-clients`); the two runs are
merged into the single Bitwarden row of the report's Table 1.

## Run with Docker

The packaged image carries Python 3.12, the dependencies, the 53 API source trees, the
specifications, and the archived pipeline output. It needs no Python installation and no
extraction step, so it is the shortest way to run the package. Docker Desktop (Windows,
macOS) or Docker Engine (Linux) is the only requirement.

Download `lrasgen-v1.tar.gz` from the
[Zenodo archive](https://doi.org/10.5281/zenodo.20727685), load it, and
open a shell inside the package:

```bash
docker load -i lrasgen-v1.tar.gz
docker run -it --rm lrasgen:v1
```

The shell opens in `/v1`, which holds the same tree as this repository, so every command
in the sections below runs there unchanged.

The three entry points are:

```bash
# One API
docker run --rm lrasgen:v1 python src/main.py \
  --api-path /v1/api-sources/CatWatch/catwatch \
  --framework spring-boot --output-dir /v1/output/CatWatch

# All 53 APIs
docker run --rm lrasgen:v1 python scripts/run_all_apis.py

# Reproduce RQ1-RQ3, which needs neither an API key nor the network
docker run --rm lrasgen:v1 python scripts/evaluate_rq1.py
```

An API run needs network access, because every model call goes to a cloud endpoint.
The archived output is already inside the image, so the RQ1-RQ3 scripts run offline.

Output written inside the container is discarded when the container exits, so mount a
host directory over `/v1/output` to keep it.

**Windows (Command Prompt):**
```cmd
docker run --rm -v "%cd%/out:/v1/output" lrasgen:v1 python scripts/run_all_apis.py
```

**Linux / macOS:**
```bash
docker run --rm -v "$PWD/out:/v1/output" lrasgen:v1 python scripts/run_all_apis.py
```

The image is built for `linux/amd64`. It also runs on Apple silicon, where emulation
makes execution slower without changing the results.

LLM access needs no setup, because the keys in `src/config.py` are active inside the
image. The `-e DEEPSEEK_API_KEY=...` and `-e OPENROUTER_API_KEY=...` flags override them.

## Prerequisites

When the Docker image is used, this section and Setup do not apply.

- **Python 3.10+**
- **LLM API keys** — at least one of:
  - [DeepSeek API](https://platform.deepseek.com/) — DeepSeek V4 Flash
  - [OpenRouter](https://openrouter.ai/) — GPT-5.4-mini and Gemini 3.1 Flash Lite
- **Network access** — all LLM calls go to cloud APIs

## Setup

### 1. Install Python dependencies

```bash
pip install -r src/requirements.txt
```

### 2. Obtain the API sources

The 53 API source trees are shipped as `api-sources.7z`. Extract the archive into the
`api-sources/` directory so that each API source tree is a subdirectory under
`api-sources/`, which is where the batch runner reads them from by default.

### 3. Configure LLM access

If neither variable is set, the packaged default key is used, so the pipeline runs without
any further configuration.

**Windows (Command Prompt):**
```cmd
set DEEPSEEK_API_KEY=sk-...
set OPENROUTER_API_KEY=sk-or-v1-...
```

**Linux / macOS:**
```bash
export DEEPSEEK_API_KEY="sk-..."
export OPENROUTER_API_KEY="sk-or-v1-..."
```

| Variable | Required | Description |
|----------|----------|-------------|
| `DEEPSEEK_API_KEY` | For DeepSeek | DeepSeek API key (default provider) |
| `OPENROUTER_API_KEY` | For GPT / Gemini | OpenRouter API key |

No key has to be supplied: `src/config.py` already carries one for each endpoint, and the
pipeline uses those. Each variable above overrides the corresponding hard-coded key, so
setting one is only necessary to run on your own account.

Each packaged key is valid for 30 days or until its quota of 200 USD is exhausted,
whichever comes first. The quota covers a full run over the 53 subject APIs, so the
benchmark, or any subset of it, can be executed at no cost to the user.

## Quick Start — Run a Single API

**Windows:**
```cmd
python src\main.py --api-path <package-root>\api-sources\CatWatch\catwatch --framework spring-boot --output-dir <package-root>\output\CatWatch
```

**Linux / macOS:**
```bash
python src/main.py --api-path <package-root>/api-sources/CatWatch/catwatch --framework spring-boot --output-dir <package-root>/output/CatWatch
```

Both paths are absolute: `--api-path` points at the API's project root and `--output-dir` at the directory its output is written to. The `--framework` flag is required and names the framework the API is built with, one of
the thirteen the pipeline supports (`jersey`, `jdk`, `spring-boot`, `spring-boot-kotlin`,
`aspnetcore`, `flask`, `django`, `webpy`, `tornado`, `express`, `koa`, `nextjs`, and
`nestjs`). On success the output appears under the directory `--output-dir` names,
containing intermediate JSON files for each step and the final `generated_oas.json`:

```
output/CatWatch/
├── step1_entry_files.json
├── step2_code_files.json
├── step3_endpoints.json
├── step4_details.json
├── step5_constraints.json
└── generated_oas.json
```

The terminal log reports the total number of endpoints, parameters, constraints, and
responses identified.

## Full Batch Run — All 53 APIs

```bash
python scripts/run_all_apis.py
```

The script reads the API source trees from `api-sources/` and writes each API's output
under `output/lrasgen_generated/`; `--datasets` and `--out-root` override those two
roots. `--only NAME[,NAME]` runs a subset, `--group N` runs one batch of the run order,
`--parallel N` sets how many APIs run at once, and `--list` prints the APIs with their
source paths and frameworks.

## Reproducing the Reported Results

`scripts/evaluate_rq1.py`, `scripts/evaluate_rq2.py`, and `scripts/evaluate_rq3.py` turn
the archived pipeline output into the RQ1–RQ3 figures and write them under `evaluation/`.
None of the three calls an LLM or needs an API key, so they can be run against the
archived output directly. `EVALUATION.md` documents the matching rules they apply and the
files each one writes. `scripts/cost_table.py` writes the runtime, token, and cost table
to `output/cost_table.md`.

## Pipeline Steps

| Step | File | What it does | Uses LLM? |
|------|------|-------------|-----------|
| 1 | `step1.py` | Scans source tree for endpoint entry files using framework-specific patterns | No |
| 2 | `step2.py` | Resolves imports, extracts and cleans source code | No |
| 3 | `step3.py` | Extracts endpoint methods (HTTP method, path, summary) | Yes |
| 4 | `step4.py` | Extracts parameters and responses per endpoint | Yes |
| 5 | `step5.py` | Extracts parameter constraints (min, max, enum, format, etc.) | Yes |
| 6 | `step6.py` | Assembles the extracted data into an OpenAPI 3.1.1 document and checks it | No |

## Supported Frameworks

| Language | Frameworks |
|----------|------------|
| Java | Jersey, JDK, Spring Boot |
| Kotlin | Spring Boot |
| C# | ASP.NET Core |
| Python | Django, Flask, Tornado, Web.py |
| JavaScript | Express, Next.js |
| TypeScript | Koa, NestJS |

## Command-Line Reference

```
python src/main.py --api-path <PATH> --framework <NAME> --output-dir <PATH> [OPTIONS]
```

| Flag | Description | Default |
|------|-------------|---------|
| `--api-path` | Absolute path to the project root of one subject API | *required* |
| `--framework` | Framework the API is built with | *required* |
| `--output-dir` | Absolute path of the directory this API's output is written to | *required* |
| `--config-file` | Framework-specific configuration file (Django `urls.py`, Flask `__init__.py`) | — |
| `--keyword` | Framework-specific search keyword (Tornado handler list) | — |
| `--urls` | Web.py URL routing list, comma-separated pattern/controller pairs | — |
| `--url-context` | Routes declared outside the handlers | — |
| `--exclude-deps` | Directories whose files are left out of the dependency set reaching the prompts | — |
| `--exclude-dirs` | Directories skipped when scanning for endpoint entry files | — |

## License

The package is distributed under the Apache License 2.0, which covers the source code, the
data, and the documentation alike; third-party material retains its own licenses. See
`LICENSE` and `NOTICE`.

## Citation

```bibtex
@article{lrasgenpaper,
  author  = {Deng, Sida and Huang, Rubing and Zhang, Man and Cui, Chenhui and Towey, Dave and Wang, Rongcun},
  title   = {{LRASGen}: {LLM}-based {RESTful} {API} Specification Generation},
  journal = {ACM Transactions on Software Engineering and Methodology},
  year    = {2026},
  doi     = {10.1145/3810241}
}
```

## Troubleshooting

**"No entry files found"**: Python frameworks (Django, Flask, Tornado, Web.py) always need
`--framework` plus the flags that locate their routing, such as `--config-file`,
`--keyword`, or `--urls`. Check `scripts/run_all_apis.py` for the exact command each of
the 53 subject APIs uses.

**Connection errors**: Verify your API key is correct and your network can reach
`openrouter.ai` and `api.deepseek.com`.

**Empty or partial output**: The LLM may have returned a response that does not parse.
The pipeline retries a failed call up to `CHAT_MAX_RETRIES` times with exponential
backoff. Check the terminal log for `[WARN]` lines.
