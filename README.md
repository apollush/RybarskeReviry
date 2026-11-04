# rybarskereviry.sk

Web Android aplikácie **Rybárske Revíry SK**. Je to statická stránka v čistom HTML, CSS a JavaScripte bez build kroku: súbory sa nahrajú na server tak, ako sú.

## Štruktúra

| Cesta | Čo obsahuje |
|---|---|
| `index.html` | Úvodná stránka |
| `reviry.html` | Zoznam revírov s vyhľadávaním (generovaný) |
| `revir/*.html` | Stránka každého revíru (generované). Stará adresa premenovaného revíru presmeruje na novú, pri zrušenom revíri povie, že už v zozname nie je. |
| `organizacie.html`, `organizacia/*.html` | Revíry podľa organizácie, ktorá ich obhospodaruje (generované, bez súradníc) |
| `toky.html`, `tok/*.html` | Všetky úseky toku, ktorý má aspoň tri revíry (generované, bez súradníc) |
| `404.html` | Stránka pre neexistujúcu adresu (generovaná). Na Websupporte ju zapne `.htaccess`, GitHub Pages ju použije sám. |
| `privacy_policy.html` | Ochrana súkromia. Adresu nemeňte, odkazuje na ňu Google Play. |
| `assets/` | Štýly, skripty, ikony a snímky obrazovky aplikácie. `assets/img/og-image.jpg` je obrázok pri zdieľaní odkazu, vzniká z `tools/og-image.html`. |
| `data/adresy-revirov.json` | Všetky adresy, ktoré revír kedy mal (číslo revíru → adresy). Dopĺňa ho generátor, nič z neho nemažte. |
| `data/organizacie.json` | Ako sa na webe volajú organizácie, ktoré revíry obhospodarujú |
| `data/slovensko.json` | Mapa Slovenska na stránke revíru: hranica štátu, Dunaj a krajské mestá |
| `data/sidla.json` | Mestá a obce, ktoré sa ukážu na priblíženej mape revíru (ručne zadané, približné súradnice) |
| `tools/build_reviry.py` | Generátor stránok revírov |
| `tools/aktualizuj-reviry.command` | Prebuduje stránky revírov a nahrá ich na GitHub |
| `sitemap.xml`, `robots.txt` | Pre vyhľadávače (generované) |

## Databáza revírov je súkromná

Stránky revírov vznikajú z databázy aplikácie `reviry.xml`. Tá **nie je v tomto repozitári ani na webe**. Leží vedľa projektu v priečinku `RybarskeReviry-databaza/reviry.xml`. Na web sa z nej dostane len to, čo je vidieť na stránke revíru: názov, číslo, charakter a typ vody, organizácia, rozloha, popis a poloha revíru (jeden bod na mape Slovenska a GPS súradnice, nie hranice revíru). Každá stránka revíru obsahuje len súradnice svojho revíru. Zoznam revírov, vyhľadávanie a sitemap žiadne súradnice nemajú, takže celá databáza nie je pokope v žiadnom súbore. Generátor to pred zápisom kontroluje.

## Aktualizácia revírov

Po nahradení `RybarskeReviry-databaza/reviry.xml` novou verziou spustite dvojklikom `tools/aktualizuj-reviry.command`. Prebuduje stránky revírov a nahrá ich na GitHub.

Ručne, bez nahrania na GitHub (stačí Python 3, bez ďalších balíkov):

```bash
python3 tools/build_reviry.py
```

Iné umiestnenie databázy: `python3 tools/build_reviry.py --xml /cesta/k/reviry.xml`. Generované súbory needitujte ručne.

## Zverejnený web

Web beží zadarmo na GitHub Pages: https://apollush.github.io/RybarskeReviry/. GitHub ho zverejní znova pri každom nahraní do vetvy `main`, zvyčajne do dvoch minút. Prázdny súbor `.nojekyll` zabezpečí, že GitHub súbory zverejní bez úprav. Doména rybarskereviry.sk na tento web zatiaľ nesmeruje.

## Cenník a iPhone (prepínače)

Na začiatku `tools/build_reviry.py` sú prepínače. Generátor podľa nich zostaví všetky ceny a tlačidlá do obchodov na všetkých stránkach. V `index.html` a `privacy_policy.html` prepisuje časti medzi značkami `<!-- gen:… -->` a `<!-- /gen:… -->`, tie preto ručne neupravujte.

| Prepínač | Čo robí |
|---|---|
| `CENNIK` | `"jednorazovo"` = dnešných 6,99 € v Google Play. `"novy"` = zadarmo + Plná verzia za 5,99 € ročne alebo 14,99 € navždy. Nový zapnite až v deň, keď ho má aj aplikácia v Google Play. |
| `APP_STORE_URL` | Odkaz na aplikáciu v App Store. Prázdny = na iPhone a iPade tlačidlá ponúkajú e-mail („Na iPhone čoskoro“). Vyplnený = tlačidlá do App Store aj Google Play, telefón vidí len svoj obchod, počítač oba. |
| `APP_STORE_ID` | Číslo aplikácie v App Store pre banner v Safari. |
| `APP_STORE_PT` | Provider token z App Store Connect, aby bolo vidno, odkiaľ ľudia prišli (`ct` je miesto na webe). |
| `APP_STORE_PREDOBJEDNAVKA` | `True`, kým je v App Store len predobjednávka: tlačidlo „Predobjednať v App Store“. |
| `CENA_JEDNORAZOVO`, `CENA_ROCNE`, `CENA_NAVZDY` | Ceny s DPH. Na webe sa píšu len odtiaľto. |

Po zmene prepínača spustite dvojklikom `tools/aktualizuj-reviry.command`. Web prebuduje a nahrá na GitHub.

## Lokálny náhľad

```bash
python3 -m http.server 8080
```

Potom otvorte http://localhost:8080.
