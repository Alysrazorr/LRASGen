
# Where a model is served, one entry per endpoint the pipeline calls. These are
# the fields that are identical for every model behind an endpoint, so they are
# written once here rather than restated by each model below. Setting
# api_key_env in the environment overrides api_key_default; the literal is the
# key used when that variable is unset, which is how the pipeline is run here.
PROVIDER_CONFIG = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "api_key_default": "sk-6e9fb9494119400487cc09ea401b6c09",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "api_key_default": "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",
    },
}

# The models to call, in the order cross-validation polls them. `name` is how a
# model is identified everywhere else: it labels the usage and cost report, and
# the first entry here is the model the pipeline asks when it asks only one.
# `provider` names the entry
# above that serves the model, and llm.py resolves the sender from it, so the
# models behind one provider share a sender.
MODEL_CONFIG = [
    {
        "name": "deepseek",
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "price": [0.02, 0.6],
    },
    {
        "name": "gpt",
        "provider": "openrouter",
        "model": "openai/gpt-5.4-mini",
        "price": [0.75, 4.5],
    },
    {
        "name": "gemini",
        "provider": "openrouter",
        "model": "google/gemini-3.1-flash-lite",
        "price": [0.25, 1.5],
    },
]


# Each model together with the provider that serves it. This is what the
# pipeline reads, so nothing downstream has to know the config is layered.
PROVIDERS = [{**PROVIDER_CONFIG[m["provider"]], **m} for m in MODEL_CONFIG]

TEMPERATURE = 0.2

MAX_TOKENS = 131072

REQUEST_TIMEOUT_S = 120

# How many models run, and how they are combined, both follow from MODEL_CONFIG.
# Putting one model in the list runs that model alone; putting several runs them
# against each other. This is the only place either behaviour is decided.

# The model the pipeline asks when it asks only one. That is the first model
# configured, so the model to run alone goes at the top of MODEL_CONFIG.
PRIMARY_MODEL = PROVIDERS[0]["name"]

# Cross-validation compares models with each other, so it needs more than one to
# compare. Below that there is nothing to agree or disagree about, and every
# step asks PRIMARY_MODEL alone.
ENABLE_CROSS_VALIDATION = len(PROVIDERS) > 1

# How many models must list an entity for cross-validation to keep it. A
# majority of the configured models, which as a fraction of the whole is half
# the list: three models give 1.5, so two of them have to agree. The comparison
# against this is strict, and that strictness is what makes the rule a majority
# rather than a tie; see cross_validate in llm.py.
CROSS_VALIDATE_MIN_VOTES = len(PROVIDERS) / 2

CHAT_MAX_RETRIES = 3

CROSS_VALIDATE_MAX_ROUNDS = 3

RETRY_BACKOFF_BASE_S = 2

ERROR_MESSAGE_MAX_CHARS = 200
RESPONSE_SNIPPET_MAX_CHARS = 500

MAX_IMPORT_DEPTH = 99

FLASK_IMPORT_MAX_DEPTH = 2

# One level: the fields of the class the request names. A field typed as
# another class is reported as that one field rather than opened in turn, which
# is what the request itself declares and what the specification records.
DTO_EXPANSION_MAX_DEPTH = 1

STEP4_MAX_WORKERS = 10
STEP5_MAX_WORKERS = 10

STEP4_PROGRESS_EVERY = 20
STEP5_PROGRESS_EVERY = 50
