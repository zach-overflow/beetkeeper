#!/usr/bin/env bash
set -euo pipefail

sha="$1"
docs_version="$2"
site_url="${SITE_URL:-https://beetkeeper.dadbodaudio.com}"

echo "Waiting for the GitHub Pages build of ${sha}..."
status="" commit=""
for _ in $(seq 1 30); do
	build="$(curl -sS -H "Authorization: Bearer ${GH_TOKEN}" \
		"https://api.github.com/repos/${GITHUB_REPOSITORY}/pages/builds/latest")"
	status="$(jq -r '.status' <<<"${build}")"
	commit="$(jq -r '.commit' <<<"${build}")"
	if [[ "${commit}" == "${sha}" && "${status}" == "built" ]]; then
		break
	fi
	if [[ "${commit}" == "${sha}" && "${status}" == "errored" ]]; then
		echo "❌ The Pages build of ${sha} errored."
		exit 1
	fi
	sleep 10
done
if [[ "${commit}" != "${sha}" || "${status}" != "built" ]]; then
	echo "❌ Timed out waiting for the Pages build of ${sha} (last seen: commit=${commit} status=${status})."
	exit 1
fi

failed=0
for path in "" "latest/" "${docs_version}/"; do
	url="${site_url}/${path}"
	code=""
	for attempt in $(seq 1 6); do
		# The query string busts the Fastly CDN cache so we test the build we just waited for.
		code="$(curl -sS -o /dev/null -w '%{http_code}' "${url}?smoke=${sha:0:12}-${attempt}")"
		[[ "${code}" == "200" ]] && break
		sleep 10
	done
	if [[ "${code}" == "200" ]]; then
		echo "✅ ${url} -> ${code}"
	else
		echo "❌ ${url} -> ${code}"
		failed=1
	fi
done
exit "${failed}"
