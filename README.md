# CodeMap

A command-line tool for exploring codebases with retrieval-augmented generation (RAG). Index a local repository, search its source, and ask questions with references to files and lines.

Search runs locally using keywords or optional embeddings. Generated answers use a language model provider you configure.

## Quick start

Requires Python 3.11+ and a POSIX environment. Tested on Linux; native Windows is unsupported and macOS is untested.

From your local clone:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

codemap index .
codemap search "chunk_text" --limit 3
codemap context "How does chunk_text split Python code?"
```

These commands need no API key or model download. To explore another project, index its path and pass `--repository /path/to/project` to subsequent commands.

## Generated answers

Configure a compatible Chat Completions API using your provider's full endpoint URL and model ID. Replace the placeholders below:

```bash
export CODEMAP_REMOTE_ENDPOINT='https://provider.example.invalid/v1/chat/completions'
export CODEMAP_MODEL='your-model-id'

codemap answer "How does chunk_text split Python code?" \
  --provider chat --allow-remote --prompt-key
```

Replace the example question with your own question about the indexed repository. Use `codemap context "your question"` to preview the selected code.

The API key is entered at a hidden prompt. `--allow-remote` permits sending your question and selected source context to that provider. Review the context first; provider charges and data policies apply.

Without a configured provider, `answer` defaults to `basic`, which returns matching references rather than a generated explanation.

## Optional search by meaning

Keyword search works out of the box. Semantic search adds a local embedding model to help find related code even when your question uses different words.

```bash
python -m pip install -e '.[embeddings]'
codemap index . --embeddings --download-model
```

This downloads the model once. Searches then combine keywords and meaning automatically. Keep `--embeddings` when reindexing; the model finds relevant code, while your configured provider generates answers.

## Notes

- Reindex after source changes. Use `codemap status` to check for changes and `codemap --help` for available commands.
- Scanning respects `.gitignore` and `.codemapignore`. Privacy filters are best effort; exclude confidential files yourself and keep `.repo-index/` out of Git in every repository you analyze.
- Intended for small to medium repositories. Check cited source when reviewing generated answers; valid citations do not guarantee accuracy.
