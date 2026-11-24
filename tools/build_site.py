"""Generates site/ (iampino.com) in English, Italian and Spanish.

    python3 tools/build_site.py

Run from the repo root. The pictures in site/img come from brand/ (tools/cut_stickers.py)."""

import os
import shutil

REPO = "https://github.com/alessio-ragni/pino"
GUIDE = REPO + "/blob/main/docs/deployment.md"
HOW = REPO + "/blob/main/docs/how-it-works.md"

T = {
    "en": {
        "lang": "en", "title": "Pino",
        "desc": "Pino is a personal assistant with a voice, a face and a screen. One Pino, one memory, many bodies.",
        "nav": ["Why a face", "The story", "Bodies", "Plant a pine"],
        "hero_kicker": "Hey Pino",
        "hero_h": "I'm Pino.",
        "hero_p": "A personal assistant with a voice, a face and a screen. There is only one Pino: one memory, many bodies. Today it lives on a tablet in the kitchen; tomorrow on a tiny holographic screen, on WhatsApp, on your phone.",
        "cta1": "Plant a pine", "cta2": "Read the code",
        "why_h": "Why a face",
        "why_p": [
            "Everything is going interface-less: you talk, something answers, and that's it. I don't buy it. When you talk to a person, the person is the interface: a raised eyebrow says more than a paragraph, a grimace says something else again. Words are only part of it.",
            "So Pino talks and shows. Its voice gives you the first useful thing in one sentence; the rest goes on a card you can look at with your hands in the dough: a recipe step by step, tomorrow's events, the shopping list. And it has a face that listens, thinks and smiles back.",
        ],
        "story_h": "Franco, Franchino, Pino",
        "story": [
            ("Franco", "The first one was a Frankenstein of spare hardware, hence the name. Part of it was meant to work like Alexa, without a frontier model. It was slow, and it was impossible to carry around."),
            ("Franchino", "The smaller one: a tablet with a screen that is always on, Claude behind it, and cards drawn with A2UI, Google's protocol for interfaces written by an agent."),
            ("Pino", "The grown-up one, with many bodies and one memory. Pino is what my sister used to call our dad, who is no longer here. It's a way to remember him. A kinder one."),
        ],
        "faces_h": "Pino's faces",
        "faces_p": "Pino listens, thinks, laughs, gets worried and is happy to help: the face says it before the voice does.",
        "faces": ["Hi!", "Done", "Calm", "Yay!", "Oh no", "Really?", "All good", "Thanks"],
        "first_try": "The first try: a little tree with a face. Pino became a drop instead: the pine is in the green.",
        "shades_h": "Fifty Shades of Pino",
        "shades_p": "Same Pino, same memory, different bodies. When more than one hears its name, you decide which one answers.",
        "bodies": [
            ("Tablet", "Today", "In the kitchen, always on: voice, cards and a circle that shows what it is doing."),
            ("WhatsApp", "Soon", "Write to Pino where your life already happens."),
            ("Holographic mini-TV", "Coming", "A tiny ESP32-S3 screen with Pino's face: the first Pino that replaces Alexa for good."),
            ("Mac and iPhone", "Later", "Pino at your desk and in your pocket."),
        ],
        "does_h": "What Pino does today",
        "does": [
            "It waits for its name, «Hey Pino», on the device itself: nothing leaves the house until it hears it.",
            "It answers aloud in a sentence or two and puts the details on a card.",
            "Alarms, timers, reminders and lists of its own.",
            "It remembers what matters about you and your people, quietly. Ask «what do you know about me?» to see it.",
            "It asks before doing anything that leaves the house: a message, an email, an event.",
            "It thinks with Claude Code, on the Claude subscription of whoever installs it.",
        ],
        "plant_h": "Plant a pine",
        "plant_p": "There is no Pino to sign up for. Pino is yours: you install it on your own server, with your own Claude subscription, and it grows with you. The code is open, the guide takes you from zero to the first «Hey Pino».",
        "plant1": "Install your Pino", "plant2": "How it works",
        "foot": "Made by Alessio Ragni, who writes about it on",
    },
    "it": {
        "lang": "it", "title": "Pino",
        "desc": "Pino è un assistente personale con una voce, una faccia e uno schermo. Un solo Pino, una sola memoria, tanti corpi.",
        "nav": ["Perché una faccia", "La storia", "I corpi", "Pianta un pino"],
        "hero_kicker": "Ehi Pino",
        "hero_h": "Sono Pino.",
        "hero_p": "Un assistente personale con una voce, una faccia e uno schermo. Di Pino ce n'è uno solo: una memoria, tanti corpi. Oggi vive su un tablet in cucina; domani su un piccolo schermo olografico, su WhatsApp, sul telefono.",
        "cta1": "Pianta un pino", "cta2": "Leggi il codice",
        "why_h": "Perché una faccia",
        "why_p": [
            "Tutto sta diventando senza interfaccia: parli, qualcosa risponde, fine. Non ci credo. Quando parli con una persona, la persona è l'interfaccia: un sopracciglio alzato dice più di un paragrafo, una smorfia dice tutt'altro. Le parole sono solo una parte.",
            "Per questo Pino parla e mostra. Con la voce ti dà subito la cosa utile, in una frase; il resto va su una card che puoi guardare con le mani in pasta: una ricetta passo passo, gli impegni di domani, la lista della spesa. E ha una faccia che ascolta, pensa e ti sorride.",
        ],
        "story_h": "Franco, Franchino, Pino",
        "story": [
            ("Franco", "Il primo era un Frankenstein di hardware avanzato, da qui il nome. Una parte doveva funzionare come Alexa, senza un modello di frontiera. Era lento, e portarselo in giro era impossibile."),
            ("Franchino", "Il più piccolo: un tablet con lo schermo sempre acceso, Claude dietro, e le card disegnate con A2UI, il protocollo di Google per le interfacce scritte da un agente."),
            ("Pino", "Quello cresciuto, con tanti corpi e una sola memoria. Pino è come mia sorella chiamava Babbo, che non c'è più. È un modo di ricordarlo. Più gentile."),
        ],
        "faces_h": "Le facce di Pino",
        "faces_p": "Pino ascolta, pensa, ride, si preoccupa ed è contento di aiutarti: la faccia lo dice prima della voce.",
        "faces": ["Ciao!", "Fatto", "Tranquillo", "Evviva!", "Oh no", "Davvero?", "Tutto ok", "Grazie"],
        "first_try": "Il primo tentativo: un alberello con la faccia. Poi Pino è diventato una goccia: il pino è nel verde.",
        "shades_h": "Fifty Shades of Pino",
        "shades_p": "Stesso Pino, stessa memoria, corpi diversi. Quando in tanti sentono il suo nome, decidi tu chi risponde.",
        "bodies": [
            ("Tablet", "Oggi", "In cucina, sempre acceso: voce, card e un cerchio che mostra cosa sta facendo."),
            ("WhatsApp", "Presto", "Scrivi a Pino dove la tua vita succede già."),
            ("Mini TV olografica", "In arrivo", "Un piccolo schermo ESP32-S3 con la faccia di Pino: il primo Pino che manda in pensione Alexa."),
            ("Mac e iPhone", "Più avanti", "Pino sulla scrivania e in tasca."),
        ],
        "does_h": "Cosa fa Pino oggi",
        "does": [
            "Aspetta il suo nome, «Ehi Pino», sul dispositivo stesso: finché non lo sente, niente esce di casa.",
            "Risponde a voce in una frase o due e mette i dettagli su una card.",
            "Sveglie, timer, promemoria e liste tutte sue.",
            "Ricorda in silenzio quello che conta di te e delle tue persone. Chiedigli «cosa sai di me?» per vederlo.",
            "Chiede prima di fare qualcosa che esce di casa: un messaggio, una mail, un evento.",
            "Pensa con Claude Code, sull'abbonamento Claude di chi lo installa.",
        ],
        "plant_h": "Pianta un pino",
        "plant_p": "Non c'è un Pino a cui iscriversi. Pino è tuo: lo installi sul tuo server, con il tuo abbonamento Claude, e cresce con te. Il codice è aperto, la guida ti porta da zero al primo «Ehi Pino».",
        "plant1": "Installa il tuo Pino", "plant2": "Come funziona",
        "foot": "Fatto da Alessio Ragni, che ne scrive su",
    },
    "es": {
        "lang": "es", "title": "Pino",
        "desc": "Pino es un asistente personal con voz, cara y pantalla. Un solo Pino, una sola memoria, muchos cuerpos.",
        "nav": ["Por qué una cara", "La historia", "Los cuerpos", "Planta un pino"],
        "hero_kicker": "Hey Pino",
        "hero_h": "Soy Pino.",
        "hero_p": "Un asistente personal con voz, cara y pantalla. Pino hay uno solo: una memoria, muchos cuerpos. Hoy vive en una tablet en la cocina; mañana en una pequeña pantalla holográfica, en WhatsApp, en tu teléfono.",
        "cta1": "Planta un pino", "cta2": "Lee el código",
        "why_h": "Por qué una cara",
        "why_p": [
            "Todo se está quedando sin interfaz: hablas, algo responde y ya. No me lo creo. Cuando hablas con una persona, la persona es la interfaz: una ceja levantada dice más que un párrafo, una mueca dice otra cosa. Las palabras son solo una parte.",
            "Por eso Pino habla y muestra. Con la voz te da lo útil en una frase; el resto va a una tarjeta que puedes mirar con las manos en la masa: una receta paso a paso, las citas de mañana, la lista de la compra. Y tiene una cara que escucha, piensa y te sonríe.",
        ],
        "story_h": "Franco, Franchino, Pino",
        "story": [
            ("Franco", "El primero era un Frankenstein de hardware sobrante, de ahí el nombre. Una parte debía funcionar como Alexa, sin un modelo de frontera. Era lento e imposible de llevar encima."),
            ("Franchino", "El pequeño: una tablet con la pantalla siempre encendida, Claude detrás y tarjetas dibujadas con A2UI, el protocolo de Google para interfaces escritas por un agente."),
            ("Pino", "El mayor, con muchos cuerpos y una sola memoria. Pino es como mi hermana llamaba a nuestro padre, que ya no está. Es una forma de recordarlo. Más amable."),
        ],
        "faces_h": "Las caras de Pino",
        "faces_p": "Pino escucha, piensa, se ríe, se preocupa y se alegra de ayudarte: la cara lo dice antes que la voz.",
        "faces": ["¡Hola!", "Hecho", "Tranquilo", "¡Bien!", "Oh, no", "¿En serio?", "Todo bien", "Gracias"],
        "first_try": "El primer intento: un arbolito con cara. Luego Pino se convirtió en una gota: el pino está en el verde.",
        "shades_h": "Fifty Shades of Pino",
        "shades_p": "El mismo Pino, la misma memoria, cuerpos distintos. Cuando varios oyen su nombre, tú decides cuál responde.",
        "bodies": [
            ("Tablet", "Hoy", "En la cocina, siempre encendida: voz, tarjetas y un círculo que muestra lo que está haciendo."),
            ("WhatsApp", "Pronto", "Escríbele a Pino donde ya pasa tu vida."),
            ("Mini TV holográfica", "En camino", "Una pequeña pantalla ESP32-S3 con la cara de Pino: el primer Pino que jubila a Alexa."),
            ("Mac e iPhone", "Más adelante", "Pino en tu escritorio y en tu bolsillo."),
        ],
        "does_h": "Qué hace Pino hoy",
        "does": [
            "Espera su nombre, «Hey Pino», en el propio dispositivo: hasta que lo oye, nada sale de casa.",
            "Responde en voz alta en una o dos frases y deja los detalles en una tarjeta.",
            "Alarmas, temporizadores, recordatorios y listas propias.",
            "Recuerda en silencio lo que importa de ti y de los tuyos. Pregúntale «¿qué sabes de mí?» para verlo.",
            "Pregunta antes de hacer algo que sale de casa: un mensaje, un correo, un evento.",
            "Piensa con Claude Code, con la suscripción de Claude de quien lo instala.",
        ],
        "plant_h": "Planta un pino",
        "plant_p": "No hay un Pino al que suscribirse. Pino es tuyo: lo instalas en tu propio servidor, con tu suscripción de Claude, y crece contigo. El código es abierto y la guía te lleva de cero al primer «Hey Pino».",
        "plant1": "Instala tu Pino", "plant2": "Cómo funciona",
        "foot": "Hecho por Alessio Ragni, que escribe sobre ello en",
    },
}

PATHS = {"en": "", "it": "it/", "es": "es/"}
NAMES = {"en": "English", "it": "Italiano", "es": "Español"}
IDS = ["why", "story", "bodies", "plant"]
FACES = ["hello", "thumbsup", "calm", "joy", "sad", "wow", "cool", "love"]


def page(code: str) -> str:
    t = T[code]
    up = "../" if PATHS[code] else ""
    langs = " ".join(
        f'<a href="{up}{PATHS[c]}" hreflang="{c}"{" aria-current=\"page\"" if c == code else ""}>{NAMES[c]}</a>'
        for c in T
    )
    alts = "\n".join(f'<link rel="alternate" hreflang="{c}" href="https://iampino.com/{PATHS[c]}">' for c in T)
    nav = "".join(f'<a href="#{i}">{n}</a>' for i, n in zip(IDS, t["nav"]))
    why = "".join(f"<p>{p}</p>" for p in t["why_p"])
    story = "".join(
        f'<li><span class="step">{n}</span><p>{p}</p></li>' for n, p in t["story"]
    )
    bodies = "".join(
        f'<article class="body{" now" if i == 0 else ""}"><span class="when">{w}</span><h3>{n}</h3><p>{p}</p></article>'
        for i, (n, w, p) in enumerate(t["bodies"])
    )
    does = "".join(f"<li>{d}</li>" for d in t["does"])
    faces = "".join(
        f'<figure><img src="{up}img/pino-{f}.png" alt="Pino: {n}" loading="lazy"><figcaption>{n}</figcaption></figure>'
        for f, n in zip(FACES, t["faces"])
    )
    return f"""<!doctype html>
<html lang="{t['lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{t['title']}</title>
<meta name="description" content="{t['desc']}">
<meta property="og:title" content="Pino">
<meta property="og:description" content="{t['desc']}">
<meta property="og:image" content="https://iampino.com/pino.png">
<meta name="twitter:card" content="summary_large_image">
{alts}
<link rel="icon" href="{up}pino.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600&family=Nunito+Sans:wght@400;600;700&display=swap">
<link rel="stylesheet" href="{up}style.css">
</head>
<body>
<header class="top"><div class="wrap bar">
  <a class="brand" href="{up}{PATHS[code]}"><img src="{up}pino.svg" alt="" width="32" height="32"> Pino</a>
  <nav>{nav}</nav>
  <div class="langs">{langs}</div>
</div></header>

<main>
<section class="hero"><div class="wrap hero-grid">
  <div class="hero-text">
    <p class="kicker">«{t['hero_kicker']}»</p>
    <h1>{t['hero_h']}</h1>
    <p class="lead">{t['hero_p']}</p>
    <p class="ctas"><a class="btn" href="#plant">{t['cta1']}</a><a class="btn ghost" href="{REPO}">{t['cta2']}</a></p>
  </div>
  <div class="hero-pino"><img src="{up}img/pino-hello.png" alt="Pino" width="315" height="389"></div>
</div></section>

<section id="why"><div class="wrap"><h2>{t['why_h']}</h2>{why}</div></section>

<section id="faces"><div class="wrap"><h2>{t['faces_h']}</h2><p>{t['faces_p']}</p><div class="faces">{faces}</div></div></section>

<section id="story" class="tint"><div class="wrap"><h2>{t['story_h']}</h2><ol class="story">{story}</ol>
<figure class="first-try"><img src="{up}img/first-try.jpg" alt="" loading="lazy"><figcaption>{t['first_try']}</figcaption></figure></div></section>

<section id="bodies"><div class="wrap"><h2>{t['shades_h']}</h2><p>{t['shades_p']}</p><div class="bodies">{bodies}</div></div></section>

<section class="tint"><div class="wrap"><h2>{t['does_h']}</h2><ul class="does">{does}</ul></div></section>

<section id="plant"><div class="wrap plant">
  <h2>{t['plant_h']}</h2>
  <p>{t['plant_p']}</p>
  <p class="ctas"><a class="btn" href="{GUIDE}">{t['plant1']}</a><a class="btn ghost" href="{HOW}">{t['plant2']}</a></p>
  <div class="forest" aria-hidden="true"><img src="{up}img/pino-calm.png" alt=""><img src="{up}img/pino-wow.png" alt=""><img src="{up}img/pino-thumbsup.png" alt=""><img src="{up}img/pino-joy.png" alt=""><img src="{up}img/pino-hello.png" alt=""></div>
</div></section>
</main>

<footer><div class="wrap">{t['foot']} <a href="https://alessioragni.com">alessioragni.com</a> · <a href="{REPO}">GitHub</a> · MIT</div></footer>
</body>
</html>
"""


CSS = """/* Layout: one 1080px column; paragraphs run the full width of it. */
:root{
  --bg:#f4faf3; --paper:#ffffff; --tint:#e6f5e4; --ink:#0f2a14; --muted:#4b6650; --line:#cfe5cc;
  --green:#3cc23e; --green-dark:#1f8a2c; --outline:#0e3b14;
  --display:"Fredoka","Nunito Sans",system-ui,sans-serif; --body:"Nunito Sans",system-ui,sans-serif;
}
@media (prefers-color-scheme: dark){:root{
  --bg:#0c160e; --paper:#122015; --tint:#13261a; --ink:#e4f3e4; --muted:#9ebfa2; --line:#21402a; --green-dark:#7fe08a;
  color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);font-size:18px;line-height:1.6}
a{color:var(--green-dark)}
img{max-width:100%;height:auto}
.wrap{max-width:1080px;margin:0 auto;padding-left:max(20px,env(safe-area-inset-left,0px));padding-right:max(20px,env(safe-area-inset-right,0px))}
p,li{max-width:none}
h1,h2,h3{font-family:var(--display);font-weight:600;line-height:1.1;text-wrap:balance;margin:0}
h1{font-size:clamp(3rem,9vw,5.5rem)}
h2{font-size:clamp(1.8rem,4vw,2.6rem);margin-bottom:16px}
h3{font-size:1.3rem}
section{padding-block:56px}
section.tint{background:var(--tint)}
.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.bar{display:flex;align-items:center;gap:16px 24px;flex-wrap:wrap;padding-block:10px}
.brand{display:flex;align-items:center;gap:8px;font-family:var(--display);font-size:1.4rem;font-weight:600;color:var(--ink);text-decoration:none}
nav{display:flex;gap:18px;flex-wrap:wrap;flex:1}
nav a,.langs a{color:var(--muted);text-decoration:none;font-weight:600;font-size:.95rem}
nav a:hover,.langs a:hover,.langs a[aria-current]{color:var(--ink)}
.langs{display:flex;gap:12px}
.hero{padding-block:48px 32px}
.hero-grid{display:grid;grid-template-columns:1.4fr 1fr;gap:32px;align-items:center}
.hero-text{display:grid;gap:16px;min-width:0}
.kicker{font-family:var(--display);color:var(--green-dark);font-size:1.3rem;margin:0}
.lead{font-size:1.25rem;color:var(--muted);margin:0}
.hero-pino{display:grid;place-items:center}
.hero-pino img{width:min(300px,80%);animation:bob 4s ease-in-out infinite}
@keyframes bob{50%{transform:translateY(-10px) rotate(-2deg)}}
@media (prefers-reduced-motion:reduce){.hero-pino img{animation:none}}
.ctas{display:flex;gap:12px;flex-wrap:wrap;margin:8px 0 0}
.btn{display:inline-block;background:var(--green);color:#06210b;border:2px solid var(--outline);border-radius:999px;padding:10px 22px;font-weight:700;text-decoration:none}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--line)}
.btn:focus-visible,a:focus-visible{outline:3px solid var(--green);outline-offset:3px}
.story{list-style:none;margin:0;padding:0;display:grid;gap:20px}
.story li{display:grid;grid-template-columns:150px 1fr;gap:16px;align-items:baseline}
.story p{margin:0}
.step{font-family:var(--display);font-size:1.5rem;color:var(--green-dark)}
.bodies{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-top:24px}
.body{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:18px;display:grid;gap:8px;align-content:start}
.body.now{border:2px solid var(--green)}
.body p{margin:0;color:var(--muted);font-size:1rem}
.when{font-size:.8rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--green-dark)}
.does{margin:0;padding-left:1.2em;display:grid;gap:8px}
.faces{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:12px;margin-top:20px}
.faces figure{margin:0;display:grid;gap:6px;justify-items:center;text-align:center}
.faces img{height:120px;width:auto;object-fit:contain;transition:transform .2s}
.faces figure:hover img{transform:translateY(-6px) rotate(-3deg)}
.faces figcaption{font-family:var(--display);color:var(--muted)}
.first-try{margin:28px 0 0;display:grid;gap:8px}
.first-try img{width:100%;max-width:560px;border-radius:18px;border:1px solid var(--line);background:#fff}
.first-try figcaption{color:var(--muted);font-size:.95rem}
.plant{display:grid;gap:12px}
.plant p{margin:0}
.forest{display:flex;align-items:flex-end;gap:10px;margin-top:24px}
.forest img{width:40px}
.forest img:nth-child(2){width:56px}.forest img:nth-child(3){width:76px}.forest img:nth-child(4){width:100px}.forest img:nth-child(5){width:132px}
footer{border-top:1px solid var(--line);padding-block:28px;color:var(--muted);font-size:.95rem}
@media (max-width:820px){
  .hero-grid{grid-template-columns:1fr}
  .hero-pino{order:-1}
  .hero-pino img{width:180px}
  .bodies{grid-template-columns:repeat(2,minmax(0,1fr))}
  .faces{grid-template-columns:repeat(4,minmax(0,1fr))}
  .faces img{height:96px}
  .story li{grid-template-columns:1fr;gap:4px}
  nav{display:none}
}
@media (max-width:460px){.bodies{grid-template-columns:1fr}}
"""

os.makedirs("site/it", exist_ok=True)
os.makedirs("site/es", exist_ok=True)
for c in T:
    open(f"site/{PATHS[c]}index.html", "w").write(page(c))
open("site/style.css", "w").write(CSS)
shutil.copy("brand/pino.svg", "site/pino.svg")
open("site/CNAME", "w").write("iampino.com\n")
print("ok")
