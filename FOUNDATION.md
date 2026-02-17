# FAMILY AGENT OS — FOUNDATION DOCUMENT

## 1. Mission

We are building a **Family Agent Operating System**.

This system will:

* Run locally on dedicated Mac Mini machines
* Provide each family member with their own personal AI agent runtime
* Be modular, safe, and extensible
* Prioritize security, sovereignty, and controlled autonomy
* Be built incrementally, starting with Jason's Core Controller

This is not an experiment.
This is infrastructure for the next 10+ years.

## 2. High-Level Vision

We are building a **multi-node agent ecosystem**.

### Phase 1

Build **Jason Core Agent (Daddy Node)** on its own Mac Mini.

This machine acts as:

* Architectural reference implementation
* Golden base repo
* Policy authority
* Template for all future family nodes

### Phase 2

Deploy Personal Agent Nodes:

* Jennifer Node
* Kiera Node
* Scarlet Node

Each node:

* Runs independently
* Has its own data, secrets, memory
* Shares the same core architecture
* Cannot access other nodes' secrets or data

## 3. Core Architectural Principles

### 3.1 Local-First

* All agents run locally.
* SQLite is preferred over distributed DBs.
* No Kubernetes.
* No Docker orchestration complexity unless absolutely required.
* macOS LaunchAgents are acceptable for process management.

Simplicity is a feature.

### 3.2 Data Sovereignty

Each user has:

```
~/agentbase/     → code
~/agentdata/<profile>/ → data, logs, secrets, sandbox
```

No shared database between users.

No shared secrets.

No cross-node read access.

### 3.3 Modular Skill Architecture

Agents must use:

```
/skills/
    communication/
    system/
    memory/
    builders/
    domain_specific/
```

Each skill:

* Self-contained
* Has its own schema definitions
* Does not directly access unrelated subsystems
* Communicates via defined interfaces

No monolithic God files.

### 3.4 Profile-Based Runtime

Every agent process must run with:

```
--profile <name>
```

Profiles define:

* DB path
* Secrets path
* Log path
* Policy tier
* Tool permissions

Profile separation is mandatory.

### 3.5 Tool Tier System (Security Model)

We implement a capability-tiered tool system.

Tier 0 — Safe:

* Read-only file access (scoped)
* Math
* Local embeddings
* Web search
* Notes retrieval

Tier 1 — Requires approval:

* Sending email
* Posting to social media
* Writing outside sandbox
* Installing packages
* Modifying system files

Tier 2 — Jason Core Only:

* Payment systems
* DNS
* Client infrastructure
* System-level secrets
* Cross-node operations

No agent should ever have unrestricted filesystem + shell + internet access simultaneously without human gating.

### 3.6 Execution Sandbox

Any code execution must:

* Run inside a sandbox directory
* Not access home directory root
* Not access .ssh, Keychain, browser profiles
* Not access other users' folders

Sandbox isolation is mandatory for builder-type agents.

### 3.7 Memory Model

Agents must support:

1. Profile Memory (explicit facts)
2. Project Memory (idea storage)
3. Episodic Memory (actions performed)
4. Document Memory (chunked + embedded)

Memory must be:

* Viewable
* Editable
* Deletable
* Not silently permanent

### 3.8 Observability

Each node must log:

* Agent decisions
* Tool invocations
* Failures
* Approval events
* API usage cost

System must support:

```
/health
/status
/api-usage
/logs
```

Self-healing patterns (like Tony Stark) are encouraged.

## 4. Technology Constraints

Preferred:

* Python 3.12+
* SQLite
* Local embeddings
* File-based configuration
* LaunchAgents
* rsync deploy simplicity

Avoid:

* OpenClaw
* Skill marketplaces
* Remote plugin execution
* Unreviewed third-party agent frameworks
* Over-engineered cloud-native stacks

We do not use OpenClaw in this system.

## 5. Node Order of Construction

### Step 1 — Jason Core Node

Jason Core defines:

* Policy engine
* Tool tier enforcement
* Approval workflow
* Sandbox runner
* Profile routing system
* Memory engine
* Base skill templates

Jason node is the reference implementation.

Do not build sub-nodes until Jason node is stable.

### Step 2 — Jennifer Node

Focus:

* Creative automation
* Communication workflows
* Light builder tools

Lower technical risk.

### Step 3 — Kiera Node

Focus:

* Idea incubation
* Micro-business experiments
* Controlled outbound approval
* Creator pack

Stronger safety gating required.

### Step 4 — Scarlet Node

Focus:

* Math tools
* Builder pack
* Structured project management
* Creative structured domains (Minecraft, knitting)

Most suitable for structured tool usage.

## 6. Deployment Philosophy

Deployment must be:

* One command
* Idempotent
* Non-destructive to data
* Profile-aware
* Service-aware

Code and data must never mix.

## 7. Cost Model

System must track:

* API usage per profile
* Cost per tool
* Monthly burn

Goal: controlled, transparent cost.

Local embeddings preferred to reduce API dependency.

## 8. Long-Term Vision

This is not just a chatbot.

This is:

* A personal AI operating system
* A creativity amplifier
* A business incubator platform
* A digital autonomy training ground

The system must be extendable to:

* Home automation
* Cross-node communication (future phase)
* Shared knowledge exchange (opt-in only)
* Inter-agent collaboration (Jason approved)

## 9. Non-Goals

We are NOT building:

* An AI toy
* An uncontrolled autonomous bot
* A public SaaS
* A cloud-hosted dependency
* A plugin marketplace
* A self-modifying system without oversight

## 10. End State

In 3–5 years:

Each family member:

* Has an AI system they built themselves
* Understands its internals
* Knows how to extend it
* Uses it to generate income or amplify output
* Controls it, not the other way around

Jason Core acts as:

* Architect
* Guardian
* Policy authority
* Infrastructure maintainer

## Development Directive for Cursor Agent

When generating architecture:

1. Start with Jason Core.
2. Build profile routing and policy enforcement first.
3. Build sandboxed execution.
4. Build memory system.
5. Build tool tier gating.
6. Then build starter skill packs.
7. Only after stabilization, scaffold sub-nodes.

Always prioritize:

* Simplicity
* Isolation
* Observability
* Controlled autonomy
* Long-term maintainability

Never introduce OpenClaw or plugin marketplaces.
