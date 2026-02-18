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

## Hub-routed inbox (reliable cross-subnet transport)

Because sub-agent to sub-agent LAN routes can fail across subnets, the network now supports hub routing:

- `route_envelope` lets any node send an inner envelope to `jcore`.
- `jcore` validates, audits, and forwards to the final target.
- Result: full node-to-node reachability as long as each node can reach `jcore`.

This keeps the transport simple and adds a single policy/audit choke point.

## Shared knowledge tunnel (today + later)

- **Today:** The tunnel is **task delegation**: one agent sends a bounded task (e.g. “run this query”, “store this”) to another via `POST /interop/inbox` with a signed envelope. Perfect for “ask jcore to do X” or “broadcast to family”.
- **Later (optional):** A **shared knowledge** layer: e.g. family-wide read-only facts, or broadcast summaries agents can consume. Same security: only tunnel members have the key; new message types can reuse the same envelope/signature.

## Shareable skills

- **Repo layout:** `skills/` in Family_Agent (e.g. `skills/communication/`, `skills/memory/`, `skills/builders/`, profile-specific under `skills/jennifer/` etc.). Core doesn’t auto-load yet; when it does, deploy can copy “family” skills to every node and profile-specific ones only where needed.
- **Installing on another agent:** Copy the skill module (and any config) into the repo, add to that profile’s skill list or to the family set, deploy. “Minor edits” = small config or prompt per profile (e.g. name, preferences).

## Skill transfer protocol (request -> approve -> deliver -> install -> verify)

- **Manifest layer:** every node keeps `~/agent_skills/manifest.yaml` with machine-readable skills (`skill_id`, version, checksum, permissions, entrypoints, etc.).
- **Discovery:** `skills_checkin` now returns both friendly text and `skills_manifest_delta`.
- **Protocol task types:**
  - `skill_request` (to hub)
  - `skill_approve` (hub approval resolution)
  - `skill_deliver` (bundle transfer + install)
  - `skill_install_result` (installation report/audit)
- **Package format:** `tar.gz` bundle with checksum verification before install.
- **Install path:** `~/agent_skills/<skill_id>/...`.

Guardrails:

- Risky permissions (`screen`, `filesystem_write`, `network_external`, `secrets_access`) require approval/override.
- Rate limit: max 1 successful new skill install per node per 24h unless explicit override.

## Identity signing migration

Interop remains backward compatible with shared-key HMAC, and now supports optional per-node Ed25519 signatures:

- `compat`: HMAC only (default)
- `provenance`: HMAC + verify identity signatures when present
- `strict`: require valid identity signature

Identity mode is controlled by profile config (`interop_identity_mode`) and runtime secret file (`interop_identity_mode.txt`).

## Summary

| Agent   | Node    | Profile  | Their agent | In tunnel |
|---------|---------|----------|-------------|-----------|
| Pepper  | (yours) | —        | Your workhorse | Optional later |
| Family Agent (Master) | jcore | jason | Yes | Yes |
| Sub     | jencore | jennifer | Yes         | Yes       |
| Sub     | score   | scarlet  | Yes         | Yes       |
| Sub     | kcore   | kiera    | Yes         | Yes       |

One key, one tunnel, one deploy source (Family_Agent). Skills and shared knowledge stay in the family.
