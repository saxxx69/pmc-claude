# PMC Code Review — 2026-05-09

## Summary
- **Critical: 6**
- **Warning: 9**
- **Info: 6**

---

## Critical Findings

### [C-01] HNSW index persistence is write-only — data never loaded from disk

**File:** `pmc/storage/hnsw_index.py:26-33`, `pmc/memory.py:48`

**Issue:** `_init_index()` always creates a fresh empty hnswlib index. `save()` writes `hnsw.bin` on close, but no `load()` call exists anywhere. On every `PMCMemory.__init__`, `_rehydrate_index()` repopulates the index by re-encoding all 12k+ nodes from SQLite. This means:
1. The persisted `hnsw.bin` file is never read — it is dead output.
2. Cold start time grows linearly with graph size (currently 12,053 nodes × embedding call).
3. Every process discards the HNSW graph state it saved — ANN index quality degradation per ingest.

**Fix:**
```python
def _init_index(self) -> None:
    try:
        import hnswlib
        self._index = hnswlib.Index(space="cosine", dim=self.dim)
        if self.persist_path and os.path.exists(self.persist_path):
            meta_path = self.persist_path + ".meta.json"
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    meta = json.load(f)
                self._uuid_to_label = meta["uuid_to_label"]
                self._label_to_uuid = {int(k): v for k, v in meta.get("label_to_uuid", {}).items()}
                self._next_label = meta["next_label"]
                self._index.load_index(self.persist_path, max_elements=self.capacity)
                return
        self._index.init_index(max_elements=self.capacity, ef_construction=200, M=16)
        self._index.set_ef(50)
    except Exception:
        self._index = None
```
And in `memory.py` skip `_rehydrate_index()` when the index was loaded from disk.

---

### [C-02] HNSW capacity fixed at 20 000 — no resize, ingestion will crash

**File:** `pmc/memory.py:45`, `pmc/storage/hnsw_index.py:30`

**Issue:** `hnswlib.Index.init_index(max_elements=self.capacity)` allocates a fixed-size structure. `add_items()` raises `RuntimeError: The number of elements exceeds the specified limit` when capacity is exceeded — with no `resize_index()` anywhere in the codebase. At ~12k nodes and growing (FUNCTION nodes: 3715 per CLAUDE.md), every ingest of a non-trivial project will hard-crash mid-pipeline.

**Fix:**
```python
def add(self, nid: uuid.UUID, vec: list[float]) -> None:
    key = str(nid)
    if key in self._uuid_to_label:
        return
    if self._index is not None:
        current = self._index.get_current_count()
        if current >= self._index.get_max_elements() - 1:
            new_cap = self._index.get_max_elements() * 2
            self._index.resize_index(new_cap)
            self.capacity = new_cap
    # ... rest unchanged
```

---

### [C-03] Race condition in turn_index assignment — duplicate turn nodes

**File:** `pmc/cli/main.py:185-216`, `plugin/hooks/pmc-conversation-ingest.sh:91-100`

**Issue:** The Stop hook launches `pmc converse-ingest` in background (`&`). If two Stop events fire in quick succession for the same session (e.g. rapid responses), both processes execute:
1. `SELECT COALESCE(MAX(turn_index), -1)` → same value (e.g. 2)
2. Both insert `turn_index=3` for the same role

The idempotency check in `ingestion/conversation.py:239-250` is a SELECT before INSERT with no UNIQUE constraint on `(session_id, turn_index, role)`. SQLite has no unique enforcement here; both inserts succeed. The FOLLOWS linked-list is now forked.

**Fix:** Add a UNIQUE index to the DB schema:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_turn_unique
  ON nodes(
    json_extract(properties,'$.session_id'),
    json_extract(properties,'$.turn_index'),
    json_extract(properties,'$.role')
  )
  WHERE type_id='CONVERSATION_TURN';
```
And handle `IntegrityError` in `ingest_turn` to make it truly idempotent.

---

### [C-04] Shell variable injected into Python heredoc — code injection

**File:** `plugin/hooks/pmc-conversation-ingest.sh:52-87`, `108-144`

**Issue:** Both Python heredocs embed shell variables via interpolation:
```bash
path = "$transcript_path"         # line 57
limit = $CONTEXT_LIMIT_TOKENS     # line 113
threshold = $CONTEXT_THRESHOLD_PCT # line 114
```
`transcript_path` comes from parsing untrusted JSON (the Claude Code event). A path containing `"`, `\`, newline, or `$(...)` (if the JSON is malformed or injected) can break string literal syntax or execute arbitrary Python. Lines 113-114 are less severe (env vars), but `transcript_path` is fully attacker-controlled if the hook event is tampered with.

**Fix:** Pass variables via environment, not string interpolation:
```bash
TRANSCRIPT_PATH="$transcript_path" python3 << 'PYEOF'
import json, sys, os
path = os.environ["TRANSCRIPT_PATH"]
# ... rest of script
PYEOF
```
Note: use `<< 'PYEOF'` (single-quoted) to disable all interpolation inside the heredoc.

---

### [C-05] Concurrent HNSW writes across processes — hnsw.bin corruption

**File:** `plugin/hooks/pmc-conversation-ingest.sh:91-100`, `plugin/hooks/pmc-user-prompt.sh:57,64,70`

**Issue:** `pmc-user-prompt.sh` spawns three serial `pmc` CLI subprocesses. `pmc-conversation-ingest.sh` spawns one more in background `&`. Each process:
1. Calls `PMCMemory.__init__` → `_rehydrate_index()` from DB
2. Mutates HNSW in-memory
3. On `m.close()` → `hnsw.save()` overwrites `hnsw.bin`

SQLite WAL handles DB row isolation. `hnsw.bin` has no locking. Two concurrent `pmc` processes will race to write it; the last one wins, losing any vectors the other added. In the worst case, the metadata JSON and the binary index are written by different processes with different label maps → corrupted index.

**Fix:** Use a file lock around `hnsw.save()` and `_init_index()` load:
```python
import fcntl

def save(self) -> None:
    if not self.persist_path:
        return
    lock_path = self.persist_path + ".lock"
    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        # ... write meta + index
        fcntl.flock(lf, fcntl.LOCK_UN)
```

---

### [C-06] Context usage calculation includes output_tokens — premature /clear trigger

**File:** `plugin/hooks/pmc-conversation-ingest.sh:132-139`

**Issue:** Context % is computed as:
```python
total = (
    cache_read_input_tokens +
    cache_creation_input_tokens +
    input_tokens +
    output_tokens
)
pct = int(total * 100 / limit)
```
Output tokens are not consumed from the *input* context window for the current request — they are produced, not consumed. The Anthropic API reports `output_tokens` separately. Summing them inflates the calculated usage, causing the 80%-threshold auto-`/clear` to fire well before the context is actually full. For a 20k-token response on a 100k-input-token session this adds ~20% phantom context, tripling false-positive `/clear` triggers.

**Fix:**
```python
total = (
    usage.get('cache_read_input_tokens', 0) +
    usage.get('cache_creation_input_tokens', 0) +
    usage.get('input_tokens', 0)
    # do NOT add output_tokens
)
```

---

## Warning Findings

### [W-01] HNSW _init_index swallows all exceptions silently

**File:** `pmc/storage/hnsw_index.py:32-33`

**Issue:** `except Exception: self._index = None` catches `ImportError`, `MemoryError`, version incompatibilities, and filesystem errors alike. The fallback is brute-force cosine over all stored vectors — O(n) per query, catastrophic at 12k+ nodes. The caller has no signal that hnswlib failed.

**Fix:** Log at minimum `warnings.warn(f"hnswlib unavailable, using brute-force fallback: {e}")`. Consider re-raising on `MemoryError`.

---

### [W-02] hnsw.save() failure silently ignored in PMCMemory.close()

**File:** `pmc/memory.py:122-127`

**Issue:**
```python
def close(self) -> None:
    try:
        self.hnsw.save()
    except Exception:
        pass
    self.backend.close()
```
A disk-full or permission error on `hnsw.save()` is silently swallowed. The index update is lost with no user notification. This is especially bad given C-01 — the file is the only persistence mechanism.

**Fix:** At minimum log the exception: `except Exception as e: import warnings; warnings.warn(f"hnsw save failed: {e}")`

---

### [W-03] Cooldown lock file path traversal if session_id contains `/`

**File:** `plugin/hooks/pmc-conversation-ingest.sh:154-158`

**Issue:**
```bash
COOLDOWN_FILE="/tmp/pmc-autoclear-${session_id}.lock"
touch "$COOLDOWN_FILE"
```
If `session_id` contains `/` (e.g. `abc/../../etc/crontab`), the `touch` follows the traversal. `session_id` comes from a JSON field parsed from the Claude Code event payload. While Claude Code-generated IDs are UUIDs, there is no validation before use.

**Fix:**
```bash
# Sanitize: replace any non-alphanumeric chars
safe_session=$(printf '%s' "$session_id" | tr -c 'a-zA-Z0-9_-' '_')
COOLDOWN_FILE="/tmp/pmc-autoclear-${safe_session}.lock"
```

---

### [W-04] Cooldown lock file never cleaned up

**File:** `plugin/hooks/pmc-conversation-ingest.sh:154-158`

**Issue:** `touch "$COOLDOWN_FILE"` creates a lock that persists across reboots in `/tmp` (or indefinitely on systems without tmp cleanup). On the same system running multiple Claude Code sessions, a previous session's lockfile will block the auto-clear of a new session with the same ID (reused session IDs are common in dev environments).

**Fix:** Add `trap 'rm -f "$COOLDOWN_FILE"' EXIT` or store lock with a timestamp and check TTL.

---

### [W-05] Direct conn.execute() bypasses StorageBackend abstraction

**File:** `pmc/cli/main.py:185-190, 249-253, 327-332`, `pmc/ingestion/conversation.py:154-162, 239-247`, `pmc/operations/conversation.py:103-111, 231-233`, `pmc/synthesis/synthesizer.py:19-23`

**Issue:** Multiple modules call `backend.conn.execute(...)` directly via `# type: ignore[attr-defined]`. This:
1. Assumes SQLite is the only backend forever.
2. Bypasses the `StorageBackend` ABC — any non-SQLite backend (future in-memory test backend, etc.) will crash with `AttributeError`.
3. Makes the type ignore comments a permanent fixture.

**Fix:** Add `find_by_session_and_index()`, `find_turns_by_session()`, `count_nodes_by_type()` abstract methods to `StorageBackend` ABC, with SQLite implementations.

---

### [W-06] validate_plan silently allows self-referential dependency

**File:** `pmc/planner/validator.py:40-43`

**Issue:**
```python
for dep in step.depends_on:
    if dep not in seen and dep != step.step_id:
        errors.append(f"forward_dependency:...")
```
The `dep != step.step_id` condition silently ignores `depends_on: ["s1"]` when `step_id == "s1"`. A self-loop in `depends_on` is neither flagged as circular nor as a forward-dependency. The topo sort in `runner.py` would then visit it correctly only because `idx[sid]` exists, but the validator reports no error where it should.

**Fix:**
```python
if dep == step.step_id:
    errors.append(f"self_dependency:{step.step_id}")
elif dep not in seen:
    errors.append(f"forward_dependency:{step.step_id}->{dep}")
```

---

### [W-07] PTY write to another process — fragile and potentially destructive

**File:** `plugin/hooks/pmc-conversation-ingest.sh:169-178`

**Issue:**
```bash
CLAUDE_PID=$(pgrep -x "claude" 2>/dev/null | grep -v $$ | head -1)
printf "/clear\n" > "$CLAUDE_PTY"
```
Writing `/clear\n` to another process's PTY injects a command into the terminal — while the user may be mid-typing. On a multi-user or multi-window system, `pgrep -x "claude"` can match the wrong process. If the PTY happens to be open in an interactive shell (not Claude Code), this types `/clear` into that shell.

**Fix:** Use Claude Code's documented hook output mechanism (stdout return value JSON) rather than direct PTY injection if available. At minimum, add a guard verifying the matched PID is a direct parent of the current process.

---

### [W-08] infer() full table scan on every inference call

**File:** `pmc/operations/reasoning.py:103-108`

**Issue:**
```python
for a in backend.all_nodes():
    for e1 in backend.get_edges_out(a.id, rel1):
        for e2 in backend.get_edges_out(e1.target, rel2):
```
`backend.all_nodes()` returns all non-deprecated nodes (12k+). For each, it runs two indexed edge lookups. For a 2-step chain this is O(N × avg_fan_out²). This is called from the executor for every `INFER` op in a plan. No memoization, no batching.

This would be INFO (performance), but it's in scope as a correctness issue: at 12k nodes and non-trivial fan-out, this can hit the `timeout_ms` plan limit (default 10s), causing the step to "fail" by timeout rather than by logic error. The caller has no way to distinguish timeout from missing data.

**Fix:** Mark `INFER` steps with higher timeout or restrict `all_nodes()` to a type filter derived from the rule pattern.

---

### [W-09] _extract_json fails with misleading error on empty-after-strip fence

**File:** `pmc/planner/generator.py:51-66`

**Issue:** If the LLM returns ` ```json\n``` ` (empty fence), `_extract_json` strips the fences to `""`, then `text.find("{")` returns -1, raising `PlannerError("no_json_object_in_response")`. This error gives no indication of what was actually returned, making debugging planner failures opaque. Additionally, `_extract_json` takes the first `{` and last `}` across the entire response — a model that explains its JSON before emitting it (e.g. "Here is the plan: {...}") will silently have the explanation stripped, which is correct, but the function's name/contract implies it extracts only JSON.

**Fix:** Include the raw response (truncated) in the error:
```python
raise PlannerError(f"no_json_object_in_response: raw={text[:200]!r}")
```

---

## Info Findings

### [I-01] _now() redefined in 5+ modules

**Files:** `pmc/storage/sqlite.py:17`, `pmc/ingestion/pipeline.py:64`, `pmc/ingestion/conversation.py:90`, `pmc/operations/semantic_linking.py:38`, `pmc/operations/reasoning.py` (implicitly via datetime.now)

**Issue:** `def _now() -> datetime: return datetime.now(timezone.utc)` is copy-pasted in at least 4 modules. Single source of truth violation.

**Fix:** Move to `pmc/utils.py` and import from there.

---

### [I-02] Magic numbers for similarity thresholds scattered across modules

**Files:** `pmc/operations/semantic_linking.py:35-36` (0.65), `pmc/ingestion/conversation.py:172` (0.50), `pmc/operations/conversation.py:128` (0.55), `pmc/operations/retrieval.py:27` (0.3)

**Issue:** Four different similarity thresholds, none documented as to why they differ. A change to retrieval sensitivity requires hunting all four files.

**Fix:** Centralize in `pmc/config.py` as named constants: `SEMANTIC_LINK_THRESHOLD`, `REFERENCE_THRESHOLD`, `CONVERSATION_THRESHOLD`, `RETRIEVAL_THRESHOLD`.

---

### [I-03] Schema loader path fragile under pip install

**File:** `pmc/schema/loader.py:15`

**Issue:** `Path(__file__).resolve().parents[2] / "schema" / "default.json"` assumes a specific directory depth (2 levels up from `pmc/schema/`). Under `pip install`, `__file__` is the installed `.pyc` path, which may not have `schema/` as a sibling.

**Fix:** Use `importlib.resources`:
```python
from importlib.resources import files
p = files("pmc") / ".." / "schema" / "default.json"
```
Or declare `schema/default.json` as `package_data` in `pyproject.toml` and use `importlib.resources.files("pmc.schema")`.

---

### [I-04] token_count stored as word count (not actual tokens)

**File:** `pmc/ingestion/conversation.py:270`

**Issue:** `"token_count": len(turn.text.split())` counts whitespace-split words, not subword tokens. This property is stored on every `CONVERSATION_TURN` node and presumably used for context budgeting. For CJK text, code, or heavily punctuated content, the word count underestimates tokens by 2-5×.

**Fix:** Either rename to `word_count` (honest) or use `len(text) // 4` as a rough token estimate, or integrate `tiktoken`.

---

### [I-05] Deprecated IS NULL branch dead in conversation query

**File:** `pmc/operations/conversation.py:107`

**Issue:** `AND (deprecated IS NULL OR deprecated=0)` — the schema in `sqlite.py:83` declares `deprecated INTEGER NOT NULL DEFAULT 0`. The `IS NULL` branch can never match. It's harmless but adds noise.

**Fix:** `AND deprecated=0`

---

### [I-06] Content.data stored as bytes in SQLite BLOB — large files cause DB bloat

**File:** `pmc/storage/sqlite.py:262-270`, `pmc/ingestion/pipeline.py:143-159`

**Issue:** `fp.read_bytes()` then stored as `BLOB` in `contents.data`. For a codebase like suite-ptb (835 files × avg ~5KB = ~4MB), the DB grows large quickly. There is no size cap on ingested files, no deduplication check before insert (hash is stored but not checked for existing content), and no option to store content externally.

**Fix:** Before `insert_content`, query `SELECT id FROM contents WHERE hash=?` to deduplicate. Add a `MAX_CONTENT_BYTES` guard (e.g. skip files > 500KB).

---

_Reviewed: 2026-05-09_
_Reviewer: Claude Code (adversarial review)_
_Depth: deep_
_Files reviewed: 19 Python + 3 Bash = 22 total_
