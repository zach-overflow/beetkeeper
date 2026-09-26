# Installation

beetkeeper can be run as a [**Docker image**](#docker) (recommended for a self-hosted deployment), installed
from [**PyPI**](#pypi) alongside an existing beets install, or downloaded as a
[**standalone binary**](#standalone-binary) that needs neither Python nor Docker.

All three methods point beetkeeper at your **beets directory**: the directory holding your beets `config.yaml`
and library database, passed as the `BEETSDIR` env var or the `--beetsdir` CLI flag. See
[Configuration](../configuration.md) for what beetkeeper reads from that config file.

## Docker

Map your host directories to the container's volume paths:

| Container path | Function                                     |
| :------------- | :------------------------------------------- |
| `/beets`       | Persistent beets config file and app data    |
| `/music`       | Music library (beets-tagged and imported)    |
| `/downloads`   | Raw downloaded music, unprocessed by beets   |


=== "docker compose"

    ```yaml
    services:
      beetkeeper:
        image: ghcr.io/zach-overflow/beetkeeper
        restart: unless-stopped
        stop_grace_period: 30s
        ports:
          - "8337:8337"
        environment:
          BEETSDIR: /beets
        volumes:
          - /host/path/to/beets_app_directory:/beets
          - /host/path/to/downloads:/data/raw
          - /host/path/to/music_library:/data/music
    ```

=== "docker run"

    ```shell
    docker run \
      -v /host/path/to/beets_app_directory:/beets \
      -v /host/path/to/downloads:/data/raw \
      -v /host/path/to/music_library:/data/music \
      -e BEETSDIR=/beets \
      -p 8337:8337 \
	  --stop-timeout 30 \
	  ghcr.io/zach-overflow/beetkeeper
    ```

See [Deployment](./deployment.md) for the full Docker workflow, including the one-time database migration step.

## PyPI

To run without Docker, install **both** the server package and the beets plugin package into the same
virtualenv as your `beets` install:

```shell
pip install beetkeeper beetkeeper-plugin
```

Then run the server, pointing it at your beets directory:

```shell
beetkeeper --beetsdir /path/to/beetsdir run
```

!!! note "Two packages"
    `beetkeeper` is the server; `beetkeeper-plugin` is the beets plugin that reports library events back to
    a running server. Install both so automated event tracking works.

## Standalone binary

Every [GitHub release](https://github.com/zach-overflow/beetkeeper/releases) attaches a single-file server
binary per platform. It bundles the beetkeeper server, beets, and the beetkeeper beets plugin, and fetches its
own Python runtime on first run, so nothing needs to be installed beforehand — no Python, no Docker.

| File | Platform |
| :--- | :------- |
| `beetkeeper-macos-aarch64` | Apple Silicon macOS |
| `beetkeeper-linux-x86_64` | x64 Linux |
| `beetkeeper-linux-aarch64` | ARM64 Linux |

No Intel macOS binary is published; on an Intel Mac, install from PyPI or use the Docker image instead.

Download the file for your platform and its `.sha256` checksum, verify it, and make it executable. The commands
below fetch the latest release; to pin a version, replace `releases/latest/download` with
`releases/download/vX.Y.Z`.

=== "macOS"

    ```shell
    FILE=beetkeeper-macos-aarch64   # your file from the table
    curl -LO "https://github.com/zach-overflow/beetkeeper/releases/latest/download/${FILE}"
    curl -LO "https://github.com/zach-overflow/beetkeeper/releases/latest/download/${FILE}.sha256"
    shasum -a 256 -c "${FILE}.sha256"
    chmod +x "${FILE}" && sudo mv "${FILE}" /usr/local/bin/beetkeeper
    ```

=== "Linux"

    ```shell
    FILE=beetkeeper-linux-x86_64    # your file from the table
    curl -LO "https://github.com/zach-overflow/beetkeeper/releases/latest/download/${FILE}"
    curl -LO "https://github.com/zach-overflow/beetkeeper/releases/latest/download/${FILE}.sha256"
    sha256sum -c "${FILE}.sha256"
    chmod +x "${FILE}" && sudo mv "${FILE}" /usr/local/bin/beetkeeper
    ```

Then run it exactly like the PyPI install:

```shell
beetkeeper --beetsdir /path/to/beetsdir run
```

To upgrade, download the newer release's file the same way and replace the old binary. beetkeeper's own
database is migrated automatically at the next startup — see
[Deployment](./deployment.md#upgrading-an-existing-install).

!!! note "First run downloads a Python runtime"
    The binary fetches a stripped CPython on first launch (network needed once) and caches it under
    `~/.cache/nce` on Linux or `~/Library/Caches/nce` on macOS. Set `SCIE_BASE` to move that cache.

!!! note "macOS: the binary is not signed"
    The macOS binaries are neither code-signed nor notarized. A `curl` download runs as-is; a file saved by a
    browser is quarantined and blocked by Gatekeeper until you run `xattr -d com.apple.quarantine <file>`.

!!! note "Event tracking with the binary"
    The beets plugin is bundled, so imports run through beetkeeper's UI or API are tracked once your beets
    config enables `beetkeeper_plugin` (see
    [Configuration](../configuration.md#the-beets-plugin-beetkeeper_plugin) for its `server_url` and
    `api_token` settings). Only a `beet` command installed separately needs `pip install beetkeeper-plugin`
    in its own environment, as described in the [PyPI](#pypi) note above.
