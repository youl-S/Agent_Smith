# Agent Smith — Notre implémentation (guide de reprise pour Theo)

> Objectif de ce doc : que tu comprennes **nos briques** et **comment les
> lancer / les brancher** en 10 min, pour attaquer le SWE-bench sans avoir à
> reverse-engineer le code. La recette MBPP (plus bas) est ton **template**
> de câblage : tu rebranches les mêmes pièces pour le SWE.

---

## 🗺️ Vue d'ensemble

```
   tâche ──► Orchestrator (boucle agent, benchmark-agnostic)
                 │  messages
                 ▼
            LLMManager ──► LLMClient ──► provider (Groq, API OpenAI-compat.)
                 │  rotation clés + fallback + backoff
                 ▼  texte brut
            CodeExtractor ──► extrait UN bloc de code (python/xml/json/react)
                 │  code
                 ▼
            Sandbox.run(code) ──► sous-process isolé
                 │                   │ appels d'outils (stubs)
                 │                   ▼
                 │              McpClient ──► serveur MCP (mcp_tools_*.py)
                 ▼
            dict résultat {type: final_answer | success | error}
                 │
                 ▼
            SolutionOutput ──► solution.json
```

Chaque brique est **découplée** : l'Orchestrator ne sait pas s'il fait du
MBPP ou du SWE, la Sandbox ne connaît pas le LLM, les outils vivent dans un
serveur MCP séparé. C'est ce qui te permet de brancher le SWE sans toucher au
cœur.

---

## 🧩 Les briques

### 📦 `srcs/models.py` — contrats de données (Pydantic)

| Modèle | Rôle |
|--------|------|
| `SandboxConfig` | allowlist imports, dossiers autorisés, limites temps/mémoire |
| `MBPPTaskInput` | entrée tâche MBPP |
| `SWEBenchTaskInput` | entrée tâche SWE (`instance_id`, `problem_statement`, `docker_image`, `eval_script`, `hints_text`, `repo`) ← **déjà prêt pour toi** |
| `StepMetrics` | métriques d'une itération |
| `SolutionOutput` | 📤 sortie finale écrite dans `solution.json` |

### 🧠 `srcs/llm/` — couche LLM (importable via `from srcs.llm import ...`)

| Élément | Signature clé | Rôle |
|---------|---------------|------|
| `LLMClient` | `.complete(base_url, model, api_key, messages, stop_sequences)` | un appel API → `LLMResponse` |
| `LLMManager` | `.generate(messages, stop_sequences)` | parcourt providers/clés, **rotation + fallback + backoff**, renvoie toujours un `LLMResponse` |
| `CodeExtractor` | `.extract(raw_text) -> ExtractedCodeBlock` | extrait le code, formats `python` / `xml` / `json hermes` / `react`, strip `<think>` |
| `Orchestrator` | `.run(task_id, benchmark, task_message) -> SolutionOutput` | **la boucle agent**, générique |

`Orchestrator.__init__` prend tous les plafonds en paramètres (donc tu passes
les tiens pour le SWE) :

```python
Orchestrator(
    manager, extractor, sandbox, system_prompt,
    stop_sequences=["<end_code>"],
    max_iterations=10,
    max_input_tokens=6000,    # MBPP: 6000   | SWE: 300000
    max_output_tokens=1500,   # MBPP: 1500   | SWE: 10000
    max_time_seconds=120.0,   # MBPP: 120    | SWE: 900
)
```

### 🧱 `srcs/sandbox/` — exécution isolée

| Élément | Signature clé | Rôle |
|---------|---------------|------|
| `Sandbox.run(code)` | `-> dict` | exécute le code dans un sous-process, gère timeout + pont outils |
| `Sandbox._launch_server(protocol, args)` | `"stdio"/"http"` | connecte le client MCP |
| `Sandbox.get_man()` | `-> str` | **manuel auto-généré** (outils MCP + restrictions) à injecter dans le prompt |
| `McpClient` | `list_tools()` / `call_tool(name, args)` / `stdio_client()` / `http_client()` | pont vers le serveur MCP |

**Contrat de retour de `Sandbox.run(code)`** (ce que l'Orchestrator lit) :

```python
{"type": "final_answer", "answer": "<la solution soumise>"}
{"type": "success",      "stdout": "...", "stderr": "..."}
{"type": "error",        "traceback": "...", "stdout": "...", "stderr": "..."}
```

**Garde-fous appliqués au code exécuté** : builtins dangereux retirés
(`eval`, `exec`, `getattr`...), `import` et `open()` sur allowlist, accès
dunder bloqué (AST), réseau coupé, limites temps + mémoire (`RLIMIT_AS`).
`final_answer(x)` hérite de `BaseException` → impossible à avaler avec un
`except`.

> ⚠️ Côté outils MCP : un stub renvoie `result.content[0].text`. Si le texte
> commence par `FAIL`, la sandbox lève un `RuntimeError` (voir `make_stub`
> dans [sandbox.py](../srcs/sandbox/sandbox.py)). Garde cette convention pour
> tes outils SWE.

### 🛠️ Serveurs MCP (racine du repo)

| Fichier | État | Contenu |
|---------|------|---------|
| `mcp_tools_mbpp.py` | ✅ | outil `run_tests(code, test_list, test_imports)` → rapport `PASS/FAIL` |
| `mcp_tools_swebench.py` | ⬜ vide | **ton point d'entrée** : ici tu exposeras les outils SWE |

Un serveur MCP se lance en `stdio` (défaut) ou `--http`, exemple
[mcp_tools_mbpp.py](../mcp_tools_mbpp.py) avec `FastMCP`.

### ✋ `srcs/tools.py` — briques d'outils (hors MCP pour l'instant)

Fonctions filesystem/recherche **déjà écrites** que tu pourras envelopper en
outils MCP SWE : `read_file`, `edit_file`, `list_files`, `search_code`,
`search_function_or_class_definition_in_code`, `find_references` (via `jedi`).
Elles ciblent `/testbed` (le repo monté dans le conteneur SWE). Les fonctions
d'exécution `run_tests`, `get_patch`, `run_command` y sont encore des stubs.

---

## ▶️ Comment lancer chaque brique (commandes prêtes)

### 0. Setup

```bash
# deps
uv sync

# clés API : le .env contient GROQ_API_KEY_1..N (rotation auto).
# discover_key_vars() ramasse toute variable d'env contenant "API_KEY".
```

### 1. Tests

```bash
uv run pytest
```

### 2. Serveur MCP seul (debug d'un outil)

```bash
# stdio (défaut)
uv run python mcp_tools_mbpp.py
# http (écoute en streamable-http)
uv run python mcp_tools_mbpp.py --http
```

### 3. Sandbox en CLI (coller du code, Ctrl-D pour exécuter)

```bash
# branche un serveur MCP en stdio + charge une config
uv run sandbox \
  --mcp-stdio "python mcp_tools_mbpp.py" \
  --config-file srcs/sandbox/config_file.json

# ou sans flags : la CLI demande le transport puis le code en interactif
uv run sandbox
```

### 4. Agent MBPP bout-en-bout

```bash
uv run python -m srcs.mbpp.agent_mbpp \
  --task_file=task.json \
  --output=out/solution.json \
  --model_name="llama-3.3-70b-versatile" \
  --provider_url="https://api.groq.com/openai/v1"
```

Exemple de `task.json` (format `MBPPTaskInput`) :

```json
{
  "task_id": 11,
  "task_definition": "Write a function to remove first and last occurrence of a given character from the string.",
  "function_definition": "def remove_Occ(s, ch):",
  "test_imports": [],
  "test_list": [
    "assert remove_Occ(\"hello\",\"l\") == \"heo\"",
    "assert remove_Occ(\"abcda\",\"a\") == \"bcd\""
  ]
}
```

---

## 🔌 Comment ça se branche — la recette MBPP = ton template SWE

`run_mbpp()` dans [srcs/mbpp/agent_mbpp.py](../srcs/mbpp/agent_mbpp.py) montre
le câblage complet. Pour le SWE tu reproduis **exactement** les mêmes 4
étapes, en remplaçant les pièces marquées 🔁 :

```python
# 1. Provider LLM (identique)
target  = ProviderTarget(name="provider", base_url=provider_url,
                         model=model_name, key_env_vars=discover_key_vars())
manager = LLMManager(targets=[target], client=LLMClient(timeout_s=60.0))

# 2. Sandbox + serveur MCP        🔁 pointe vers TON serveur SWE
sandbox = Sandbox()
sandbox._launch_server("stdio", "python mcp_tools_swebench.py")

# 3. Orchestrator                 🔁 prompt SWE + limites SWE
orchestrator = Orchestrator(
    manager=manager, extractor=CodeExtractor, sandbox=sandbox,
    system_prompt=build_system_prompt_swe(...),   # à toi
    max_iterations=..., max_input_tokens=300000,
    max_output_tokens=10000, max_time_seconds=900,
)

# 4. Lancer                       🔁 benchmark="swebench", message issue
result = orchestrator.run(task_id=task.instance_id,
                          benchmark="swebench",
                          task_message=build_task_message_swe(task))
# result est un SolutionOutput prêt à sérialiser en solution.json
```

**En clair, ce que tu as à fournir côté SWE** : un serveur
`mcp_tools_swebench.py` (outils `run_tests` / `get_patch` / `run_command`
basés sur le conteneur Docker + les helpers de `tools.py`), un system prompt
SWE, et le `build_task_message` à partir de `SWEBenchTaskInput`. Le reste
(LLM, extraction, sandbox, boucle, format de sortie) est déjà en place et
réutilisable tel quel. 🚀
