#!/usr/bin/env python3
"""Write the palette stylesheets of the four Catppuccin flavours and of the
themes derived from core/themes.py PALETTES (static/css/themes/).

Each theme is two files: its palette, written here, and the shared rules in
static/css/themes/catppuccin.css, written by hand. The rules only ever read
--ctp-* variables, so the themes cannot drift apart.

Usage:  python tools/build_catppuccin_themes.py           # write the files
        python tools/build_catppuccin_themes.py --check   # exit 1 if stale

tests/unit/test_themes.py runs the check, so a hand edit to a generated file
fails the suite instead of being overwritten later.

The palette is @catppuccin/palette 1.8.0 (https://catppuccin.com/palette),
copied below so this script needs no network. Role choices follow the
Catppuccin style guide: links blue, success green, warnings yellow, errors
red, information teal, text on an accent fill is base. Bootstrap's
"primary" has no guide entry; it is mauve, the usual Catppuccin accent.
Inline code is pink, as in Catppuccin's editor themes.

One deviation, Latte only: green, teal, yellow, blue and pink are too light to read
on Latte's near-white base (as low as 2.3:1). Each role colour is darkened
(HLS lightness, hue kept) until it reaches 4.5:1 on base, mantle and crust --
the page, cards and headers. Against base, "accent text on the page" and
"base text on an accent fill" are the same ratio, so one shade serves both.
The dark flavours' roles pass as they are. Alert text (role text on the role
washed 15% into base) and .text-muted are checked the same way, and moved
where they fall short.
"""

import colorsys
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "static", "css", "themes")
if ROOT not in sys.path:  # run as a script
    sys.path.insert(0, ROOT)
from core import themes  # noqa: E402

PALETTE = {
    "latte": {
        "rosewater": "#dc8a78", "flamingo": "#dd7878", "pink": "#ea76cb", "mauve": "#8839ef", "red": "#d20f39",
        "maroon": "#e64553", "peach": "#fe640b", "yellow": "#df8e1d", "green": "#40a02b", "teal": "#179299",
        "sky": "#04a5e5", "sapphire": "#209fb5", "blue": "#1e66f5", "lavender": "#7287fd", "text": "#4c4f69",
        "subtext1": "#5c5f77", "subtext0": "#6c6f85", "overlay2": "#7c7f93", "overlay1": "#8c8fa1", "overlay0": "#9ca0b0",
        "surface2": "#acb0be", "surface1": "#bcc0cc", "surface0": "#ccd0da", "base": "#eff1f5", "mantle": "#e6e9ef",
        "crust": "#dce0e8",
    },
    "frappe": {
        "rosewater": "#f2d5cf", "flamingo": "#eebebe", "pink": "#f4b8e4", "mauve": "#ca9ee6", "red": "#e78284",
        "maroon": "#ea999c", "peach": "#ef9f76", "yellow": "#e5c890", "green": "#a6d189", "teal": "#81c8be",
        "sky": "#99d1db", "sapphire": "#85c1dc", "blue": "#8caaee", "lavender": "#babbf1", "text": "#c6d0f5",
        "subtext1": "#b5bfe2", "subtext0": "#a5adce", "overlay2": "#949cbb", "overlay1": "#838ba7", "overlay0": "#737994",
        "surface2": "#626880", "surface1": "#51576d", "surface0": "#414559", "base": "#303446", "mantle": "#292c3c",
        "crust": "#232634",
    },
    "macchiato": {
        "rosewater": "#f4dbd6", "flamingo": "#f0c6c6", "pink": "#f5bde6", "mauve": "#c6a0f6", "red": "#ed8796",
        "maroon": "#ee99a0", "peach": "#f5a97f", "yellow": "#eed49f", "green": "#a6da95", "teal": "#8bd5ca",
        "sky": "#91d7e3", "sapphire": "#7dc4e4", "blue": "#8aadf4", "lavender": "#b7bdf8", "text": "#cad3f5",
        "subtext1": "#b8c0e0", "subtext0": "#a5adcb", "overlay2": "#939ab7", "overlay1": "#8087a2", "overlay0": "#6e738d",
        "surface2": "#5b6078", "surface1": "#494d64", "surface0": "#363a4f", "base": "#24273a", "mantle": "#1e2030",
        "crust": "#181926",
    },
    "mocha": {
        "rosewater": "#f5e0dc", "flamingo": "#f2cdcd", "pink": "#f5c2e7", "mauve": "#cba6f7", "red": "#f38ba8",
        "maroon": "#eba0ac", "peach": "#fab387", "yellow": "#f9e2af", "green": "#a6e3a1", "teal": "#94e2d5",
        "sky": "#89dceb", "sapphire": "#74c7ec", "blue": "#89b4fa", "lavender": "#b4befe", "text": "#cdd6f4",
        "subtext1": "#bac2de", "subtext0": "#a6adc8", "overlay2": "#9399b2", "overlay1": "#7f849c", "overlay0": "#6c7086",
        "surface2": "#585b70", "surface1": "#45475a", "surface0": "#313244", "base": "#1e1e2e", "mantle": "#181825",
        "crust": "#11111b",
    },
}

NAMES = {"latte": "Latte", "frappe": "Frappé", "macchiato": "Macchiato", "mocha": "Mocha"}
DARK = {"latte": False, "frappe": True, "macchiato": True, "mocha": True}

# Bootstrap role -> palette colour (style guide, see module docstring).
ROLES = {
    "primary": "mauve",
    "success": "green",
    "info": "teal",
    "warning": "yellow",
    "danger": "red",
    "link": "blue",
    "link-hover": "sky",
    "code": "pink",
}
# Roles that have an .alert-x / subtle background in Bootstrap.
ALERT_ROLES = ("primary", "success", "info", "warning", "danger")
MIN_CONTRAST = 4.5


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(hex_color):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG 2 contrast ratio between two hex colours."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _shift(hex_color, delta):
    """``hex_color`` with its HLS lightness moved by ``delta``; hue and
    saturation kept, so a deepened yellow is still amber, not brown."""
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in _rgb(hex_color)))
    r, g, b = colorsys.hls_to_rgb(h, min(1.0, max(0.0, l + delta)), s)
    return "#" + "".join(f"{round(c * 255):02x}" for c in (r, g, b))


def mix(a, b, share_of_a):
    """sRGB mix, as CSS ``color-mix(in srgb, a share%, b)`` computes it."""
    return "#" + "".join(
        f"{round(x * share_of_a + y * (1 - share_of_a)):02x}"
        for x, y in zip(_rgb(a), _rgb(b))
    )


def backgrounds(palette):
    """The surfaces text sits on: page, panes (cards, modals) and headers."""
    return [palette[n] for n in ("base", "mantle", "crust")]


def readable(value, against, step_sign):
    """``value``, moved in lightness until it reaches MIN_CONTRAST on every
    colour in ``against``. Raises if it cannot: a silent failing colour is
    worse than a build error."""
    original = value
    for step in range(0, 201):
        value = _shift(original, step_sign * step / 200)
        if min(contrast(value, bg) for bg in against) >= MIN_CONTRAST:
            return value
    raise ValueError(f"{original} cannot reach {MIN_CONTRAST}:1 on {against}")


def role_colour(palette, colour, dark):
    """``colour`` as is, or darkened (Latte) until it reads on every surface."""
    return readable(palette[colour], backgrounds(palette), +1 if dark else -1)


# Alerts and subtle badges draw the role's text on the role washed into base.
SUBTLE_SHARE = 0.15


def emphasis_colour(palette, role_value, dark):
    """Text for the role's subtle background, moved away from it until it
    reads: lighter on a dark flavour, darker on Latte."""
    subtle = mix(role_value, palette["base"], SUBTLE_SHARE)
    return readable(role_value, [subtle], +1 if dark else -1)


def muted_colour(palette):
    """.text-muted: the first of subtext0/subtext1/text that reads on every
    surface (Latte's subtext0 is 3.7:1 on crust)."""
    for name in ("subtext0", "subtext1", "text"):
        if min(contrast(palette[name], bg) for bg in backgrounds(palette)) >= MIN_CONTRAST:
            return name
    return "text"


# Neutral buttons (secondary, light): hover and active move the fill toward
# base, away from the text on it, so a state never reads worse than the
# button at rest. catppuccin.css writes these shares into its color-mix().
NEUTRAL_HOVER_SHARE = 0.8
NEUTRAL_ACTIVE_SHARE = 0.6


def secondary_fill(palette):
    """Secondary fills carry text, not base: the darkest surface that still
    holds text at MIN_CONTRAST."""
    return next(
        s for s in ("surface1", "surface0")
        if contrast(palette["text"], palette[s]) >= MIN_CONTRAST
    )


def raised(dark):
    """A "light" panel (.bg-light, bg-body-secondary): a raised surface on a
    dark flavour; on Latte surface0 is a heavy grey, so crust instead."""
    return "surface0" if dark else "crust"


def on_dark(dark):
    """Light text for surfaces that are dark on every theme (the reader's
    chrome, the bulk-action bars): .text-light, .btn-outline-light. A dark
    flavour's text already is light; Latte's is dark, so its base."""
    return "text" if dark else "base"


def dark_fill(dark):
    """A fill that is dark on every theme (--bs-dark, .bg-dark), carrying
    white or on_dark text. Latte's crust is a light grey, so its text."""
    return "crust" if dark else "text"


def year_in_review_colours(flavour):
    """The flavour's entry in wrapped.THEME_COLORS, from the same choices as
    its stylesheet, so the two cannot drift."""
    p, dark = PALETTE[flavour], DARK[flavour]
    return {
        "primary": role_colour(p, ROLES["primary"], dark),
        "secondary": p[secondary_fill(p)],
        "success": role_colour(p, ROLES["success"], dark),
        "info": role_colour(p, ROLES["info"], dark),
        "warning": role_colour(p, ROLES["warning"], dark),
        "danger": role_colour(p, ROLES["danger"], dark),
        "bg": p["base"],
        "bg_secondary": p[raised(dark)],
        "text": p["text"],
        "text_muted": p[muted_colour(p)],
        "is_dark": dark,
    }


def _svg_url(svg):
    # Percent-encoded the way Bootstrap writes its own icons.
    encoded = (svg.replace("%", "%25").replace("#", "%23").replace("<", "%3c")
               .replace(">", "%3e").replace('"', "'"))
    return 'url("data:image/svg+xml,' + encoded + '")'


_CLOSE_PATH = ("M.293.293a1 1 0 0 1 1.414 0L8 6.586 14.293.293a1 1 0 1 1 1.414 1.414L9.414 "
               "8l6.293 6.293a1 1 0 0 1-1.414 1.414L8 9.414l-6.293 6.293a1 1 0 0 1-1.414-1.414L6.586 "
               "8 .293 1.707a1 1 0 0 1 0-1.414")


def _icons(on_fill, on_primary, text, focus, nav_text):
    """The SVG variables: icons drawn in a colour CSS cannot pass into a
    data: URL. ``on_fill`` is the text on a role fill, ``on_primary`` the
    text on the primary fill (form marks sit on it), ``nav_text`` the
    navbar's."""
    def close(colour):
        return _svg_url("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' "
                        f"fill='{colour}'><path d='{_CLOSE_PATH}'/></svg>")
    return [
        # The close X on an accent fill, drawn in that fill's text colour.
        "    --ctp-close-on-fill: " + close(on_fill) + ";",
        "    --ctp-close-on-primary: " + close(on_primary) + ";",
        "    --ctp-select-chevron: " + _svg_url(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><path fill='none' "
            f"stroke='{text}' stroke-linecap='round' stroke-linejoin='round' "
            "stroke-width='2' d='m2 5 6 6 6-6'/></svg>") + ";",
        "    --ctp-switch-focus: " + _svg_url(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='-4 -4 8 8'>"
            f"<circle r='3' fill='{focus}'/></svg>") + ";",
        # Form check marks, drawn like any text on the primary fill.
        "    --ctp-check-mark: " + _svg_url(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20'><path fill='none' "
            f"stroke='{on_primary}' stroke-linecap='round' stroke-linejoin='round' "
            "stroke-width='3' d='m6 10 3 3 6-6'/></svg>") + ";",
        "    --ctp-check-indeterminate: " + _svg_url(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20'><path fill='none' "
            f"stroke='{on_primary}' stroke-linecap='round' stroke-linejoin='round' "
            "stroke-width='3' d='M6 10h8'/></svg>") + ";",
        "    --ctp-radio-dot: " + _svg_url(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='-4 -4 8 8'>"
            f"<circle r='2' fill='{on_primary}'/></svg>") + ";",
        "    --ctp-switch-on: " + _svg_url(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='-4 -4 8 8'>"
            f"<circle r='3' fill='{on_primary}'/></svg>") + ";",
        "    --ctp-toggler-icon: " + _svg_url(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 30 30'><path "
            f"stroke='{nav_text}' stroke-linecap='round' stroke-miterlimit='10' "
            "stroke-width='2' d='M4 7h22M4 15h22M4 23h22'/></svg>") + ";",
    ]


def _var(name, value, note=""):
    r, g, b = _rgb(value)
    return f"    --ctp-{name}: {value}; --ctp-{name}-rgb: {r}, {g}, {b};{note}"


def render(flavour):
    p = PALETTE[flavour]
    dark = DARK[flavour]
    lines = [
        f"/* Catppuccin {NAMES[flavour]}: palette for static/css/themes/catppuccin.css.",
        " * GENERATED by tools/build_catppuccin_themes.py -- edit that, not this. */",
        "",
        ":root {",
        f"    color-scheme: {'dark' if dark else 'light'};",
        "",
    ]
    for name, value in p.items():
        lines.append(_var(name, value))

    lines += ["", "    /* Bootstrap roles. */"]
    for role, colour in ROLES.items():
        value = role_colour(p, colour, dark)
        note = "" if value == p[colour] else f"  /* {colour}, deepened to read on every surface */"
        lines.append(_var(role, value, note))
        if role in ALERT_ROLES:
            lines.append(f"    --ctp-{role}-emphasis: {emphasis_colour(p, value, dark)};")
    lines.append(f"    --ctp-muted: var(--ctp-{muted_colour(p)});")
    lines.append(_var("secondary", p[secondary_fill(p)]))
    # Catppuccin's primary is a pastel carrying base, like every other role.
    lines.append("    --ctp-primary-text: var(--ctp-primary); --ctp-primary-text-rgb: var(--ctp-primary-rgb);")
    lines.append("    --ctp-on-primary: var(--ctp-base);")

    lines += [
        "",
        "    /* What differs between the light flavour and the dark ones. */",
        # .text-white is white text for a dark fill. On a dark flavour the page
        # itself is that fill; on Latte it stays white (cover overlays etc.).
        f"    --ctp-white-text: {'var(--ctp-text)' if dark else '#ffffff'};",
        # Bootstrap sets color-scheme: dark on every [data-bs-theme=dark],
        # which includes Latte's header.
        f"    --ctp-color-scheme: {'dark' if dark else 'light'};",
        f"    --ctp-raised: var(--ctp-{raised(dark)}); "
        f"--ctp-raised-rgb: var(--ctp-{raised(dark)}-rgb);",
        f"    --ctp-on-dark: var(--ctp-{on_dark(dark)}); "
        f"--ctp-on-dark-rgb: var(--ctp-{on_dark(dark)}-rgb);",
        f"    --ctp-dark-fill: var(--ctp-{dark_fill(dark)}); "
        f"--ctp-dark-fill-rgb: var(--ctp-{dark_fill(dark)}-rgb);",
        # The header: a crust bar with text, as in the Catppuccin ports.
        "    --ctp-nav-bg: var(--ctp-crust); --ctp-nav-text: var(--ctp-text);",
        "    --ctp-nav-muted: var(--ctp-subtext1); --ctp-nav-rule: 1px solid var(--ctp-surface0);",
    ]
    lines += _icons(p["base"], p["base"], p["text"], p["lavender"], p["text"])
    lines += ["}", ""]
    return "\n".join(lines)


# ── The themes derived from a design palette (core.themes.PALETTES) ────────
# The palette has ten colours; the rules read Catppuccin's names. Surfaces are
# mixed from page, raised and rule, each backed off until body text reads on
# it; role colours are the palette's, moved only where one falls short on a
# surface the palette does not name (cards, headers). Primary is a fill that
# carries white text, so it gets a separate text side, the same hue stepped
# toward the ink until it reads.
WARNING_SEED = {True: "#e0af68", False: "#8a5a00"}

# Comic texture and line, read by comic.css (and comic-ink.css, for the themes
# with a frame). Noir's is all palette.
COMIC = {
    "newsprint": {
        "paper": "radial-gradient(rgb(60 45 20 / 0.09) 0.6px, transparent 0.9px)", "paper-size": "5px 5px",
        "title": "none", "panel": "var(--ctp-surface0)",
    },
    "pop-art": {
        "paper": "radial-gradient(rgb(215 0 26 / 0.09) 1.1px, transparent 1.4px)", "paper-size": "7px 7px",
        "tone": "none", "tone-size": "auto", "frame": "2px solid var(--ctp-text)",
        "shadow": "3px 3px 0 var(--ctp-text)", "title": "none",
        "panel": "var(--ctp-text)", "corner": "2px",
    },
    "manga": {
        "paper": "none", "paper-size": "auto",
        "tone": "radial-gradient(rgb(0 0 0 / 0.14) 0.7px, transparent 1px)", "tone-size": "4px 4px",
        "frame": "1.5px solid var(--ctp-text)", "shadow": "none",
        "title": "repeating-conic-gradient(from 0deg at 92% 60%, rgb(0 0 0 / 0.06) 0 1.5deg, "
                 "transparent 1.5deg 6deg)",
        "panel": "var(--ctp-text)", "corner": "2px",
    },
}
NAV_RULE = {"noir": "2px solid var(--ctp-primary)", "pop-art": "3px solid var(--ctp-text)"}


def _surface(start, end, share, ink):
    """``start`` moved up to ``share`` of the way to ``end``, less where body
    text would no longer read on it."""
    for step in range(round(share * 100), -1, -5):
        value = themes.toward(start, end, step / 100)
        if contrast(ink, value) >= MIN_CONTRAST:
            return value
    return start


def derive(theme_id):
    """{name: hex} in Catppuccin's vocabulary for a design palette."""
    pal = themes.PALETTES[theme_id]
    dark = themes.is_dark_theme(theme_id)
    ink = pal["ink"]
    # Pop Art and Manga rule in ink; their surfaces are a grey of it (comic.css
    # draws the inked lines).
    rule = (pal["rule"] if contrast(ink, pal["rule"]) >= MIN_CONTRAST
            else themes.toward(pal["raised"], pal["rule"], 0.15))
    crust = (themes.toward(pal["page"], "#000000", 0.25) if dark
             else _surface(pal["raised"], rule, 0.25, ink))
    p = {"base": pal["page"], "mantle": pal["raised"], "crust": crust, "text": ink}
    p["surface0"] = _surface(pal["raised"], rule, 0.5, ink)
    p["surface1"] = _surface(pal["raised"], rule, 1.0, ink)
    p["surface2"] = themes.toward(p["surface1"], ink, 0.2)
    sign = +1 if dark else -1
    surfaces = backgrounds(p)
    p["muted"] = readable(pal["muted"], surfaces, sign)
    p["lavender"] = readable(pal["link"], surfaces, sign)
    p["primary"] = pal["primary"]
    p["primary-text"] = readable(
        themes.accent_text_side(pal["primary"], pal["page"], pal["emphasis"]), surfaces, sign)
    p["link"] = p["lavender"]
    p["link-hover"] = readable(themes.toward(p["link"], pal["emphasis"], 0.3), surfaces, sign)
    p["success"] = readable(pal["success"], surfaces, sign)
    p["danger"] = readable(pal["error"], surfaces, sign)
    # Noir has one red: its information colour is a grey.
    p["info"] = p["muted"] if theme_id == "noir" else p["link"]
    p["warning"] = readable(WARNING_SEED[dark], surfaces, sign)
    p["secondary"] = p[secondary_fill(p)]
    p["nav"] = pal.get("nav", pal["primary"])
    return p


def render_derived(theme_id):
    p = derive(theme_id)
    dark = themes.is_dark_theme(theme_id)
    lines = [
        f"/* {themes.DERIVED_THEMES[theme_id]}: palette for static/css/themes/catppuccin.css.",
        " * GENERATED by tools/build_catppuccin_themes.py from core/themes.py PALETTES --",
        " * edit those, not this. */",
        "",
        ":root {",
        f"    color-scheme: {'dark' if dark else 'light'};",
        "",
    ]
    for name in ("base", "mantle", "crust", "text", "surface0", "surface1", "surface2", "lavender"):
        lines.append(_var(name, p[name]))
    # One muted colour serves every label and placeholder.
    for name in ("subtext0", "subtext1", "overlay0", "overlay1", "overlay2"):
        lines.append(_var(name, p["muted"]))

    lines += ["", "    /* Bootstrap roles. */"]
    for role in ("primary", "success", "info", "warning", "danger", "link", "link-hover"):
        lines.append(_var(role, p[role]))
        if role in ALERT_ROLES:
            text_side = p["primary-text"] if role == "primary" else p[role]
            lines.append(f"    --ctp-{role}-emphasis: {emphasis_colour(p, text_side, dark)};")
    lines.append(_var("primary-text", p["primary-text"]))
    lines.append("    --ctp-on-primary: #ffffff;")
    lines.append("    --ctp-code: var(--ctp-primary-text);")
    lines.append("    --ctp-muted: var(--ctp-subtext0);")
    lines.append(_var("secondary", p["secondary"]))

    lines += [
        "",
        f"    --ctp-white-text: {'var(--ctp-text)' if dark else '#ffffff'};",
        f"    --ctp-color-scheme: {'dark' if dark else 'light'};",
        "    --ctp-raised: var(--ctp-mantle); --ctp-raised-rgb: var(--ctp-mantle-rgb);",
        f"    --ctp-on-dark: var(--ctp-{'text' if dark else 'base'}); "
        f"--ctp-on-dark-rgb: var(--ctp-{'text' if dark else 'base'}-rgb);",
        f"    --ctp-dark-fill: var(--ctp-{'crust' if dark else 'text'}); "
        f"--ctp-dark-fill-rgb: var(--ctp-{'crust' if dark else 'text'}-rgb);",
        # The header is the primary fill (Noir: black) with white text.
        f"    --ctp-nav-bg: {p['nav']}; --ctp-nav-text: #ffffff;",
        "    --ctp-nav-muted: rgba(255, 255, 255, 0.85); "
        f"--ctp-nav-rule: {NAV_RULE.get(theme_id, 'none')};",
    ]
    lines += _icons(p["base"], "#ffffff", p["text"], p["lavender"], "#ffffff")
    if theme_id in COMIC:
        lines += ["", "    /* Texture and line, for comic.css. */"]
        lines += [f"    --comic-{name}: {value};" for name, value in COMIC[theme_id].items()]
    lines += ["}", ""]
    return "\n".join(lines)


def outputs():
    out = {
        os.path.join(OUT_DIR, f"catppuccin-{flavour}.css"): render(flavour)
        for flavour in PALETTE
    }
    out.update({
        os.path.join(OUT_DIR, f"{theme_id}.css"): render_derived(theme_id)
        for theme_id in themes.DERIVED_THEMES
    })
    return out


def main(argv):
    check = "--check" in argv
    stale = []
    for path, text in outputs().items():
        current = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if current == text:
            continue
        if check:
            stale.append(os.path.relpath(path, ROOT))
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            print("wrote", os.path.relpath(path, ROOT))
    if stale:
        print("stale, run tools/build_catppuccin_themes.py:", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
