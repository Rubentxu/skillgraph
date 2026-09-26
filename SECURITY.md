# Security Policy — SkillGraph

> **Status:** Active. Coordinated disclosure process for
> SkillGraph core, runtime, and CLI.

## Reporting a vulnerability

We accept vulnerability reports through **GitHub Security
Advisories** on this repository:

```
https://github.com/Rubentxu/skillgraph/security/advisories/new
```

Please **do not** file a public GitHub issue for security-sensitive
reports. Public issues on active vulnerabilities will be closed
without action and the reporter will be redirected to the private
channel.

A report should include:

- A clear description of the vulnerability and its impact.
- Reproduction steps or a proof-of-concept (when feasible).
- Affected version(s) (`skillgraph.__version__` and commit SHA).
- Environment (OS, Python version, SQLite version, mode: local /
  container / CI).

## Response targets

| Severity | Acknowledgement | Triage | Fix target |
|---|---|---|---|
| Critical | 48 hours | 7 days | 30 days |
| High | 7 days | 14 days | **90 days** |
| Medium | 14 days | 30 days | next minor |
| Low | 30 days | next cycle | next minor |

Severity is assessed using CVSS v3.1 as a guide, combined with the
project's threat model (local-first Python tool, SQLite storage,
untrusted Markdown/YAML inputs, optional LLM adapter).

## Coordinated disclosure

We follow **coordinated disclosure**:

1. Reporter and maintainer agree on a disclosure timeline
   (default: 90 days from acknowledgement for High severity).
2. Maintainer prepares a fix and a release; reporter reviews when
   feasible.
3. Fix is released and CVE is requested via GitHub Security
   Advisories (GHSA).
4. After the agreed timeline elapses (or the fix is public), the
   advisory is published with full details.

If a vulnerability is being actively exploited in the wild, the
timeline is shortened at the maintainer's discretion.

## Scope

In scope:

- SkillGraph core (`src/skillgraph/core/`).
- Runtime and controllers (`src/skillgraph/runtime/`).
- CLI (`src/skillgraph/cli/`).
- Storage (`src/skillgraph/platform/storage.py`).
- Knowledge, evidence, and governance subsystems.

Out of scope (third-party):

- Vulnerabilities in `PyYAML`, `dulwich`, `pytest`, `ruff`, or any
  transitive dependency. Report upstream.
- Vulnerabilities introduced by user-supplied Domain Packs (the
  Adapter protocol assumes untrusted packs and isolates by
  construction; report only if isolation breaks).

## Acknowledgements

We thank the security community for responsible disclosure.
Contributors are credited in release notes unless they prefer
anonymity.

---

_Last updated: 2026-09-26 (WI-01)._