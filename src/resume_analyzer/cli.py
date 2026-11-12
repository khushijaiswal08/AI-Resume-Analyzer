"""Command-line interface.

resume-analyzer analyze resume.pdf --jd job.txt --format md
resume-analyzer serve --port 8000
"""

import argparse
import sys
from pathlib import Path

from resume_analyzer.config import get_settings
from resume_analyzer.llm.base import LLMClient
from resume_analyzer.models import AnalysisResult
from resume_analyzer.parsing import ParseError
from resume_analyzer.service import analyze_document, build_llm_client


def build_parser() -> argparse.ArgumentParser:
    """Define the CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="resume-analyzer", description="Explainable resume analysis."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    analyze = commands.add_parser("analyze", help="Analyse a resume file.")
    analyze.add_argument("file", type=Path, help="Resume file (PDF, DOCX or TXT).")
    analyze.add_argument("--jd", type=Path, help="Text file containing a job description.")
    analyze.add_argument("--format", choices=["json", "md"], default="md", help="Output format.")
    analyze.add_argument(
        "--no-llm", action="store_true", help="Skip the LLM even if an API key is configured."
    )

    serve = commands.add_parser("serve", help="Run the web app.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=None, help="Default: $PORT or 8000.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `resume-analyzer` console script. Returns an exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "resume_analyzer.api:app", host=args.host, port=args.port or get_settings().port
        )
        return 0
    return _run_analyze(args)


def _run_analyze(args: argparse.Namespace) -> int:
    settings = get_settings()
    llm_client: LLMClient | None = None if args.no_llm else build_llm_client(settings)
    try:
        data = args.file.read_bytes()
        jd_text = args.jd.read_text(encoding="utf-8") if args.jd else None
        result = analyze_document(data, jd_text, settings=settings, llm_client=llm_client)
    except OSError as exc:
        print(f"error: cannot read file: {exc}", file=sys.stderr)
        return 2
    except ParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = result.model_dump_json(indent=2) if args.format == "json" else to_markdown(result)
    # Write UTF-8 explicitly: Windows consoles may default to a narrower code page.
    sys.stdout.buffer.write((output + "\n").encode("utf-8"))
    sys.stdout.flush()
    return 0


def to_markdown(result: AnalysisResult) -> str:
    """Render an AnalysisResult as a readable Markdown report."""
    lines = [
        "# Resume analysis",
        "",
        f"**ATS-style score: {result.ats_score.total}/100** "
        "(transparent heuristic, not any real ATS vendor's algorithm)",
        "",
        "| Criterion | Score | Reason |",
        "|---|---|---|",
    ]
    lines += [
        f"| {item.criterion} | {item.score}/{item.max} | {item.reason} |"
        for item in result.ats_score.breakdown
    ]
    lines += ["", f"**Sections:** {', '.join(result.sections) or 'none detected'}"]
    lines += [f"**Word count:** {result.word_count}", "", "## Skills"]
    if result.skills:
        lines += [
            f"- **{category}**: {', '.join(names)}" for category, names in result.skills.items()
        ]
    else:
        lines.append("- none detected")

    if result.jd_match:
        match = result.jd_match
        lines += [
            "",
            f"## Job description match: {match.match_percent}%",
            f"- Matched: {', '.join(match.matched) or '-'}",
            f"- Missing: {', '.join(match.missing) or '-'}",
        ]

    lines += ["", "## AI insights"]
    if not result.llm.used:
        lines.append(f"_Not used: {result.llm.reason}_")
    else:
        if result.llm.summary:
            lines += [result.llm.summary, ""]
        lines += [f"- {item}" for item in result.llm.suggestions]
        if result.llm.interview_questions:
            lines += ["", "### Interview questions"]
            lines += [
                f"{number}. {q.question} _({q.skill}, {q.difficulty})_"
                for number, q in enumerate(result.llm.interview_questions, start=1)
            ]

    r = result.redaction
    lines += [
        "",
        f"_Redacted before any LLM call: {r.emails} emails, {r.phones} phones, {r.urls} URLs._",
    ]
    if result.warnings:
        lines += ["", "## Warnings", *[f"- {warning}" for warning in result.warnings]]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
