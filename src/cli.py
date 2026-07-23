from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from context import build_context, context_records, render_context
from indexer import build_index, default_index_file
from search import SearchResult, search_index
from stats import collect_stats
from status import IndexStatus, check_index


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.handler(args)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codemap")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="scan a repository")
    index_parser.add_argument("repository", type=Path)
    index_parser.add_argument("--index-file", type=Path)
    index_parser.add_argument("--max-file-size", type=int, default=1_000_000)
    index_parser.add_argument("--max-lines", type=int, default=120)
    index_parser.add_argument("--overlap-lines", type=int, default=20)
    index_parser.set_defaults(handler=run_index)

    stats_parser = subparsers.add_parser("stats", help="show index statistics")
    stats_parser.add_argument("--repository", type=Path, default=Path.cwd())
    stats_parser.add_argument("--index-file", type=Path)
    stats_parser.set_defaults(handler=run_stats)

    status_parser = subparsers.add_parser("status", help="check index status")
    status_parser.add_argument("--repository", type=Path, default=Path.cwd())
    status_parser.add_argument("--index-file", type=Path)
    status_parser.add_argument("--max-file-size", type=int, default=1_000_000)
    status_parser.set_defaults(handler=run_status)

    context_parser = subparsers.add_parser("context", help="build search context")
    context_parser.add_argument("query")
    context_parser.add_argument("--repository", type=Path, default=Path.cwd())
    context_parser.add_argument("--index-file", type=Path)
    context_parser.add_argument("--limit", type=int, default=5)
    context_parser.add_argument("--language")
    context_parser.add_argument("--path")
    context_parser.add_argument("--lines-before", type=int, default=2)
    context_parser.add_argument("--lines-after", type=int, default=2)
    context_parser.add_argument("--max-lines", type=int, default=80)
    context_parser.add_argument("--format", choices=("text", "json"), default="text")
    context_parser.set_defaults(handler=run_context)

    search_parser = subparsers.add_parser("search", help="search indexed chunks")
    search_parser.add_argument("query")
    search_parser.add_argument("--repository", type=Path, default=Path.cwd())
    search_parser.add_argument("--index-file", type=Path)
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.add_argument("--language")
    search_parser.add_argument("--path")
    search_parser.add_argument("--show-snippets", action="store_true")
    search_parser.set_defaults(handler=run_search)

    return parser


def run_index(args: argparse.Namespace) -> int:
    index_file = args.index_file or default_index_file(args.repository)
    summary = build_index(
        args.repository,
        index_file=index_file,
        max_file_size=args.max_file_size,
        max_lines=args.max_lines,
        overlap_lines=args.overlap_lines,
    )

    print(f"Repository: {summary.repository}")
    print(f"Index: {summary.index_file}")
    print(f"Metadata: {summary.metadata_file}")
    print(f"Format: {summary.format_version}")
    print(f"Files seen: {summary.files_seen}")
    print(f"Files indexed: {summary.files_indexed}")
    print(f"Files skipped: {summary.files_skipped}")
    print(f"Chunks: {summary.chunks_written}")
    print_languages(summary.languages)
    return 0


def run_stats(args: argparse.Namespace) -> int:
    index_file = args.index_file or default_index_file(args.repository)
    stats = collect_stats(index_file)

    print(f"Index: {stats.index_file}")
    print(f"Format: {stats.format_version if stats.format_version is not None else 'unknown'}")
    print(f"Files: {stats.files}")
    print(f"Chunks: {stats.chunks}")
    print_languages(stats.languages)
    return 0


def run_status(args: argparse.Namespace) -> int:
    index_file = args.index_file or default_index_file(args.repository)
    index_status = check_index(
        args.repository,
        index_file=index_file,
        max_file_size=args.max_file_size,
    )

    print_index_status(index_status)
    return 0


def run_context(args: argparse.Namespace) -> int:
    index_file = args.index_file or default_index_file(args.repository)
    sections = build_context(
        args.query,
        index_file,
        limit=args.limit,
        language=args.language,
        path=args.path,
        lines_before=args.lines_before,
        lines_after=args.lines_after,
        max_lines=args.max_lines,
    )

    if not sections:
        if args.format == "json":
            print("[]")
            return 0

        print("No context")
        return 0

    if args.format == "json":
        print(json.dumps(context_records(sections), ensure_ascii=False, indent=2))
    else:
        print(render_context(sections))

    return 0


def run_search(args: argparse.Namespace) -> int:
    index_file = args.index_file or default_index_file(args.repository)
    results = search_index(
        args.query,
        index_file,
        limit=args.limit,
        language=args.language,
        path=args.path,
    )

    if not results:
        print("No results")
        return 0

    for result in results:
        print_search_result(result, show_snippets=args.show_snippets)

    return 0


def print_index_status(index_status: IndexStatus) -> None:
    print(f"Repository: {index_status.repository}")
    print(f"Index: {index_status.index_file}")
    print(f"Current: {'yes' if index_status.is_current else 'no'}")
    print(f"Files indexed: {index_status.indexed_files}")
    print(f"Files scanned: {index_status.scanned_files}")
    print(f"Unchanged: {len(index_status.unchanged_files)}")
    print(f"Changed: {len(index_status.changed_files)}")
    print(f"Missing: {len(index_status.missing_files)}")
    print(f"New: {len(index_status.new_files)}")
    print_paths("Changed files", index_status.changed_files)
    print_paths("Missing files", index_status.missing_files)
    print_paths("New files", index_status.new_files)


def print_search_result(result: SearchResult, *, show_snippets: bool = False) -> None:
    chunk = result.chunk
    terms = ", ".join(result.matched_terms) if result.matched_terms else "-"
    lines = format_lines(result.matched_lines)
    print(f"{chunk.file}:{chunk.start_line}-{chunk.end_line}")
    print(f"  score: {result.score:g}")
    print(f"  terms: {terms}")
    print(f"  lines: {lines}")

    if show_snippets:
        for line in search_snippets(result):
            print(f"  {line}")


def search_snippets(result: SearchResult, *, limit: int = 3) -> list[str]:
    selected_lines = set(result.matched_lines[:limit])
    snippets: list[str] = []

    for line_number, line in enumerate(result.chunk.content.splitlines(), start=result.chunk.start_line):
        if line_number not in selected_lines:
            continue

        text = line.strip()
        if len(text) > 120:
            text = f"{text[:117]}..."
        snippets.append(f"{line_number}: {text}")

    return snippets


def format_lines(lines: tuple[int, ...]) -> str:
    if not lines:
        return "-"

    visible = ", ".join(str(line) for line in lines[:8])
    return f"{visible}, ..." if len(lines) > 8 else visible


def print_languages(languages: dict[str, int]) -> None:
    if not languages:
        print("Languages: none")
        return

    print("Languages:")
    for language, count in languages.items():
        print(f"  {language}: {count}")


def print_paths(label: str, paths: tuple[str, ...], *, limit: int = 20) -> None:
    if not paths:
        return

    print(f"{label}:")
    for path in paths[:limit]:
        print(f"  {path}")

    remaining = len(paths) - limit
    if remaining > 0:
        print(f"  ... {remaining} more")


if __name__ == "__main__":
    raise SystemExit(main())
