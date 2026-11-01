"""`repo-graph <tool> ...`: the six MCP tools as one-shot shell commands.

For agents with no MCP client, CI, and low-memory machines: one call loads the
cached layout (rebuilding it first if the code changed), answers, and exits. No
resident server, no watcher.

Each subcommand calls the same function the MCP server registers, so the text is
byte for byte what the MCP tool returns. The flags are read off that function's
signature (names, types, defaults, bounds and help), so the CLI can't drift from
the MCP schema.

    repo-graph orient
    repo-graph find checkout
    pytest 2>&1 | repo-graph find - --kind stacktrace
    repo-graph impact "Cart.add,checkout" --direction backward
    repo-graph trace login
    repo-graph read handleLogin --context-lines 3
    repo-graph refresh --full
"""

from __future__ import annotations

import argparse
import contextlib
import inspect
import os
import sys
import typing

from pydantic.fields import FieldInfo

from . import server

# Per tool, the parameters taken positionally (in order). Everything else is a
# `--flag`. Keys are the CLI's subcommands; a test locks them to the MCP registry.
POSITIONAL: dict[str, tuple[str, ...]] = {
    "orient": ("seed",),
    "find": ("query",),
    "impact": ("nodes",),
    "trace": ("from_node", "to_node"),
    "read": ("node",),
    "refresh": ("repo_path",),
}

# A positional given as `-` is read from stdin: `git diff | repo-graph find -`.
STDIN = "-"


def _field(annotation) -> tuple[type, FieldInfo | None]:
    """(base type, pydantic Field) out of an `Annotated[T, Field(...)]` hint."""
    args = typing.get_args(annotation)
    if not args:
        return annotation, None
    info = next((a for a in args[1:] if isinstance(a, FieldInfo)), None)
    return args[0], info


def _bounded(typ: type, info: FieldInfo | None):
    """An argparse `type=` that enforces the Field's ge/le, as the MCP schema does."""
    lo = hi = None
    for m in (info.metadata if info else []):
        lo = getattr(m, "ge", lo)
        hi = getattr(m, "le", hi)

    def convert(raw: str):
        val = typ(raw)
        if lo is not None and val < lo:
            raise argparse.ArgumentTypeError(f"must be >= {lo}")
        if hi is not None and val > hi:
            raise argparse.ArgumentTypeError(f"must be <= {hi}")
        return val

    convert.__name__ = typ.__name__  # argparse names the type in its error text
    return convert


def _help(info: FieldInfo | None) -> str:
    # argparse %-formats help strings.
    return (info.description or "").replace("%", "%%") if info else ""


def _add_tool(sub, name: str) -> None:
    fn = getattr(server, name)
    doc = inspect.getdoc(fn) or ""
    p = sub.add_parser(
        name,
        allow_abbrev=False,  # `--dir` must not quietly mean `--direction`
        help=doc.split(". ")[0].rstrip(".") + ".",
        description=doc.replace("%", "%%"),
    )
    p.add_argument(
        "--repo",
        default=os.environ.get("REPO_GRAPH_REPO", os.getcwd()),
        help="Path to the target repository, or a git URL to clone and map. "
             "Default: $REPO_GRAPH_REPO, else the current directory.",
    )
    p.add_argument(
        "--verbose", action="store_true",
        help="Keep the engine's progress log on stderr (dropped by default).",
    )
    hints = typing.get_type_hints(fn, include_extras=True)
    for pname, param in inspect.signature(fn).parameters.items():
        typ, info = _field(hints[pname])
        required = param.default is inspect.Parameter.empty
        if pname in POSITIONAL[name]:
            p.add_argument(
                pname,
                nargs=None if required else "?",
                default=None if required else param.default,
                help=_help(info) + f" `{STDIN}` reads it from stdin.",
            )
        elif typ is bool:
            p.add_argument(f"--{pname.replace('_', '-')}", dest=pname,
                           action="store_true", help=_help(info))
        else:
            p.add_argument(f"--{pname.replace('_', '-')}", dest=pname,
                           type=_bounded(typ, info), default=param.default,
                           metavar=pname.upper(), help=_help(info))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-graph",
        allow_abbrev=False,
        description="Ask the repo-graph structural map one question and exit. "
                    "Same answers as the MCP tools, no server.",
    )
    sub = parser.add_subparsers(dest="tool", required=True, metavar="TOOL")
    for name in POSITIONAL:
        _add_tool(sub, name)
    return parser


@contextlib.contextmanager
def _engine_log_dropped():
    """Send fd 2 to devnull for the duration. glia writes its progress log
    (`[gmap]`, `[live]`, ...; ~40 lines a call) from Rust straight to fd 2, so
    swapping `sys.stderr` wouldn't catch it, and an agent reading the command's
    output would pay for every line."""
    sys.stderr.flush()
    saved = os.dup(2)
    try:
        with open(os.devnull, "w") as null:
            os.dup2(null.fileno(), 2)
        yield
    finally:
        sys.stderr.flush()
        os.dup2(saved, 2)
        os.close(saved)


def run(argv: list[str]) -> int:
    """Parse `argv` (`<tool> [args]`), print the tool's answer, return the exit code."""
    args = build_parser().parse_args(argv)

    # The answers carry `⊘`, `→` and box glyphs; don't let a cp1252 or C-locale
    # stream turn one into a UnicodeEncodeError.
    for stream in (sys.stdout, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    kwargs = {k: v for k, v in vars(args).items() if k not in ("tool", "repo", "verbose")}
    for pname in POSITIONAL[args.tool]:
        if kwargs.get(pname) == STDIN:
            kwargs[pname] = sys.stdin.read()

    try:
        repo = server._resolve_repo(args.repo)
    except RuntimeError as e:
        print(f"repo-graph: error: {e}", file=sys.stderr)
        return 1
    if not os.path.isdir(repo):
        print(f"repo-graph: error: not a directory: {repo}", file=sys.stderr)
        return 1
    server.REPO_PATH = repo

    quiet = contextlib.nullcontext() if args.verbose else _engine_log_dropped()
    try:
        with quiet:
            out = getattr(server, args.tool)(**kwargs)
            # Drop the graph while the log is still muted: since glia 0.5.2 a
            # freed graph logs its heap trim, which at exit would land on stderr.
            server._graph = None
    except Exception as e:  # the MCP runtime turns these into a tool error
        print(f"repo-graph: error: {e}", file=sys.stderr)
        return 1
    print(out)
    return 0
