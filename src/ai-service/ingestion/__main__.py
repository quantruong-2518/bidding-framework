"""Enable `python -m ingestion` to run the ingestion CLI."""

from __future__ import annotations

from ingestion.entry import main

if __name__ == "__main__":
    raise SystemExit(main())
