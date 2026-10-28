"""Builds the revír pages from data/reviry.json.

Run from the project folder:  python3 tools/build_reviry.py

Outputs
  reviry.html               list of all revíry with search and filters
  revir/<slug>.html         one page per revír (what people land on from Google)
  assets/js/reviry-data.js  small search index for the homepage and list search
  sitemap.xml, robots.txt
"""
import html
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://rybarskereviry.sk/"
PRICE = "6,99&nbsp;€"
PLAY = "https://play.google.com/store/apps/details?id=sk.rr.rybarskereviry"

TYPES = {
    "kaprovy": {"code": "k", "adj": "kaprový", "label": "Kaprový revír", "water": "Kaprové vody"},
    "lipnovy": {"code": "l", "adj": "lipňový", "label": "Lipňový revír", "water": "Lipňové vody"},
}

# Slovak alphabetical order (ch is its own letter after h; á, é, ... sort with their base letter)
ALPHABET = ["a", "b", "c", "č", "d", "ď", "e", "f", "g", "h", "ch", "i", "j", "k", "l", "ľ", "m", "n", "ň",
            "o", "ô", "p", "q", "r", "s", "š", "t", "ť", "u", "v", "w", "x", "y", "z", "ž"]
FOLD = str.maketrans("áäéíĺóŕúý", "aaeiloruy")


def letters(word):
    word = word.lower().translate(FOLD)
    out, i = [], 0
    while i < len(word):
        if word[i:i + 2] == "ch":
            out.append("ch"); i += 2
        else:
            out.append(word[i]); i += 1
    return out


def sort_key(name):
    return [ALPHABET.index(c) if c in ALPHABET else 100 + ord(c[0]) for c in letters(name)]


def group_letter(name):
    first = letters(name)[0]
    return first.upper() if first != "ch" else "Ch"


def slugify(text):
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def search_key(r):
    return re.sub(r"[^a-z0-9]+", " ", slugify(r["name"] + " " + r["number"])).strip()


def esc(text):
    return html.escape(text, quote=True)


def nbsp(text):
    """Keep 'č. 1a' and short prepositions together, as the rest of the site does."""
    text = esc(text).replace("č. ", "č.&nbsp;")
    return re.sub(r"(?<=\s)([aiouvszkAIOUVSZK])\s", r"\1&nbsp;", text)


def play_url(content):
    return f"{PLAY}&amp;referrer=utm_source%3Drybarskereviry.sk%26utm_medium%3Dweb%26utm_content%3D{content}"


def base_name(name):
    return re.sub(r"\s+č\.\s*\S+$", "", name)


SPRITE = """  <svg class="sprite" aria-hidden="true" focusable="false">
    <symbol id="i-check" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></symbol>
    <symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></symbol>
    <symbol id="i-lock" viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></symbol>
    <symbol id="i-mail" viewBox="0 0 24 24"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></symbol>
    <symbol id="i-arrow" viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></symbol>
    <symbol id="i-menu" viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16"/></symbol>
    <symbol id="i-close" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></symbol>
  </svg>"""


def page(*, title, description, canonical, asset, home, body, ld, current="", og_title=None, scripts=()):
    # Same menu as the homepage: section links lead back to its sections, Revíry is its own page.
    # current: "reviry" on the list itself, "revir" on a revír page (Revíry stays highlighted there)
    revir_class = "nav-revir is-active" if current == "revir" else "nav-revir"
    revir_attr = ' aria-current="page"' if current == "reviry" else ""
    nav = "\n".join([
        f'          <li><a href="{home}">Domov</a></li>',
        f'          <li><a class="{revir_class}" href="{asset}reviry.html"{revir_attr}>'
        '<svg class="icon" aria-hidden="true"><use href="#i-search"/></svg><span>Revíry</span>'
        '<span class="nav-sub">Hľadať podľa názvu alebo čísla</span>'
        '<svg class="icon nav-go" aria-hidden="true"><use href="#i-arrow"/></svg></a></li>',
        f'          <li><a href="{home}#description">Hranice</a></li>',
        f'          <li><a href="{home}#galery">Ukážky</a></li>',
        f'          <li><a href="{home}#recenzie">Recenzie</a></li>',
        f'          <li><a href="{home}#cena">Cena</a></li>',
        f'          <li><a href="{home}#otazky">FAQ</a></li>',
    ])
    extra_js = "\n".join(f'  <script src="{asset}{s}" defer></script>' for s in scripts)
    ld_json = json.dumps(ld, ensure_ascii=False, indent=2)
    return f"""<!doctype html>
<html lang="sk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <link rel="canonical" href="{canonical}">
  <meta name="theme-color" content="#0B3640">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="sk_SK">
  <meta property="og:site_name" content="Rybárske Revíry SK">
  <meta property="og:title" content="{esc(og_title or title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:image" content="{SITE}assets/img/icon-512.png">
  <link rel="icon" href="{asset}favicon.ico" sizes="any">
  <link rel="icon" href="{asset}assets/img/favicon-32.png" type="image/png" sizes="32x32">
  <link rel="apple-touch-icon" href="{asset}assets/img/apple-touch-icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:ital,wdth,wght@0,62..100,400..800;1,62..100,400..800&display=swap">
  <link rel="stylesheet" href="{asset}assets/css/style.css">
  <script>document.documentElement.classList.add('js')</script>
  <script type="application/ld+json">
{ld_json}
  </script>
</head>
<body>
  <a class="skip-link" href="#main">Preskočiť na obsah</a>
{SPRITE}

  <header class="site-header">
    <div class="container header-inner">
      <a class="brand" href="{home}">
        <img src="{asset}assets/img/icon-192.png" width="56" height="56" alt="">
        <span class="brand__name">Rybárske <span>Revíry&nbsp;SK</span></span>
      </a>
      <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-nav" data-nav-toggle>
        <svg class="icon icon--menu" aria-hidden="true"><use href="#i-menu"/></svg>
        <svg class="icon icon--close" aria-hidden="true"><use href="#i-close"/></svg>
        <span class="nav-toggle__label">Menu</span>
      </button>
      <nav id="site-nav" class="site-nav" aria-label="Hlavná navigácia">
        <ul>
{nav}
        </ul>
      </nav>
      <a class="btn-buy btn-buy--sm" data-cta="header" href="{play_url('header')}">Stiahnuť</a>
    </div>
  </header>

  <main id="main">
{body}
  </main>

  <footer class="site-footer" data-sticky-hide>
    <div class="container footer-inner">
      <p>© <span data-year>2026</span> Rybárske Revíry SK. Všetky práva vyhradené.</p>
      <ul>
        <li><a href="{asset}reviry.html">Zoznam revírov</a></li>
        <li><a href="{asset}privacy_policy.html">Ochrana súkromia</a></li>
        <li><button type="button" class="link-button" data-cookie-open>Nastavenia cookies</button></li>
      </ul>
    </div>
  </footer>

  <div class="sticky-buy" data-sticky inert>
    <img src="{asset}assets/img/icon-96.png" width="40" height="40" alt="">
    <p class="sticky-buy__text"><strong>Rybárske Revíry SK</strong><span>{PRICE} jednorazovo</span></p>
    <a class="btn-buy btn-buy--sm" data-cta="sticky" href="{play_url('sticky')}">Stiahnuť</a>
  </div>

  <div class="cookie" id="cookie" role="region" aria-label="Súhlas s cookies" hidden>
    <p>Analytické cookies (Google Analytics) nám pomáhajú zistiť, ako sa stránka používa. Načítame ich iba s&nbsp;vaším súhlasom. <a href="{asset}privacy_policy.html">Ochrana súkromia</a></p>
    <div class="cookie__actions">
      <button type="button" class="btn-plain" data-consent="granted">Súhlasím</button>
      <button type="button" class="btn-plain" data-consent="denied">Odmietam</button>
    </div>
  </div>

{extra_js}
  <script src="{asset}assets/js/main.js" defer></script>
</body>
</html>
"""


def buy_button(cta, label="Chcem aplikáciu"):
    return f"""<a class="btn-buy" data-cta="{cta}" href="{play_url(cta)}">
              <span class="btn-buy__label">{label}</span>
              <span class="btn-buy__meta">{PRICE} jednorazovo · Google Play</span>
            </a>"""


def row(r, href):
    t = TYPES[r["type"]]
    return (f'<li data-search="{esc(search_key(r))}" data-type="{t["code"]}">'
            f'<a class="revir-row" href="{href}">'
            f'<span class="revir-row__name">{nbsp(r["name"])}</span>'
            f'<span class="revir-row__num">{esc(r["number"])}</span>'
            f'<span class="revir-row__type"><span class="type-dot type-dot--{t["code"]}" aria-hidden="true"></span>{t["adj"]}</span>'
            f'</a></li>')


def cta_band(cta):
    return f"""    <section class="section section-dark revir-cta" aria-labelledby="cta-title" data-sticky-hide>
      <div class="container revir-cta__inner">
        <div>
          <h2 id="cta-title" class="h2">Všetky revíry s&nbsp;hranicami v&nbsp;telefóne</h2>
          <p>Viac než 330 kaprových a&nbsp;lipňových revírov, navigácia k&nbsp;vode, lovné miery a&nbsp;rybárske poriadky. Pre telefóny s&nbsp;Androidom.</p>
        </div>
        {buy_button(cta)}
      </div>
    </section>"""


def map_figure(r):
    name = nbsp(r["name"])
    if r.get("outline"):
        o = r["outline"]
        x, y, w, h = (float(v) for v in o["viewBox"].split())
        return f"""        <figure class="revir-map revir-map--shape">
          <svg viewBox="{o['viewBox']}" role="img" aria-label="Tvar revíru {esc(r['name'])}">
            <rect class="m-land" x="{x}" y="{y}" width="{w}" height="{h}"/>
            <path class="revir-map__fill" d="{o['d']}"/>
            <path class="revir-map__line" d="{o['d']}"/>
          </svg>
          <figcaption>Tvar revíru {name}. Na mape s&nbsp;navigáciou ho uvidíte v&nbsp;aplikácii.</figcaption>
        </figure>"""
    return f"""        <figure class="revir-map revir-map--locked">
          <svg viewBox="0 0 600 400" aria-hidden="true" focusable="false">
            <defs><filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="7"/></filter></defs>
            <rect class="m-land" width="600" height="400"/>
            <g class="m-contours">
              <path d="M40 60c60-30 150-20 190 20s10 90-60 100-170-20-160-60 0-40 30-60Z"/>
              <path d="M70 75c45-20 115-12 140 15s5 62-45 70-120-14-115-42 0-28 20-43Z"/>
              <path d="M430 290c50-30 130-25 160 10s0 80-70 85-140-20-130-55 10-25 40-40Z"/>
            </g>
            <path class="m-road" d="M380 -10 L420 120 L470 260 Q500 340 520 420"/>
            <path class="revir-map__river" d="M-20 300 C90 260 150 330 250 290 S420 160 520 190 S640 140 640 140"/>
            <path class="revir-map__blur" d="M-20 300 C90 260 150 330 250 290 S420 160 520 190 S640 140 640 140" pathLength="1" filter="url(#soft)"/>
          </svg>
          <figcaption>
            <span class="revir-map__lock"><svg class="icon" aria-hidden="true"><use href="#i-lock"/></svg></span>
            <span>Presné hranice revíru {name} sú zakreslené v&nbsp;aplikácii.</span>
          </figcaption>
        </figure>"""


def detail_page(r, all_reviry, demo):
    t = TYPES[r["type"]]
    name = nbsp(r["name"])
    facts = [("Charakter", t["water"])]
    for key, label in (("organization", "Organizácia"), ("season", "Obdobie lovu"), ("area", "Rozloha")):
        if r.get(key):
            facts.append((label, r[key]))
    facts_html = "\n".join(
        f'            <div><dt>{label}</dt><dd>{nbsp(value)}</dd></div>' for label, value in facts)

    if r.get("description"):
        about = f"""    <section class="section-sm revir-about" aria-labelledby="about-title">
      <div class="container">
        <h2 id="about-title" class="h3">Popis revíru</h2>
        <p class="revir-about__text">{nbsp(r["description"])}</p>
        <p class="revir-about__note">Údaje sú informatívne. Záväzné je aktuálne znenie rybárskeho poriadku SRZ.</p>
      </div>
    </section>"""
    elif demo:
        about = """    <section class="section-sm revir-about" aria-label="Ukážka">
      <div class="container">
        <p class="demo-note">Ukážka: popis, organizácia a obdobie lovu tohto revíru sa doplnia z&nbsp;údajov aplikácie.</p>
      </div>
    </section>"""
    else:
        about = ""

    same = [x for x in all_reviry if x is not r and base_name(x["name"]) == base_name(r["name"])]
    i = all_reviry.index(r)
    around = [x for x in all_reviry[max(0, i - 3):i + 4] if x is not r and x not in same]
    related = (same + around)[:6]
    related_html = "\n".join("            " + row(x, f"{x['slug']}.html") for x in related)

    body = f"""    <section class="revir-hero" aria-labelledby="revir-title">
      <div class="container">
        <nav class="crumbs" aria-label="Omrvinková navigácia">
          <ol>
            <li><a href="../">Domov</a></li>
            <li><a href="../reviry.html">Revíry</a></li>
            <li aria-current="page">{name}</li>
          </ol>
        </nav>
        <div class="revir-hero__grid">
          <div class="revir-hero__copy">
            <p class="type-chip"><span class="type-dot type-dot--{t['code']}" aria-hidden="true"></span>{t['label']}</p>
            <h1 id="revir-title" class="revir-title">{name}</h1>
            <p class="revir-plate"><span>Číslo revíru</span> <strong>{esc(r['number'])}</strong></p>
            <dl class="revir-facts">
{facts_html}
            </dl>
            <div class="revir-actions" data-sticky-hide>
              {buy_button('revir-' + r['slug'])}
              <p>Hranice, navigácia a&nbsp;vzdialenosť k&nbsp;revíru sú v&nbsp;aplikácii.</p>
            </div>
          </div>
{map_figure(r)}
        </div>
      </div>
    </section>

{about}

    <section class="section-sm revir-inapp" aria-labelledby="inapp-title">
      <div class="container revir-inapp__grid">
        <h2 id="inapp-title" class="h3">V&nbsp;aplikácii pri revíri <span class="hydro">{name}</span> uvidíte</h2>
        <ul class="ticks ticks--light">
          <li><svg class="icon" aria-hidden="true"><use href="#i-check"/></svg><span>Presné hranice revíru na mape aj na satelite</span></li>
          <li><svg class="icon" aria-hidden="true"><use href="#i-check"/></svg><span>Popis a&nbsp;obmedzenia lovu z&nbsp;rybárskeho poriadku</span></li>
          <li><svg class="icon" aria-hidden="true"><use href="#i-check"/></svg><span>Obdobie lovu a&nbsp;dennú dobu lovu</span></li>
          <li><svg class="icon" aria-hidden="true"><use href="#i-check"/></svg><span>Navigáciu k&nbsp;vode cez Google Maps</span></li>
          <li><svg class="icon" aria-hidden="true"><use href="#i-check"/></svg><span>Vzdialenosť od vás a&nbsp;ďalšie revíry v&nbsp;okolí</span></li>
        </ul>
      </div>
    </section>

    <section class="section-sm revir-related" aria-labelledby="related-title">
      <div class="container">
        <div class="revir-related__head">
          <h2 id="related-title" class="h3">Ďalšie revíry</h2>
          <a class="text-link text-link--sm" href="../reviry.html">Celý zoznam revírov</a>
        </div>
        <ul class="revir-rows revir-rows--cols">
{related_html}
        </ul>
      </div>
    </section>

{cta_band('revir-' + r['slug'] + '-cta')}"""

    org = f", {r['organization']}" if r.get("organization") else ""
    description = (f"{r['name']}, číslo revíru {r['number']}. {t['adj'].capitalize()} zväzový revír SRZ{org}. "
                   f"Popis, obdobie lovu a presné hranice revíru na mape v aplikácii Rybárske Revíry SK.")
    canonical = f"{SITE}revir/{r['slug']}.html"
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BodyOfWater",
                "name": r["name"],
                "identifier": {"@type": "PropertyValue", "propertyID": "Číslo revíru SRZ", "value": r["number"]},
                "description": r.get("description") or f"{t['label']} SRZ číslo {r['number']}.",
                "url": canonical,
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Domov", "item": SITE},
                    {"@type": "ListItem", "position": 2, "name": "Revíry", "item": SITE + "reviry.html"},
                    {"@type": "ListItem", "position": 3, "name": r["name"], "item": canonical},
                ],
            },
        ],
    }
    return page(
        title=f"{r['name']} ({r['number']}) – {t['adj']} revír | Rybárske Revíry SK",
        og_title=f"{r['name']} – {t['adj']} revír {r['number']}",
        description=description, canonical=canonical, asset="../", home="../", body=body, ld=ld,
        current="revir")


def list_page(reviry, demo):
    counts = {"": len(reviry), "k": sum(r["type"] == "kaprovy" for r in reviry), "l": sum(r["type"] == "lipnovy" for r in reviry)}
    groups = {}
    for r in reviry:
        groups.setdefault(group_letter(r["name"]), []).append(r)
    blocks = []
    for letter, items in groups.items():
        rows = "\n".join("              " + row(r, "revir/" + r["slug"] + ".html") for r in items)
        blocks.append(f"""          <section class="letter-group" aria-labelledby="l-{slugify(letter)}">
            <h2 id="l-{slugify(letter)}" class="letter-group__letter">{letter}</h2>
            <ul class="revir-rows">
{rows}
            </ul>
          </section>""")
    groups_html = "\n".join(blocks)

    demo_html = (f"""        <p class="demo-note">Ukážka: v&nbsp;náhľade je {len(reviry)} revírov z&nbsp;aplikácie. Po napojení na údaje aplikácie tu bude všetkých viac než 330.</p>
""" if demo else "")

    def shown(n):
        if n == 1:
            return "Zobrazený 1 revír"
        return f"Zobrazené {n} revíry" if 2 <= n <= 4 else f"Zobrazených {n} revírov"

    body = f"""    <section class="list-hero" aria-labelledby="list-title">
      <div class="container">
        <nav class="crumbs" aria-label="Omrvinková navigácia">
          <ol>
            <li><a href="./">Domov</a></li>
            <li aria-current="page">Revíry</li>
          </ol>
        </nav>
        <h1 id="list-title" class="h2">Zväzové revíry na Slovensku</h1>
        <p class="list-hero__lead">Kaprové a&nbsp;lipňové revíry SRZ s&nbsp;číslom revíru. Hľadajte podľa názvu toku, nádrže alebo čísla revíru.</p>
{demo_html}        <form class="revir-filter" role="search" action="reviry.html" method="get" data-revir-filter>
          <div class="search-field">
            <svg class="icon" aria-hidden="true"><use href="#i-search"/></svg>
            <label for="q" class="visually-hidden">Hľadať revír</label>
            <input id="q" name="q" type="search" placeholder="Napríklad Váh, Bodrog alebo 2-4420" autocomplete="off" enterkeyhint="search">
          </div>
          <fieldset class="type-filter">
            <legend class="visually-hidden">Druh revíru</legend>
            <label class="chip"><input type="radio" name="t" value="" checked> Všetky <span>{counts['']}</span></label>
            <label class="chip"><input type="radio" name="t" value="k"> <span class="type-dot type-dot--k" aria-hidden="true"></span>Kaprové <span>{counts['k']}</span></label>
            <label class="chip"><input type="radio" name="t" value="l"> <span class="type-dot type-dot--l" aria-hidden="true"></span>Lipňové <span>{counts['l']}</span></label>
          </fieldset>
        </form>
        <p class="result-count" data-count aria-live="polite">{shown(counts[''])}</p>
      </div>
    </section>

    <section class="revir-index" aria-label="Zoznam revírov">
      <div class="container">
        <div class="letter-groups">
{groups_html}
        </div>
        <div class="empty-state" data-empty hidden>
          <p><strong>Taký revír sme nenašli.</strong> Skúste iný názov, len časť názvu alebo číslo revíru.</p>
          <p>Chýba vám zväzový revír? Napíšte nám na <span class="nowrap">info@rybarskereviry.sk</span>.</p>
        </div>
      </div>
    </section>

{cta_band('reviry-cta')}"""

    ld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Zväzové revíry na Slovensku",
        "numberOfItems": len(reviry),
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": r["name"], "url": f"{SITE}revir/{r['slug']}.html"}
            for i, r in enumerate(reviry)
        ],
    }
    return page(
        title="Zoznam rybárskych revírov SRZ – kaprové a lipňové revíry | Rybárske Revíry SK",
        og_title="Zväzové revíry na Slovensku",
        description="Zoznam kaprových a lipňových zväzových revírov SRZ s číslami revírov. Vyhľadajte revír podľa názvu alebo čísla a pozrite si jeho popis a hranice v aplikácii.",
        canonical=f"{SITE}reviry.html", asset="", home="./", body=body, ld=ld, current="reviry",
        scripts=("assets/js/reviry-data.js", "assets/js/reviry.js"))


def main():
    doc = json.loads((ROOT / "data" / "reviry.json").read_text(encoding="utf-8"))
    demo = bool(doc.get("demo"))
    reviry = doc["reviry"]
    for r in reviry:
        r.setdefault("slug", slugify(r["name"]))
        if "type" not in r:
            r["type"] = "lipnovy" if r["number"].split("-")[2] == "5" else "kaprovy"
    reviry.sort(key=lambda r: sort_key(r["name"]))
    slugs = [r["slug"] for r in reviry]
    assert len(slugs) == len(set(slugs)), "duplicate slug"

    out_dir = ROOT / "revir"
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("*.html"):
        old.unlink()
    for r in reviry:
        (out_dir / f"{r['slug']}.html").write_text(detail_page(r, reviry, demo), encoding="utf-8")
    (ROOT / "reviry.html").write_text(list_page(reviry, demo), encoding="utf-8")

    index = [{"n": r["name"], "c": r["number"], "t": TYPES[r["type"]]["code"], "s": r["slug"], "k": search_key(r)} for r in reviry]
    (ROOT / "assets" / "js" / "reviry-data.js").write_text(
        "// Generated by tools/build_reviry.py from data/reviry.json\nwindow.RR_REVIRY = "
        + json.dumps(index, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")

    urls = [SITE, SITE + "reviry.html", SITE + "privacy_policy.html"] + [f"{SITE}revir/{s}.html" for s in slugs]
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}sitemap.xml\n", encoding="utf-8")
    print(f"{len(reviry)} revírov: reviry.html, revir/*.html, assets/js/reviry-data.js, sitemap.xml, robots.txt")


if __name__ == "__main__":
    main()
