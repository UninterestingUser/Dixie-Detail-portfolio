---
title: Documentation conventions
summary: How every document and data file in this repository is written, labeled and kept current, for human readers and for AI retrieval.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-18
tags: [documentation, conventions, rag]
related: [docs/README.md, docs/templates/doc-template.md, docs/templates/decision-template.md, tools/check_docs.py]
---

# Documentation conventions

This repository is the single source of truth for how the Dixie Detail business system works and why. The same files serve two readers: a person browsing on GitHub, and an AI system that splits them into chunks, indexes them and answers questions from them. Every rule below serves one or both.

## Formats

- **Markdown (`.md`)** for anything explained in sentences: goals, how something works, procedures, decisions.
- **YAML (`.yaml`)** in `data/` for hard facts that code or people look up: services, rules with numbers, secret names, settings, accounts. The price matrix stays a CSV because the pricebook import reads it.
- No other formats for documentation. Diagrams are written as Mermaid inside Markdown, so they stay text.

## Where things go

| Folder | What belongs there | Example |
| --- | --- | --- |
| `docs/overview/` | Why the system exists, what it covers, the vocabulary, the phases | `glossary.md` |
| `docs/architecture/` | How the system is built and connected | `secrets.md` |
| `docs/reference/` | Business rules and behavior in detail: pricing, booking, tax, texts | `pricing.md` |
| `docs/decisions/` | One file per decision, with the reasons and the alternatives | `0028-secrets-in-bitwarden.md` |
| `docs/operations/` | Procedures for running the server: deploy, back up, restore, fix | `troubleshooting.md` |
| `docs/guides/` | Day-to-day use of the system, by role, written as tasks | `owner-daily-routine.md` (planned) |
| `data/` | Structured facts, each file with a `meta` block | `data/pricing-rules.yaml` |

## The header block

Every Markdown file under `docs/` starts with a YAML header. `tools/check_docs.py` rejects a file without one.

```yaml
---
title: Pricing rules                # what a person would call this page
summary: How a price is built ...   # one sentence, under 200 characters
audience: [owner, staff, developer] # who it is for; filter for role-specific AI
visibility: internal                # internal = any staff or AI; restricted = owner and developers only
status: current                     # current | planned | draft | historical | superseded
updated: 2026-10-13                 # date of the last real change
tags: [pricing, booking]            # optional, lowercase
related: [docs/reference/sales-tax.md, data/pricing-rules.yaml]  # optional repo paths
---
```

What `status` means, because an AI repeats whatever a document claims:

| Status | Meaning |
| --- | --- |
| `current` | Describes something that exists and works today. |
| `planned` | Describes the design for something not built yet. Write it in the future tense ("will"), so nobody mistakes it for a working feature. |
| `draft` | Work in progress; not yet agreed. |
| `historical` | A record of how something was done or decided at the time. Kept for context, not instructions. |
| `superseded` | Replaced by the file named in `superseded_by`. |

Decision records use their own header; see [templates/decision-template.md](templates/decision-template.md).

YAML files in `data/` start with a `meta` block with `title`, `summary`, `updated` and `status`, for the same reasons.

## Writing for retrieval

A retrieval system hands the AI a few paragraphs cut from the middle of a file. Each paragraph has to make sense on its own.

- **One topic per file.** Split a file that covers two things.
- **Descriptive headings.** "Condition adjustment" or "How the second Monthly job is timed", never "Rules" or "Notes". A heading travels with its chunk.
- **Name the subject in each section.** Write "The condition adjustment adds 10%", not "It adds 10%". Never write "see above" or "as mentioned".
- **Define terms once in the [glossary](overview/glossary.md)** and use them exactly. A class is always a "vehicle class", and a size variant is never also called a "tier".
- **Keep files short.** A few screens at most. Long procedures become numbered steps under clear headings.
- **Give the reason with the rule.** "Two people take 60% of the time (the owner's measured figure)" lets an AI explain the rule, not just recite it.
- **Use plain words.** The owner and future staff read these too.
- **Write in US English.** The owner writes US English: color, behavior, canceled, catalog, labeled, recognize. Third-party names, commands and library identifiers keep their own spelling.

## Facts live in one place

A fact written in two places will eventually disagree with itself, and an AI fed both gives a confident wrong answer.

- Numbers that code uses live in `data/`. Prose explains them and links to the file instead of repeating the number, except for a worked example.
- Each rule is explained in one reference file. Other files link to it.
- When a rule changes, change the data file, the reference file and add a decision record in the same pull request.

## What never goes in the docs

- **Secret values** of any kind. Secret *names* are fine and live in `data/configuration.yaml`.
- **Customer personal data**: names, numbers, addresses, vehicles of real customers. Use invented examples. Exports and import corrections stay outside the repository.
- **Card or bank details.**

## Docs are part of done

A pull request that changes behavior, a setting, a secret name, a server path or a business rule also updates the matching documentation. The pull request checklist asks for it, and Claude Code is told the same in `CLAUDE.md`.

| You changed | Also update |
| --- | --- |
| A business rule | The reference file, the data file if it holds the number, and a new decision record |
| A setting or secret | `data/configuration.yaml` and `.env.example` |
| A server path, unit file or script | The architecture or operations file that names it |
| Something built that was `planned` | Its status to `current`, and the text from "will" to present tense |
| A problem you had to troubleshoot | A row in [operations/troubleshooting.md](operations/troubleshooting.md) |

## Decision records

- One decision per file in `docs/decisions/`, numbered in order: `0029-short-name.md`.
- A decision is never edited to say something new. A changed decision gets a new record that `supersedes` the old one, and the old one gets `status: superseded` and `superseded_by`.
- [decisions/README.md](decisions/README.md) lists every record. The checker fails if one is missing from the list.

## Checks

`tools/check_docs.py` runs on every pull request through `.github/workflows/docs.yml`, and locally with `python3 tools/check_docs.py`. It checks:

- every docs file has a valid header block
- every relative link points at a file that exists
- every YAML file parses and has a `meta` block
- every decision record is listed in the decision index, with a matching number
- nothing that looks like a key, token or private key has been committed
