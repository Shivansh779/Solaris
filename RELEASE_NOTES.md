# Release Notes

## 1.0.2 — Model error-state handling

### Added

Session-scoped model availability tracking. Solaris no longer retries a model it
already knows is unusable, which removes repeated failed round trips from the
fallback chain.

| Provider response | Treatment | Duration |
| --- | --- | --- |
| `429` rate limit | Model disabled | Rest of session |
| `404` / model-not-found | Model disabled | Rest of session |
| `503` service unavailable | Cooldown | 30 seconds, then eligible again |
| Anything else | Unchanged | — |

- **429 and model-not-found** add the model to `unavailable_models`. It is skipped
  by the automatic fallback chain for the remainder of the session.
- **503** records a timestamp in `temporary_unavailable`. The model is skipped
  while the cooldown is under 30 seconds; once it expires the entry is removed
  and the model becomes eligible again. Each model carries its own independent
  timestamp.
- Any unrecognised error keeps the previous behaviour: log, spinner update, short
  sleep, move to the next model.

### Scope

- Applies to the OpenRouter fallback chain in `ask_openrouter()` and to Gemini in
  `ask_gemini()`.
- The local Ollama model is not tracked — it is the last resort in the chain, and
  disabling it would make every later message fail immediately instead of trying.
- Model ordering, the success path, and the Ollama last-resort path are unchanged.

### Implementation

- New `model_state.py` holds the state and the classification helper. Two plain
  in-memory containers — a `set` and a `dict` — with no persistence, so all state
  is discarded when Solaris exits.
- `model_state.py` is a separate module rather than inline in `chatbot.py` because
  `chatbot.py` executes `input()` at import time and cannot be imported by pytest.
- Error classification reads `status_code` first, then `code`, then falls back to
  the message body. The attribute lookup is required: OpenRouter exceptions carry
  only the message in `str(e)`, so the existing substring check could not see the
  status at all. An explicit `429`/`404`/`503` always wins over the message body,
  so a 503 that happens to mention a missing model is still treated as temporary.

### Testing

- 16 tests in `Test/model_state/test_model_state.py`, covering all five failure
  classes, the 30-second cooldown boundary in both directions, independent
  per-model cooldowns, ordering preservation, and session reset.
- The test file has to be added with `git add -f`: `.gitignore` lists `Test/`, but
  the existing suite is already tracked in git, so the rule is only inert for
  files committed before it was added.

### Known issues

- `chatbot.py` is stored with CRLF line endings in git but LF in the working tree,
  so it shows up as a full-file rewrite. This normalisation was already present in
  the working tree before this change; the functional diff is confined to
  `ask_gemini()` and `ask_openrouter()`. Worth committing the normalisation on its
  own before merging.
- `helper_ai.about()` still reports version `1.0.1`; the string is hardcoded and
  was not bumped with this release note.
- The wiring inside `ask_openrouter()`/`ask_gemini()` is not covered by the
  committed suite, only by `model_state` itself, for the import reason above.