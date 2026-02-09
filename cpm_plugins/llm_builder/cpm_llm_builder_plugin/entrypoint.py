"""Entrypoint for the CPM LLM builder plugin."""

from __future__ import annotations

from . import features


class LLMBuilderEntrypoint:
    """Initialize plugin state and register features."""

    def init(self, ctx) -> None:
        self.context = ctx
        features.set_plugin_root(ctx.plugin_root)
        _ = features.CPMLLMBuilder

