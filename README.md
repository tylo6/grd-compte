# Carte Grands Comptes — Antea Group

Carte interactive des 26 Grands Comptes d'Antea Group en France.
Fichier HTML autonome (zéro CDN externe), publiable sur GitHub Pages ou Cloudflare Pages.

---

## Structure du projet

```
carte-grd-compte/
├── data/
│   └── sites.csv              ← Source de données (éditer ici)
├── scripts/
│   └── generate_map.py        ← Script de génération
├── index.html                 ← Fichier généré (ne pas éditer manuellement)
├── leaflet_embedded.css       ← CSS Leaflet patché (images base64)
├── node_modules/leaflet/      ← Leaflet.js (installé via npm)
└── README.md
```

---

## 1. Mise à jour des données

1. Ouvrir `data/sites.csv` (Excel, LibreOffice ou éditeur texte)
2. Modifier ou ajouter des lignes en respectant les colonnes :
   ```
   nom, adresse, code_postal, ville, secteur_activite,
   responsable_dcf, url_site, lat, lng, lien_sharepoint, statut, effectif
   ```
3. Pour les nouveaux sites **sans coordonnées GPS** : laisser `lat` et `lng` vides
   → le script géocodera automatiquement via Nominatim (1 req/s, bounding box France)
4. Pour le champ `statut` : utiliser `Standard` ou `Prioritaire`
5. Lancer la génération :
   ```bash
   python3 scripts/generate_map.py
   ```
6. Vérifier `index.html` en l'ouvrant dans Chrome ou Firefox
7. Pousser les modifications :
   ```bash
   git add . && git commit -m "MAJ données grands comptes" && git push
   ```

---

## 2. Premier setup (une seule fois)

Si vous clonez ce repo sur une nouvelle machine, installez Leaflet et patchez le CSS :

```bash
# Installer Node.js via NVM si nécessaire
# Puis :
export PATH="$HOME/.nvm/versions/node/$(ls ~/.nvm/versions/node | tail -1)/bin:$PATH"
npm install leaflet

# Patcher le CSS (embarquer les images PNG en base64)
for img in marker-icon marker-icon-2x marker-shadow layers layers-2x; do
    B64=$(base64 -i node_modules/leaflet/dist/images/${img}.png | tr -d '\n')
    sed -i '' "s|url(images/${img}.png)|url(data:image/png;base64,${B64})|g" \
        node_modules/leaflet/dist/leaflet.css
done
cp node_modules/leaflet/dist/leaflet.css leaflet_embedded.css

# Vérification (doit retourner 0)
grep -c "url(images/" leaflet_embedded.css

# Générer la carte
python3 scripts/generate_map.py
```

---

## 3. Activation GitHub Pages (accès public)

1. Pousser le repo sur GitHub
2. Aller dans **Settings → Pages**
3. Source : branche `main`, dossier `/` (root)
4. Cliquer sur **Save**
5. URL résultante : `https://[username].github.io/[nom-repo]/`

Le fichier `index.html` est servi directement — aucun build requis.

---

## 4. Option accès restreint — Cloudflare Pages

Pour un accès limité aux collaborateurs Antea (protection par email) :

1. Aller sur [dashboard.cloudflare.com](https://dashboard.cloudflare.com) → **Pages**
2. Connecter le repo GitHub
3. Build settings :
   - Commande de build : *(laisser vide)*
   - Répertoire de publication : `/`
4. Déployer — URL résultante : `https://grands-comptes-map.pages.dev`
5. Pour restreindre l'accès :
   - **Zero Trust → Access → Applications → Add an application**
   - Choisir "Self-hosted"
   - Domaine : `grands-comptes-map.pages.dev`
   - Ajouter une policy : Login via **One-time PIN** (email `@antea-group.com`)

---

## 5. Ajouter un lien SharePoint à un grand compte

1. Ouvrir `data/sites.csv`
2. Trouver la ligne du grand compte concerné
3. Coller l'URL SharePoint dans la colonne `lien_sharepoint`
   ```
   ORANO,...,https://anteagroup.sharepoint.com/sites/GC-ORANO,...
   ```
4. Relancer la génération :
   ```bash
   python3 scripts/generate_map.py
   ```
5. Pousser le commit

Le bouton **📁 Dossier Grand Compte** apparaît automatiquement dans la popup du marqueur.

---

## Fonctionnalités de la carte

- **26 marqueurs colorés** — une couleur distincte par grand compte, icône par secteur
- **Barre de recherche** — filtre en temps réel sur nom, ville, secteur
- **Filtre secteur** et **filtre statut** (Standard / Prioritaire)
- **Légende interactive** — clic pour masquer/afficher un compte
- **Compteur dynamique** mis à jour à chaque filtre
- **Bouton Recentrer** — retour vue France entière
- **Popup détaillée** — responsable DCF, effectif, lien web, dossier SharePoint

## Notes techniques

- `index.html` est **100 % autonome** : zéro CDN, zéro dépendance externe en JS/CSS
- Seule dépendance réseau : les tuiles CartoDB (fond de carte, chargées à la demande)
- Compatible `file://` local, GitHub Pages, Cloudflare Pages
- Encodage UTF-8 — accents français supportés
- Taille : ~190 Ko
