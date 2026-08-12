---
name: glab
description: "Use when the user mentions `glab`, `glab api`, the GitLab CLI, the GitLab API, or wants to view, query, search, or change GitLab. Covers querying the GitLab API, raw API calls, MRs/merge requests, review comment replies, issues, CI/CD pipelines, releases, repos, notifications, status, and any task that views or queries GitLab data."
user-invocable: true
---

# GitLab CLI (glab) Reference

## Fence policy

Coding agents run fenced. Fence permits the everyday mutations:
`git push`, `glab mr comment`, `glab mr approve`, `glab mr create`,
`glab issue create`, `glab issue update`, `glab ci retry`,
and `glab mr merge`. Invoking a command that names a mutation
is the consent for that mutation, so run it rather than asking again.

Fence denies raw `glab api`, `glab repo create` and `glab repo edit`,
`glab config`, `glab auth`, and the other destructive namespaces. Output
those for the operator to run in an unfenced shell. Raw reads go through
`glab-api-safe`.

## Body text policy

Every command below that carries a `-d`/`--description` or `-m`/`--message`
publishes under the user's name. Load the `contribution-voice` skill and follow it
before writing that text. It governs the structure: length, layout,
sign-offs, and the cut pass.

This covers `glab mr create`, `glab mr note`, `glab issue create`,
and `glab issue note`.

Prefer the dedicated commands where one fits. Reach for a bare `glab` call
only when no command covers the case.

## Merge Requests

```bash
# List
glab mr list
glab mr list -M --per-page 10                                            # merged MRs
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
glab mr merge 123 --squash --remove-source-branch
glab mr merge 123 --auto-merge                                         # merge once CI passes

# Approve & comment
glab mr approve 123
glab mr unapprove 123
glab mr note 123 -m "Please fix X"                                     # note/comment; also `glab mr comment`

# CI status
glab ci status                                                         # pipeline status for current branch
glab ci status -b main --live                                          # stream until complete

# Edit
glab mr update 123 --label "bug" --reviewer charlie
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
glab issue list --assignee @me                                        # open issues (default)
glab issue list --label "bug"

# View
glab issue view 456
glab issue view 456 --comments
glab issue view 456 --web

# Create
glab issue create --title "Bug: X fails" --description "Steps..." --label "bug" --assignee @me

# Manage
glab issue update 456 --label "priority" --milestone "v2.0"
glab issue close 456
glab issue reopen 456
glab issue note 456 -m "Fixed in !123"                                # note/comment; also `glab issue comment`
glab issue subscribe 456
glab issue unsubscribe 456
```

## CI / Pipelines

```bash
# List pipelines
glab ci list
glab ci list -r main --per-page 5                                      # by ref
glab ci list -s failed                                                 # by status

# View a pipeline (branch/tag positional, or -w for the web UI)
glab ci view main
glab ci view --web

# Job logs
glab ci trace <job-id>                                                  # live log tail for a job
glab ci view                                                           # interactive job/trace browser

# Retry / cancel
glab ci retry 12345678
glab ci cancel pipeline 12345678                                       # namespace: pipeline or job

# Trigger pipeline
glab ci run -b main
glab ci run -b main --variables-env "ENV=staging"

# Download artifacts
glab job artifact main build                                           # artifacts of job `build` on ref `main`
```

## Releases

```bash
# Create
glab release create v1.2.3 -N "Fixes #123"
glab release create v1.2.3 -N "Release notes" dist/*.tar.gz

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
glab mr list -R owner/other-repo
```

## Search

```bash
# Projects
glab repo search --search "nix config"

# Issues and MRs
glab issue list --search "memory leak" -R owner/repo
glab mr list --search "fix authentication" --author alice
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
`-X`/`--method` (including glued forms such as `-XPOST`)/`--hostname`/`-f`/`-F`/`--field`/`--raw-field`/`--input` (except `query=` value under `graphql`, where `@file` is still rejected), strips `?`/`#` suffixes to the bare path before matching, rejects format extensions such as `.json`, and runs a
best-effort GraphQL heuristic that rejects any query whose body contains
a surviving `mutation` or `subscription` keyword after comments and
string literals have been stripped. The heuristic is not a real GraphQL
parser; aliased mutations are out of scope and `@file` queries are
rejected outright. Policy rejections exit 64 with a single-line reason
on stderr; on rejection, switch to the matching dedicated subcommand or
escalate to an unfenced shell rather than retrying the same call. Run
`glab-api-safe --help` for the full policy summary.

Placeholders `:namespace`, `:repo`, `:branch`, `:fullpath`, `:group`,
`:id`, `:user`, and `:username` are replaced from current git context.
Default method is GET.

```bash
# GET piped into jq
glab-api-safe projects/:namespace%2F:repo/pipelines \
  | jq '.[:5] | .[] | {id, status, ref}'

# Paginate all results
glab-api-safe projects/:namespace%2F:repo/issues --paginate | jq '.[].title'

# GraphQL (heuristic-screened; mutations and subscriptions are rejected)
glab-api-safe graphql -f query='{ currentUser { username } }'

# Events (read only)
glab-api-safe events | jq '.[] | {action_name, target_type}'
```

### Unsafe: requires unfenced shell

> ⚠️ The commands below mutate GitLab state. They use `glab api` directly
> with `-X` / `-F` / `--input` and are rejected by `glab-api-safe`. They must
> only be run in an unfenced shell with explicit operator consent. Prefer
> the dedicated `glab` subcommands (`glab issue update`, `glab mr update`, etc.)
> wherever they exist.

```bash
# PUT / POST
glab api projects/:namespace%2F:repo/issues/456 -X PUT -F state=closed
glab api projects/:namespace%2F:repo/labels -F name="triage" -F color="e4e669"

# Typed fields (-F): true/false/null/integers become JSON types; @file reads file
glab api projects/:namespace%2F:repo/issues -F title="Bug" -F description=@issue.md
```

## JSON Output Pattern

List and view commands accept `-F json` (`mr list`, `ci list`) or
`-O json` (`issue list`), then pipe into `jq`:

```bash
# JSON output piped to jq
glab mr list -F json | jq '.[] | {iid, title, state, source_branch}'
glab ci list -F json | jq '.[] | {id, status, ref, sha}'
glab issue list -O json | jq '.[] | {iid, title, labels}'

# Filter inline
glab mr list -F json | jq '.[] | select(.state == "opened") | .iid'

# Combine with jq outside glab for complex transforms
glab issue list -O json | jq '.[] | select(.labels | any(.name == "bug"))'
```

## Status & Auth

```bash
glab auth status             # active account, token scopes, host
glab auth status -t          # shows the token; allowed under Fence, never echo the value
# `glab auth login` and `glab auth logout` stay denied.
```
