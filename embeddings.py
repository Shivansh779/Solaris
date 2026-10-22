"""Local embedding model access for Solaris' semantic memory.

Every vector Solaris stores is produced here, on this machine, by a local
Ollama model. Nothing in this module ever calls a cloud API — the whole point
of Constellation Memory is that it never leaves the disk.

The default model is `all-minilm:33m` (all-MiniLM-L12-v2): 384 dimensions,
67 MB on disk, Apache-2.0. It is a symmetric sentence-similarity model, so
documents and questions are embedded the same way — there are no
`search_document:` / `search_query:` prefixes to get wrong.

Public contract — no function in this module ever raises:

    embed(texts)          -> list[list[float]] | None
        One vector per input, in input order, so `len(result) == len(texts)`
        always. `None` when Ollama is unreachable, the model is missing or
        the response is malformed — never a partial list, because a short
        list would silently attach the wrong vector to the wrong chunk.
        `[]` for an empty input list. A request that outlives `TIMEOUT`
        seconds is given up on rather than blocking the caller.
    embed_one(text)       -> list[float] | None
    model_name()          -> str          the configured model id
    dimension()           -> int | None   actual dimension of the last embed
    expected_dimension()  -> int | None   dimension the configured model should have
    model_available()     -> bool         Ollama is up and the model is pulled
    warm()                -> None         load the model in the background
"""

import numbers
import threading

from _log import system_log

DEFAULT_MODEL = "all-minilm:33m"

# The dimension of the default model. `dimension()` reports what the model
# actually produced, so a model change is visible instead of silently mixing
# two vector spaces.
DIMENSION = 384

# Ollama unloads an idle model after 5 minutes by default, and the next
# embed then pays a full model load (0.3-3s) in the middle of a chat turn.
KEEP_ALIVE = "30m"

# Ollama's runner fails reproducibly on very large embed batches (>=512
# inputs dies with a runner EOF). 256 is comfortably safe.
MAX_BATCH = 256

# The Ollama SDK sets no timeout of its own (httpx timeout=None), so a busy
# or wedged Ollama would freeze the app in the middle of a turn. 60 seconds
# is far above the measured cost of a normal batch (0.06 s idle, ~20 s for
# 300 texts); past that the batch is given up on instead of blocking.
TIMEOUT = 60

# Embedded in place of an empty input so the returned list always holds one
# vector per input the caller passed.
EMPTY_TEXT = " "

_lock = threading.Lock()
_last_dimension = None
_last_model = None
_warmed = False
_warming = False


def _note(level, message):
    """Log without ever raising: a broken log file must not break embedding."""
    try:
        system_log("EMBED", level, message)
    except Exception:
        pass


def model_name():
    """The configured embedding model id.

    `config.json` is user-editable, so it may be missing, malformed, or hold a
    blank model name. Every one of those falls back to DEFAULT_MODEL. The file
    is read fresh on every call (never cached in a module global) so a change
    on the Settings page takes effect without a restart.
    """
    try:
        import config_io

        config = config_io.load_config() or {}
        model = (config.get("embeddings") or {}).get("model")
    except Exception:
        return DEFAULT_MODEL
    if not isinstance(model, str):
        return DEFAULT_MODEL
    return model.strip() or DEFAULT_MODEL


def expected_dimension():
    """The dimension the configured model is expected to produce.

    None when the model was changed to something this module does not know the
    size of — the caller has to measure it with `dimension()` instead.
    """
    return DIMENSION if model_name() == DEFAULT_MODEL else None


def dimension():
    """The dimension of the last successful embed, or None if none has happened.

    This is the number a vector schema has to be built from: it is read from
    the model's actual output, not from a hardcoded constant.
    """
    with _lock:
        return _last_dimension


def model_available():
    """True when Ollama is running and the configured model is pulled."""
    try:
        import ollama

        response = _list_models(ollama)
    except Exception:
        return False
    wanted = model_name()
    for name in _model_names(response):
        if name == wanted or (":" not in wanted and name == f"{wanted}:latest"):
            return True
    return False


def embed(texts):
    """Embed strings with the local model.

    Returns one vector per input, in input order, or None when the model is
    unavailable or the response was malformed. Never raises: a missing model
    must not break the app.
    """
    try:
        items = _clean_all(texts)
        if not items:
            return []
        try:
            import ollama
        except Exception as error:
            _note("WARNING", f"Ollama client unavailable: {error}")
            return None
        return _embed_batches(ollama, model_name(), items)
    except Exception as error:
        _note("WARNING", f"Embedding failed unexpectedly: {error}")
        return None


def embed_one(text):
    """Embed a single string. None when the model is unavailable or text is empty."""
    if not isinstance(text, str) or not text.strip():
        return None
    vectors = embed([text])
    if not vectors:
        return None
    return vectors[0]


def warm():
    """Load the model into Ollama in the background.

    The first embed of a process pays the runner spawn and the Metal init;
    doing it here keeps that cost out of a chat turn. Safe to call any number
    of times: a failed warm-up can be retried later.
    """
    global _warmed, _warming
    with _lock:
        if _warmed or _warming:
            return
        _warming = True

    def _run():
        global _warmed, _warming
        ok = False
        try:
            model = model_name()
            if not model_available():
                _note("INFO", f"Embedding warm-up skipped: {model} is not pulled.")
                return
            import ollama

            vectors = _embed_batches(ollama, model, ["warmup"])
            if vectors is None:
                _note("WARNING", f"Embedding warm-up skipped: {model} did not answer.")
                return
            ok = True
            _note("INFO", f"Embedding model {model} is warm.")
        except Exception as error:
            _note("WARNING", f"Embedding warm-up skipped: {error}")
        finally:
            with _lock:
                # _warmed is written first: once _warming is False the outcome
                # is final and a later warm() cannot race with this thread.
                _warmed = ok
                _warming = False

    try:
        threading.Thread(target=_run, daemon=True).start()
    except Exception as error:
        with _lock:
            _warming = False
        _note("WARNING", f"Embedding warm-up could not start: {error}")


# ------------------------------------------------------------------ internals


def _clean_all(texts):
    """Normalise the caller's input into a list of non-empty strings.

    One entry per input, always: empty, whitespace-only and non-string values
    become a single space so the returned vectors stay aligned with the input
    list the caller zips them against.
    """
    if texts is None:
        return []
    if isinstance(texts, str):
        texts = [texts]
    try:
        items = list(texts)
    except TypeError:
        return []
    return [_clean(item) for item in items]


def _clean(text):
    """One input string, guaranteed non-empty."""
    if isinstance(text, str):
        value = text.strip()
    else:
        try:
            value = str(text).strip()
        except Exception:
            value = ""
    return value or EMPTY_TEXT


def _embed_batches(ollama, model, items):
    """Embed the items in batches, preserving order. None on any failure."""
    vectors = []
    dimension = None
    for start in range(0, len(items), MAX_BATCH):
        batch = items[start:start + MAX_BATCH]
        try:
            response = _embed_batch(ollama, model, batch)
        except Exception as error:
            _note("WARNING", f"Embedding failed for {len(batch)} text(s): {error}")
            return None
        batch_vectors = _read_embeddings(response, len(batch))
        if batch_vectors is None:
            _note("WARNING", "Ollama returned a malformed embedding response.")
            return None
        if dimension is None:
            dimension = len(batch_vectors[0])
        elif any(len(vector) != dimension for vector in batch_vectors):
            _note("WARNING", "Ollama returned inconsistent embedding dimensions.")
            return None
        vectors.extend(batch_vectors)
    _remember(model, dimension)
    return vectors


def _timeout_client(ollama):
    """An Ollama client with a timeout, or None when the SDK has no such client.

    The SDK's own client sets no timeout, so a request can block forever.
    """
    factory = getattr(ollama, "Client", None)
    if factory is None:
        return None
    try:
        return factory(timeout=TIMEOUT)
    except Exception:
        return None


def _embed_batch(ollama, model, batch):
    """One embed request, through a timeout client when the SDK offers one."""
    client = _timeout_client(ollama)
    if client is not None and hasattr(client, "embed"):
        return client.embed(model=model, input=batch, keep_alive=KEEP_ALIVE)
    return ollama.embed(model=model, input=batch, keep_alive=KEEP_ALIVE)


def _list_models(ollama):
    """The models Ollama has pulled."""
    client = _timeout_client(ollama)
    if client is not None and hasattr(client, "list"):
        return client.list()
    return ollama.list()


def _read_embeddings(response, expected):
    """Validate the Ollama response and return the vectors as float lists.

    None when the response is malformed: no embeddings, the wrong count, or a
    vector that is not a list of finite numbers.
    """
    if isinstance(response, dict):
        raw = response.get("embeddings")
    else:
        raw = getattr(response, "embeddings", None)
    if not isinstance(raw, (list, tuple)) or len(raw) != expected:
        return None
    vectors = []
    for vector in raw:
        if not isinstance(vector, (list, tuple)) or not vector:
            return None
        values = []
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, numbers.Real):
                return None
            number = float(value)
            if number != number or number in (float("inf"), float("-inf")):
                return None
            values.append(number)
        vectors.append(values)
    return vectors


def _remember(model, dimension):
    """Record the dimension the model actually produced."""
    global _last_dimension, _last_model
    if not dimension:
        return
    with _lock:
        changed = _last_dimension != dimension or _last_model != model
        _last_dimension = dimension
        _last_model = model
    if not changed:
        return
    expected = DIMENSION if model == DEFAULT_MODEL else None
    if expected is not None and expected != dimension:
        _note("WARNING", f"Model {model} produced {dimension}-dim vectors, expected "
                         f"{expected}. The vector index has to be rebuilt.")
    else:
        _note("INFO", f"Embedding model {model} produces {dimension}-dim vectors.")


def _model_names(response):
    """The model names Ollama reports, as plain strings."""
    if isinstance(response, dict):
        entries = response.get("models")
    else:
        entries = getattr(response, "models", None)
    names = []
    for entry in entries or []:
        if isinstance(entry, dict):
            name = entry.get("model")
        else:
            name = getattr(entry, "model", None)
        if isinstance(name, str):
            names.append(name)
    return names
