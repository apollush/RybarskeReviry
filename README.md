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
| `data/organizacie.json` | Ako sa na webe volajú organizácie, ktoré revíry obhospodarujú |
| `data/obrysy.json` | Tvar revíru na jeho stránke (zatiaľ len VN Liptovská Mara) |
| `tools/build_reviry.py` | Generátor stránok revírov |
| `tools/aktualizuj-reviry.command` | Prebuduje stránky revírov a nahrá ich na GitHub |
| `sitemap.xml`, `robots.txt` | Pre vyhľadávače (generované) |

## Databáza revírov je súkromná

Stránky revírov vznikajú z databázy aplikácie `reviry.xml`. Tá **nie je v tomto repozitári ani na webe**. Leží vedľa projektu v priečinku `RybarskeReviry-databaza/reviry.xml`. Na web sa z nej dostane len to, čo je vidieť na stránke revíru: názov, číslo, charakter a typ vody, organizácia, rozloha a popis. Súradnice revírov sa nezverejňujú: generátor ich použije len na výber revírov v okolí a pred zápisom skontroluje, že sa do stránok nedostali.

## Aktualizácia revírov

Po nahradení `RybarskeReviry-databaza/reviry.xml` novou verziou sa web aktualizuje sám: úloha `sk.rybarskereviry.databaza` v `~/Library/LaunchAgents` otvorí v Termináli `tools/aktualizuj-reviry.command`. Ten prebuduje stránky revírov a nahrá ich na GitHub. Skript sa dá spustiť aj dvojklikom.

Ručne, bez nahrania na GitHub (stačí Python 3, bez ďalších balíkov):

```bash
python3 tools/build_reviry.py
```

Iné umiestnenie databázy: `python3 tools/build_reviry.py --xml /cesta/k/reviry.xml`. Generované súbory needitujte ručne.

## Lokálny náhľad

```bash
python3 -m http.server 8080
```

Potom otvorte http://localhost:8080.
