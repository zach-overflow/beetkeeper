<!--  
beetkeeper: A highly configurable, self-hosted app for beets music library management. Supports both automated and manual workflows.
Copyright (C) 2026 Zach Gottesman

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.  
-->

# Beetkeeper

[![PyPI Version](https://img.shields.io/pypi/v/beetkeeper)](https://pypi.org/project/beetkeeper/)
[![python](https://img.shields.io/badge/python-3.14%2B-blue.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
![license](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue?style=flat)

A self-hosted web app for managing and monitoring [beets](https://beets.io/). Supports both automated and manual beet workflows.

## Features

Not to be confused with the [beets web plugin](https://beets.readthedocs.io/en/v2.5.0/plugins/web.html), `beetkeeper` offers the following features out of the box:

| Feature                                                     | **`beetkeeper`** |    `beets[web]`  |
| :---------------------------------------------------------- |      :---:       |      :---:       |
| Explore current and past `beets` imports                    |  ✅              |  ❌               |
| Supports automated REST API-based import workflows          |  ✅              |  ❌               |
| UI support for manual imports                               |  ✅              |  ❌               |
| Advanced search UI, supports all [query types](https://beets.readthedocs.io/en/v2.5.0/reference/query.html) |  ✅              |  ❌               |
| Automated beets event tracking and history preservation     |  ✅              |  ❌               |
| Async API support                                           |  ✅              |  ❌               |
| Play library audio files in browser                         |  ❌              |  ✅               |

## Getting Started

Refer to the official user documentation at [beetkeeper.dadbodaudio.com](https://beetkeeper.dadbodaudio.com/latest/).

## Installation

Installable as a Docker image (recommended), or as a Python package from PyPI. For detailed installation instructions,
refer to the [user doc section on installation](https://beetkeeper.dadbodaudio.com/latest/installation/).


## Contributing and Development Info

Refer to the [contributor docs](./docs/contributor_docs).

## Releases

Check out the [releases page](https://github.com/zach-overflow/beetkeeper/releases) for more details.

## Bugs Reports / Feature Requests

Feel free to file them on the [issues page](https://github.com/zach-overflow/beetkeeper/issues).
