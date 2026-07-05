#!/usr/bin/env bash
set -euo pipefail

usage() {
	echo "USAGE: gen-complete-platforms.sh" && exit 1
}

if [[ -z "${TARGET_INTERPRETER_CONSTRAINTS}" ]]; then
	echo "Missing required envvar 'TARGET_INTERPRETER_CONSTRAINTS"
	usage
fi
if [[ -z "${MOUNT_OUTPUT_DIRPATH}" ]]; then
	echo "Missing required envvar 'MOUNT_OUTPUT_DIRPATH"
	usage
fi
if [[ -z "${PLATFORM_TGT}" ]]; then
	echo "Missing required envvar 'PLATFORM_TGT"
	usage
fi
if [[ -z "${PYTHON_VERSION}" ]]; then
	echo "Missing required envvar 'PYTHON_VERSION"
	usage
fi
if [[ -z "${OUTPUT_FILENAME}" ]]; then
	echo "Missing required envvar 'OUTPUT_FILENAME'"
	usage
fi


if [[ "$OUTPUT_FILENAME" == musl-* ]]; then
	apk add bash curl gcc git linux-headers musl-dev
fi

PYTHON_PROGNAME="python${PYTHON_VERSION}"
PYTHON_PROG_PATH="$(which $PYTHON_PROGNAME)"

python -m venv .venv
source .venv/bin/activate
pip install pex
pex3 interpreter inspect \
	--python "$PYTHON_PROG_PATH" \
	--interpreter-constraint="$TARGET_INTERPRETER_CONSTRAINTS" \
	--markers \
	--tags \
	--indent=2 > "$MOUNT_OUTPUT_DIRPATH/$OUTPUT_FILENAME"
