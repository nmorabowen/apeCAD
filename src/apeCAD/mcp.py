"""`python -m apeCAD.mcp`: the MCP server over stdio (spec agent-surface-mcp §8).

Kept apart from `apeCAD.agent.mcp` so a missing `mcp` extra is one clear line on stderr.
"""

from __future__ import annotations

import importlib.util
import sys


def main(argv: list[str] | None = None) -> None:
    if importlib.util.find_spec("mcp") is None:
        print("apeCAD.mcp needs the mcp extra: pip install 'apeCAD[mcp]'", file=sys.stderr)
        raise SystemExit(2)
    from apeCAD.agent.mcp import main as serve

    serve(argv)


if __name__ == "__main__":
    main()
