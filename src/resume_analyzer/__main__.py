"""Allow `python -m resume_analyzer ...` as an alternative to the console script."""

from resume_analyzer.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
