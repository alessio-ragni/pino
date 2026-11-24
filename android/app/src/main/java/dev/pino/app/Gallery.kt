package dev.pino.app

/**
 * A gallery of what the A2UI basic catalog can draw on this tablet, one card per kind of screen:
 * text styles and icons, a recipe with a photo, tabs, a row that scrolls sideways, a form, a modal.
 * It runs only on the tablet, with no server and no Claude, to see the renderer as it is:
 *
 *     adb shell am start -a dev.pino.app.ASCOLTA --es demo gallery
 */
object Gallery {
    private const val V = "v0.9.1"
    private const val CATALOG = "https://a2ui.org/specification/v0_9_1/catalogs/basic/catalog.json"

    private fun surface(id: String, components: String, data: String? = null): List<String> = buildList {
        add("""{"version":"$V","createSurface":{"surfaceId":"$id","catalogId":"$CATALOG"}}""")
        if (data != null) add("""{"version":"$V","updateDataModel":{"surfaceId":"$id","path":"/","value":$data}}""")
        add("""{"version":"$V","updateComponents":{"surfaceId":"$id","components":$components}}""")
    }

    val cards: List<Pair<CardMeta, List<String>>> = listOf(
        CardMeta("demo-text", "A2UI · testo, icone, pulsanti", emptyList()) to surface(
            "demo-text",
            """[
              {"id":"root","component":"Column","children":["h1","h2","h3","h4","h5","body","cap","d1","icons","d2","buttons"]},
              {"id":"h1","component":"Text","text":"Titolo h1","variant":"h1"},
              {"id":"h2","component":"Text","text":"Titolo h2","variant":"h2"},
              {"id":"h3","component":"Text","text":"Titolo h3","variant":"h3"},
              {"id":"h4","component":"Text","text":"Titolo h4","variant":"h4"},
              {"id":"h5","component":"Text","text":"Titolo h5","variant":"h5"},
              {"id":"body","component":"Text","text":"Testo normale: **grassetto** e *corsivo*, se il renderer legge il markdown.","variant":"body"},
              {"id":"cap","component":"Text","text":"Didascalia piccola","variant":"caption"},
              {"id":"d1","component":"Divider"},
              {"id":"icons","component":"Row","justify":"spaceAround","children":["i1","i2","i3","i4","i5","i6"]},
              {"id":"i1","component":"Icon","name":"calendarToday"},
              {"id":"i2","component":"Icon","name":"home"},
              {"id":"i3","component":"Icon","name":"mail"},
              {"id":"i4","component":"Icon","name":"phone"},
              {"id":"i5","component":"Icon","name":"favorite"},
              {"id":"i6","component":"Icon","name":"check"},
              {"id":"d2","component":"Divider"},
              {"id":"buttons","component":"Row","children":["b1","b2","b3"]},
              {"id":"b1t","component":"Text","text":"Primario"},
              {"id":"b2t","component":"Text","text":"Normale"},
              {"id":"b3t","component":"Text","text":"Senza bordo"},
              {"id":"b1","component":"Button","child":"b1t","variant":"primary","action":{"event":{"name":"demo"}}},
              {"id":"b2","component":"Button","child":"b2t","action":{"event":{"name":"demo"}}},
              {"id":"b3","component":"Button","child":"b3t","variant":"borderless","action":{"event":{"name":"demo"}}}
            ]""",
        ),
        CardMeta("demo-recipe", "A2UI · ricetta con foto", emptyList()) to surface(
            "demo-recipe",
            """[
              {"id":"root","component":"Column","children":["img","title","meta","card"]},
              {"id":"img","component":"Image","url":"https://upload.wikimedia.org/wikipedia/commons/thumb/3/33/Espaguetis_carbonara.jpg/960px-Espaguetis_carbonara.jpg","fit":"cover","variant":"header"},
              {"id":"title","component":"Text","text":"Carbonara per due","variant":"h2"},
              {"id":"meta","component":"Row","children":["m1","m2","m3"]},
              {"id":"m1","component":"Text","text":"20 minuti","variant":"caption","weight":1},
              {"id":"m2","component":"Text","text":"Facile","variant":"caption","weight":1},
              {"id":"m3","component":"Text","text":"2 persone","variant":"caption","weight":1},
              {"id":"card","component":"Card","child":"now"},
              {"id":"now","component":"Column","children":["nowl","nowt"]},
              {"id":"nowl","component":"Text","text":"Adesso · passo 2 di 5","variant":"caption"},
              {"id":"nowt","component":"Text","text":"Rosola il guanciale senza olio finché è croccante.","variant":"h3"}
            ]""",
        ),
        CardMeta("demo-tabs", "A2UI · schede (Tabs)", emptyList()) to surface(
            "demo-tabs",
            """[
              {"id":"root","component":"Tabs","tabs":[{"title":"Ingredienti","child":"t1"},{"title":"Passi","child":"t2"},{"title":"Note","child":"t3"}]},
              {"id":"t1","component":"Column","children":["a1","a2","a3"]},
              {"id":"a1","component":"Text","text":"200 g spaghetti"},
              {"id":"a2","component":"Text","text":"100 g guanciale"},
              {"id":"a3","component":"Text","text":"3 tuorli, 50 g pecorino"},
              {"id":"t2","component":"List","children":["s1","s2","s3"]},
              {"id":"s1","component":"Text","text":"1. Acqua a bollire"},
              {"id":"s2","component":"Text","text":"2. Guanciale in padella"},
              {"id":"s3","component":"Text","text":"3. Crema di uova e pecorino"},
              {"id":"t3","component":"Text","text":"Niente panna. Fuori dal fuoco quando unisci le uova."}
            ]""",
        ),
        CardMeta("demo-row", "A2UI · elenco orizzontale", emptyList()) to surface(
            "demo-row",
            """[
              {"id":"root","component":"Column","children":["intro","row"]},
              {"id":"intro","component":"Text","text":"Tre robot aspirapolvere: scorri di lato","variant":"h4"},
              {"id":"row","component":"List","direction":"horizontal","children":["c1","c2","c3"]},
              {"id":"c1","component":"Card","child":"c1c"},
              {"id":"c1c","component":"Column","children":["c1a","c1b","c1d"]},
              {"id":"c1a","component":"Icon","name":"home"},
              {"id":"c1b","component":"Text","text":"Modello A","variant":"h5"},
              {"id":"c1d","component":"Text","text":"299 € · 120 min","variant":"caption"},
              {"id":"c2","component":"Card","child":"c2c"},
              {"id":"c2c","component":"Column","children":["c2a","c2b","c2d"]},
              {"id":"c2a","component":"Icon","name":"favorite"},
              {"id":"c2b","component":"Text","text":"Modello B","variant":"h5"},
              {"id":"c2d","component":"Text","text":"449 € · 180 min","variant":"caption"},
              {"id":"c3","component":"Card","child":"c3c"},
              {"id":"c3c","component":"Column","children":["c3a","c3b","c3d"]},
              {"id":"c3a","component":"Icon","name":"check"},
              {"id":"c3b","component":"Text","text":"Modello C","variant":"h5"},
              {"id":"c3d","component":"Text","text":"599 € · 200 min","variant":"caption"}
            ]""",
        ),
        CardMeta("demo-form", "A2UI · modulo", emptyList()) to surface(
            "demo-form",
            """[
              {"id":"root","component":"Column","children":["f1","f2","f3","f4","f5","f6"]},
              {"id":"f1","component":"TextField","label":"Messaggio da mandare","value":{"path":"/message"}},
              {"id":"f2","component":"CheckBox","label":"Ricordamelo anche domani","value":{"path":"/again"}},
              {"id":"f3","component":"ChoicePicker","label":"Quando","displayStyle":"chips","options":[{"label":"Stasera","value":"tonight"},{"label":"Domani","value":"tomorrow"},{"label":"Sabato","value":"saturday"}],"value":{"path":"/when"}},
              {"id":"f4","component":"DateTimeInput","label":"Data e ora","enableDate":true,"enableTime":true,"value":{"path":"/at"}},
              {"id":"f5","component":"Slider","label":"Volume","min":0,"max":10,"value":{"path":"/volume"}},
              {"id":"f6t","component":"Text","text":"Manda"},
              {"id":"f6","component":"Button","child":"f6t","variant":"primary","action":{"event":{"name":"demo_send"}}}
            ]""",
            """{"message":"Arrivo tra dieci minuti","again":false,"when":["tomorrow"],"at":"2026-11-16T07:30:00","volume":6}""",
        ),
        CardMeta("demo-modal", "A2UI · finestra (Modal)", emptyList()) to surface(
            "demo-modal",
            """[
              {"id":"root","component":"Column","children":["intro","modal"]},
              {"id":"intro","component":"Text","text":"Un pulsante che apre una finestra con i dettagli."},
              {"id":"modal","component":"Modal","trigger":"open","content":"inside"},
              {"id":"opent","component":"Text","text":"Vedi i dettagli"},
              {"id":"open","component":"Button","child":"opent","action":{"event":{"name":"demo_open"}}},
              {"id":"inside","component":"Column","children":["mt","mb"]},
              {"id":"mt","component":"Text","text":"Dettagli","variant":"h3"},
              {"id":"mb","component":"Text","text":"Qui ci sta quello che non serve vedere sempre."}
            ]""",
        ),
    )
}
