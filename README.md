# Beetkeeper

[![python](https://img.shields.io/badge/python-3.14-blue.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
![license](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue?style=flat)

**Currently under development**

A self-hosted web app for managing and monitoring [beets](https://beets.io/).

## Features

Not to be confused with the [beets web plugin](https://beets.readthedocs.io/en/v2.5.0/plugins/web.html), `beetkeeper` offers the following features out of the box:

| Feature                                                     | **`beetkeeper`** |    `beets[web]`  |
| :---------------------------------------------------------- |      :---:       |      :---:       |
| Explore current and past `beets` imports                    |  ✅              |  ❌               |
| UI supports manually running imports                        |  ✅              |  ❌               |
| Advanced search UI, supports all [query types](https://beets.readthedocs.io/en/v2.5.0/reference/query.html) |  ✅              |  ❌               |
| All UI functionality available via REST API for automation  |  ✅              |  ❌               |
| Async API support                                           |  ✅              |  ❌               |
| Play library audio files in browser                         |  ❌              |  ✅               |
| 

## Installation

You can install `beetkeeper` either as a Python library, or as a Docker image.
TBD when we will have our first release generally available.

### Docker Installation

The docker container is fairly straightforward. 
You just need to map your host directories to the following container volume paths:

|  Container Volume Path     |  Function                                  |
| :------------------------- |--------------------------------------------|
| `/beets`                   | Persistent beets config file and app data  |
| `/music`                   | Music library (beets-tagged and imported)  |
| `/downloads`               | Raw downloaded music, unprocessed by beets |

Example docker usage is shown below:

Via docker run:

```shell
docker run \
	-v /host/path/to/beets_app_directory:/beets \
	-v /host/path/to/downloads:/data/raw \
	-v /host/path/to/music_library:/data/music \
	-e BEETKEEPER_CONFIG=/beets/config.yaml \
	ghcr.io/zach-overflow/beetkeeper
```

Or via docker-compose:

```yaml
services:
  beetkeeper:
    image: ghcr.io/zach-overflow/beetkeeper
    restart: unless-stopped
    ports:
      - "8080:8080"
	environment:
	  BEETKEEPER_CONFIG=/beets/config.yaml
    volumes:
      - /host/path/to/beets_app_directory:/beets
	  - /host/path/to/downloads:/data/raw
	  - /host/path/to/music_library:/data/music
```

## Releases

Check out the [releases page](https://github.com/zach-overflow/beetkeeper/releases) for more details.

## Bugs Reports / Feature Requests

Feel free to file them on the [issues page](https://github.com/zach-overflow/beetkeeper/issues).
