# beetkeeper

A self-hosted web app for managing and monitoring [beets](https://beets.io/) — supporting both
**automated** (REST API) and **manual** (web UI) music-library workflows.

Not to be confused with the [beets web plugin](https://beets.readthedocs.io/en/stable/plugins/web.html),
beetkeeper offers the following out of the box:

| Feature                                                     | **beetkeeper** | `beets[web]` |
| :---------------------------------------------------------- | :---: | :---: |
| Explore current and past beets imports                      | :white_check_mark: | :x: |
| Automated REST API-based imports                            | :white_check_mark: | :x: |
| Manually run imports from the UI                            | :white_check_mark: | :x: |
| Advanced search UI, all [query types](https://beets.readthedocs.io/en/stable/reference/query.html) | :white_check_mark: | :x: |
| All UI functionality available via REST API                 | :white_check_mark: | :x: |
| Async API support                                           | :white_check_mark: | :x: |
| Play library audio files in the browser                     | :x: | :white_check_mark: |

## Get started

<div class="grid cards" markdown>

- :material-download: **[Install](installation.md)** — via Docker or PyPI.
- :material-cog: **[Configure](configuration.md)** — the optional `beetkeeper` section of your beets config.
- :material-play: **[Use it](usage/quickstart.md)** — the CLI and the web UI.
- :material-server: **[Deploy](usage/deployment.md)** — run it under Docker.

</div>

## Web interface

**Run multiple imports** — and monitor them simultaneously, whether started manually or via the REST API.

![Running imports](assets/images/base_import_screenshot_0-0-3rc1.png){ width="70%" }

**Automated event tracking** — album/song import completion, file modifications, and more. The full beets
event history is retained whether triggered via the UI or the API.

![Event tracking](assets/images/events_example_0-0-3rc1.png){ width="70%" }

**Search your beets library** — similar in spirit to `beets[web]`, exposing the full beets query language.

![Search](assets/images/base_search_example_0-0-3rc1.png){ width="70%" }

## License

beetkeeper is licensed under [AGPL-3.0-or-later](https://www.gnu.org/licenses/agpl-3.0.en.html).
