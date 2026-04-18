# repo-graph-py

Native Rust engine for [`mcp-repo-graph`](https://pypi.org/project/mcp-repo-graph/) — parses source, builds a unified cross-language graph, stores it in a zero-copy `.gmap` file.

This package is the Rust engine (via pyo3 + maturin). Users install it transitively through `mcp-repo-graph`; there is usually no reason to install it directly.

## Install

```bash
pip install mcp-repo-graph
```

This pulls `repo-graph-py` as a dependency and gives you the `repo-graph` CLI.

## Platform support

- **v0.4.12** — Linux x86_64 only (prebuilt wheel). Other platforms will need Rust + maturin at install time until v0.4.13 adds the full wheel matrix.
- **v0.4.13 (planned)** — Linux x86_64/aarch64 (manylinux), macOS x86_64/arm64, Windows x86_64 × Python 3.11–3.14 via maturin GitHub Actions.

## License

MIT
