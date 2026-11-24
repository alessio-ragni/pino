"""The screen. Claude says what to show, the tablet draws it with Google's A2UI renderer.

Everything that reaches the tablet is A2UI (the open protocol for agent-generated
interfaces), drawn on Android by the official `androidx.a2ui` Compose renderer.
What changes from v1 is how Claude gets there:

* **Cards.** Each topic is a card (a recipe, the shopping list, tomorrow's
  events). A card is one A2UI surface, plus a title and a short thread of
  answers that the tablet draws around it. Claude updates the card it is
  already on instead of opening a new one.
* **Templates.** Writing a full A2UI tree token by token is slow, and a small
  model gets it wrong. For the common cases Claude passes plain data
  (`show_events`, `show_recipe`, `show_list`, `show_table`) and the server
  builds the A2UI. `show` stays for anything else, with a flat component list.
* **Checked against the catalog.** Component names and properties are checked
  against the basic catalog the renderer knows. A mistake comes back to Claude
  as the tool's error, so it can fix it, instead of an empty card.

The protocol version is `PINO_A2UI_VERSION`: `v0.9.1` by default, the one the
Android renderer reads.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Protocol

MESSAGE_KEYS = ("createSurface", "updateComponents", "updateDataModel", "deleteSurface")

CATALOGS = {
    "v0.9.1": "https://a2ui.org/specification/v0_9_1/catalogs/basic/catalog.json",
    "1.0": "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json",
}

# The basic catalog as the Android renderer (material3-a2ui 1.0.0-alpha02) reads it.
COMMON = {"id", "component", "weight", "accessibility"}
CATALOG: dict[str, set[str]] = {
    "Text": {"text", "variant"},
    "Image": {"url", "description", "fit", "variant"},
    "Icon": {"name"},
    "Row": {"children", "align", "justify"},
    "Column": {"children", "align", "justify"},
    "List": {"children", "direction", "align"},
    "Card": {"child"},
    "Tabs": {"tabs"},
    "Divider": {"axis"},
    "Button": {"child", "action", "variant", "checks"},
    "CheckBox": {"label", "value", "checks"},
    "TextField": {"label", "value", "variant", "validationRegexp", "checks"},
    "ChoicePicker": {"label", "options", "value", "variant", "displayStyle", "checks"},
    "DateTimeInput": {"label", "value", "enableDate", "enableTime", "min", "max", "checks"},
    "Slider": {"label", "value", "min", "max", "checks"},
    "Modal": {"trigger", "content"},
    "Video": {"url"},
    "AudioPlayer": {"url", "description"},
}
ENUMS = {
    ("Text", "variant"): {"h1", "h2", "h3", "h4", "h5", "caption", "body"},
    ("Button", "variant"): {"default", "primary", "borderless"},
    ("List", "direction"): {"vertical", "horizontal"},
    ("Divider", "axis"): {"horizontal", "vertical"},
    ("Image", "fit"): {"contain", "cover", "fill", "none", "scaleDown"},
    ("Image", "variant"): {"icon", "avatar", "smallFeature", "mediumFeature", "largeFeature", "header"},
}
CHILD_LISTS = {"Row", "Column", "List"}
CHILD_ONE = {"Card": "child", "Button": "child"}

CONFIRM_SURFACE = "conferma"

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


class Invalid(ValueError):
    pass


def card_id(raw: Any) -> str:
    cid = str(raw or "").strip().lower().replace(" ", "-")
    if not _ID.match(cid) or cid == CONFIRM_SURFACE:
        raise Invalid(f"card_id {raw!r}: use a short lowercase id like 'recipe' or 'tomorrow'")
    return cid


def check(messages: Any, version: str) -> list[dict]:
    """Messages ready to send, with the version and catalog filled in. Raises `Invalid`."""
    if isinstance(messages, str):
        try:
            messages = json.loads(messages)
        except json.JSONDecodeError as bad:
            raise Invalid(f"not valid JSON: {bad}") from bad
    if isinstance(messages, dict):
        messages = [messages]
    if not isinstance(messages, list) or not messages:
        raise Invalid("needs a non-empty list of A2UI messages")

    out: list[dict] = []
    for i, msg in enumerate(messages):
        where = f"message {i + 1}"
        if not isinstance(msg, dict):
            raise Invalid(f"{where}: must be an object")
        keys = [k for k in MESSAGE_KEYS if k in msg]
        if len(keys) != 1:
            raise Invalid(f"{where}: needs exactly one key among {', '.join(MESSAGE_KEYS)}")
        body = msg[keys[0]]
        if not isinstance(body, dict) or not body.get("surfaceId"):
            raise Invalid(f"{where}: missing surfaceId")
        if keys[0] == "createSurface" and not body.get("catalogId"):
            body["catalogId"] = CATALOGS.get(version, CATALOGS["v0.9.1"])
        if keys[0] == "updateComponents":
            comps = body.get("components")
            if not isinstance(comps, list) or not comps:
                raise Invalid(f"{where}: components must be a non-empty list")
            for c in comps:
                if not isinstance(c, dict) or not c.get("id") or not c.get("component"):
                    raise Invalid(f"{where}: every component needs id and component")
        out.append({"version": version, keys[0]: body})
    return out


def validate(components: Any) -> list[dict]:
    """A flat component list checked against the catalog: names, properties, enums, references."""
    if not isinstance(components, list) or not components:
        raise Invalid("components must be a non-empty flat list")
    ids: set[str] = set()
    for c in components:
        if not isinstance(c, dict) or not c.get("id") or not c.get("component"):
            raise Invalid("every component needs 'id' and 'component'")
        if c["id"] in ids:
            raise Invalid(f"duplicate id {c['id']!r}")
        ids.add(c["id"])
    if "root" not in ids:
        raise Invalid("one component must have id 'root'")
    for c in components:
        name = c["component"]
        if name not in CATALOG:
            raise Invalid(f"{c['id']}: unknown component {name!r}; available: {', '.join(CATALOG)}")
        extra = set(c) - COMMON - CATALOG[name]
        if extra:
            raise Invalid(
                f"{c['id']}: {name} has no {', '.join(sorted(extra))}; it takes {', '.join(sorted(CATALOG[name]))}"
            )
        weight = c.get("weight")
        if weight is not None and (not isinstance(weight, (int, float)) or weight <= 0):
            # The Android renderer crashes the whole app on a zero weight: never let one through.
            raise Invalid(f"{c['id']}: weight must be a number greater than zero")
        for (comp, prop), allowed in ENUMS.items():
            if comp == name and prop in c and isinstance(c[prop], str) and c[prop] not in allowed:
                raise Invalid(f"{c['id']}: {prop} must be one of {', '.join(sorted(allowed))}")
        refs: list[str] = []
        if name in CHILD_LISTS:
            kids = c.get("children", [])
            if isinstance(kids, list):
                refs = kids
            elif not isinstance(kids, dict):
                raise Invalid(f"{c['id']}: children must be a list of ids")
        if name in CHILD_ONE and c.get(CHILD_ONE[name]):
            refs = [c[CHILD_ONE[name]]]
        if name == "Tabs":
            refs = [t.get("child") for t in c.get("tabs", []) if isinstance(t, dict)]
        for ref in refs:
            if isinstance(ref, str) and ref not in ids:
                raise Invalid(f"{c['id']}: refers to {ref!r}, which is not in the list")
    return components


# ── templates: plain data in, A2UI out ────────────────────────────────────

WORDS = {
    "it": {
        "ingredients": "Ingredienti",
        "for": "per",
        "now": "Adesso",
        "step": "Passo",
        "of": "di",
        "empty_list": "La lista è vuota.",
        "no_events": "Niente in programma.",
        "items": "cose",
    },
    "en": {
        "ingredients": "Ingredients",
        "for": "serves",
        "now": "Now",
        "step": "Step",
        "of": "of",
        "empty_list": "The list is empty.",
        "no_events": "Nothing planned.",
        "items": "items",
    },
}


class _Tree:
    """Builds a flat component list with unique ids."""

    def __init__(self) -> None:
        self.items: list[dict] = []
        self._n = 0

    def add(self, component: str, cid: str | None = None, **props: Any) -> str:
        self._n += 1
        cid = cid or f"c{self._n}"
        self.items.append({"id": cid, "component": component, **props})
        return cid

    def text(self, text: str, variant: str = "body") -> str:
        return self.add("Text", text=str(text), variant=variant)


def _t(lang: str) -> dict[str, str]:
    return WORDS.get(lang, WORDS["it"])


def events_tree(events: list[dict], lang: str = "it") -> list[dict]:
    """[{day?, time, title, place?, note?}] → one row per event, a heading per day."""
    t = _Tree()
    rows: list[str] = []
    day = None
    if not events:
        rows.append(t.text(_t(lang)["no_events"]))
    for e in events:
        if e.get("day") and e.get("day") != day:
            day = e["day"]
            rows.append(t.text(day, "h4"))
        right = [t.text(e.get("title", ""), "h5")]
        detail = " · ".join(x for x in (e.get("place"), e.get("note")) if x)
        if detail:
            right.append(t.text(detail, "caption"))
        col = t.add("Column", children=right, weight=1)
        time = t.add("Text", text=e.get("time") or "—", variant="h5")
        rows.append(t.add("Row", children=[time, col], align="center"))
        rows.append(t.add("Divider"))
    if rows and t.items[-1]["component"] == "Divider":
        rows.pop()
    t.add("Column", "root", children=rows)
    return t.items


def recipe_tree(
    ingredients: list[Any],
    sections: list[dict],
    servings: str | int | None = None,
    current_step: int | None = None,
    lang: str = "it",
) -> list[dict]:
    """The step you are on first and large, then ingredients in two columns, then every phase."""
    w = _t(lang)
    t = _Tree()
    root: list[str] = []
    steps = [(s.get("name", ""), step) for s in sections for step in s.get("steps", [])]
    total = len(steps)
    if current_step and 1 <= current_step <= total:
        phase, step = steps[current_step - 1]
        label = f"{w['now']} · {w['step']} {current_step} {w['of']} {total}" + (f" · {phase}" if phase else "")
        inner = t.add("Column", children=[t.text(label, "caption"), t.text(step, "h3")])
        root.append(t.add("Card", child=inner))

    head = w["ingredients"] + (f" · {w['for']} {servings}" if servings else "")
    root.append(t.text(head, "h4"))
    lines = []
    for ing in ingredients:
        if isinstance(ing, dict):
            lines.append(" ".join(str(x) for x in (ing.get("qty"), ing.get("name")) if x))
        else:
            lines.append(str(ing))
    half = (len(lines) + 1) // 2
    cols = []
    for part in (lines[:half], lines[half:]):
        if part:
            cols.append(t.add("Column", children=[t.text("• " + line) for line in part], weight=1))
    if cols:
        root.append(t.add("Row", children=cols))

    n = 0
    for section in sections:
        root.append(t.add("Divider"))
        if section.get("name"):
            root.append(t.text(section["name"], "h4"))
        for step in section.get("steps", []):
            n += 1
            mark = "✓ " if current_step and n < current_step else ""
            variant = "h5" if n == current_step else ("caption" if mark else "body")
            root.append(t.text(f"{mark}{n}. {step}", variant))
    t.add("Column", "root", children=root)
    return t.items


def list_tree(items: list[dict], lang: str = "it") -> list[dict]:
    """[{text, done}] → one checkbox each, what is still to buy first."""
    t = _Tree()
    rows = [t.add("CheckBox", label=i.get("text", ""), value=bool(i.get("done"))) for i in items]
    if not rows:
        rows = [t.text(_t(lang)["empty_list"])]
    t.add("Column", "root", children=rows)
    return t.items


def table_tree(columns: list[str], rows: list[list[Any]]) -> list[dict]:
    t = _Tree()
    out = []
    if columns:
        out.append(t.add("Row", children=[t.add("Text", text=str(c), variant="caption", weight=1) for c in columns]))
        out.append(t.add("Divider"))
    for r in rows:
        out.append(t.add("Row", children=[t.add("Text", text=str(v), weight=1) for v in r]))
    t.add("Column", "root", children=out)
    return t.items


# ── the tools Claude sees ─────────────────────────────────────────────────


class Screen(Protocol):
    """What the session offers the screen tools."""

    async def show_card(self, cid: str, title: str, components: list[dict]) -> None: ...

    async def close_card(self, cid: str) -> bool: ...


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _err(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


CARD_ID = {"type": "string", "description": "Short lowercase id of the card/topic, e.g. 'carbonara', 'tomorrow'."}
TITLE = {"type": "string", "description": "Card title, short, in the user's language."}


def server(screen: Screen, lang: str = "it"):
    """The in-process MCP server `screen`: the card tools."""
    from claude_agent_sdk import create_sdk_mcp_server

    return create_sdk_mcp_server(name="screen", version="2.0.0", tools=tools(screen, lang))


def tools(screen: Screen, lang: str = "it") -> list:
    """The tool objects (each has `.name` and `.handler`), apart so tests can call them."""
    from claude_agent_sdk import tool

    async def put(args: dict, build: Callable[[], list[dict]]) -> dict:
        try:
            cid = card_id(args.get("card_id"))
            comps = validate(build())
        except Invalid as bad:
            return _err(f"Not shown: {bad}")
        except (TypeError, AttributeError, KeyError) as bad:
            return _err(f"Not shown, the data has the wrong shape: {bad}")
        await screen.show_card(cid, str(args.get("title") or cid), comps)
        return _ok(f"Shown on card '{cid}'.")

    @tool(
        "show_events",
        "Show events (calendar, schedule) as a card: one row per event, a heading per day.",
        {
            "type": "object",
            "properties": {
                "card_id": CARD_ID,
                "title": TITLE,
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "day": {"type": "string", "description": "Optional day heading, e.g. 'Domenica 16'."},
                            "time": {"type": "string", "description": "e.g. '09:30' or 'tutto il giorno'."},
                            "title": {"type": "string"},
                            "place": {"type": "string"},
                            "note": {"type": "string"},
                        },
                        "required": ["title"],
                    },
                },
            },
            "required": ["card_id", "title", "events"],
        },
    )
    async def show_events(args: dict[str, Any]) -> dict[str, Any]:
        return await put(args, lambda: events_tree(args.get("events") or [], lang))

    @tool(
        "show_recipe",
        "Show a recipe as a card: the current step big at the top, ingredients, then the phases "
        "(e.g. Preparazione, Cottura, Impiattamento) with their steps. To move to the next step, call it "
        "again with the same card_id and a new current_step.",
        {
            "type": "object",
            "properties": {
                "card_id": CARD_ID,
                "title": TITLE,
                "servings": {"type": "string"},
                "ingredients": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"qty": {"type": "string"}, "name": {"type": "string"}},
                        "required": ["name"],
                    },
                },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "steps": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["steps"],
                    },
                },
                "current_step": {
                    "type": "integer",
                    "description": "1-based step the cook is on, counted across sections.",
                },
            },
            "required": ["card_id", "title", "ingredients", "sections"],
        },
    )
    async def show_recipe(args: dict[str, Any]) -> dict[str, Any]:
        return await put(
            args,
            lambda: recipe_tree(
                args.get("ingredients") or [],
                args.get("sections") or [],
                args.get("servings"),
                args.get("current_step"),
                lang,
            ),
        )

    @tool(
        "show_list",
        "Show a simple checklist card that is NOT the household shopping list (that one has its own tools).",
        {
            "type": "object",
            "properties": {
                "card_id": CARD_ID,
                "title": TITLE,
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}, "done": {"type": "boolean"}},
                        "required": ["text"],
                    },
                },
            },
            "required": ["card_id", "title", "items"],
        },
    )
    async def show_list(args: dict[str, Any]) -> dict[str, Any]:
        return await put(args, lambda: list_tree(args.get("items") or [], lang))

    @tool(
        "show_table",
        "Show a table card: comparisons, prices, results.",
        {
            "type": "object",
            "properties": {
                "card_id": CARD_ID,
                "title": TITLE,
                "columns": {"type": "array", "items": {"type": "string"}},
                "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
            },
            "required": ["card_id", "title", "rows"],
        },
    )
    async def show_table(args: dict[str, Any]) -> dict[str, Any]:
        return await put(args, lambda: table_tree(args.get("columns") or [], args.get("rows") or []))

    @tool(
        "show",
        "Show anything else as a card, with a flat list of A2UI components (basic catalog). One component "
        "has id 'root'. Containers (Column, Row, List) list child ids in 'children'; Card and Button use "
        "'child'. Components: Text(text, variant h1..h5|body|caption), Image(url, fit), Icon(name), Row, "
        "Column, List(direction), Card(child), Tabs(tabs:[{title, child}]), Divider, Button(child, action, "
        "variant), CheckBox(label, value). Any component takes 'weight' inside a Row.",
        {
            "type": "object",
            "properties": {
                "card_id": CARD_ID,
                "title": TITLE,
                "components": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["card_id", "title", "components"],
        },
    )
    async def show(args: dict[str, Any]) -> dict[str, Any]:
        return await put(args, lambda: args.get("components"))

    @tool(
        "close_card",
        "Remove a card from the screen when the person says they are done with it.",
        {"type": "object", "properties": {"card_id": CARD_ID}, "required": ["card_id"]},
    )
    async def close_card(args: dict[str, Any]) -> dict[str, Any]:
        try:
            cid = card_id(args.get("card_id"))
        except Invalid as bad:
            return _err(str(bad))
        return _ok("Closed.") if await screen.close_card(cid) else _err(f"No open card '{cid}'.")

    return [show_events, show_recipe, show_list, show_table, show, close_card]
