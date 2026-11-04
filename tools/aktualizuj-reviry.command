#!/bin/sh
# Prebuduje stránky revírov zo súkromnej databázy (../RybarskeReviry-databaza/reviry.xml) a nahrá ich na GitHub.
# Spustí sa sám, keď sa databáza zmení (úloha sk.rybarskereviry.databaza v ~/Library/LaunchAgents),
# alebo dvojklikom (aj po zmene prepínača cenníka alebo App Store v build_reviry.py). Commitne len
# vygenerované stránky a samotný generátor, nič iné.

cd "$(dirname "$0")/.." || exit 1
echo "Aktualizujem stránky revírov z databázy…"
if ! python3 tools/build_reviry.py; then
  echo "Web sa neaktualizoval, pozrite chybu vyššie."
  exit 1
fi

git add reviry.html revir organizacie.html organizacia toky.html tok 404.html assets/js/reviry-data.js \
  data/adresy-revirov.json sitemap.xml robots.txt index.html privacy_policy.html tools/build_reviry.py
if git diff --cached --quiet; then
  echo "Stránky revírov sú aktuálne, nie je čo nahrať."
else
  count=$(git diff --cached --name-only | wc -l | tr -d ' ')
  git commit -q -m "Aktualizácia webu ($count súborov)"
fi

if [ -n "$(git log '@{u}..HEAD' --oneline 2>/dev/null)" ]; then
  if GIT_TERMINAL_PROMPT=0 git push -q; then
    echo "Hotovo: zmeny sú na GitHube."
  else
    echo "Nahratie na GitHub zlyhalo. Zmeny sú uložené v počítači a nahrajú sa nabudúce."
    exit 1
  fi
fi
