"""Shared colour tokens for every generated profile asset.

One palette, two themes. Generators emit these as CSS custom properties inside
each SVG, so a single committed file renders correctly in both GitHub themes
without a duplicate `<picture>` source.

Two rules this palette encodes, and which every asset must keep:

* ``accent`` is GitHub's own contribution green, so the calendar belongs to the
  page natively instead of sitting on it as a foreign object.
* ``warn`` is amber and means *risk*. It is never emphasis and never decoration.
  It currently appears on exactly one mark: the shared-assumption edge in the
  hero graph.

Text colours are paired: anything drawn on ``paper`` takes ``ink`` or ``dim``;
anything drawn on ``bg`` takes ``text`` or ``muted``. Mixing the pairs is the
usual cause of an asset that reads correctly in one theme and not the other.
"""

# Keys consumed by the contribution calendar. Kept under their original names so
# the chart renderer and its tests are untouched by the wider palette.
CHART_KEYS = ("bg", "border", "text", "muted", "accent")

# Keys consumed by the hero graph, the journey profile, and the section glyphs.
FIGURE_KEYS = ("paper", "ink", "dim", "rule", "rule_soft", "line", "node", "grid", "accent", "warn")

THEMES = {
    "light": {
        # chart
        "bg": "#ffffff", "border": "#d1d9e0", "text": "#1f2328", "muted": "#59636e",
        "accent": "#1a7f37",
        "cells": ("#eff2f5", "#9be9a8", "#40c463", "#30a14e", "#216e39"),
        # figures
        "paper": "#ffffff", "ink": "#14181d", "dim": "#6a737f",
        "rule": "#dde1e7", "rule_soft": "#eef0f3", "line": "#9aa4b0",
        "node": "#ffffff", "grid": "#eef1f5", "warn": "#9a6700",
    },
    "dark": {
        # chart
        "bg": "#0d1117", "border": "#30363d", "text": "#f0f3f6", "muted": "#a2aab5",
        "accent": "#3fb950",
        "cells": ("#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"),
        # figures
        "paper": "#0d1117", "ink": "#e9edf2", "dim": "#8b95a2",
        "rule": "#2a313a", "rule_soft": "#20262e", "line": "#56636f",
        "node": "#151b23", "grid": "#171e26", "warn": "#d29922",
    },
}

# Embedded SVGs cannot fetch a webfont, so every asset draws with stacks that
# ship on the reader's machine. Changing these to a hosted family silently falls
# back to a default and misaligns any hand-placed text.
SANS = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
SERIF = "Iowan Old Style,Palatino Linotype,Palatino,Georgia,serif"

# Motion is opt-out, not opt-in: every animated asset wraps its keyframes in this
# guard so a reader who has asked their system to reduce motion sees a still image.
REDUCED_MOTION = "@media(prefers-reduced-motion:reduce){*{animation:none!important}}"


def declarations(theme, keys):
    """Return ``--key:value`` declarations for *keys* in *theme*, semicolon joined."""
    values = THEMES[theme]
    return ";".join(f"--{key.replace('_', '-')}:{values[key]}" for key in keys)


def theme_css(keys, cells=False):
    """Return a full SVG ``<style>`` body that themes *keys* for light and dark.

    Light is declared on the bare selector so it is the fallback wherever
    ``prefers-color-scheme`` is unsupported or unset; dark overrides only the
    custom properties, never the rules that consume them.
    """
    def block(theme):
        body = declarations(theme, keys)
        if cells:
            ramp = ";".join(f"--cell{i}:{c}" for i, c in enumerate(THEMES[theme]["cells"]))
            body = f"{body};{ramp}"
        return body

    return (f"svg{{{block('light')}}}"
            f"@media(prefers-color-scheme:dark){{svg{{{block('dark')}}}}}")
