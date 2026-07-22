from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    return 0


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog="repo-index")


if __name__ == "__main__":
    raise SystemExit(main())
