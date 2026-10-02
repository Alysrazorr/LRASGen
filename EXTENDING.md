# EXTENDING LRASGen

LRASGen ships with a fixed set of LLM providers and a fixed set of REST API
frameworks. This document describes how to add a new one in each case.

Neither extension requires changing the pipeline steps. Both are additive: an
existing configuration keeps working unchanged.

## 1. Adding a new LLM/model

Two files are involved: `src/config.py`, which says where a model is served and
what it costs, and `src/llm.py`, which holds one sender function per model.

### 1.1 Describe the endpoint

`PROVIDER_CONFIG` in `src/config.py` holds one entry per endpoint the pipeline
calls, and the fields that every model behind that endpoint shares. Add an entry
when the new model is served somewhere the pipeline does not reach yet:

```python
PROVIDER_CONFIG = {
    ...
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "api_key_env": "OLLAMA_API_KEY",
        "api_key_default": "ollama",
    },
}
```

`api_key_env` names the environment variable that overrides `api_key_default`,
which is the literal used when that variable is unset. Two models behind one
endpoint share one entry here rather than restating the URL and the key.

### 1.2 List the model

`MODEL_CONFIG` in the same file lists the models to call. `name` identifies the
model everywhere else, `provider` names the `PROVIDER_CONFIG` entry that serves
it, `model` is the identifier that endpoint expects, and `price` is
`[input, output]` in USD per 1 million tokens:

```python
MODEL_CONFIG = [
    ...
    {
        "name": "ollama",
        "provider": "ollama",
        "model": "llama3.3:70b",
        "price": [0.0, 0.0],
    },
]
```

`PROVIDERS` is built at import from the two tables, so nothing downstream reads
the layering. `price` is what `_cost_usd()` in `llm.py` reads, and a model with
no price reports a cost of 0. `get_usage()` reports one entry per model in this
list.

### 1.3 Write its sender

`_sender()` in `src/llm.py` resolves a model to the function named after it: the
model's `name`, with `-` replaced by `_`, prefixed with `_send_`. Adding a model
means adding that function and nothing else, with no table in between to update:

```python
def _send_ollama(spec, messages, temperature=TEMPERATURE):
    client = _client(spec)
    return client.chat.completions.create(
        model=spec["model"],
        messages=messages,
        stream=False,
        temperature=temperature,
        max_tokens=MAX_TOKENS,
        timeout=REQUEST_TIMEOUT_S,
        response_format={"type": "json_object"},
    )
```

`_client(spec)` builds an OpenAI-compatible client from the endpoint entry, so a
sender states no URL and no key. The returned object must expose `usage`
(prompt, completion, and total tokens) and `choices[0].message.content`;
`chat()` reads both.

`_check_senders()` runs at import and raises when a configured model has no
function of its name, so a missing sender is reported before the run starts
rather than part way through the first API that uses it.

### 1.4 Run it

There is no switch to set. `ask()` in `src/llm.py` reads the model list:
`ENABLE_CROSS_VALIDATION` is `len(PROVIDERS) > 1`, so a list holding one model
asks that model alone (`PRIMARY_MODEL`, the first entry in the list) and a list
holding several cross-validates across them. A model joins a run by being in
`MODEL_CONFIG` and leaves it by being taken out.

`cross_validate()` keeps an entity that more than half the models list, testing
each count strictly against `len(PROVIDERS) / 2`; with three models that is a
majority of two. `chat()` retries a failed call `CHAT_MAX_RETRIES` times with
exponential backoff, and `cross_validate()` re-prompts for up to
`CROSS_VALIDATE_MAX_ROUNDS` rounds on disagreement. Both constants are in
`src/config.py`.

### 1.5 Use it

```bash
python src/main.py --api-path api-sources/CatWatch/catwatch --framework spring-boot --output-dir output/CatWatch
```

The models the run calls come from `MODEL_CONFIG`, so the same command runs one
model or several depending on what that list holds.


## 2. Adding a new REST API framework

Three files are involved: `src/frameworks.py`, `src/step1.py`, and
`src/main.py`. Which parts you touch depends on how the framework declares its
endpoints.

### 2.1 Describe the framework

Add an entry to `FRAMEWORKS` in `src/frameworks.py`:

```python
"fastapi": {
    "language": "python",
    "name": "FastAPI",
    "suffix": ".py",
    "scan_type": "regex",
    "regex": [
        r'@\w*\.(get|post|put|delete|patch)\([\'"][^\'"]+[\'"]',
        r'@\w*\.(get|post|put|delete|patch)\([\'"][^\'"]+[\'"]\)',
        r'APIRouter\s*\(',
    ],
},
```

| Field | Meaning |
|---|---|
| `language` | informational; recorded in the pipeline output |
| `name` | display name |
| `suffix` | file extension to scan |
| `scan_type` | `"regex"` or `"special"` |
| `regex` | content patterns that mark a file as an endpoint entry file (used by `"regex"` only) |

Because `main.py` builds `--framework`'s choices from `FRAMEWORKS.keys()`, the
new framework is immediately accepted on the command line.

### 2.2 If the framework needs custom discovery

`"regex"` is enough when entry files can be found by walking the tree and
matching file contents. It is not enough when the routes are declared somewhere
else: a URL dispatch table, a handler list, or the file path itself.

For those, set `scan_type` to `"special"`, write a handler in `src/step1.py`,
and register it in the `_HANDLERS` table at the bottom of that file:

```python
# src/step1.py
def _handle_fastapi(api):
    """Find the routers a FastAPI app mounts, then scan those files."""
    ...
    return matched_files


_HANDLERS = {
    "django": _handle_django,
    "flask":  _handle_flask,
    "tornado": _handle_tornado,
    "webpy":  _handle_webpy,
    "nextjs": _handle_nextjs,
    "fastapi": _handle_fastapi,      # added
}
```

A handler receives the `api` dict and returns a list of entry file paths. It can
read any extra key the caller supplies — the existing handlers use
`api["config_file"]`, `api["keyword"]`, and `api["urls"]` for exactly this
purpose, and those three arrive from the matching `--config-file`, `--keyword`,
and `--urls` command-line flags.

`step1.main()` dispatches on `scan_type`:

```python
if scan_type == "special":
    handler = _HANDLERS.get(api["framework"])
    if handler is None:
        raise NotImplementedError(...)
    files = handler(api)
else:
    files = _scan_by_regex(api)
```

### 2.3 The framework must be named

`--framework` is required. `src/main.py` builds its choices from
`FRAMEWORKS.keys()`, so a framework added to `frameworks.py` is accepted on the
command line without a second edit.

The pipeline does not guess the framework from the project layout. When an API
is run on its own, `--framework` states it; in a batch run,
`scripts/run_all_apis.py` states it for each of the 53 subject APIs.


### 2.4 Use it

```bash
python src/main.py --api-path MyApi/my-service --framework fastapi
```

## 3. Adding an API to the benchmark

A new subject API does not need a change to the pipeline. Add it to the `APIS`
list in `scripts/run_all_apis.py`, one tuple per API:

```python
APIS = [
    ...
    ("MyApi", "MyApi/my-service", "fastapi", []),
]
```

The four fields are the short name, the source path under the dataset root, the
framework, and any extra command-line arguments that API needs, such as the
`["--exclude-dirs", "src/main/java/app/coronawarn/verification/client"]` that
CWA carries. Place the source tree under the dataset root, then run the script;
`--list` prints the table it builds from those entries.

To run one API on its own, name its directory and output directory directly:

```bash
python src/main.py --api-path api-sources/MyApi/my-service --framework fastapi --output-dir output/MyApi
```

`src/apis.yaml` carries the same 53 APIs as a readable list. The batch script
builds its own table from `APIS` and does not read this file.
