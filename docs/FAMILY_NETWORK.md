# Family Agent Network: Master, Sub-Agents & Shared Tunnel

## Model

- **Pepper** — Jason’s existing workhorse agent (separate, already in use).
- **jcore** — Family Agent: Jason’s Master agent for this network. Single source of truth for deploy, can jump in to help any sub-agent.
- **Sub-agents:** jencore (Jennifer), score (Scarlet), kcore (Kiera). Each person’s agent is **theirs**; same codebase, isolated data and identity.
- **Shared tunnel** = secure channel among jcore + jencore + score + kcore (and optionally Pepper later if you wire it in).

## Goals

1. **Solid base** — Everyone gets the same agent stack; they can build on it (clone backup repo, run locally, add skills).
2. **You can help** — You deploy from Family_Agent to any node; their agent stays theirs, you just update code/config.
3. **Agents talk to each other** — All four can send tasks and (later) share context over a **secure** tunnel; outsiders can’t join.
4. **Shareable skills** — If one agent gets a great skill, we can install it on another with minor edits (family skill pool in repo, deploy picks per profile).

## Secure tunnel (today)

- **Interop** = signed, replay-protected messages between nodes.
- Every node that should be in the tunnel has the **same secret**: `interop_shared_key.txt` in that profile’s `secrets/` dir.
- Only nodes with that key can create or accept interop messages. No key → no cross-node traffic (graceful).
- **In practice:** One family key lives in this repo (e.g. `secrets/interop_shared_key.txt`); deploy copies it to each profile’s secrets on jcore, jencore, score, kcore. Then all four can use `delegate_node_task` (and any future interop features).

## Shared knowledge tunnel (today + later)

- **Today:** The tunnel is **task delegation**: one agent sends a bounded task (e.g. “run this query”, “store this”) to another via `POST /interop/inbox` with a signed envelope. Perfect for “ask jcore to do X” or “broadcast to family”.
- **Later (optional):** A **shared knowledge** layer: e.g. family-wide read-only facts, or broadcast summaries agents can consume. Same security: only tunnel members have the key; new message types can reuse the same envelope/signature.

## Shareable skills

- **Repo layout:** `skills/` in Family_Agent (e.g. `skills/communication/`, `skills/memory/`, `skills/builders/`, profile-specific under `skills/jennifer/` etc.). Core doesn’t auto-load yet; when it does, deploy can copy “family” skills to every node and profile-specific ones only where needed.
- **Installing on another agent:** Copy the skill module (and any config) into the repo, add to that profile’s skill list or to the family set, deploy. “Minor edits” = small config or prompt per profile (e.g. name, preferences).

## Summary

| Agent   | Node    | Profile  | Their agent | In tunnel |
|---------|---------|----------|-------------|-----------|
| Pepper  | (yours) | —        | Your workhorse | Optional later |
| Family Agent (Master) | jcore | jason | Yes | Yes |
| Sub     | jencore | jennifer | Yes         | Yes       |
| Sub     | score   | scarlet  | Yes         | Yes       |
| Sub     | kcore   | kiera    | Yes         | Yes       |

One key, one tunnel, one deploy source (Family_Agent). Skills and shared knowledge stay in the family.
