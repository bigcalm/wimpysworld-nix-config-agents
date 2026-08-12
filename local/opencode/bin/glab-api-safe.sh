#!/usr/bin/env bash

# glab-api-safe: Fence-friendly wrapper around `glab api`.
#
# This wrapper exists so the Fence policy can deny the broad `glab api` escape
# hatch while still letting agents perform read-shaped REST and GraphQL
# requests against the GitLab API. The semantics are "safe", not strictly
# "read-only": GET requests against method-overloaded endpoints are permitted,
# but any request that smuggles a body or overrides the method via `glab`'s
# own flags is rejected.
#
# Policy summary:
#   * Argv pre-check rejects -X/--method (including glued forms such as
#     -XPOST), --hostname, -f/--field, -F/--raw-field, and --input on every
#     token. The only exception is `-f query=...` (or -F/--field/--raw-field
#     with `query=`) when the endpoint is `graphql`.
#   * REST endpoints must match an allow-list. A deny-list overrides the
#     allow-list and rejects credential, admin, secrets, runner,
#     personal-access-token, access-token, deploy-token, and support-PIN
#     endpoints.
#   * GraphQL queries are parsed best-effort (comments and string literals
#     stripped) and rejected if a `mutation` or `subscription` keyword
#     survives. This is a heuristic, not a real GraphQL parser; aliased
#     queries and `@file` queries are out of scope (`@file` is rejected
#     outright).
#   * On a policy violation the wrapper exits 64 with a single-line reason
#     on stderr. Otherwise it delegates to the GitLab CLI API command with the
#     request argv unchanged.

readonly EX_POLICY=64

die() {
	printf 'glab-api-safe: %s\n' "$*" >&2
	exit "${EX_POLICY}"
}

usage() {
	cat <<'EOF'
glab-api-safe: Fence-friendly wrapper around `glab api`.

USAGE
    glab-api-safe ENDPOINT [glab api flags...]
    glab-api-safe graphql -f query='{ ... }'
    glab-api-safe --help

POLICY
    Argv pre-check rejects -X/--method (including glued forms such as
    -XPOST), --hostname, -f/--field, -F/--raw-field, and --input on every
    token. The exception is `-f query=...` (or the equivalent
    -F/--field/--raw-field forms) when the endpoint is `graphql`, so
    read-only GraphQL queries remain usable.

    REST endpoints must match an allow-list: projects, projects/*, groups,
    groups/*, user, user/*, users/*, namespaces, namespaces/*, search,
    events, markdown, version, meta, todos, todos/*, issues, issues/*,
    merge_requests, merge_requests/*, snippets, snippets/*.

    A deny-list overrides the allow-list and rejects admin/*,
    personal_access_tokens, runners, applications, */variables, */secrets,
    */runners, */access_tokens, */deploy_tokens, user/support_pin, and the
    user credential surface (user/emails, user/keys, user/gpg_keys).

    GraphQL: the query value is stripped of `#` comments and `"..."` /
    `"""..."""` string literals, then rejected if a `mutation` or
    `subscription` keyword survives. This is a heuristic, not a real
    parser, so aliased mutations, fragment-sourced operations, and
    `@file` queries are not detected and `@file` is rejected outright.

    On a policy violation glab-api-safe exits 64 with a single-line reason
    on stderr. Otherwise it delegates to the GitLab CLI API command with the
    request argv unchanged.
EOF
}

# Surface --help/-h before any other parsing so users can discover the
# policy without tripping the endpoint requirement.
for arg in "$@"; do
	case "${arg}" in
	-h | --help)
		usage
		exit 0
		;;
	esac
done

# Copy positional args into an indexed array. We need to walk the argv
# twice (once to find the endpoint, once to enforce flag policy) and
# bash's positional parameters are awkward to index from a loop variable.
args=("$@")
nargs=${#args[@]}

if [[ ${nargs} -eq 0 ]]; then
	die "missing endpoint (try: glab-api-safe --help)"
fi

# Phase 1: find the first positional argument. Treat the flags that glab api
# documents as taking a separate value as consuming the following argv
# entry, so we skip past their values when looking for the endpoint.
endpoint=""
i=0
while [[ ${i} -lt ${nargs} ]]; do
	tok="${args[${i}]}"
	case "${tok}" in
	--)
		# Everything after `--` is positional; the next token is the
		# endpoint if present.
		i=$((i + 1))
		if [[ ${i} -lt ${nargs} ]]; then
			endpoint="${args[${i}]}"
		fi
		break
		;;
	--*=*)
		i=$((i + 1))
		;;
	-X | --method | -f | --field | -F | --raw-field | --input | \
		-H | --header | --hostname | --jq | -q | -t | --template | --cache)
		i=$((i + 2))
		;;
	-*)
		i=$((i + 1))
		;;
	*)
		endpoint="${tok}"
		break
		;;
	esac
done

if [[ -z ${endpoint} ]]; then
	die "missing endpoint (try: glab-api-safe --help)"
fi

is_graphql=0
case "${endpoint}" in
graphql | graphql/*)
	is_graphql=1
	;;
esac

# Phase 2: argv pre-check. Reject body- and method-related flags on every
# token. For graphql, allow `-f query=...` / `-F query=...` / the
# `--field` / `--raw-field` equivalents and capture the query value for
# the heuristic.
graphql_query=""
graphql_query_set=0
j=0
while [[ ${j} -lt ${nargs} ]]; do
	tok="${args[${j}]}"
	case "${tok}" in
	--input | --input=*)
		die "--input is not permitted (stdin bodies are blocked)"
		;;
	-X | --method)
		die "method override (${tok}) is not permitted"
		;;
	--method=*)
		die "method override (--method=) is not permitted"
		;;
	--hostname | --hostname=*)
		die "--hostname is not permitted (token exfiltration risk)"
		;;
	-f | -F | --field | --raw-field)
		j=$((j + 1))
		if [[ ${j} -ge ${nargs} ]]; then
			die "${tok} requires an argument"
		fi
		val="${args[${j}]}"
		if [[ ${is_graphql} -eq 1 && ${val} == query=* ]]; then
			graphql_query="${val#query=}"
			graphql_query_set=1
		else
			die "${tok} is only permitted as 'query=' for the graphql endpoint"
		fi
		;;
	--field=* | --raw-field=*)
		flag="${tok%%=*}"
		val="${tok#*=}"
		if [[ ${is_graphql} -eq 1 && ${val} == query=* ]]; then
			graphql_query="${val#query=}"
			graphql_query_set=1
		else
			die "${flag}= is only permitted as 'query=' for the graphql endpoint"
		fi
		;;
	-f* | -F* | -X*)
		die "glued ${tok:0:2} short flags are not supported by glab-api-safe"
		;;
	esac
	j=$((j + 1))
done

# Phase 3a: REST allow-list and deny-list. Skipped for graphql.
if [[ ${is_graphql} -eq 0 ]]; then
	# Allow-list: the endpoint path must match one of these prefixes.
	# Patterns are case-sensitive and use shell case-glob semantics.
	case "${endpoint}" in
	projects | projects/*) ;;
	groups | groups/*) ;;
	user | user/*) ;;
	users/*) ;;
	namespaces | namespaces/*) ;;
	search | search/*) ;;
	events) ;;
	markdown) ;;
	version) ;;
	meta) ;;
	todos | todos/*) ;;
	issues | issues/*) ;;
	merge_requests | merge_requests/*) ;;
	snippets | snippets/*) ;;
	*)
		die "endpoint '${endpoint}' is not on the REST allow-list"
		;;
	esac

	# Deny-list: defence in depth. Rejects credential, admin, secrets,
	# runner, and personal-access-token paths even if they would
	# otherwise be matched by the allow-list above.
	case "${endpoint}" in
	admin/*)
		die "endpoint '${endpoint}' is on the REST deny-list (admin surface)"
		;;
	personal_access_tokens | personal_access_tokens/*)
		die "endpoint '${endpoint}' is on the REST deny-list (personal access tokens)"
		;;
	runners | runners/*)
		die "endpoint '${endpoint}' is on the REST deny-list (runners)"
		;;
	applications | applications/*)
		die "endpoint '${endpoint}' is on the REST deny-list (OAuth applications)"
		;;
	*/variables | */variables/*)
		die "endpoint '${endpoint}' is on the REST deny-list (CI/CD variables)"
		;;
	*/secrets | */secrets/*)
		die "endpoint '${endpoint}' is on the REST deny-list (secrets)"
		;;
	*/runners | */runners/*)
		die "endpoint '${endpoint}' is on the REST deny-list (project/group runners)"
		;;
	*/access_tokens | */access_tokens/*)
		die "endpoint '${endpoint}' is on the REST deny-list (access tokens)"
		;;
	*/deploy_tokens | */deploy_tokens/*)
		die "endpoint '${endpoint}' is on the REST deny-list (deploy tokens)"
		;;
	user/support_pin | user/support_pin/*)
		die "endpoint '${endpoint}' is on the REST deny-list (support PIN)"
		;;
	user/emails | user/emails/* | user/keys | user/keys/* | user/gpg_keys | user/gpg_keys/*)
		die "endpoint '${endpoint}' is on the REST deny-list (user credential surface)"
		;;
	esac
fi

# Phase 3b: GraphQL heuristic. Strip `#`-to-EOL comments and double-quoted
# (incl. triple-quoted block) string literals, then look for the
# `mutation` or `subscription` keywords surviving as standalone words.
# This is best-effort, not a parser; document accordingly.
if [[ ${is_graphql} -eq 1 ]]; then
	if [[ ${graphql_query_set} -eq 0 ]]; then
		die "graphql endpoint requires a -f/-F query=... argument"
	fi
	if [[ ${graphql_query} == @* ]]; then
		die "graphql @file queries are not permitted (contents cannot be inspected)"
	fi

	# Pure-bash state machine over the query body. Avoids pulling sed,
	# awk, or perl into runtimeInputs and keeps the wrapper closure
	# small. Inputs are typically short (a single GraphQL query), so the
	# per-character loop is not a concern.
	stripped=""
	qlen=${#graphql_query}
	k=0
	state=normal
	while [[ ${k} -lt ${qlen} ]]; do
		ch="${graphql_query:${k}:1}"
		case "${state}" in
		normal)
			three="${graphql_query:${k}:3}"
			if [[ ${three} == '"""' ]]; then
				state=block
				k=$((k + 3))
				continue
			fi
			case "${ch}" in
			'"')
				state=string
				;;
			'#')
				state=comment
				;;
			*)
				stripped+="${ch}"
				;;
			esac
			;;
		string)
			if [[ ${ch} == $'\\' ]]; then
				# Skip the escape and the following character so escaped
				# quotes do not terminate the literal prematurely.
				k=$((k + 2))
				continue
			fi
			if [[ ${ch} == '"' ]]; then
				state=normal
			fi
			;;
		block)
			three="${graphql_query:${k}:3}"
			if [[ ${three} == '"""' ]]; then
				state=normal
				k=$((k + 3))
				continue
			fi
			;;
		comment)
			if [[ ${ch} == $'\n' ]]; then
				state=normal
				stripped+="${ch}"
			fi
			;;
		esac
		k=$((k + 1))
	done

	# Surviving `mutation` / `subscription` keywords are rejected. We use
	# explicit non-word boundaries because bash's [[ =~ ]] honours
	# POSIX character classes but not Perl-style \b.
	if [[ ${stripped} =~ (^|[^[:alnum:]_])(mutation|subscription)([^[:alnum:]_]|$) ]]; then
		die "graphql query rejected by heuristic (mutation/subscription keyword detected)"
	fi
fi

: "${GLAB_API_SAFE_GLAB:=glab}"
export GH_TELEMETRY="${GH_TELEMETRY:-false}"

# Use the real GitLab CLI binary through a private helper name. The raw
# `glab api` command remains denied for user-entered commands.
exec "${GLAB_API_SAFE_GLAB}" api "$@"
