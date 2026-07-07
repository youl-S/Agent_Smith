# Model Benchmark Report

Comparison of **8 LLMs across 3 providers** on the **same 5 SWE-bench tasks**, run
through the Agent Smith Thought → Code → Observation loop under the SWE-bench
limits (30 iterations, 300 000 input tokens, 10 000 output tokens, 900 s).

The backing `solution.json` files are stored under [`benchmark/`](benchmark/),
one file per `model × task` (named `<model>.json` inside each task directory),
each containing per-step metrics (`input_tokens`, `output_tokens`,
`request_time_ms`, `retries`, `sandbox_input`, `sandbox_output`, …).

---

## 1. Setup

### Models & providers compared

| # | Model (as recorded in `solution.json`) | Provider | Endpoint |
|---|----------------------------------------|----------|----------|
| 1 | `meta-llama/llama-4-maverick:fre`        | OpenRouter | `openrouter.ai/api/v1` |
| 2 | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq     | `api.groq.com/openai/v1` |
| 3 | `mistral-large-latest`                    | Mistral    | `api.mistral.ai/v1` |
| 4 | `deepseek/deepseek-v4-flash`              | OpenRouter | `openrouter.ai/api/v1` |
| 5 | `llama-3.3-70b-versatile`                 | Groq       | `api.groq.com/openai/v1` |
| 6 | `llama-3.1-8b-instant`                    | Groq       | `api.groq.com/openai/v1` |
| 7 | `mistral-medium-latest`                   | Mistral    | `api.mistral.ai/v1` |
| 8 | `qwen/qwen3.6-27b`                         | Groq       | `api.groq.com/openai/v1` |

Three providers are represented on purpose, so provider reliability (not just
raw model quality) is part of the comparison. All eight models run through the
**exact same** system prompt, tool set, sandbox and orchestrator — only the
`(base_url, model)` target changes — which is what the abstraction requirement
is meant to guarantee.

### Tasks used & why

| Task | Repo | Why selected |
|------|------|--------------|
| `django__django-11066`            | Django       | Small, localized fix (one-line `save(using=db, …)`); a "can the agent do the basics" baseline |
| `django__django-13109`            | Django       | Deliberately harder / larger context; used as the stress case that separates strong models from weak ones |
| `pydata__xarray-4629`             | xarray       | Different ecosystem (scientific stack), moderate difficulty |
| `scikit-learn__scikit-learn-13439` | scikit-learn | Requires reading more of the codebase before the fix; tests exploration efficiency |
| `sympy__sympy-18189`              | SymPy        | Math-heavy logic; different failure surface from web frameworks |

Selection criteria: **3+ distinct repositories** (Django, xarray, scikit-learn,
SymPy) spanning web, scientific-computing and symbolic-math domains, and a
spread of difficulty from a one-line change (`django-11066`) to a
multi-file/large-context change (`django-13109`, `scikit-learn-13439`). This
avoids over-fitting the conclusion to a single codebase or a single difficulty
level.

---

## 2. Results table

Per `model × task`: **Pass/Fail · iterations · input tokens · output tokens ·
wall-clock (s)**. Values are read directly from each `solution.json`
(`success`, `iterations`, `total_input_tokens`, `total_output_tokens`,
`total_time_seconds`).

Fail reason legend: `exh` = provider exhausted (all keys rate-limited /
out of quota mid-task), `inTok` = 300k input-token budget hit, `iter` = 30
iteration cap hit.

### `django__django-11066`
| Model | Result | Iter | Input tok | Output tok | Time (s) |
|-------|:------:|:----:|----------:|-----------:|---------:|
| llama-4-scout            | ✅ Pass | 6  | 24 502 | 364  | 9.9  |
| llama-4-maverick:fre    | ✅ Pass | 5  | 18 315 | 337  | 16.1 |
| mistral-large-latest     | ✅ Pass | 6  | 21 193 | 616  | 49.6 |
| llama-3.3-70b-versatile  | ✅ Pass | 7  | 27 269 | 521  | 49.9 |
| mistral-medium-latest    | ❌ exh  | 6  | 29 112 | 486  | 27.8 |
| qwen3.6-27b              | ❌ exh  | 4  | 17 318 | 738  | 58.1 |
| deepseek-v4-flash        | ❌ exh  | 14 | 71 462 | 943  | 79.7 |
| llama-3.1-8b-instant     | ❌ exh  | 18 | 58 238 | 1 131 | 330.7 |

### `django__django-13109`
| Model | Result | Iter | Input tok | Output tok | Time (s) |
|-------|:------:|:----:|----------:|-----------:|---------:|
| mistral-large-latest     | ✅ Pass | 4  | 12 258  | 415   | 29.1  |
| llama-4-maverick:fre    | ❌ inTok| 27 | 287 734 | 2 172 | 103.3 |
| llama-4-scout            | ❌ iter | 30 | 222 242 | 2 790 | 207.6 |
| mistral-medium-latest    | ❌ exh  | 24 | 201 994 | 1 955 | 327.7 |
| qwen3.6-27b             | ❌ exh  | 7  | 29 101  | 770   | 197.8 |
| llama-3.1-8b-instant     | ❌ exh  | 4  | 10 634  | 927   | 32.3  |
| deepseek-v4-flash        | ❌ exh  | 3  | 10 324  | 271   | 33.7  |
| llama-3.3-70b-versatile  | ❌ exh  | 1  | 2 198   | 76    | 1.9   |

### `pydata__xarray-4629`
| Model | Result | Iter | Input tok | Output tok | Time (s) |
|-------|:------:|:----:|----------:|-----------:|---------:|
| llama-4-maverick:fre    | ✅ Pass | 6  | 22 997 | 370   | 21.2  |
| mistral-large-latest     | ✅ Pass | 6  | 25 923 | 504   | 47.0  |
| llama-4-scout            | ✅ Pass | 11 | 56 088 | 737   | 65.3  |
| llama-3.3-70b-versatile  | ✅ Pass | 9  | 36 649 | 882   | 75.8  |
| mistral-medium-latest    | ❌ exh  | 12 | 87 471 | 1 241 | 173.5 |
| llama-3.1-8b-instant     | ❌ exh  | 16 | 50 811 | 1 380 | 274.6 |
| qwen3.6-27b             | ❌ exh  | 18 | 93 056 | 2 477 | 507.4 |
| deepseek-v4-flash        | ❌ exh  | 3  | 9 098  | 533   | 37.7  |

### `scikit-learn__scikit-learn-13439`
| Model | Result | Iter | Input tok | Output tok | Time (s) |
|-------|:------:|:----:|----------:|-----------:|---------:|
| llama-4-maverick:fre    | ✅ Pass | 5  | 17 369  | 350   | 14.3  |
| llama-4-scout            | ✅ Pass | 12 | 52 481  | 861   | 37.7  |
| deepseek-v4-flash        | ✅ Pass | 20 | 128 363 | 1 772 | 110.2 |
| mistral-large-latest     | ❌ exh  | 20 | 233 085 | 6 069 | 291.4 |
| mistral-medium-latest    | ❌ exh  | 9  | 61 475  | 659   | 116.1 |
| qwen3.6-27b             | ❌ exh  | 7  | 33 565  | 635   | 168.5 |
| llama-3.3-70b-versatile  | ❌ exh  | 6  | 22 945  | 487   | 59.2  |
| llama-3.1-8b-instant     | ❌ exh  | 6  | 15 938  | 669   | 146.3 |

### `sympy__sympy-18189`
| Model | Result | Iter | Input tok | Output tok | Time (s) |
|-------|:------:|:----:|----------:|-----------:|---------:|
| llama-4-maverick:fre    | ✅ Pass | 6  | 19 586  | 473   | 48.4  |
| llama-4-scout            | ✅ Pass | 9  | 39 636  | 509   | 49.6  |
| mistral-large-latest     | ✅ Pass | 8  | 34 415  | 1 677 | 95.1  |
| deepseek-v4-flash        | ✅ Pass | 20 | 94 921  | 2 104 | 96.7  |
| mistral-medium-latest    | ❌ exh  | 23 | 155 134 | 2 958 | 273.6 |
| qwen3.6-27b             | ❌ exh  | 18 | 86 369  | 2 161 | 360.7 |
| llama-3.1-8b-instant     | ❌ exh  | 6  | 18 928  | 1 428 | 126.3 |
| llama-3.3-70b-versatile  | ❌ exh  | 1  | 2 602   | 85    | 2.3   |

### Solve-rate summary (5 tasks)

| Model | Provider | Solved | Avg iter | Avg input tok | Avg output tok | Avg time (s) |
|-------|----------|:------:|:--------:|--------------:|---------------:|-------------:|
| llama-4-maverick:fre    | OpenRouter | **4 / 5** | 9.8  | 73 200  | 740   | 40.7  |
| llama-4-scout            | Groq       | **4 / 5** | 13.6 | 78 990  | 1 052 | 74.0  |
| mistral-large-latest     | Mistral    | **4 / 5** | 8.8  | 65 375  | 1 856 | 102.4 |
| deepseek-v4-flash        | OpenRouter | 2 / 5     | 12.0 | 62 834  | 1 125 | 71.6  |
| llama-3.3-70b-versatile  | Groq       | 2 / 5     | 4.8  | 18 333  | 410   | 37.8  |
| llama-3.1-8b-instant     | Groq       | 0 / 5     | 10.0 | 30 910  | 1 107 | 182.0 |
| mistral-medium-latest    | Mistral    | 0 / 5     | 14.8 | 107 037 | 1 460 | 183.7 |
| qwen3.6-27b             | Groq       | 0 / 5     | 10.8 | 51 882  | 1 356 | 258.5 |

Per-task difficulty (models solving / 8): `django-11066` 4/8 · `xarray-4629`
4/8 · `sympy-18189` 4/8 · `scikit-learn-13439` 3/8 · **`django-13109` 1/8**
(the hardest — only `mistral-large` solved it; the two otherwise-strong models
hit the input-token / iteration ceiling on it).

---

## 3. Provider reliability

Metrics aggregated over the 5 runs per model. **Retries** = failed API attempts
recorded across keys/passes (`sum(step.retries)`), which the manager increments
on every `401` / `429` / timeout / `5xx`. **Requests** = `total_requests`
(iterations + retries). **Avg response time** = mean `request_time_ms` over all
succeeded steps. **Availability** = share of the 5 task runs that completed
without a provider-side `all targets exhausted` failure.

| Model | Provider | Avg resp / req (ms) | Requests | Retries | Retry rate | Availability |
|-------|----------|--------------------:|---------:|--------:|:----------:|:------------:|
| llama-4-maverick:fre   | OpenRouter | 2 417 | 79  | 30  | 38 % | **5/5 (100 %)** |
| llama-4-scout           | Groq       | 707   | 247 | 179 | 72 % | **5/5 (100 %)** |
| mistral-large-latest    | Mistral    | 6 277 | 94  | 50  | 53 % | 4/5 (80 %) |
| deepseek-v4-flash       | OpenRouter | 4 489 | 90  | 30  | 33 % | 2/5 (40 %) |
| llama-3.3-70b-versatile | Groq       | 690   | 139 | 115 | 83 % | 2/5 (40 %) |
| mistral-medium-latest   | Mistral    | 2 364 | 162 | 88  | 54 % | 0/5 (0 %) |
| llama-3.1-8b-instant    | Groq       | 593   | 349 | 299 | 86 % | 0/5 (0 %) |
| qwen3.6-27b            | Groq       | 800   | 353 | 299 | 85 % | 0/5 (0 %) |

**Reading of the data:**

- **Groq is fast per request but heavily rate-limited.** The Groq endpoints have
  the lowest latency (≈600–800 ms/req) but the highest retry rates (72–86 %):
  the free tier throws `429` constantly, so the manager burns hundreds of
  requests per run cascading over keys. `llama-3.1-8b` and `qwen` needed
  **299 retries each** — practically every successful call was preceded by a
  string of rate-limit rejections.
- **OpenRouter / Mistral are slower but "quieter."** Maverick and DeepSeek
  (OpenRouter) and Mistral back off less often, but each request costs
  2.4–6.3 s. Mistral-large is the slowest endpoint at **6.3 s/req**.
- **Availability, not capability, dominated the failures.** Across the whole
  matrix, **22 of 40 runs (55 %) ended in `all targets exhausted`** vs only
  1 `input-token-limit` and 1 `iteration-limit` failure. The single biggest
  cause of a Fail was the provider running out of quota mid-task, not the model
  being unable to solve the bug. Solve rates for the exhaustion-heavy models
  (DeepSeek, llama-3.3-70b, and the three 0/5 models) are therefore a **lower
  bound** on their true capability.

---

## 4. Intermediary metrics

Measured by inspecting the `steps[]` of each **successful** `solution.json`
(the metrics need a final patch to anchor on). Two of the three suggested
metrics are reported.

### (a) Exploration efficiency — first touch of the patched file

The step at which the agent first `read_file`/`edit_file`s the file that ends
up in the final `diff`.

| Task | Model | First-touch step |
|------|-------|:----------------:|
| django-11066 | maverick / mistral-large | 1 |
| django-11066 | scout | 2 |
| django-11066 | llama-3.3-70b | 3 |
| django-13109 | mistral-large | 1 |
| xarray-4629 | mistral-large | 1 |
| xarray-4629 | maverick | 2 |
| xarray-4629 | llama-3.3-70b | 3 |
| xarray-4629 | scout | 4 |
| scikit-13439 | maverick / scout | 2 |
| scikit-13439 | deepseek | 3 |
| sympy-18189 | deepseek / mistral-large | 1 |
| sympy-18189 | maverick | 3 |
| sympy-18189 | scout | 4 |

**Median first-touch = 2 steps (range 1–4).** On every successful run the agent
located the correct file within its first four tool calls. This is directly
attributable to the tool design: `search_code` /
`search_function_or_class_definition_in_code` point the agent straight at the
relevant file, and the SWE-bench problem statements name enough symbols to make
the first search productive. Exploration is **not** the bottleneck for this
agent.

### (b) Submission discipline — iterations between "tests first pass" and `final_answer`

The gap between the first `run_tests()` that returns `EXIT_CODE: 0` and the
`final_answer(get_patch())` call.

| Task | Model | tests-pass → final |
|------|-------|:------------------:|
| django-11066 | mistral-large | 1 |
| django-11066 | maverick / scout / llama-3.3-70b | 2 |
| django-13109 | mistral-large | 1 |
| xarray-4629 | maverick / scout / llama-3.3-70b / mistral-large | 2 |
| scikit-13439 | maverick / scout | 1 |
| scikit-13439 | deepseek | 2 |
| sympy-18189 | maverick | 1 |
| sympy-18189 | scout | 2 |

**Median gap = 2 iterations, and 2 is the structural floor** of this agent: once
tests go green the agent needs one `get_patch()` call and one
`final_answer(get_patch())` call to submit. A gap of 1–2 therefore means the
models **submit immediately** when the tests pass — no dithering, no extra edits
after a green run. Submission discipline is excellent across the board; no
successful run wasted iterations after reaching a passing state.

> Two successful runs (`deepseek` and `mistral-large` on `sympy-18189`) are
> omitted from (b): they reached `final_answer` without a preceding
> `run_tests` that our `EXIT_CODE: 0` detector matched, so the "tests first
> pass" anchor is undefined for them.

---

## 5. Ablation study — sandbox output truncation

**Change under study:** the sandbox output-truncation guard in
[`srcs/sandbox/sandbox.py`](srcs/sandbox/sandbox.py) (`truncate_if_to_large`),
added in commit `9c3bed5` ("Implement output truncation and clean tool
listing"). Any `stdout`/`stderr`/`traceback` longer than 6 000 chars is capped
to the first 3 000 + last 3 000 chars with a
`{{ Tool output was truncated due to size limits }}` marker in the middle.

- **Before:** raw tool output (whole-file reads, full `run_tests` logs) is fed
  back into the conversation verbatim on every iteration.
- **After (current):** each observation is capped at ~6 KB.

Same model, same tasks, same prompt — only this one guard flips. Per the
subject, the *before* side is **deduced from the code and the recorded runs**
(we did not keep a separate un-truncated benchmark run), and quantified from the
`solution.json` data:

**Evidence that the guard is load-bearing:**

- The truncation marker actually fired in **27 of 40 runs** — over half the runs
  hit the cap at least once, so this is not a dormant safety net.
- In heavy runs the per-observation length is pinned at ~6 049 chars (3 000 +
  marker + 3 000). Example: `deepseek` on `scikit-learn-13439` ran **20
  iterations** and finished at **128 363 input tokens** with observations capped
  at 6 049 chars. A single un-truncated Django/scikit-learn test log is commonly
  15–30 KB; because input tokens are **cumulative**, feeding the full log back
  each turn multiplies the growth.
- The ceiling is real and close: `maverick` already hit the **300 000**
  input-token limit on `django-13109` (`inTok`, 287 734 tokens **with**
  truncation on). Removing the cap would push that run — and the other
  long-context runs (`scout` 222 k, `mistral-medium` 202 k) — decisively over
  budget, converting near-misses into guaranteed `input-token-limit` failures.

**Deduced before/after (same model, same tasks):**

| | Truncation OFF (before, deduced) | Truncation ON (after, measured) |
|---|---|---|
| Long-context tasks (`django-13109`, `scikit-13439`) | Observations of 15–30 KB accumulate → 300k budget hit in ≤ a handful of test iterations → **`input-token-limit` failures** | Observations capped at ~6 KB; `deepseek` solves `scikit-13439` in 20 iters at 128k tokens; `django-13109` reachable within budget |
| Token efficiency | Every verbose `run_tests` re-injected in full | ~6 KB/observation ceiling; marker preserves head+tail (test summary + `EXIT_CODE`) |
| Net effect | Fewer usable iterations; capability masked by budget exhaustion | The iteration budget is spent on reasoning, not on re-reading logs |

**Conclusion of the ablation:** truncation is a small change with an outsized
effect under the SWE-bench 300 000-token cap. It keeps the head and tail of each
log — which is exactly where the failing-test names and the `EXIT_CODE` marker
live — so the agent keeps the signal it needs for submission discipline (§4b)
while shedding the bulk that would otherwise exhaust the budget. It is retained
in the final pipeline.

---

## 6. Conclusions

**Selected for the final pipeline:**

1. **`meta-llama/llama-4-maverick:fre` (OpenRouter) — primary.** Best overall:
   4/5 solved, **100 % availability** (its only miss was the 300k token ceiling
   on the hardest task, not a capability or quota failure), lowest retry rate of
   the capable models (38 %), and it locates the target file fast (median
   first-touch 1–3). Free endpoint, so cost is not a constraint.
2. **`meta-llama/llama-4-scout-17b-16e-instruct` (Groq) — fast fallback.** Also
   4/5, 100 % availability, and by far the best latency of any capable model
   (**707 ms/req**). The catch is Groq's rate limiting (72 % retry rate): great
   when quota is available, so it is the low-latency secondary target behind
   Maverick.
3. **`mistral-large-latest` (Mistral) — capable but expensive.** The only model
   to solve the hardest task (`django-13109`), and the most robust to long
   context, but the **slowest endpoint (6.3 s/req)** and the most verbose
   (highest avg output tokens, 6 069 on one run) — kept as a heavyweight tertiary
   target for hard tasks, not the default.

**Kept as conditional / capable-when-quota-permits:**

- **`deepseek/deepseek-v4-flash` (OpenRouter)** solved the two longest-context
  tasks (`scikit-13439`, `sympy-18189`, both at 20 iterations) — genuinely
  capable — but **3 of its 5 runs died to provider exhaustion**, so its 2/5 is a
  quota artifact, not a capability verdict. Usable only with more OpenRouter
  quota/keys.

**Disregarded for the final pipeline (based on the data):**

- **`llama-3.1-8b-instant` (Groq): 0/5.** Small model, and Groq rate limits made
  it worse — **299 retries**, 0 % availability. Even the runs that got through
  produced no passing patch. Both capability and reliability fail.
- **`qwen/qwen3.6-27b` (Groq): 0/5.** Same story as above (299 retries, 0 %
  availability, slowest average wall-clock at 258 s) with nothing solved.
- **`mistral-medium-latest` (Mistral): 0/5.** The most token-hungry model
  (avg 107k input tokens, up to 202k on a *failed* task) yet solved nothing —
  it burns budget without converging. Dominated by `mistral-large` on
  capability at a similar provider cost.
- **`llama-3.3-70b-versatile` (Groq): 2/5** is a borderline case — it solved two
  easy/medium tasks cheaply (avg 18k tokens) but exhausted on the rest and
  collapsed on the hard tasks (1 iteration on `django-13109`/`sympy-18189`).
  Kept out of the default pipeline in favour of Scout, which is faster to solve
  and strictly higher solve-rate on the same provider.

**Cross-cutting lesson.** The dominant failure mode in this benchmark was
**provider availability (55 % of runs exhausted quota), not model capability.**
The abstraction that lets us swap providers behind one target list, plus
multi-key rotation and the truncation guard (§5), are what actually move the
solve rate — more so than picking a marginally "smarter" model. The final
pipeline therefore prioritises a **reliable, high-availability primary
(Maverick) with fast and heavyweight fallbacks (Scout, Mistral-large)** over any
single model.
