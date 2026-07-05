#!/usr/bin/env bash
set -euo pipefail

PYTHON_VERSION="3.14"
TARGET_INTERPRETER_CONSTRAINTS='CPython>=3.14,<3.15'
CONTAINER_MNT_PATH="/mnt/repo_src"
COMPLETE_PLATFORMS_DIR="$(pwd)/3rdparty/platforms"
CONTAINER_SCRIPT_PATH="${CONTAINER_MNT_PATH}/build_scripts/code_gen/linux_get_platforms_info.sh"


# Calls 'linux_get_platforms_info.sh' script from within the specified platform's docker image,
# and redirects to repo's complete platforms files.
export_json_from_container() {
	local platform_tgt
	local image
	local entry_cmd
	local entry_args
	local output_filename
	platform_tgt="$1"
	image="$2"
	echo "checking image type ..."
	if [[ "$image" == *alpine ]]; then
		echo "is alpine"
		entry_cmd='sh'
		entry_args="apk add bash && $CONTAINER_SCRIPT_PATH"
		output_filename="musl-linux-$platform_tgt.json"
	else
		echo "NOT alpine"
		entry_cmd='bash'
		output_filename="linux-$platform_tgt.json"
	fi
	docker run -it --rm \
		-v "$(pwd):/mnt/repo_src" \
		-e TARGET_INTERPRETER_CONSTRAINTS="${TARGET_INTERPRETER_CONSTRAINTS}" \
		-e MOUNT_OUTPUT_DIRPATH="${CONTAINER_MNT_PATH}/3rdparty/platforms" \
		-e PLATFORM_TGT="$platform_tgt" \
		-e OUTPUT_FILENAME="$output_filename" \
		-e PYTHON_VERSION="$PYTHON_VERSION" \
		--entrypoint "$entry_cmd" \
		--platform "linux/$platform_tgt" "$image" \
		-c "${entry_args}"
}

###################
####   24.04   ####
###################
IMAGE_NAME="python:${PYTHON_VERSION}-slim-bookworm"
export_json_from_container amd64 "$IMAGE_NAME"
export_json_from_container aarch64 "$IMAGE_NAME"

###################
####   musl    ####
###################
IMAGE_NAME="python:${PYTHON_VERSION}-alpine"
export_json_from_container amd64 "$IMAGE_NAME"
export_json_from_container aarch64 "$IMAGE_NAME"
