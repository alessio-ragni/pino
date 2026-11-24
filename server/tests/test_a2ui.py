import pytest

from pino.a2ui import Invalid, card_id, check, events_tree, list_tree, recipe_tree, table_tree, validate


def test_adds_version_and_catalog():
    out = check('[{"createSurface": {"surfaceId": "x"}}]', "v0.9.1")
    assert out == [
        {
            "version": "v0.9.1",
            "createSurface": {
                "surfaceId": "x",
                "catalogId": "https://a2ui.org/specification/v0_9_1/catalogs/basic/catalog.json",
            },
        }
    ]


@pytest.mark.parametrize(
    "bad",
    [
        [],
        "non json",
        [{"boh": {}}],
        [{"updateComponents": {"surfaceId": "x", "components": []}}],
        [{"updateComponents": {"surfaceId": "x", "components": [{"id": "root"}]}}],
        [{"deleteSurface": {}}],
    ],
)
def test_refuses_garbage(bad):
    with pytest.raises(Invalid):
        check(bad, "v0.9.1")


def test_components_are_checked_against_the_catalog():
    ok = [{"id": "root", "component": "Column", "children": ["t"]}, {"id": "t", "component": "Text", "text": "ciao"}]
    assert validate(ok) == ok
    with pytest.raises(Invalid, match="unknown component"):
        validate([{"id": "root", "component": "Carousel"}])
    with pytest.raises(Invalid, match="has no"):
        validate([{"id": "root", "component": "Text", "text": "x", "color": "red"}])
    with pytest.raises(Invalid, match="not in the list"):
        validate([{"id": "root", "component": "Column", "children": ["missing"]}])
    with pytest.raises(Invalid, match="variant"):
        validate([{"id": "root", "component": "Text", "text": "x", "variant": "huge"}])
    with pytest.raises(Invalid, match="weight"):
        validate([{"id": "root", "component": "Text", "text": "x", "weight": 0}])
    with pytest.raises(Invalid, match="root"):
        validate([{"id": "a", "component": "Text", "text": "x"}])


def test_templates_make_valid_a2ui():
    recipe = recipe_tree(
        [{"qty": "200 g", "name": "spaghetti"}, "pepe"],
        [{"name": "Preparazione", "steps": ["Taglia"]}, {"name": "Cottura", "steps": ["Bolli", "Scola"]}],
        "2",
        current_step=2,
    )
    validate(recipe)
    texts = [c.get("text", "") for c in recipe]
    assert any("Passo 2 di 3" in t for t in texts) and any(t.startswith("✓ 1.") for t in texts)
    validate(events_tree([{"day": "Domenica", "time": "09:00", "title": "Piscina", "place": "Comunale"}]))
    validate(events_tree([]))
    validate(list_tree([{"text": "latte", "done": False}]))
    validate(table_tree(["a", "b"], [["1", "2"]]))


def test_card_ids_are_short_and_safe():
    assert card_id("Carbonara") == "carbonara"
    with pytest.raises(Invalid):
        card_id("conferma")
    with pytest.raises(Invalid):
        card_id("../x")
