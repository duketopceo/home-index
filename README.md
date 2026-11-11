# home-index

Cheap, local-first index of everything on this machine (`~`).

- **Script mode (default):** pure Python, no network, no API. Walks `~`, ignores caches/venvs/build output, emits `INDEX.md` + `index.json`. Cost $0, data stays on the box.
- **LLM mode (optional, `--llm`):** classifies *filenames + dir names only* via OpenRouter with ZDR-allowlisted providers (`data_collection: deny`). File contents are never sent. OpenRouter still sees requests in transit, so script mode is the secure default; use `--llm` only when the free classification is worth it.

## Usage

```bash
python3 index.py --print          # stats + stdout preview
python3 index.py                  # write INDEX.md + index.json at repo root
python3 index.py --llm            # + optional OpenRouter classification (needs OPENROUTER_API_KEY in omaseal: openrouter/default)
python3 index.py --llm --yes      # skip confirmation prompt
```

## Lanes

| Lane | Path |
|---|---|
Lanes are auto-detected (first child of `~/Work/` and `~/Projects/`, plus
`~/Agents/`, `~/Pictures/Screenshots/`, and `~/.config/omarchy/` when present).
No usernames, orgs, or host paths are hardcoded. Output paths are home-relative.

## License

MIT. See `LICENSE`.

## Privacy

- Default run sends nothing anywhere.
- `--llm` sends only relative paths under `~`, never file contents, and refuses to run unless `openrouter/default` resolves via omaseal.
