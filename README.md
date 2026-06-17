# LRASGen — LLM-based RESTful API Specification Generation

LRASGen is a pipeline that automatically generates OpenAPI Specifications (OAS) directly from RESTful API source code using Large Language Models. It requires no compilation, no runtime environment, and works across six programming languages and twelve frameworks.

## Repository Structure

```
.
├── README.md
├── LICENSE
├── requirements.txt
├── run_all_apis.bat              # Batch run — Windows
├── run_all_apis.sh               # Batch run — Linux / macOS
├── src/                          # Pipeline source code
│   ├── main.py                   # Entry point — single-API pipeline orchestrator
│   ├── llm.py                    # LLM communication (GPT-5.4-mini, DeepSeek V4 Flash, Gemini 3.1 Flash Lite)
│   ├── logger.py                 # Progress logger
│   ├── frameworks.py             # Framework knowledge base
│   ├── apis.yaml                 # 53-API dataset configuration
│   ├── step1.py                  # Endpoint entry-file discovery
│   ├── step2.py                  # Dependency resolution & code extraction
│   ├── step3.py                  # Endpoint method identification (LLM)
│   ├── step4.py                  # Parameter & response identification (LLM)
│   ├── step5.py                  # Parameter constraint identification (LLM)
│   └── step6.py                  # OAS assembly & validation
├── datasets/                     # Place datasets here (see Setup)
└── output/                       # Pipeline output (generated at runtime)
```

## Prerequisites

- **Python 3.10+**
- **LLM API keys** — at least one of:
  - [OpenRouter](https://openrouter.ai/) — provides access to GPT-5.4-mini and Gemini 3.1 Flash Lite
  - [DeepSeek API](https://platform.deepseek.com/) — DeepSeek V4 Flash
- **Network access** — all LLM calls go to cloud APIs

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Alysrazorr/LRASGen.git
cd LRASGen
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Obtain the datasets

The 53-API datasets are included as `datasets/datasets.zip` (tracked via Git LFS). Extract the zip into the `datasets/` directory so that each API source tree is a subdirectory under `datasets/`.

### 4. Configure environment variables

**Windows (Command Prompt):**
```cmd
set LRASGEN_DATASETS=D:\path\to\LRASGen\datasets
set DEEPSEEK_API_KEY=sk-...
set OPENROUTER_API_KEY=sk-or-v1-...
```

**Linux / macOS:**
```bash
export LRASGEN_DATASETS="/home/user/LRASGen/datasets"
export DEEPSEEK_API_KEY="sk-..."
export OPENROUTER_API_KEY="sk-or-v1-..."
```

| Variable | Required | Description |
|----------|----------|-------------|
| `LRASGEN_DATASETS` | For batch runs | Absolute path to the `datasets/` directory (required by `run_all_apis.sh`/`.bat`) |
| `DEEPSEEK_API_KEY` | For DeepSeek | DeepSeek API key (default provider) |
| `OPENROUTER_API_KEY` | For GPT / Gemini | OpenRouter API key |

`LRASGEN_DATASETS` is only required by the batch-run scripts. For single-API mode, you can pass the path directly via `--root-path`. At least one LLM provider must be configured.

## Quick Start — Run a Single API

**Windows:**
```cmd
python src\main.py --root-path datasets --api-path catwatch --framework spring-boot --output-name catwatch
```

**Linux / macOS:**
```bash
python src/main.py --root-path datasets --api-path catwatch --framework spring-boot --output-name catwatch
```

The `--framework` flag can be omitted — the pipeline auto-detects the framework from the project structure.

Upon success, output appears under `output/catwatch/`:

```
output/catwatch/
├── step1_entry_files.json
├── step2_code_files.json
├── step3_endpoints.json
├── step4_details.json
├── step5_constraints.json
└── generated_oas.json
```

**Using a different LLM:**

```bash
# GPT-5.4-mini (via OpenRouter)
python src/main.py --root-path datasets --api-path catwatch --llm gpt

# Gemini 3.1 Flash Lite (via OpenRouter)
python src/main.py --root-path datasets --api-path catwatch --llm gemini

# Cross-validation with all 3 LLMs
python src/main.py --root-path datasets --api-path catwatch --llm all --enable-cross-validation true
```

## Full Batch Run — All 53 APIs

### Windows

```cmd
run_all_apis.bat
```

### Linux / macOS

```bash
./run_all_apis.sh
```

## Pipeline Steps

| Step | File | What it does | Uses LLM? |
|------|------|-------------|-----------|
| 1 | `step1.py` | Scans source tree for endpoint entry files using framework-specific patterns | No |
| 2 | `step2.py` | Resolves imports, extracts and cleans source code | No |
| 3 | `step3.py` | Extracts endpoint methods (HTTP method, path, summary) | Yes |
| 4 | `step4.py` | Extracts parameters and responses per endpoint | Yes |
| 5 | `step5.py` | Extracts parameter constraints (min, max, enum, format, etc.) | Yes |
| 6 | `step6.py` | Assembles all extracted data into a valid OpenAPI 3.1.1 JSON | No |

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
python main.py --root-path <PATH> --api-path <PATH> [OPTIONS]
```

| Flag | Description | Default |
|------|-------------|---------|
| `--root-path` | Root directory containing all API source trees | `.` |
| `--api-path` | Path to the API source code (relative to `--root-path`, or absolute) | *required* |
| `--framework` | Framework used by the API | auto-detected |
| `--config-file` | Framework-specific config file (Django `urls.py`, Flask `__init__.py`, etc.) | — |
| `--keyword` | Search keyword for handler discovery (Tornado) | — |
| `--urls` | Web.py URL routing list (comma-separated path/handler pairs) | — |
| `--output-dir` | Override output directory | `output/` |
| `--output-name` | Subdirectory name for this API's output | derived from `--api-path` |
| `--llm` | Provider: `gpt`, `deepseek`, `gemini`, `all` | `deepseek` |
| `--temperature` | LLM temperature | `0.2` |
| `--enable-validate` | Enable OAS schema compliance check (requires `openapi-schema-validator`) | `false` |
| `--enable-cross-validation` | Enable 3-LLM majority voting | `false` |

## License

Creative Commons Attribution 4.0 International (CC BY 4.0).

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

**`LRASGEN_DATASETS is not set`**: Only required by `run_all_apis.sh`/`.bat`. For single-API mode, use `--root-path` instead.

**"No entry files found"**: Python frameworks (Django, Flask, Tornado, Web.py) always need `--framework` plus additional flags. Check `run_all_apis.sh` / `run_all_apis.bat` for the exact commands.

**Connection errors**: Verify your API key is correct and your network can reach `openrouter.ai` and `api.deepseek.com`.

**Empty or partial output**: The LLM may have returned an invalid JSON response. The pipeline retries once by default. Check the terminal log for `[WARN]` lines.
