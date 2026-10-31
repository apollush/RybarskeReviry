"""Builds the revír pages from the app's private revír database (reviry.xml).

Run from the project folder:  python3 tools/build_reviry.py [--xml PATH]

The database is private: it lives outside the website, in ../RybarskeReviry-databaza/reviry.xml
(or the path in --xml / the REVIRY_XML environment variable), and is never copied to the site.
Only what a visitor sees on a revír page is published: name, number, character of the water,
type of water, organization, area, border flag, the description and the revír's location (one point
on the map, never its boundaries). Each revír page carries only its own point; the list, the search
index and the sitemap carry no coordinates, so the database can't be pulled from any one file.

Outputs
  reviry.html               list of all revíry with search and filters
  revir/<slug>.html         one page per revír (what people land on from Google)
  assets/js/reviry-data.js  small search index (name, number, character, slug)
  sitemap.xml, robots.txt
Every CSS and JS link, also in index.html and privacy_policy.html, gets ?v=<content hash>, so after a
change browsers load the new file instead of an old cached copy.
Public lookup files: data/organizacie.json (organization names), data/slovensko.json (map of Slovakia).
"""
import argparse
import functools
import hashlib
import html
import json
import math
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_XML = ROOT.parent / "RybarskeReviry-databaza" / "reviry.xml"
SITE = "https://rybarskereviry.sk/"
PRICE = "6,99&nbsp;€"
PLAY = "https://play.google.com/store/apps/details?id=sk.rr.rybarskereviry"

TYPES = {
    "kaprovy": {"code": "k", "adj": "kaprový", "label": "Kaprový revír", "water": "Kaprové vody"},
    "lipnovy": {"code": "l", "adj": "lipňový", "label": "Lipňový revír", "water": "Lipňové vody"},
}
# <water_category> in the database: 5 = lipňové vody, everything else = kaprové vody (as in the app)
LIPNOVE_CATEGORIES = {"5"}

# <type_area> in the database -> type of water shown on the page
TYPE_AREA = {
    "11": "Rieka", "12": "Potok", "13": "Potok",
    "20": "Rameno", "21": "Rameno", "23": "Mŕtve rameno", "24": "Odstavené rameno", "25": "Sústava ramien",
    "30": "Kanál", "31": "Kanál", "32": "Kanál", "34": "Kanál", "35": "Kanál", "36": "Kanál", "37": "Kanál", "38": "Kanál",
    "41": "Vodná nádrž", "42": "Vodná nádrž", "43": "Jazero", "45": "Štrkovisko", "48": "Zdrž vodného diela",
}

# Slovak alphabetical order (ch is its own letter after h; á, é, ... sort with their base letter)
ALPHABET = ["a", "b", "c", "č", "d", "ď", "e", "f", "g", "h", "ch", "i", "j", "k", "l", "ľ", "m", "n", "ň",
            "o", "ô", "p", "q", "r", "s", "š", "t", "ť", "u", "v", "w", "x", "y", "z", "ž"]
FOLD = str.maketrans("áäéíĺóŕúý", "aaeiloruy")


def sort_key(name):
    """Slovak order with numbers compared as numbers, so Váh č. 2 comes before Váh č. 10."""
    key = []
    for tok in re.findall(r"\d+|ch|.", name.lower().translate(FOLD)):
        if tok.isdigit():
            key.append((0, int(tok)))
        elif tok in ALPHABET:
            key.append((1, ALPHABET.index(tok)))
        else:
            # spaces and dashes before letters, so Dunaj č. 1 comes before Dunajec
            key.append((1, -1 if not tok.isalnum() else 100 + ord(tok)))
    return key


def group_letter(name):
    first = name.lower().translate(FOLD)
    first = "ch" if first.startswith("ch") else first[0]
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


def display_name(raw):
    """'Váh č.17a' -> 'Váh č. 17a', 'Dunaj č.3 - Odpadový kanál' -> 'Dunaj č. 3 – Odpadový kanál'."""
    name = " ".join(raw.split())
    name = re.sub(r"č\.\s*(?=\S)", "č. ", name)
    return name.replace(" - ", " – ")


def base_name(name):
    return re.split(r"\s+č\.\s", name)[0]


def plural(n, one, few, many):
    return one if n == 1 else (few if 2 <= n <= 4 else many)


def area_from(description):
    """The area in hectares when the opening words give it, e.g. 'Vodná plocha nádrže (2160 ha)'.
    Hectares further in the text belong to a side arm or a lake inside the revír, not the whole revír."""
    m = re.search(r"\((\d[\d\s]*)(,\d+)?\s*ha\)", description)
    if not m or m.start() > 60:
        return ""
    whole = int(re.sub(r"\s", "", m.group(1)))
    return f"{whole:,}".replace(",", " ") + (m.group(2) or "") + " ha"


def distance_km(a, b):
    if not a["center"] or not b["center"]:
        return math.inf
    (lat1, lon1), (lat2, lon2) = a["center"], b["center"]
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def load_json(name):
    data = json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
    data.pop("_comment", None)
    return data


def load_reviry(xml_path):
    organizations = load_json("organizacie.json")
    warnings = []

    def org_name(code):
        code = (code or "").strip()
        if not code:
            return ""
        if code not in organizations:
            warnings.append(f"neznáma organizácia {code} (doplňte ju do data/organizacie.json)")
            return "SRZ MO " + code.replace("_", " ").title()
        return organizations[code]

    reviry = []
    for el in ET.parse(xml_path).getroot().iter("revir"):
        number = (el.findtext("number") or "").strip()
        raw_name = (el.findtext("name") or "").strip()
        if not number or not raw_name:
            warnings.append(f"revír id={el.get('id')} nemá číslo alebo názov, vynechaný")
            continue
        description = " ".join((el.findtext("description") or "").split())
        point = el.find("center_point")
        try:
            center = (float(point.get("lat")), float(point.get("lon"))) if point is not None else None
        except (TypeError, ValueError):
            center = None
        type_area = (el.findtext("type_area") or "").strip()
        name = display_name(raw_name)
        water = TYPE_AREA.get(type_area, "")
        if type_area == "43" and "nádrž" in name.lower():
            water = "Vodná nádrž"
        reviry.append({
            "number": number,
            "name": name,
            "base": base_name(name),
            "type": "lipnovy" if (el.findtext("water_category") or "").strip() in LIPNOVE_CATEGORIES else "kaprovy",
            "water": water,
            "organizations": [o for o in (org_name(el.findtext("organization")), org_name(el.findtext("organization_2"))) if o],
            "border": (el.findtext("on_border") or "0").strip() not in ("", "0"),
            "area": area_from(description),
            "description": description,
            "center": center,
        })

    numbers = [r["number"] for r in reviry]
    if len(numbers) != len(set(numbers)):
        raise SystemExit("Chyba: v databáze sa opakuje číslo revíru, stránky neboli zmenené.")
    # Slug from the name; two revíry with the same name (Turiec č. 2) also get the number
    by_slug = {}
    for r in reviry:
        by_slug.setdefault(slugify(r["name"]), []).append(r)
    for slug, same in by_slug.items():
        for r in same:
            r["slug"] = slug if len(same) == 1 else f"{slug}-{r['number']}"
    reviry.sort(key=lambda r: (sort_key(r["name"]), r["number"]))
    return reviry, warnings


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


def cta_band(cta, count):
    return f"""    <section class="section section-dark revir-cta" aria-labelledby="cta-title" data-sticky-hide>
      <div class="container revir-cta__inner">
        <div>
          <h2 id="cta-title" class="h2">Všetky revíry s&nbsp;hranicami v&nbsp;telefóne</h2>
          <p>Všetkých {count} kaprových a&nbsp;lipňových revírov, navigácia k&nbsp;vode, lovné miery a&nbsp;rybárske poriadky. Pre telefóny s&nbsp;Androidom.</p>
        </div>
        {buy_button(cta)}
      </div>
    </section>"""


# Map of Slovakia on a revír page: equirectangular, x squeezed by cos 48.7° (the middle of Slovakia)
MAP_VIEWBOX = "0 0 1000 530"


def project(lon, lat):
    return (lon - 16.80) * math.cos(math.radians(48.7)) * 245.4 + 30, (49.66 - lat) * 245.4 + 20


def gps(r):
    """The revír's point as people type it into a map app: 48.74690, 17.81230"""
    lat, lon = r["center"]
    return f"{lat:.5f}, {lon:.5f}"


def maps_url(r):
    return "https://www.google.com/maps/search/?api=1&query=" + gps(r).replace(", ", "%2C")


@functools.lru_cache(maxsize=None)
def slovakia():
    """The parts of the map that are the same on every page: border, Danube, regional towns, grid."""
    data = load_json("slovensko.json")
    pt = lambda lon, lat: "%.1f %.1f" % project(lon, lat)
    line = lambda pts: " ".join(pt(*p) for p in pts)
    lx, ly = project(*data["dunaj_popis"])
    towns = [(t["nazov"], *project(*t["poloha"]), t.get("minor", False)) for t in data["mesta"]]
    # A faint grid every half degree: when the map is zoomed in it shows how far it moved
    lons = [16.0 + 0.5 * i for i in range(14)]
    lats = [47.0 + 0.5 * i for i in range(6)]
    grid = "".join(f"M{pt(lon, lats[0])}L{pt(lon, lats[-1])}" for lon in lons)
    grid += "".join(f"M{pt(lons[0], lat)}L{pt(lons[-1], lat)}" for lat in lats)
    return (f"M{line(data['hranica'])}Z", f"M{line(data['dunaj'])}", (lx, ly), towns, grid)


def map_figure(r):
    name = nbsp(r["name"])
    border, danube, (lx, ly), towns, grid = slovakia()
    pin, place, controls = "", "", ""
    if r["center"]:
        px, py = project(r["center"][1], r["center"][0])
        # The point is a button: it glows, and a click zooms the map in on it (assets/js/main.js)
        pin = f"""
            <g class="loc-pin" data-x="{px:.1f}" data-y="{py:.1f}" transform="translate({px:.1f} {py:.1f})" role="button" tabindex="0" aria-pressed="false" aria-label="Priblížiť mapu na revír {esc(r['name'])}">
              <circle class="loc-pin__hit" cy="-18" r="34"/>
              <circle class="loc-pin__halo" r="26"/>
              <circle class="loc-pin__pulse" r="18"/>
              <g class="loc-pin__drop"><path d="M0 0C-5-13-18-21-18-35a18 18 0 1 1 36 0C18-21 5-13 0 0Z"/><circle cy="-35" r="6.5"/></g>
            </g>"""
        controls = """
          <p class="loc-hint">Kliknutím na bod mapu priblížite</p>
          <button type="button" class="loc-zoom" hidden>Celé Slovensko</button>"""
        place = f"""
          <div class="revir-loc">
            <p class="revir-loc__gps"><span>GPS</span> <span class="revir-loc__value" translate="no">{gps(r)}</span></p>
            <a class="revir-loc__link" href="{esc(maps_url(r))}" target="_blank" rel="noopener">Otvoriť v&nbsp;Mapách Google<svg class="icon" aria-hidden="true"><use href="#i-arrow"/></svg></a>
          </div>"""
    town_marks = []
    for town, tx, ty, minor in towns:
        # A town whose dot or name would sit under the pin is left out
        if r["center"] and tx - 8 < px + 24 and px - 24 < tx + 14 + 13 * len(town) and ty - 20 < py + 22 and py - 58 < ty + 14:
            continue
        cls = "loc-town loc-town--minor" if minor else "loc-town"
        town_marks.append(f'<g class="{cls}" style="transform-origin:{tx:.1f}px {ty:.1f}px"><circle cx="{tx:.1f}" cy="{ty:.1f}" r="5"/>'
                          f'<text x="{tx + 11:.1f}" y="{ty + 8:.1f}">{esc(town)}</text></g>')
    label = f"Poloha revíru {esc(r['name'])} na mape Slovenska" if r["center"] else "Mapa Slovenska"
    return f"""        <figure class="revir-map">
          <div class="loc-stage">
          <svg class="loc-map" viewBox="{MAP_VIEWBOX}" role="group" aria-label="{label}">
            <path class="loc-grid" d="{grid}"/>
            <path class="loc-land" d="{border}"/>
            <path class="loc-danube" d="{danube}"/>
            <text class="loc-hydro" x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" style="transform-origin:{lx:.1f}px {ly:.1f}px">Dunaj</text>
            <g class="loc-towns">{''.join(town_marks)}</g>{pin}
          </svg>{controls}
          </div>
          <figcaption>{place}
          <p class="revir-map__note">
            <span class="revir-map__lock"><svg class="icon" aria-hidden="true"><use href="#i-lock"/></svg></span>
            <span>Presné hranice revíru {name} sú zakreslené v&nbsp;aplikácii.</span>
          </p>
          </figcaption>
        </figure>"""


def related_lists(r, reviry):
    """Other stretches of the same river and the nearest other revíry, each shown in name order."""
    others = [x for x in reviry if x is not r]
    same = sorted((x for x in others if x["base"] == r["base"]), key=lambda x: distance_km(r, x))[:8]
    same.sort(key=lambda x: sort_key(x["name"]))
    near = sorted((x for x in others if x["base"] != r["base"]), key=lambda x: distance_km(r, x))[:6]
    near.sort(key=lambda x: sort_key(x["name"]))
    return same, near


def detail_page(r, reviry):
    t = TYPES[r["type"]]
    name = nbsp(r["name"])
    facts = [("Charakter", nbsp(t["water"]))]
    if r["water"]:
        facts.append(("Typ vody", nbsp(r["water"])))
    if r["organizations"]:
        facts.append(("Organizácia", "<br>".join(nbsp(o) for o in r["organizations"])))
    if r["area"]:
        facts.append(("Rozloha", esc(r["area"])))
    facts_html = "\n".join(f'            <div><dt>{label}</dt><dd>{value}</dd></div>' for label, value in facts)
    chip = t["label"] + (" · hraničný" if r["border"] else "")

    about = ""
    if r["description"]:
        about = f"""    <section class="section-sm revir-about" aria-labelledby="about-title">
      <div class="container">
        <h2 id="about-title" class="h3">Popis revíru</h2>
        <p class="revir-about__text">{nbsp(r["description"])}</p>
        <p class="revir-about__note">Údaje sú informatívne. Záväzné je aktuálne znenie rybárskeho poriadku SRZ.</p>
      </div>
    </section>"""

    same, near = related_lists(r, reviry)
    blocks = []
    if same:
        blocks.append(("Ďalšie úseky toku", same))
    if near:
        blocks.append(("Revíry v okolí", near))
    related_html = []
    for i, (heading, items) in enumerate(blocks):
        rows = "\n".join("          " + row(x, f"{x['slug']}.html") for x in items)
        title_id = ' id="related-title"' if i == 0 else ""
        head = (f"""        <div class="revir-related__head">
          <h2{title_id} class="h3">{heading}</h2>
          <a class="text-link text-link--sm" href="../reviry.html">Celý zoznam revírov</a>
        </div>""" if i == 0 else f'        <h2 class="h3 revir-related__sub">{heading}</h2>')
        related_html.append(f"""{head}
        <ul class="revir-rows revir-rows--cols">
{rows}
        </ul>""")
    related = ""
    if related_html:
        related = f"""    <section class="section-sm revir-related" aria-labelledby="related-title">
      <div class="container">
{chr(10).join(related_html)}
      </div>
    </section>"""

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
            <p class="type-chip"><span class="type-dot type-dot--{t['code']}" aria-hidden="true"></span>{chip}</p>
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

{related}

{cta_band('revir-' + r['slug'] + '-cta', len(reviry))}"""

    water = f", {r['water'].lower()}" if r["water"] else ""
    org = f", {r['organizations'][0]}" if r["organizations"] else ""
    description = (f"{r['name']}, číslo revíru {r['number']}. {t['adj'].capitalize()} zväzový revír SRZ{water}{org}. "
                   f"Poloha revíru na mape, popis a presné hranice v aplikácii Rybárske Revíry SK.")
    canonical = f"{SITE}revir/{r['slug']}.html"
    water_ld = {
        "@type": "BodyOfWater",
        "name": r["name"],
        "identifier": {"@type": "PropertyValue", "propertyID": "Číslo revíru SRZ", "value": r["number"]},
        "description": r["description"] or f"{t['label']} SRZ číslo {r['number']}.",
        "url": canonical,
    }
    if r["center"]:
        water_ld["geo"] = {"@type": "GeoCoordinates", "latitude": r["center"][0], "longitude": r["center"][1]}
        water_ld["hasMap"] = maps_url(r)
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            water_ld,
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


def list_page(reviry):
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

    def shown(n):
        return f"{plural(n, 'Zobrazený', 'Zobrazené', 'Zobrazených')} {n} {plural(n, 'revír', 'revíry', 'revírov')}"

    n = counts[""]
    body = f"""    <section class="list-hero" aria-labelledby="list-title">
      <div class="container">
        <nav class="crumbs" aria-label="Omrvinková navigácia">
          <ol>
            <li><a href="./">Domov</a></li>
            <li aria-current="page">Revíry</li>
          </ol>
        </nav>
        <h1 id="list-title" class="h2">Zväzové revíry na Slovensku</h1>
        <p class="list-hero__lead">{plural(n, 'Jeden', 'Všetky', 'Všetkých')} {n} kaprových a&nbsp;lipňových revírov SRZ s&nbsp;číslom revíru. Hľadajte podľa názvu toku, nádrže alebo čísla revíru.</p>
        <form class="revir-filter" role="search" action="reviry.html" method="get" data-revir-filter>
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
        <p class="result-count" data-count aria-live="polite">{shown(n)}</p>
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

{cta_band('reviry-cta', n)}"""

    ld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Zväzové revíry na Slovensku",
        "numberOfItems": n,
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": r["name"], "url": f"{SITE}revir/{r['slug']}.html"}
            for i, r in enumerate(reviry)
        ],
    }
    return page(
        title="Zoznam rybárskych revírov SRZ – kaprové a lipňové revíry | Rybárske Revíry SK",
        og_title="Zväzové revíry na Slovensku",
        description=f"Zoznam {n} kaprových a lipňových zväzových revírov SRZ s číslami revírov. Vyhľadajte revír podľa názvu alebo čísla a pozrite si jeho popis a hranice v aplikácii.",
        canonical=f"{SITE}reviry.html", asset="", home="./", body=body, ld=ld, current="reviry",
        scripts=("assets/js/reviry-data.js", "assets/js/reviry.js"))


def main():
    parser = argparse.ArgumentParser(description="Vytvorí stránky revírov zo súkromnej databázy reviry.xml.")
    parser.add_argument("--xml", type=Path, default=Path(os.environ.get("REVIRY_XML", DEFAULT_XML)),
                        help=f"cesta k databáze (predvolená: {DEFAULT_XML.relative_to(ROOT.parent)} vedľa projektu)")
    xml_path = parser.parse_args().xml.expanduser()
    if not xml_path.is_file():
        print(f"Databáza {xml_path} sa nenašla, stránky revírov ostali bez zmeny.", file=sys.stderr)
        sys.exit(2)
    try:
        reviry, warnings = load_reviry(xml_path)
    except ET.ParseError as e:
        print(f"Databáza {xml_path} nie je platné XML ({e}), stránky revírov ostali bez zmeny.", file=sys.stderr)
        sys.exit(1)
    if not reviry:
        print("V databáze nie je žiadny revír, stránky revírov ostali bez zmeny.", file=sys.stderr)
        sys.exit(1)
    for w in sorted(set(warnings)):
        print("Upozornenie:", w, file=sys.stderr)

    # Everything is built in memory first, so a broken database never leaves the site half updated
    files = {f"revir/{r['slug']}.html": detail_page(r, reviry) for r in reviry}
    files["reviry.html"] = list_page(reviry)
    index = [{"n": r["name"], "c": r["number"], "t": TYPES[r["type"]]["code"], "s": r["slug"], "k": search_key(r)} for r in reviry]
    files["assets/js/reviry-data.js"] = ("// Generated by tools/build_reviry.py: names and numbers for the revír search\nwindow.RR_REVIRY = "
                                         + json.dumps(index, ensure_ascii=False, separators=(",", ":")) + ";\n")
    urls = [SITE, SITE + "reviry.html", SITE + "privacy_policy.html"] + [f"{SITE}revir/{r['slug']}.html" for r in reviry]
    files["sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                            + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    files["robots.txt"] = f"User-agent: *\nAllow: /\n\nSitemap: {SITE}sitemap.xml\n"

    # CSS and JS links carry ?v=<content hash>: a changed file gets a new address, so browsers (and
    # the site preview) load it instead of an old cached copy. The hand-written pages are kept current too
    for path in ("index.html", "privacy_policy.html"):
        files[path] = (ROOT / path).read_text(encoding="utf-8")
    versions = {}
    for path in ("assets/css/style.css", "assets/js/main.js", "assets/js/reviry.js", "assets/js/reviry-data.js"):
        content = files.get(path) or (ROOT / path).read_text(encoding="utf-8")
        versions[path] = hashlib.sha1(content.encode("utf-8")).hexdigest()[:8]
    asset_link = re.compile(r'(assets/(?:css|js)/[\w.-]+\.(?:css|js))(?:\?v=\w+)?"')
    stamp = lambda m: f'{m.group(1)}?v={versions[m.group(1)]}"' if m.group(1) in versions else m.group(0)
    for path in [p for p in files if p.endswith(".html")]:
        files[path] = asset_link.sub(stamp, files[path])

    # A revír page shows only its own point; the list, the search index and the sitemap show none,
    # so the coordinates of the whole database never sit together in one file
    def coord_strings(r):
        if not r or not r["center"]:
            return set()
        return {s.rstrip("0") for c in r["center"] for s in (f"{c:.4f}", f"{c:.5f}"[:-1])}
    own = {f"revir/{r['slug']}.html": coord_strings(r) for r in reviry}
    known = {s for r in reviry for s in coord_strings(r) if len(s) > 5}
    leak = re.compile("|".join(sorted(map(re.escape, known), key=len, reverse=True))) if known else None
    for path, content in files.items():
        if leak and set(leak.findall(content)) - own.get(path, set()):
            raise SystemExit(f"Chyba: do {path} by sa dostali súradnice iných revírov, nič sa nezapísalo.")

    out_dir = ROOT / "revir"
    out_dir.mkdir(exist_ok=True)
    keep = {Path(p).name for p in files if p.startswith("revir/")}
    for old in out_dir.glob("*.html"):
        if old.name not in keep:
            old.unlink()
    for path, content in files.items():
        target = ROOT / path
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")
    kapr = sum(r["type"] == "kaprovy" for r in reviry)
    print(f"{len(reviry)} revírov ({kapr} kaprových, {len(reviry) - kapr} lipňových): "
          "reviry.html, revir/*.html, assets/js/reviry-data.js, sitemap.xml, robots.txt, verzie CSS a JS v index.html a privacy_policy.html")


if __name__ == "__main__":
    main()
