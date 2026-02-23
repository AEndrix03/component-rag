"""Feature classes that expose the MCP server command."""

from __future__ import annotations

from argparse import ArgumentParser
from typing import Sequence

from cpm_core.api import CPMAbstractCommand, cpmcommand

from .server import run_server


@cpmcommand(name="serve")
class MCPServeCommand(CPMAbstractCommand):
    """Start the Model Context Protocol (MCP) server for CPM packets."""

    @classmethod
    def configure(cls, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--cpm-dir",
            default=None,
            help="Override CPM_ROOT for this process only.",
        )
        parser.add_argument(
            "--registry",
            default=None,
            help="Override REGISTRY for this process only.",
        )
        parser.add_argument(
            "--embed-url",
            default=None,
            help="Embedding server URL to expose to MCP clients.",
        )
        parser.add_argument(
            "--embed-model",
            default=None,
            help="Embedding model to use for query-time vectors.",
        )

    def run(self, argv: Sequence[str]) -> int:
        cpm_dir = getattr(argv, "cpm_dir", None)
        registry = getattr(argv, "registry", None)
        embed_url = getattr(argv, "embed_url", None)
        embed_model = getattr(argv, "embed_model", None)
        run_server(cpm_root=cpm_dir, registry=registry, embedding_url=embed_url, embedding_model=embed_model)
        return 0
