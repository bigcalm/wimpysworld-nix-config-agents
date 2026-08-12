---
name: glab
description: "Use when the user mentions `glab`, `glab api`, the GitLab CLI, the GitLab API, or wants to view, query, search, or change GitLab. Covers querying the GitLab API, raw API calls, MRs/merge requests, review comment replies, issues, CI/CD pipelines, releases, repos, notifications, status, and any task that views or queries GitLab data."
user-invocable: true
---

# GitLab CLI (glab) Reference

## Fence policy

Coding agents run fenced. Fence permits the everyday mutations:
`git push`, `glab mr comment`, `glab mr approve`, `glab mr create`,
`glab issue create`, `glab issue edit`, `glab ci retry`,
and `glab mr merge`. Invoking a command that names a mutation
is the consent for that mutation, so run it rather than asking again.

Fence denies raw `glab api`, `glab repo create` and `glab repo edit`,
`glab config`, `glab auth`, and the other destructive namespaces. Output
those for the operator to run in an unfenced shell. Raw reads go through
`glab-api-safe`.

## Body text policy

Every command below that carries a `--description` or `--description-file`
publishes under the user's name. Load the `contribution-voice` skill and follow it
before writing that text. It governs the structure: length, layout,
sign-offs, and the cut pass.

This covers `glab mr create`, `glab mr comment`, `glab mr approve`,
`glab issue create`, and `glab issue comment`.

Prefer the dedicated commands where one fits. Reach for a bare `glab` call
only when no command covers the case.

## Merge Requests

```bash
# List
glab mr list
glab mr list --state merged --per-page 10
glab mr list --assignee @me

# View
glab mr view 123
glab mr view 123 --comments
glab mr view 123 --web

# Create
glab mr create --fill                                                 # title/description from commits
glab mr create --title "feat: add X" --description "..." --draft
glab mr create --target-branch main --reviewer alice,bob --label "needs-review"

# Merge
glab mr merge 123 --squash --delete-source-branch
glab mr merge 123 --when-pipeline-succeeds                            # merge once CI passes

# Approve & comment
glab mr approve 123 --body "LGTM"
glab mr unapprove 123
glab mr comment 123 --body "Please fix X"

# CI status
glab mr ci-status 123
glab mr ci-status 123 --watch                                         # stream until complete

# Edit
glab mr update 123 --add-label "bug" --add-reviewer charlie
glab mr update 123 --target-branch develop --title "Updated title"

# Other
glab mr checkout 123
glab mr diff 123
glab mr subscribe 123
glab mr unsubscribe 123
glab mr reopen 123
glab mr close 123
```

## Issues

```bash
# List
glab issue list
glab issue list --assignee @me --state open
glab issue list --label "bug"

# View
glab issue view 456
glab issue view 456 --comments
glab issue view 456 --web

# Create
glab issue create --title "Bug: X fails" --description "Steps..." --label "bug" --assignee @me

# Manage
glab issue update 456 --add-label "priority" --milestone "v2.0"
glab issue close 456
glab issue reopen 456
glab issue comment 456 --body "Fixed in !123"
glab issue subscribe 456
glab issue unsubscribe 456
```

## CI / Pipelines

```bash
# List pipelines
glab ci list
glab ci list --branch main --per-page 5
glab ci list --pipeline-id 12345678

# View a pipeline
glab ci view 12345678
glab ci view 12345678 --web

# Pipeline logs
glab ci trace 12345678                                                # live log tail
glab ci view 12345678 --log                                           # full log
glab ci view 12345678 --job "test"                                    # specific job

# Retry / cancel
glab ci retry 12345678
glab ci cancel 12345678

# Trigger pipeline
glab ci run --ref main
glab ci run --ref main --variable "ENV=staging"

# Download artifacts
glab ci artifacts 12345678
glab ci artifacts 12345678 --job "build"
```

## Releases

```bash
# Create
glab release create v1.2.3 --notes "Fixes #123"
glab release create v1.2.3 --description "Release notes" --assets dist/*.tar.gz

# List / view / download
glab release list
glab release view v1.2.3
glab release download v1.2.3
```

## Repository

```bash
# View
glab repo view
glab repo view owner/repo

# Clone / fork
glab repo clone owner/repo
glab repo fork owner/repo --clone

# Cross-project flag (works on most commands)
glab mr list -g owner/other-repo
```

## Search

```bash
# Projects
glab search repo "nix config"

# Issues and MRs
glab search issue "memory leak" --repo owner/repo --state open
glab search mr "fix authentication" --author alice --state merged
```

## Raw API

Default to a dedicated `glab` subcommand. Use `glab-api-safe` only when no
subcommand fits. Raw `glab api` is denied under Fence. Reserve it for
mutations with no subcommand and for `@file` field input, and output the
command for the operator to run in an unfenced shell.

| Situation                              | Use                                                  |
| -------------------------------------- | ---------------------------------------------------- |
| Read-only REST fetch                   | `glab-api-safe <path>`                               |
| GraphQL read (queries only)            | `glab-api-safe graphql -f query='…'`                 |
| Dedicated subcommand exists            | that subcommand (`glab mr update`, `glab issue update`, ...) |
| Other mutation (POST/PUT/DELETE)       | `glab api -X ...` in unfenced shell                  |
| Field input from file (`-F x=@file`)   | raw `glab api` in unfenced shell                     |

`glab-api-safe` wraps `glab api`, enforces a read-only allow-list with a
defence-in-depth deny-list on the REST path, blocks
`-X`/`--method`/`-f`/`-F`/`--field`/`--raw-field`/`--input` (except `query=` value under `graphql`, where `@file` is still rejected), and runs a
best-effort GraphQL heuristic that rejects any query whose body contains
a surviving `mutation` or `subscription` keyword after comments and
string literals have been stripped. The heuristic is not a real GraphQL
parser; aliased mutations are out of scope and `@file` queries are
rejected outright. Policy rejections exit 64 with a single-line reason
on stderr; on rejection, switch to the matching dedicated subcommand or
escalate to an unfenced shell rather than retrying the same call. Run
`glab-api-safe --help` for the full policy summary.

Placeholders `{owner}`, `{repo}`, `{branch}` are replaced from current
git context. Default method is GET.

```bash
# GET with jq
glab-api-safe projects/{owner}%2F{repo}/pipelines \
  --jq '.[:5] | .[] | {id, status, ref}'

# Paginate all results
glab-api-safe projects/{owner}%2F{repo}/issues --paginate --jq '.[].title'

# GraphQL (heuristic-screened; mutations and subscriptions are rejected)
glab-api-safe graphql -f query='{ currentUser { username } }'

# Notifications (read only)
glab-api-safe events --jq '.[] | {action_name, target_type}'
```

### Unsafe: requires unfenced shell

> ⚠️ The commands below mutate GitLab state. They use `glab api` directly
> with `-X` / `-F` / `--input` and are rejected by `glab-api-safe`. They must
> only be run in an unfenced shell with explicit operator consent. Prefer
> the dedicated `glab` subcommands (`glab issue update`, `glab mr update`, etc.)
> wherever they exist.

```bash
# PUT / POST
glab api projects/{owner}%2F{repo}/issues/456 -X PUT -F state=closed
glab api projects/{owner}%2F{repo}/labels -F name="triage" -F color="e4e669"

# Typed fields (-F): true/false/null/integers become JSON types; @file reads file
glab api projects/{owner}%2F{repo}/issues -F title="Bug" -F description=@issue.md
```

## JSON Output Pattern

Most commands accept `--json fields` with optional `--jq expression`:

```bash
# Named fields only
glab mr list --json iid,title,state,source_branch
glab ci list --json id,status,ref,sha

# Filter inline
glab mr list --json iid,title,state \
  --jq '.[] | select(.state == "opened") | .iid'

# Combine with jq outside glab for complex transforms
glab issue list --json iid,title,labels | jq '.[] | select(.labels | any(.name == "bug"))'
```

## Status & Auth

```bash
glab auth status             # active account, token scopes, host
glab auth token              # allowed under Fence; never echo the value
# `glab auth login` and `glab auth logout` stay denied.
```
