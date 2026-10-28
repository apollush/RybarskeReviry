# rybarskereviry.sk

Web Android aplikácie **Rybárske Revíry SK**. Je to statická stránka v čistom HTML, CSS a JavaScripte bez build kroku: súbory sa nahrajú na server tak, ako sú.

## Štruktúra

| Cesta | Čo obsahuje |
|---|---|
| `index.html` | Úvodná stránka |
| `reviry.html` | Zoznam revírov s vyhľadávaním (generovaný) |
| `revir/*.html` | Stránka každého revíru (generované) |
| `privacy_policy.html` | Ochrana súkromia. Adresu nemeňte, odkazuje na ňu Google Play. |
| `assets/` | Štýly, skripty, ikony a snímky obrazovky aplikácie |
| `data/reviry.json` | Údaje o revíroch, zdroj pre generované stránky |
| `tools/build_reviry.py` | Generátor stránok revírov |
| `sitemap.xml`, `robots.txt` | Pre vyhľadávače (generované) |

## Stránky revírov

Po zmene `data/reviry.json` spustite (stačí Python 3, bez ďalších balíkov):

```bash
python3 tools/build_reviry.py
```

Skript nanovo vytvorí `reviry.html`, `revir/*.html`, `assets/js/reviry-data.js`, `sitemap.xml` a `robots.txt`. Generované súbory needitujte ručne.

V `data/reviry.json` je zatiaľ 39 ukážkových revírov a `"demo": true`. Po doplnení všetkých revírov z aplikácie nastavte `"demo": false`, čím zmiznú ukážkové poznámky.

## Lokálny náhľad

```bash
python3 -m http.server 8080
```

Potom otvorte http://localhost:8080.
