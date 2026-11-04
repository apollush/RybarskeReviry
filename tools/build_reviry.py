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
  revir/<slug>.html         one page per revír (what people land on from Google); an address a revír no
                            longer uses keeps a page that sends visitors to its new name or says it's gone
  organizacie.html, organizacia/<slug>.html   revíry of each organization (no coordinates)
  toky.html, tok/<slug>.html                  all stretches of each river with at least three revíry
  404.html                  shown for an address that doesn't exist
  assets/js/reviry-data.js  small search index (name, number, character, slug)
  data/adresy-revirov.json  every address each revír ever had (revír number -> slugs)
  sitemap.xml, robots.txt
Every CSS and JS link, also in index.html and privacy_policy.html, gets ?v=<content hash>, so after a
change browsers load the new file instead of an old cached copy. The number of revíry in index.html
follows the database too.
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
ROK_REVIROV = 2026  # Zmeň, keď databázu aktualizuješ na nový rok.
OG_IMAGE = SITE + "assets/img/og-image.jpg"
OG_IMAGE_ALT = "Mapa revírov s presnými hranicami v aplikácii Rybárske Revíry SK"
# Every address a revír page ever had (revír number -> slugs), so an old address never turns into a 404
ADDRESSES = ROOT / "data" / "adresy-revirov.json"

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
# The same in the accusative, for the opening sentence: "Ide o vodnú nádrž"
WATER_ACC = {
    "Rieka": "rieku", "Potok": "potok", "Rameno": "rameno", "Mŕtve rameno": "mŕtve rameno",
    "Odstavené rameno": "odstavené rameno", "Sústava ramien": "sústavu ramien", "Kanál": "kanál",
    "Vodná nádrž": "vodnú nádrž", "Jazero": "jazero", "Štrkovisko": "štrkovisko", "Zdrž vodného diela": "zdrž vodného diela",
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


# A web address split after a dot in the domain ('https://plavba. nsat.sk/...', '...nsat. sk/...'):
# the part after the space continues the same domain and runs into a path
SPLIT_URL = re.compile(r"((?:https?://|www\.)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.)\s+(?=[a-z0-9-]+(?:\.[a-z0-9-]+)*/)")
URL = re.compile(r"(?:https?://|www\.)(?:(?!&nbsp;)[^\s<])+")


def fix_split_urls(description):
    return SPLIT_URL.sub(r"\1", description)


def linkify(text_html):
    """Web addresses in a description become links. An address ends where a dot or slash runs into the
    next sentence ('…vodach.Zvýšená', '…opatrenia/Zvýšená') and drops a period or comma after it."""
    def link(m):
        url = re.split(r"(?<=[/.])(?=[A-ZÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ])", m.group(0))[0].rstrip(".,;:)")
        href = url if url.startswith("http") else "https://" + url
        return f'<a href="{href}" target="_blank" rel="nofollow noopener">{url}</a>{m.group(0)[len(url):]}'
    return URL.sub(link, text_html)


def intro(r):
    """The opening sentence of a revír's description, put together from its data (plain text)."""
    text = f"{r['name']} je {TYPES[r['type']]['adj']} zväzový revír SRZ s číslom {r['number']}."
    if r["water"]:
        text += f" Ide o {WATER_ACC[r['water']]}" + (f" s rozlohou {r['area']}" if r["area"] else "") + "."
    if r["border"]:
        text += " Je to hraničný revír."
    orgs = r["organizations"]
    if len(orgs) == 1:
        text += f" Revír obhospodaruje {orgs[0]}."
    elif orgs:
        text += f" Revír obhospodarujú {orgs[0]} a {orgs[1]}."
    return text


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
        fixed = fix_split_urls(description)
        if fixed != description:
            warnings.append(f"webová adresa v popise revíru {display_name(raw_name)} ({number}) bola rozdelená medzerou, "
                            "na webe je opravená (opravte ju aj v databáze)")
            description = fixed
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


def page(*, title, description, canonical, asset, home, body, ld=None, current="", og_title=None, scripts=(),
         head="", noindex=False):
    # Same menu as the homepage: section links lead back to its sections, Revíry is its own page.
    # current: "reviry" on the list itself, "revir" on the pages under it (Revíry stays highlighted there).
    # head: tags that must come first in <head> (the 404 page's <base>, a redirect); canonical=None leaves
    # out the canonical link and og:url (404); noindex keeps a page out of Google
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
    ld_html = ""
    if ld:
        ld_html = f"""
  <script type="application/ld+json">
{json.dumps(ld, ensure_ascii=False, indent=2)}
  </script>"""
    first = f"\n  {head}" if head else ""
    robots = '\n  <meta name="robots" content="noindex">' if noindex else ""
    canonical_link = f'\n  <link rel="canonical" href="{canonical}">' if canonical else ""
    og_url = f'\n  <meta property="og:url" content="{canonical}">' if canonical else ""
    return f"""<!doctype html>
<html lang="sk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">{first}
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">{robots}{canonical_link}
  <meta name="theme-color" content="#0B3640">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="sk_SK">
  <meta property="og:site_name" content="Rybárske Revíry SK">
  <meta property="og:title" content="{esc(og_title or title)}">
  <meta property="og:description" content="{esc(description)}">{og_url}
  <meta property="og:image" content="{OG_IMAGE}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{OG_IMAGE_ALT}">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="icon" href="{asset}favicon.ico" sizes="any">
  <link rel="icon" href="{asset}assets/img/favicon-32.png" type="image/png" sizes="32x32">
  <link rel="apple-touch-icon" href="{asset}assets/img/apple-touch-icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:ital,wdth,wght@0,62..100,400..800;1,62..100,400..800&display=swap">
  <link rel="stylesheet" href="{asset}assets/css/style.css">
  <script>document.documentElement.classList.add('js')</script>{ld_html}
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


def row(r, href, more=""):
    """One revír in a list; more: details after the number, e.g. " · rieka" on an organization's page."""
    t = TYPES[r["type"]]
    return (f'<li data-search="{esc(search_key(r))}" data-type="{t["code"]}">'
            f'<a class="revir-row" href="{href}">'
            f'<span class="revir-row__name">{nbsp(r["name"])}</span>'
            f'<span class="revir-row__num">{esc(r["number"])}{more}</span>'
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


@functools.lru_cache(maxsize=None)
def places():
    """Towns and villages as (name, x, y, rank) in map units, biggest first (data/sidla.json)."""
    return tuple(sorted(((n, *project(lon, lat), rank) for n, lon, lat, rank in load_json("sidla.json")["sidla"]),
                        key=lambda p: p[3]))


# What the zoomed-in map shows (all in map units, as the labels look once the page scales them by 0.3)
ZOOM, VIEW_W, VIEW_H = 4, 250.0, 132.5
FONT = {1: 9.0, 2: 9.0, 3: 8.0}  # label height; the widest case (phones) so that nothing overlaps there either


def label_box(x, y, name, size):
    """Where a dot and its name sit, as a box (x0, y0, x1, y1); the name starts to the right of the dot."""
    return (x - 2, y - size * 0.8, x + 3.5 + 0.56 * size * len(name), y + size * 0.3)


def zoomed_obstacles(px, py, danube_label):
    """Fixed things in the zoomed-in view: the pin and its glow, the "Celé Slovensko" button (top right)
    and the Danube label."""
    vx0, vy0 = px - VIEW_W / 2, py - VIEW_H / 2 - 6
    return [(px - 10, py - 20, px + 10, py + 10),
            (vx0 + VIEW_W - 115, vy0, vx0 + VIEW_W, vy0 + 42),
            (danube_label[0] - 12, danube_label[1] - 7, danube_label[0] + 12, danube_label[1] + 4)]


def fits_zoomed(box, px, py, taken):
    """True when the label lies fully inside the zoomed-in view and overlaps nothing in `taken`."""
    vx0, vy0 = px - VIEW_W / 2, py - VIEW_H / 2 - 6
    if not (box[0] >= vx0 + 3 and box[2] <= vx0 + VIEW_W - 3 and box[1] >= vy0 + 3 and box[3] <= vy0 + VIEW_H - 3):
        return False
    return not any(box[0] < t[2] and t[0] < box[2] and box[1] < t[3] and t[1] < box[3] for t in taken)


def nearby_places(px, py, regional, danube_label):
    """Towns and villages for the zoomed-in view around (px, py): biggest first, nearest first within a size,
    never overlapping each other, the pin, the Danube label, the regional towns or the button."""
    taken = zoomed_obstacles(px, py, danube_label) + [label_box(x, y, name, FONT[1]) for name, x, y in regional]
    names = {name for name, *_ in regional}
    shown = []
    for name, x, y, rank in sorted(places(), key=lambda p: (p[3], (p[1] - px) ** 2 + (p[2] - py) ** 2)):
        if name in names or abs(x - px) > VIEW_W or abs(y - py) > VIEW_H:
            continue
        box = label_box(x, y, name, FONT[rank])
        if fits_zoomed(box, px, py, taken):
            taken.append(box)
            shown.append((name, x, y, rank))
            if len(shown) >= 14:
                break
    return shown


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
    towns_kept = []
    for town, tx, ty, minor in towns:
        # A town whose dot or name would sit under the pin is left out
        if r["center"] and tx - 8 < px + 24 and px - 24 < tx + 14 + 13 * len(town) and ty - 20 < py + 22 and py - 58 < ty + 14:
            continue
        cls = "loc-town loc-town--minor" if minor else "loc-town"
        if r["center"]:
            # A regional town whose name would be cut off by the edge of the zoomed-in view is hidden there
            if fits_zoomed(label_box(tx, ty, town, FONT[1]), px, py, zoomed_obstacles(px, py, (lx, ly))):
                towns_kept.append((town, tx, ty))
            else:
                cls += " loc-town--far"
        town_marks.append(f'<g class="{cls}" style="transform-origin:{tx:.1f}px {ty:.1f}px"><circle cx="{tx:.1f}" cy="{ty:.1f}" r="5"/>'
                          f'<text x="{tx + 11:.1f}" y="{ty + 8:.1f}">{esc(town)}</text></g>')
    place_marks = ""
    if r["center"]:
        marks = "".join(f'<g class="loc-place loc-place--{rank}" style="transform-origin:{x:.1f}px {y:.1f}px">'
                        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{5 if rank < 3 else 4}"/>'
                        f'<text x="{x + 11:.1f}" y="{y + 8:.1f}">{esc(name)}</text></g>'
                        for name, x, y, rank in nearby_places(px, py, towns_kept, (lx, ly)))
        place_marks = f'\n            <g class="loc-places" aria-hidden="true">{marks}</g>'
    label = f"Poloha revíru {esc(r['name'])} na mape Slovenska" if r["center"] else "Mapa Slovenska"
    return f"""        <figure class="revir-map">
          <div class="loc-stage">
          <svg class="loc-map" viewBox="{MAP_VIEWBOX}" role="group" aria-label="{label}">
            <path class="loc-grid" d="{grid}"/>
            <path class="loc-land" d="{border}"/>
            <path class="loc-danube" d="{danube}"/>
            <text class="loc-hydro" x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" style="transform-origin:{lx:.1f}px {ly:.1f}px">Dunaj</text>
            <g class="loc-towns">{''.join(town_marks)}</g>{place_marks}{pin}
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


def detail_page(r, reviry, org_slugs, tok_slugs):
    t = TYPES[r["type"]]
    name = nbsp(r["name"])
    facts = [("Charakter", nbsp(t["water"]))]
    if r["water"]:
        facts.append(("Typ vody", nbsp(r["water"])))
    if r["organizations"]:
        # An organization with its own page (all of data/organizacie.json) links to the list of its revíry
        facts.append(("Organizácia", "<br>".join(f'<a href="../organizacia/{org_slugs[o]}.html">{nbsp(o)}</a>' if o in org_slugs
                                                  else nbsp(o) for o in r["organizations"])))
    if r["area"]:
        facts.append(("Rozloha", esc(r["area"])))
    facts_html = "\n".join(f'            <div><dt>{label}</dt><dd>{value}</dd></div>' for label, value in facts)
    chip = t["label"] + (" · hraničný" if r["border"] else "")

    # Always shown: a sentence put together from the revír's data, then its description if it has one
    text = f'\n        <p class="revir-about__text">{linkify(nbsp(r["description"]))}</p>' if r["description"] else ""
    about = f"""    <section class="section-sm revir-about" aria-labelledby="about-title">
      <div class="container">
        <h2 id="about-title" class="h3">Popis revíru</h2>
        <p class="revir-about__text">{nbsp(intro(r))}</p>{text}
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
        all_link = ""
        if items is same and r["base"] in tok_slugs:
            all_link = (f'\n        <a class="text-link text-link--sm revir-related__all" href="../tok/{tok_slugs[r["base"]]}.html">'
                        f'Všetky revíry na toku {nbsp(r["base"])}</a>')
        related_html.append(f"""{head}
        <ul class="revir-rows revir-rows--cols">
{rows}
        </ul>{all_link}""")
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
    description = (f"Rybolov na revíri {r['name']}: {t['adj']} zväzový revír SRZ č. {r['number']}{water}{org}. "
                   f"Poloha na mape a popis revíru. Presné hranice v aplikácii Rybárske Revíry SK.")
    canonical = f"{SITE}revir/{r['slug']}.html"
    water_ld = {
        "@type": "BodyOfWater",
        "name": r["name"],
        "identifier": {"@type": "PropertyValue", "propertyID": "Číslo revíru SRZ", "value": r["number"]},
        "description": r["description"] or intro(r),
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
        title=f"{r['name']} – rybársky revír {r['number']}, rybolov | Rybárske Revíry SK",
        og_title=f"{r['name']} – {t['adj']} revír {r['number']}",
        description=description, canonical=canonical, asset="../", home="../", body=body, ld=ld,
        current="revir")


def list_page(reviry):
    counts = {"": len(reviry), "k": sum(r["type"] == "kaprovy" for r in reviry), "l": sum(r["type"] == "lipnovy" for r in reviry)}
    groups = {}
    for r in reviry:
        groups.setdefault(group_letter(r["name"]), []).append(r)
    blocks = []
    ids = set()
    for letter, items in groups.items():
        rows = "\n".join("              " + row(r, "revir/" + r["slug"] + ".html") for r in items)
        # Č, Š and Ž would get the same id as C, S and Z: the second one becomes l-c2, l-s2, l-z2
        anchor = "l-" + slugify(letter)
        anchor = next(a for a in (anchor, *(f"{anchor}{i}" for i in range(2, 9))) if a not in ids)
        ids.add(anchor)
        blocks.append(f"""          <section class="letter-group" aria-labelledby="{anchor}">
            <h2 id="{anchor}" class="letter-group__letter">{letter}</h2>
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
        <h1 id="list-title" class="h2">Zväzové rybárske revíry SRZ {ROK_REVIROV}</h1>
        <p class="list-hero__lead">{plural(n, 'Jeden', 'Všetky', 'Všetkých')} {n} kaprových a&nbsp;lipňových revírov SRZ s&nbsp;číslom revíru. Hľadajte podľa názvu toku, nádrže alebo čísla revíru.</p>
        <p class="list-hero__links">
          <a class="text-link text-link--sm" href="organizacie.html">Revíry podľa organizácie</a>
          <a class="text-link text-link--sm" href="toky.html">Revíry podľa toku</a>
        </p>
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
        "name": f"Zväzové rybárske revíry SRZ {ROK_REVIROV}",
        "numberOfItems": n,
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": r["name"], "url": f"{SITE}revir/{r['slug']}.html"}
            for i, r in enumerate(reviry)
        ],
    }
    return page(
        title=f"Zväzové rybárske revíry SRZ {ROK_REVIROV} – zoznam kaprových a lipňových revírov",
        og_title=f"Zväzové rybárske revíry SRZ {ROK_REVIROV}",
        description=(f"Zoznam všetkých {n} kaprových a lipňových zväzových revírov SRZ na rok {ROK_REVIROV} s číslami revírov. "
                     "Nájdite revír podľa názvu alebo čísla a pozrite si jeho polohu a popis."),
        canonical=f"{SITE}reviry.html", asset="", home="./", body=body, ld=ld, current="reviry",
        scripts=("assets/js/reviry-data.js", "assets/js/reviry.js"))


def org_groups(reviry):
    """Each organization of data/organizacie.json that looks after at least one revír -> its revíry,
    organizations in alphabetical order (a revír with two organizations is on both pages)."""
    names = set(load_json("organizacie.json").values())
    groups = {}
    for r in reviry:
        for o in r["organizations"]:
            if o in names:
                groups.setdefault(o, []).append(r)
    return dict(sorted(groups.items(), key=lambda kv: sort_key(kv[0])))


def tok_groups(reviry):
    """Each river (base name) with at least three revíry -> its stretches in order: č. 1, 1a, 1b, 2, ..."""
    groups = {}
    for r in reviry:
        groups.setdefault(r["base"], []).append(r)

    def stretch(r):
        m = re.match(r"\s*č\.\s*(\d+)([a-z]*)", r["name"][len(r["base"]):])
        return (int(m.group(1)), m.group(2), sort_key(r["name"])) if m else (0, "", sort_key(r["name"]))
    return {base: sorted(items, key=stretch) for base, items in sorted(groups.items(), key=lambda kv: sort_key(kv[0]))
            if len(items) >= 3}


def group_page(*, path, title, description, heading, lead, crumb, items, more, cta, count):
    """A list of revíry under one heading: an organization's revíry or all stretches of a river."""
    rows = "\n".join("          " + row(r, f"../revir/{r['slug']}.html", more(r)) for r in items)
    url = SITE + path
    body = f"""    <section class="list-hero" aria-labelledby="list-title">
      <div class="container">
        <nav class="crumbs" aria-label="Omrvinková navigácia">
          <ol>
            <li><a href="../">Domov</a></li>
            <li><a href="../reviry.html">Revíry</a></li>
            <li aria-current="page">{nbsp(crumb)}</li>
          </ol>
        </nav>
        <h1 id="list-title" class="h2">{heading}</h1>
        <p class="list-hero__lead">{lead}</p>
      </div>
    </section>

    <section class="revir-index revir-group" aria-label="Zoznam revírov">
      <div class="container">
        <ul class="revir-rows revir-rows--cols">
{rows}
        </ul>
      </div>
    </section>

{cta_band(cta, count)}"""
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ItemList",
                "name": html.unescape(re.sub(r"<[^>]+>", "", heading)),
                "numberOfItems": len(items),
                "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": r["name"], "url": f"{SITE}revir/{r['slug']}.html"}
                                    for i, r in enumerate(items)],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Domov", "item": SITE},
                    {"@type": "ListItem", "position": 2, "name": "Revíry", "item": SITE + "reviry.html"},
                    {"@type": "ListItem", "position": 3, "name": crumb, "item": url},
                ],
            },
        ],
    }
    return page(title=title, description=description, canonical=url, asset="../", home="../", body=body, ld=ld, current="revir")


def org_page(org, slug, items, count):
    n = len(items)
    revirov = plural(n, "zväzový revír", "zväzové revíry", "zväzových revírov")
    return group_page(
        path=f"organizacia/{slug}.html",
        title=f"Revíry {org} – zoznam zväzových revírov | Rybárske Revíry SK",
        description=(f"Zoznam {n} zväzových revírov, ktoré obhospodaruje {org}, s číslami revírov, typom vody "
                     "a odkazom na popis každého revíru." if n > 1 else
                     f"Zväzový revír, ktorý obhospodaruje {org}, s číslom revíru, typom vody a odkazom na popis revíru."),
        heading=f"Revíry, ktoré obhospodaruje {nbsp(org)}",
        lead=(f"{nbsp(org)} obhospodaruje {n} {revirov}. Pri každom nájdete číslo revíru, typ vody a&nbsp;popis. "
              "Presné hranice sú v&nbsp;aplikácii Rybárske Revíry SK."),
        crumb=org, items=items, more=lambda r: f" · {esc(r['water'].lower())}" if r["water"] else "",
        cta=f"organizacia-{slug}-cta", count=count)


def tok_page(tok, slug, items, count):
    n = len(items)
    return group_page(
        path=f"tok/{slug}.html",
        title=f"{tok} – rybárske revíry a čísla revírov | Rybárske Revíry SK",
        description=(f"Všetky zväzové revíry na toku {tok}: {n} {plural(n, 'úsek', 'úseky', 'úsekov')} s číslami revírov, "
                     "typom vody a organizáciou. Presné hranice úsekov v aplikácii Rybárske Revíry SK."),
        heading=f"{nbsp(tok)}: všetky revíry",
        lead=(f"Na toku {nbsp(tok)} {plural(n, 'je', 'sú', 'je')} {n} "
              f"{plural(n, 'zväzový revír', 'zväzové revíry', 'zväzových revírov')} SRZ. "
              "Každý úsek má vlastné číslo revíru a&nbsp;môže mať iné pravidlá lovu."),
        crumb=tok, items=items,
        more=lambda r: "".join(f" · {nbsp(x)}" for x in ([r["water"].lower()] if r["water"] else []) + r["organizations"]),
        cta=f"tok-{slug}-cta", count=count)


def overview_page(*, path, title, description, heading, lead, groups, slugs, folder, plain):
    """organizacie.html and toky.html: every organization or river with the number of its revíry."""
    rows = "\n".join(
        f'          <li><a class="revir-row{" revir-row--plain" if plain else ""}" href="{folder}/{slugs[name]}.html">'
        f'<span class="revir-row__name">{nbsp(name)}</span>'
        f'<span class="revir-row__num">{len(items)} {plural(len(items), "revír", "revíry", "revírov")}</span></a></li>'
        for name, items in groups.items())
    body = f"""    <section class="list-hero" aria-labelledby="list-title">
      <div class="container">
        <nav class="crumbs" aria-label="Omrvinková navigácia">
          <ol>
            <li><a href="./">Domov</a></li>
            <li><a href="reviry.html">Revíry</a></li>
            <li aria-current="page">{heading}</li>
          </ol>
        </nav>
        <h1 id="list-title" class="h2">{heading}</h1>
        <p class="list-hero__lead">{lead}</p>
      </div>
    </section>

    <section class="revir-index revir-group" aria-label="{heading}">
      <div class="container">
        <ul class="revir-rows revir-rows--cols">
{rows}
        </ul>
      </div>
    </section>"""
    ld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": heading,
        "numberOfItems": len(groups),
        "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": name, "url": f"{SITE}{folder}/{slugs[name]}.html"}
                            for i, name in enumerate(groups)],
    }
    return page(title=title, description=description, canonical=SITE + path, asset="", home="./", body=body, ld=ld, current="revir")


def note_page(*, title, heading, text, links, asset, home, canonical=None, head=""):
    """A short page that only says something and offers a way on: 404, a moved or a removed revír.
    None of them belongs in Google or in the sitemap."""
    actions = "\n".join(f'          <a class="btn-plain" href="{href}">{label}</a>' for label, href in links)
    para = f'\n        <p class="list-hero__lead">{text}</p>' if text else ""
    body = f"""    <section class="list-hero page-note" aria-labelledby="note-title">
      <div class="container">
        <h1 id="note-title" class="h2">{heading}</h1>{para}
        <div class="page-note__actions">
{actions}
        </div>
      </div>
    </section>"""
    return page(title=title, description=html.unescape(re.sub(r"<[^>]+>", "", text or heading)), canonical=canonical,
                asset=asset, home=home, body=body, current="revir", head=head, noindex=True)


def moved_page(new):
    """An old address of a revír that is now called differently: goes on to its page at once."""
    href = f"{new['slug']}.html"
    return note_page(
        title=f"{new['name']} | Rybárske Revíry SK", heading=f"Revír sa teraz volá {nbsp(new['name'])}.",
        text=f'Stránka revíru je na novej adrese: <a href="{href}">{nbsp(new["name"])}</a>.',
        links=[(f"Otvoriť revír {nbsp(new['name'])}", href), ("Zoznam revírov", "../reviry.html")],
        asset="../", home="../", canonical=f"{SITE}revir/{href}",
        head=f'<meta http-equiv="refresh" content="0; url={href}">')


def gone_page():
    return note_page(
        title="Revír už nie je v zozname | Rybárske Revíry SK",
        heading="Tento revír už v&nbsp;zozname zväzových revírov nie je.", text="",
        links=[("Zoznam revírov", "../reviry.html"), ("Domov", "../")], asset="../", home="../")


# The 404 page is shown at any address (/revir/neexistuje.html, also under /RybarskeReviry/ on GitHub
# Pages), so it sets <base> to the site's root before anything loads. Links to a section of the page
# itself (#main) would follow the <base> to the homepage, so they get the page's own address back.
# The browser fetches a page's files ahead of its scripts, from the address it was opened at, so the
# page's stylesheet, script and images go in only after <base> (not_found_assets)
NOT_FOUND_HEAD = ("<script>(function () { var b = document.createElement('base'); "
                  "b.href = location.pathname.indexOf('/RybarskeReviry/') === 0 ? '/RybarskeReviry/' : '/'; "
                  "document.head.appendChild(b); document.addEventListener('DOMContentLoaded', function () { "
                  "document.querySelectorAll('a[href^=\"#\"]').forEach(function (a) { "
                  "a.href = location.pathname + a.getAttribute('href'); }); "
                  "document.querySelectorAll('img[data-src]').forEach(function (i) { i.src = i.getAttribute('data-src'); }); "
                  "document.querySelectorAll('script[data-src]').forEach(function (s) { "
                  "var js = document.createElement('script'); js.src = s.getAttribute('data-src'); document.body.appendChild(js); }); "
                  "}); })();</script>")


def not_found_assets(content):
    """The 404 page's own files, written so that the browser asks for them only once <base> is set."""
    content = re.sub(r'<link rel="stylesheet" href="(assets/[^"]+)">',
                     r"""<script>document.write('<link rel="stylesheet" href="\1">')</script>""", content)
    content = re.sub(r'<img src="(assets/[^"]+)"', r'<img data-src="\1"', content)
    return re.sub(r'<script src="(assets/[^"]+)" defer></script>', r'<script data-src="\1"></script>', content)


def not_found_page():
    return note_page(
        title="Stránka sa nenašla | Rybárske Revíry SK", heading="Túto stránku sme nenašli",
        text="Revír mohol zmeniť názov alebo adresu. Nájdite ho v&nbsp;zozname podľa názvu alebo čísla.",
        links=[("Zoznam revírov", "reviry.html"), ("Domov", "./")], asset="", home="./", head=NOT_FOUND_HEAD)


def old_addresses(reviry):
    """Adds today's addresses to data/adresy-revirov.json and returns the file's new content plus a page
    for every address a revír no longer uses: a redirect to its new name, or a note that it's gone."""
    known = json.loads(ADDRESSES.read_text(encoding="utf-8")) if ADDRESSES.is_file() else {}
    comment = known.pop("_comment", "Číslo revíru -> všetky adresy (revir/<adresa>.html), ktoré revír kedy mal. "
                                    "Dopĺňa ho tools/build_reviry.py, nič nemažte.")
    for r in reviry:
        slugs = known.setdefault(r["number"], [])
        if r["slug"] not in slugs:
            slugs.append(r["slug"])
    current = {r["slug"] for r in reviry}
    by_number = {r["number"]: r for r in reviry}
    pages = {}
    for number, slugs in known.items():
        for slug in slugs:
            path = f"revir/{slug}.html"
            if slug in current or path in pages:
                continue
            pages[path] = moved_page(by_number[number]) if number in by_number else gone_page()
    lines = [f"  {json.dumps('_comment')}: {json.dumps(comment, ensure_ascii=False)}"]
    lines += [f"  {json.dumps(number)}: {json.dumps(known[number], ensure_ascii=False)}" for number in sorted(known)]
    return "{\n" + ",\n".join(lines) + "\n}\n", pages


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
    orgs, toky = org_groups(reviry), tok_groups(reviry)
    org_slugs = {o: slugify(o) for o in orgs}
    tok_slugs = {t: slugify(t) for t in toky}
    if len(set(org_slugs.values())) != len(org_slugs) or len(set(tok_slugs.values())) != len(tok_slugs):
        raise SystemExit("Chyba: dve organizácie alebo dva toky by mali rovnakú adresu stránky, nič sa nezapísalo.")
    files = {f"revir/{r['slug']}.html": detail_page(r, reviry, org_slugs, tok_slugs) for r in reviry}
    files["data/adresy-revirov.json"], moved = old_addresses(reviry)
    files.update(moved)
    files["reviry.html"] = list_page(reviry)
    files["404.html"] = not_found_page()
    for o, items in orgs.items():
        files[f"organizacia/{org_slugs[o]}.html"] = org_page(o, org_slugs[o], items, len(reviry))
    for t, items in toky.items():
        files[f"tok/{tok_slugs[t]}.html"] = tok_page(t, tok_slugs[t], items, len(reviry))
    files["organizacie.html"] = overview_page(
        path="organizacie.html", title="Rybárske revíry podľa organizácie SRZ | Rybárske Revíry SK",
        description=(f"Zväzové revíry SRZ podľa organizácie, ktorá ich obhospodaruje: {len(orgs)} organizácií, "
                     "pri každej počet revírov a zoznam revírov s číslami."),
        heading="Revíry podľa organizácie SRZ",
        lead="Zväzové revíry podľa organizácie SRZ, ktorá ich obhospodaruje. Pri každej nájdete zoznam jej revírov s&nbsp;číslami revírov.",
        groups=orgs, slugs=org_slugs, folder="organizacia", plain=True)
    files["toky.html"] = overview_page(
        path="toky.html", title="Rybárske revíry podľa toku – Váh, Hron, Dunaj a ďalšie | Rybárske Revíry SK",
        description=(f"Zväzové revíry SRZ podľa toku: {len(toky)} tokov s aspoň tromi revírmi, pri každom zoznam úsekov "
                     "s číslami revírov, typom vody a organizáciou."),
        heading="Revíry podľa toku",
        lead="Toky, na ktorých sú aspoň tri zväzové revíry SRZ. Pri každom nájdete všetky jeho úseky s&nbsp;číslami revírov.",
        groups=toky, slugs=tok_slugs, folder="tok", plain=False)
    index = [{"n": r["name"], "c": r["number"], "t": TYPES[r["type"]]["code"], "s": r["slug"], "k": search_key(r)} for r in reviry]
    files["assets/js/reviry-data.js"] = ("// Generated by tools/build_reviry.py: names and numbers for the revír search\nwindow.RR_REVIRY = "
                                         + json.dumps(index, ensure_ascii=False, separators=(",", ":")) + ";\n")
    urls = ([SITE, SITE + "reviry.html", SITE + "privacy_policy.html"] + [f"{SITE}revir/{r['slug']}.html" for r in reviry]
            + [SITE + "organizacie.html"] + [f"{SITE}organizacia/{s}.html" for s in org_slugs.values()]
            + [SITE + "toky.html"] + [f"{SITE}tok/{s}.html" for s in tok_slugs.values()])
    files["sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                            + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    files["robots.txt"] = f"User-agent: *\nAllow: /\n\nSitemap: {SITE}sitemap.xml\n"

    # CSS and JS links carry ?v=<content hash>: a changed file gets a new address, so browsers (and
    # the site preview) load it instead of an old cached copy. The hand-written pages are kept current too
    for path in ("index.html", "privacy_policy.html"):
        files[path] = (ROOT / path).read_text(encoding="utf-8")
    # The number of revíry on the homepage follows the database: "349 kaprových…", "spolu 349."
    files["index.html"] = re.sub(r"\d+(?=(?: |&nbsp;)kaprových)|(?<=spolu )\d+(?=\.)", str(len(reviry)), files["index.html"])
    versions = {}
    for path in ("assets/css/style.css", "assets/js/main.js", "assets/js/reviry.js", "assets/js/reviry-data.js"):
        content = files.get(path) or (ROOT / path).read_text(encoding="utf-8")
        versions[path] = hashlib.sha1(content.encode("utf-8")).hexdigest()[:8]
    asset_link = re.compile(r'(assets/(?:css|js)/[\w.-]+\.(?:css|js))(?:\?v=\w+)?"')
    stamp = lambda m: f'{m.group(1)}?v={versions[m.group(1)]}"' if m.group(1) in versions else m.group(0)
    for path in [p for p in files if p.endswith(".html")]:
        files[path] = asset_link.sub(stamp, files[path])
    files["404.html"] = not_found_assets(files["404.html"])

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
    # Pages of organizations and rivers carry no coordinates at all, not even ones the database doesn't know
    for path, content in files.items():
        if path.startswith(("organizacia/", "tok/")) or path in ("organizacie.html", "toky.html"):
            if re.search(r"\b\d{1,2}\.\d{4,}\b", content):
                raise SystemExit(f"Chyba: v {path} sú súradnice, nič sa nezapísalo.")

    # A folder holds only what this build made: an organization or river that is gone loses its page.
    # A revír never does, its old addresses stay (data/adresy-revirov.json)
    for folder in ("revir", "organizacia", "tok"):
        out_dir = ROOT / folder
        out_dir.mkdir(exist_ok=True)
        keep = {Path(p).name for p in files if p.startswith(folder + "/")}
        for old in out_dir.glob("*.html"):
            if old.name not in keep:
                old.unlink()
    for path, content in files.items():
        target = ROOT / path
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")
    kapr = sum(r["type"] == "kaprovy" for r in reviry)
    print(f"{len(reviry)} revírov ({kapr} kaprových, {len(reviry) - kapr} lipňových), {len(moved)} starých adries, "
          f"{len(orgs)} organizácií, {len(toky)} tokov: reviry.html, revir/*.html, organizacie.html, organizacia/*.html, "
          "toky.html, tok/*.html, 404.html, assets/js/reviry-data.js, data/adresy-revirov.json, sitemap.xml, robots.txt, "
          "počet revírov a verzie CSS a JS v index.html a privacy_policy.html")


if __name__ == "__main__":
    main()
