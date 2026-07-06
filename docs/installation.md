# Installation

beetkeeper can be run either as a **Docker image** (recommended for a self-hosted deployment) or installed
from **PyPI** alongside an existing beets install.

Both methods point beetkeeper at your **beets** config: `BEETSDIR` (env var — the **directory** holding your
beets `config.yaml`) or `--config-path` (CLI flag — the config file itself). See
[Configuration](configuration.md) for what beetkeeper reads from that file.

## Docker

Map your host directories to the container's volume paths:

| Container path | Function                                     |
| :------------- | :------------------------------------------- |
| `/beets`       | Persistent beets config file and app data    |
| `/music`       | Music library (beets-tagged and imported)    |
| `/downloads`   | Raw downloaded music, unprocessed by beets   |

=== "docker run"

    ```shell
    docker run \
      -v /host/path/to/beets_app_directory:/beets \
      -v /host/path/to/downloads:/data/raw \
      -v /host/path/to/music_library:/data/music \
      -e BEETSDIR=/beets \
      -p 8337:8337 \
      ghcr.io/zach-overflow/beetkeeper
    ```

=== "docker compose"

    ```yaml
    services:
      beetkeeper:
        image: ghcr.io/zach-overflow/beetkeeper
        restart: unless-stopped
        ports:
          - "8337:8337"
        environment:
          BEETSDIR: /beets
        volumes:
          - /host/path/to/beets_app_directory:/beets
          - /host/path/to/downloads:/data/raw
          - /host/path/to/music_library:/data/music
    ```

See [Deployment](usage/deployment.md) for the full Docker workflow, including the one-time database migration step.

## PyPI

To run without Docker, install **both** the server package and the beets plugin package into the same
virtualenv as your `beets` install:

```shell
pip install beetkeeper beetkeeper-plugin
```

Then run the server, pointing it at your beets config:

```shell
beetkeeper run --config-path <path to your beets config>
```

!!! note "Two packages"
    `beetkeeper` is the server; `beetkeeper-plugin` is the beets plugin that reports library events back to
    a running server. Install both so automated event tracking works.
