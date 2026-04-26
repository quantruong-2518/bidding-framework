"""CLI entry point: ``python -m kb_writer <subcommand>``.

Currently routes only to :func:`kb_writer.pack_builder.main` for the
``rebuild-packs`` subcommand. Future subcommands (e.g. atom validate)
get wired here.
"""

from __future__ import annotations

from kb_writer.pack_builder import main


if __name__ == "__main__":
    raise SystemExit(main())
