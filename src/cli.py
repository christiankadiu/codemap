from __future__ import annotations

import argparse
import sys
from pathlib import Path

from indexer import build_index, default_index_file
from stats import collect_stats


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.handler(args)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repo-index")
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
    print(f"Files: {stats.files}")
    print(f"Chunks: {stats.chunks}")
    print_languages(stats.languages)
    return 0


def print_languages(languages: dict[str, int]) -> None:
    if not languages:
        print("Languages: none")
        return

    print("Languages:")
    for language, count in languages.items():
        print(f"  {language}: {count}")


if __name__ == "__main__":
    raise SystemExit(main())
