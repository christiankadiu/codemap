from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from codemap.answers import build_answer_request
from codemap.config import config_record, load_config, provider_options, render_config
from codemap.context import build_context, context_records, render_context
from codemap.embeddings import LocalEmbeddingProvider
from codemap.indexer import build_index, default_index_file
from codemap.interactive import prompt_api_key
from codemap.privacy import redact
from codemap.providers import provider_for_name, provider_names, validate_chat_options
from codemap.remote_provider import validate_endpoint
from codemap.responses import build_response, render_response, response_record
from codemap.retriever import MODES, retrieve
from codemap.search import SearchResult
from codemap.stats import collect_stats
from codemap.status import IndexStatus, check_index


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.handler(args)
    except OSError:
        print("error: filesystem or network operation failed", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError) as exc:
        print(f"error: {redact(str(exc))}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codemap")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="scan a repository")
    index_parser.add_argument("repository", type=Path)
    index_parser.add_argument("--index-file", type=Path)
    index_parser.add_argument("--max-file-size", type=int, default=1_000_000)
    index_parser.add_argument("--max-lines", type=int, default=120)
    index_parser.add_argument("--overlap-lines", type=int, default=20)
    index_parser.add_argument("--strategy", choices=("auto", "lines"), default="auto")
    index_parser.add_argument("--embeddings", action="store_true", help="build local semantic vectors")
    index_parser.add_argument("--download-model", action="store_true", help="allow downloading the pinned embedding model")
    index_parser.add_argument("--full", action="store_true", help="rebuild without reusing the previous index")
    index_parser.add_argument("--batch-size", type=int, default=32)
    index_parser.set_defaults(handler=run_index)

    stats_parser = subparsers.add_parser("stats", help="show index statistics")
    stats_parser.add_argument("--repository", type=Path, default=Path.cwd())
    stats_parser.add_argument("--index-file", type=Path)
    stats_parser.set_defaults(handler=run_stats)

    config_parser = subparsers.add_parser("config", help="show runtime config")
    config_parser.add_argument("--format", choices=("text", "json"), default="text")
    config_parser.set_defaults(handler=run_config)

    status_parser = subparsers.add_parser("status", help="check index status")
    status_parser.add_argument("--repository", type=Path, default=Path.cwd())
    status_parser.add_argument("--index-file", type=Path)
    status_parser.add_argument("--max-file-size", type=int)
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

    answer_parser = subparsers.add_parser(
        "answer", help="prepare an answer",
        description="Use basic for local references, chat for a compatible Chat Completions API, or remote for a custom JSON adapter.",
        epilog="For chat, set CODEMAP_REMOTE_ENDPOINT to the full API URL and CODEMAP_MODEL to your model ID. Use --prompt-key to enter the key privately, or set CODEMAP_REMOTE_KEY. Optional: CODEMAP_CHAT_FORMAT=json_schema and CODEMAP_REASONING_EFFORT=low only when supported by your model. No cloud provider or model is selected by default.",
    )
    answer_parser.add_argument("question")
    answer_parser.add_argument("--repository", type=Path, default=Path.cwd())
    answer_parser.add_argument("--index-file", type=Path)
    answer_parser.add_argument("--limit", type=int, default=5)
    answer_parser.add_argument("--language")
    answer_parser.add_argument("--path")
    answer_parser.add_argument("--lines-before", type=int, default=2)
    answer_parser.add_argument("--lines-after", type=int, default=2)
    answer_parser.add_argument("--max-lines", type=int, default=80)
    answer_parser.add_argument("--format", choices=("text", "json"), default="text")
    answer_parser.add_argument("--provider", choices=provider_names())
    answer_parser.add_argument("--show-context", action="store_true")
    answer_parser.add_argument("--allow-remote", action="store_true", help="consent to send the question and selected code to the configured endpoint")
    answer_parser.add_argument("--prompt-key", action="store_true", help="enter an API key privately for this request without saving it")
    answer_parser.set_defaults(handler=run_answer)

    search_parser = subparsers.add_parser("search", help="search indexed chunks")
    search_parser.add_argument("query")
    search_parser.add_argument("--repository", type=Path, default=Path.cwd())
    search_parser.add_argument("--index-file", type=Path)
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.add_argument("--language")
    search_parser.add_argument("--path")
    search_parser.add_argument("--show-snippets", action="store_true")
    search_parser.set_defaults(handler=run_search)

    for command in (search_parser, context_parser, answer_parser):
        command.add_argument("--mode", choices=MODES, default="auto")
        command.add_argument("--min-score", type=float, default=0.2, help="minimum semantic cosine similarity")
    for command in (context_parser, answer_parser):
        command.add_argument("--max-chars", type=int, default=12000)

    return parser


def run_index(args: argparse.Namespace) -> int:
    if args.download_model and not args.embeddings:
        raise ValueError("--download-model requires --embeddings")
    provider = (LocalEmbeddingProvider(allow_download=args.download_model, batch_size=args.batch_size)
                if args.embeddings else None)
    index_file = args.index_file or default_index_file(args.repository)
    summary = build_index(
        args.repository,
        index_file=index_file,
        max_file_size=args.max_file_size,
        max_lines=args.max_lines,
        overlap_lines=args.overlap_lines,
        strategy=args.strategy,
        embedding_provider=provider,
        incremental=not args.full,
        batch_size=args.batch_size,
    )

    print(f"Format: {summary.format_version}")
    print(f"Files seen: {summary.files_seen}")
    print(f"Files indexed: {summary.files_indexed}")
    print(f"Files skipped: {summary.files_skipped}")
    print(f"Chunks: {summary.chunks_written}")
    print(f"Files reused: {summary.files_reused}")
    print(f"Embeddings reused: {summary.embeddings_reused}")
    print(f"Embeddings created: {summary.embeddings_created}")
    print(f"Files redacted: {summary.redacted_files}")
    print_languages(summary.languages)
    return 0


def run_stats(args: argparse.Namespace) -> int:
    index_file = args.index_file or default_index_file(args.repository)
    stats = collect_stats(index_file)

    print(f"Format: {stats.format_version if stats.format_version is not None else 'unknown'}")
    print(f"Files: {stats.files}")
    print(f"Chunks: {stats.chunks}")
    print_languages(stats.languages)
    return 0


def run_config(args: argparse.Namespace) -> int:
    config = load_config()

    if args.format == "json":
        print(json.dumps(config_record(config), ensure_ascii=False, indent=2))
    else:
        print(render_config(config))

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
        max_chars=args.max_chars,
        mode=args.mode,
        min_score=args.min_score,
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


def run_answer(args: argparse.Namespace) -> int:
    config = load_config(provider=args.provider)
    if config.provider in ("remote", "chat") and not args.allow_remote:
        raise ValueError("remote answers send your question and selected code externally; review your ignore rules and use --allow-remote to consent")
    if args.prompt_key and config.provider == "basic":
        raise ValueError("--prompt-key requires --provider chat or remote")
    index_file = args.index_file or default_index_file(args.repository)
    request = build_answer_request(
        args.question,
        index_file,
        limit=args.limit,
        language=args.language,
        path=args.path,
        lines_before=args.lines_before,
        lines_after=args.lines_after,
        max_lines=args.max_lines,
        max_chars=args.max_chars,
        mode=args.mode,
        min_score=args.min_score,
    )
    options = provider_options(config, allow_remote=args.allow_remote)
    if request.has_context and config.provider == "chat":
        validate_chat_options(options)
    elif request.has_context and config.provider == "remote":
        if not options.remote_endpoint:
            raise ValueError("remote provider endpoint is not configured")
        validate_endpoint(options.remote_endpoint)
    if args.prompt_key and request.has_context:
        options = replace(options, remote_access_key=prompt_api_key())
    response = build_response(
        request,
        provider=provider_for_name(config.provider),
        options=options,
    )

    if args.format == "json":
        record = response_record(response)
        if args.show_context:
            record["context"] = context_records(request.context)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0

    print(render_response(response))

    if args.show_context and request.has_context:
        print()
        print("Context:")
        print(render_context(request.context))

    return 0


def run_search(args: argparse.Namespace) -> int:
    index_file = args.index_file or default_index_file(args.repository)
    results = retrieve(
        args.query,
        index_file,
        limit=args.limit,
        language=args.language,
        path=args.path,
        mode=args.mode,
        min_score=args.min_score,
    )

    if not results:
        print("No results")
        return 0

    for result in results:
        print_search_result(result, show_snippets=args.show_snippets)

    return 0


def print_index_status(index_status: IndexStatus) -> None:
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
    selected_lines = set(result.matched_lines[:limit] or range(result.chunk.start_line, min(result.chunk.end_line + 1, result.chunk.start_line + limit)))
    snippets: list[str] = []

    for line_number, line in enumerate(result.chunk.content.split("\n"), start=result.chunk.start_line):
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
