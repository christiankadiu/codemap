from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repo-index")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="scan a repository")
    index_parser.add_argument("repository")
    index_parser.add_argument("--index-file")
    index_parser.add_argument("--max-file-size", type=int, default=1_000_000)
    index_parser.add_argument("--max-lines", type=int, default=120)
    index_parser.add_argument("--overlap-lines", type=int, default=20)

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
