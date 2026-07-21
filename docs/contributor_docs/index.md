# Contributing

Documentation for working on beetkeeper itself. If you just want to run beetkeeper, see the
[getting started](../quickstart/index.md) page.

Contributions are welcome! If you are interested in contributing, please read through this page first.

Whether you want to contribute a doc change, a new feature, or a bug fix, it is recommended that you open an `

## AI / LLM Usage Rules


* All AI usage in any form must be disclosed. You must state the tool you used (e.g. Claude Code, Cursor, Amp) along with the extent that the work was AI-assisted.

* The contributor must fully understand all code they are sharing. If you can't explain what your changes do and how they interact with the greater system without the aid of AI tools, do not contribute to this project.

* **All community interactions, including comments, discussion, issues, PR titles, and descriptions must be composed by a human**. The one exception here is LLM-assisted translations. Please note when this is in use (ex: "I am translating from LANGUAGE with an LLM")

* **No AI-generated media or "art" is allowed. This means, no AI-generated images, videos, audio, etc**. Code is the only acceptable AI-generated content, per the other rules in this policy. As beetkeeper is itself a celebration of music and art, this a zero-tolerance rule.


This AI policy was adopted from the [ghostty-org AI policy](https://github.com/ghostty-org/ghostty/blob/2aa773a23a87289175bd022dfb617a5e8c27e824/AI_POLICY.md) and the [Pantsbuild LLM Assistance Notice](https://www.pantsbuild.org/dev/docs/contributions).
 

## Development Guides

- **[Testing & development](testing_and_development.md)** — local dev setup, running the test suite, and
  the Pants-based build workflow.
- **[Building artifacts](building_artifacts.md)** — packaging the wheels, the per-arch image PEXes, and the
  server image; regenerating the complete-platform JSONs.
- **[Release management](release_management.md)** — how releases are cut and published.

The source lives on [GitHub](https://github.com/zach-overflow/beetkeeper); issues and feature requests are
welcome on the [issue tracker](https://github.com/zach-overflow/beetkeeper/issues).
