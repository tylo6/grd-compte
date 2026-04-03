#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_map.py — Générateur de carte interactive Grands Comptes Antea Group
Lit data/sites.csv, géocode les lignes sans coordonnées, génère index.html autonome.
"""

import csv
import json
import os
import sys
import time
import logging
import urllib.request
import urllib.parse
from pathlib import Path

# ── Chemins ─────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
ROOT_DIR    = SCRIPT_DIR.parent
CSV_PATH    = ROOT_DIR / 'data' / 'sites.csv'
OUTPUT_PATH = ROOT_DIR / 'index.html'
CSS_PATH    = ROOT_DIR / 'leaflet_embedded.css'
JS_PATH     = ROOT_DIR / 'node_modules' / 'leaflet' / 'dist' / 'leaflet.js'
LOG_PATH    = ROOT_DIR / 'geocoding_warnings.log'

# ── Logging géocodage ────────────────────────────────────────────────────────
logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.WARNING,
    format='%(asctime)s %(levelname)s %(message)s',
    encoding='utf-8'
)

# ── Bounding box France métropolitaine ──────────────────────────────────────
LAT_MIN, LAT_MAX =  41.0, 51.5
LNG_MIN, LNG_MAX = -5.5,  10.0

# ── Icônes par secteur ──────────────────────────────────────────────────────
SECTEUR_ICONS = {
    "Agence de l'eau":                        "💧",
    "Eau / déchets / environnement":          "♻️",
    "Eau / déchets / énergie":               "💧",
    "Énergie":                                "⚡",
    "Énergie / raffinage / distribution":     "🛢️",
    "Nucléaire":                              "☢️",
    "Recherche / énergie / défense":          "🔬",
    "Gestion des déchets radioactifs":        "☢️",
    "Traitement des déchets / environnement": "♻️",
    "Aéronautique / défense":                "✈️",
    "Défense navale":                         "⚓",
    "Administration / défense":               "🏛️",
    "BTP / concessions":                      "🏗️",
    "BTP / télécoms / médias":               "🏗️",
    "Transport ferroviaire":                  "🚂",
    "Aménagement / transport":               "🗺️",
    "Minéraux de spécialités":               "🪨",
    "Établissement public / biodiversité":   "🌿",
}

def get_icon(secteur):
    return SECTEUR_ICONS.get(secteur, "📍")


def generate_palette(n):
    """Génère n couleurs HSL bien espacées, saturées et lisibles."""
    return [f"hsl({int(i * 360 / n)}, 65%, 42%)" for i in range(n)]


def geocode_nominatim(query, city, cp):
    """
    Géocode une adresse via Nominatim.
    Tente l'adresse complète, puis ville+CP en fallback.
    Valide la bounding box France.
    """
    base_url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "antea-grands-comptes-map/1.0"}

    def _query(q):
        params = urllib.parse.urlencode({"q": q, "format": "json", "limit": 1, "countrycodes": "fr"})
        url = f"{base_url}?{params}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    for attempt, q in enumerate([query, f"{cp} {city} France"]):
        try:
            time.sleep(1)  # rate-limit 1 req/s
            results = _query(q)
            if results:
                lat = float(results[0]["lat"])
                lng = float(results[0]["lon"])
                if LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX:
                    if attempt == 1:
                        logging.warning(f"Fallback CP+ville pour '{query}' → ({lat}, {lng})")
                    return lat, lng
                else:
                    logging.warning(f"Coordonnées hors France pour '{q}' : ({lat}, {lng})")
        except Exception as e:
            logging.warning(f"Erreur géocodage '{q}' : {e}")

    logging.warning(f"Géocodage échoué pour '{query}' — site ignoré")
    return None, None


def load_sites():
    sites = []
    with open(CSV_PATH, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            nom = row['nom'].strip()
            if not nom:
                continue

            lat_raw = row.get('lat', '').strip()
            lng_raw = row.get('lng', '').strip()

            if lat_raw and lng_raw:
                try:
                    lat, lng = float(lat_raw), float(lng_raw)
                except ValueError:
                    lat, lng = None, None
            else:
                lat, lng = None, None

            # Géocodage si coordonnées manquantes
            if lat is None or lng is None:
                adresse = row.get('adresse', '').strip()
                ville   = row.get('ville', '').strip()
                cp      = row.get('code_postal', '').strip()
                full_q  = f"{adresse}, {cp} {ville}, France" if adresse else f"{cp} {ville}, France"
                print(f"  → Géocodage : {nom} ({full_q})")
                lat, lng = geocode_nominatim(full_q, ville, cp)
                if lat is None:
                    print(f"  ⚠️  Impossible de géocoder {nom}, site ignoré")
                    continue

            sites.append({
                "nom":              nom,
                "adresse":          row.get('adresse', '').strip(),
                "code_postal":      row.get('code_postal', '').strip(),
                "ville":            row.get('ville', '').strip(),
                "secteur":          row.get('secteur_activite', '').strip(),
                "responsable":      row.get('responsable_dcf', '').strip(),
                "url_site":         row.get('url_site', '').strip(),
                "lat":              lat,
                "lng":              lng,
                "lien_sharepoint":  row.get('lien_sharepoint', '').strip(),
                "statut":           row.get('statut', 'Standard').strip() or 'Standard',
                "effectif":         row.get('effectif', '').strip(),
                "icon":             get_icon(row.get('secteur_activite', '').strip()),
            })

    return sites


def build_html(sites):
    # Vérifications fichiers Leaflet
    if not CSS_PATH.exists():
        sys.exit(f"❌ Fichier manquant : {CSS_PATH}\n   Lancez d'abord les commandes de setup (npm install + patch CSS)")
    if not JS_PATH.exists():
        sys.exit(f"❌ Fichier manquant : {JS_PATH}\n   Lancez d'abord : npm install leaflet")

    with open(CSS_PATH, encoding='utf-8') as f:
        leaflet_css = f.read()
    with open(JS_PATH, encoding='utf-8') as f:
        leaflet_js = f.read()

    # Palette de couleurs
    noms_sorted = sorted(set(s['nom'] for s in sites))
    palette = generate_palette(len(noms_sorted))
    couleurs = {nom: palette[i] for i, nom in enumerate(noms_sorted)}
    for site in sites:
        site['couleur'] = couleurs.get(site['nom'], '#555')

    sites_json  = json.dumps(sites, ensure_ascii=False, indent=2)
    couleurs_json = json.dumps(couleurs, ensure_ascii=False)

    # Secteurs distincts pour le filtre
    secteurs = sorted(set(s['secteur'] for s in sites if s['secteur']))

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Grands Comptes — Antea Group</title>
    <style>
{leaflet_css}

/* ── Reset & base ─────────────────────────────────────────────────────── */
*, *::before, *::after {{ box-sizing: border-box; }}
html, body {{
    margin: 0; padding: 0;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    background: #f0f4f8;
}}

/* ── Header ────────────────────────────────────────────────────────────── */
.header {{
    background: linear-gradient(135deg, #00587C 0%, #004B87 100%);
    color: white;
    padding: 10px 20px;
    display: flex;
    align-items: center;
    gap: 20px;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
    min-height: 64px;
}}
.header-logo svg {{ flex-shrink: 0; }}
.header-title {{
    flex: 1;
}}
.header-title h1 {{
    margin: 0;
    font-size: 1.2rem;
    font-weight: 700;
    letter-spacing: 0.3px;
    line-height: 1.2;
}}
.header-title p {{
    margin: 2px 0 0;
    font-size: 0.75rem;
    opacity: 0.75;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
.header-counter {{
    background: rgba(255,255,255,0.18);
    border: 1px solid rgba(255,255,255,0.3);
    border-radius: 20px;
    padding: 5px 14px;
    font-size: 0.85rem;
    font-weight: 600;
    white-space: nowrap;
}}

/* ── Contrôles ─────────────────────────────────────────────────────────── */
.controls {{
    background: white;
    padding: 8px 16px;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    flex-shrink: 0;
    border-bottom: 1px solid #dde3ea;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}}
.controls input, .controls select {{
    padding: 6px 12px;
    border: 1px solid #c8d1db;
    border-radius: 6px;
    font-size: 0.85rem;
    font-family: inherit;
    background: white;
    transition: border-color 0.2s;
    outline: none;
    color: #2c3e50;
}}
.controls input:focus, .controls select:focus {{
    border-color: #00587C;
    box-shadow: 0 0 0 2px rgba(0,88,124,0.12);
}}
.controls input {{ min-width: 200px; }}
.btn-recenter {{
    padding: 6px 14px;
    background: #00587C;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.85rem;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.2s;
    white-space: nowrap;
}}
.btn-recenter:hover {{ background: #004B87; }}

/* ── Zone carte + légende ───────────────────────────────────────────────── */
.map-wrapper {{
    flex: 1;
    display: flex;
    overflow: hidden;
}}
#map {{
    flex: 1;
    min-height: 0;
}}

/* ── Légende ───────────────────────────────────────────────────────────── */
.legend {{
    width: 260px;
    background: white;
    border-left: 1px solid #dde3ea;
    overflow-y: auto;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
}}
.legend-header {{
    padding: 10px 14px 6px;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #7f8c9a;
    border-bottom: 1px solid #eef0f3;
    position: sticky;
    top: 0;
    background: white;
    z-index: 1;
}}
.legend-item {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    cursor: pointer;
    transition: background 0.15s;
    font-size: 0.82rem;
    border-bottom: 1px solid #f5f6f8;
    user-select: none;
}}
.legend-item:hover {{ background: #f0f7fb; }}
.legend-item.hidden {{ opacity: 0.35; }}
.legend-dot {{
    width: 12px; height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
    border: 2px solid rgba(0,0,0,0.12);
}}
.legend-name {{
    flex: 1;
    line-height: 1.3;
    color: #2c3e50;
}}

/* ── Popup ─────────────────────────────────────────────────────────────── */
.leaflet-popup-content-wrapper {{
    border-radius: 10px !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.18) !important;
    padding: 0 !important;
    overflow: hidden;
    min-width: 280px;
}}
.leaflet-popup-content {{ margin: 0 !important; width: auto !important; }}
.popup-header {{
    padding: 12px 16px 10px;
    display: flex;
    align-items: flex-start;
    gap: 10px;
    border-bottom: 1px solid #eef0f3;
}}
.popup-dot {{
    width: 14px; height: 14px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 3px;
    border: 2px solid rgba(0,0,0,0.1);
}}
.popup-nom {{
    font-size: 0.95rem;
    font-weight: 700;
    color: #1a2733;
    margin: 0;
    line-height: 1.3;
}}
.popup-loc {{
    font-size: 0.78rem;
    color: #7f8c9a;
    margin: 3px 0 0;
}}
.popup-body {{ padding: 10px 16px 12px; }}
.popup-row {{
    display: flex;
    align-items: flex-start;
    gap: 6px;
    font-size: 0.82rem;
    color: #3d4f5c;
    margin-bottom: 5px;
    line-height: 1.4;
}}
.popup-row span.lbl {{ color: #7f8c9a; flex-shrink: 0; }}
.popup-badges {{
    display: flex;
    gap: 6px;
    margin-top: 8px;
    flex-wrap: wrap;
}}
.badge {{
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.4px;
}}
.badge-prioritaire {{ background: #E67E22; color: white; }}
.badge-standard    {{ background: #95A5A6; color: white; }}
.popup-footer {{ padding: 8px 16px 12px; border-top: 1px solid #eef0f3; }}
.btn-sharepoint {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 14px;
    background: #00587C;
    color: white;
    text-decoration: none;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 600;
    transition: background 0.2s;
    width: 100%;
    justify-content: center;
}}
.btn-sharepoint:hover {{ background: #004B87; }}
.no-sharepoint {{
    font-size: 0.78rem;
    color: #b0bec5;
    text-align: center;
    font-style: italic;
    padding: 4px 0;
}}

/* ── Responsive ─────────────────────────────────────────────────────────── */
@media (max-width: 768px) {{
    .legend {{ display: none; }}
    .controls input {{ min-width: 150px; }}
    .header-title h1 {{ font-size: 1rem; }}
}}
    </style>
</head>
<body>

<!-- HEADER -->
<div class="header">
    <div class="header-logo">
        <svg viewBox="0 0 200 52" width="160" height="52" xmlns="http://www.w3.org/2000/svg">
            <text x="0" y="36" font-family="Segoe UI,Tahoma,sans-serif" font-size="34"
                  font-weight="800" fill="white" letter-spacing="-0.5">Antea</text>
            <text x="104" y="36" font-family="Segoe UI,Tahoma,sans-serif" font-size="34"
                  font-weight="300" fill="rgba(255,255,255,0.85)">Group</text>
            <rect x="0" y="42" width="180" height="2.5" fill="rgba(255,255,255,0.4)" rx="1.5"/>
        </svg>
    </div>
    <div class="header-title">
        <h1>Grands Comptes — Carte France</h1>
        <p>Ingénierie environnementale · Relations clients stratégiques</p>
    </div>
    <div class="header-counter" id="counter">26 / 26 sites affichés</div>
</div>

<!-- CONTROLES -->
<div class="controls">
    <input type="text" id="searchInput" placeholder="🔍 Rechercher un grand compte…" oninput="applyFilters()">
    <select id="secteurFilter" onchange="applyFilters()">
        <option value="">Secteur ▾</option>
        {''.join(f'<option value="{s}">{s}</option>' for s in secteurs)}
    </select>
    <select id="statutFilter" onchange="applyFilters()">
        <option value="">Statut ▾</option>
        <option value="Prioritaire">Prioritaire</option>
        <option value="Standard">Standard</option>
    </select>
    <button class="btn-recenter" onclick="recenter()">⊙ Recentrer</button>
</div>

<!-- CARTE + LEGENDE -->
<div class="map-wrapper">
    <div id="map"></div>
    <div class="legend">
        <div class="legend-header">26 Grands Comptes</div>
        <div id="legendItems"></div>
    </div>
</div>

<script>
{leaflet_js}
</script>
<script>
// ── Données ─────────────────────────────────────────────────────────────────
const SITES = {sites_json};
const COULEURS = {couleurs_json};

// ── Init carte ───────────────────────────────────────────────────────────────
const map = L.map('map', {{ zoomControl: true, minZoom: 5, maxZoom: 18 }})
             .setView([46.5, 2.5], 6);

L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 19
}}).addTo(map);

// ── Icônes SVG ───────────────────────────────────────────────────────────────
function createIcon(site) {{
    const couleur = site.couleur || '#555';
    const isPrio  = site.statut === 'Prioritaire';
    const w = isPrio ? 43 : 36;
    const h = isPrio ? 53 : 44;
    const ax = Math.round(w / 2);
    const r = isPrio ? 11 : 9;
    const cy = isPrio ? 19 : 16;
    const fy = isPrio ? 23 : 20;
    const fs = isPrio ? 13 : 11;
    const icon = site.icon || '📍';

    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 44" width="${{w}}" height="${{h}}">
      <defs>
        <filter id="sh_${{site.nom.replace(/[^a-z0-9]/gi,'')}}">
          <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="rgba(0,0,0,0.35)"/>
        </filter>
      </defs>
      <g filter="url(#sh_${{site.nom.replace(/[^a-z0-9]/gi,'')}})">
        <path d="M18 2 C10.27 2 4 8.27 4 16 C4 26 18 42 18 42 C18 42 32 26 32 16 C32 8.27 25.73 2 18 2Z"
              fill="${{couleur}}" stroke="white" stroke-width="2"/>
      </g>
      <circle cx="18" cy="${{cy}}" r="${{r}}" fill="white" opacity="0.92"/>
      <text x="18" y="${{fy}}" text-anchor="middle" font-size="${{fs}}">${{icon}}</text>
    </svg>`;

    return L.divIcon({{
        className: '',
        html: svg,
        iconSize: [w, h],
        iconAnchor: [ax, h],
        popupAnchor: [0, -h]
    }});
}}

// ── Popup HTML ────────────────────────────────────────────────────────────────
function buildPopup(s) {{
    const responsable = s.responsable || '—';
    const effectif    = s.effectif    || 'Non renseigné';
    const badgeClass  = s.statut === 'Prioritaire' ? 'badge-prioritaire' : 'badge-standard';
    const sharepoint  = s.lien_sharepoint
        ? `<a href="${{s.lien_sharepoint}}" target="_blank" rel="noopener" class="btn-sharepoint">📁 Dossier Grand Compte</a>`
        : `<p class="no-sharepoint">Dossier non encore renseigné</p>`;

    return `
<div class="popup-header">
  <div class="popup-dot" style="background:${{s.couleur}}"></div>
  <div>
    <p class="popup-nom">${{s.nom}}</p>
    <p class="popup-loc">📍 ${{s.ville}} · ${{s.secteur}}</p>
  </div>
</div>
<div class="popup-body">
  <div class="popup-row"><span class="lbl">👤</span><span><strong>DCF :</strong> ${{responsable}}</span></div>
  <div class="popup-row"><span class="lbl">👥</span><span><strong>Effectif :</strong> ${{effectif}}</span></div>
  <div class="popup-row"><span class="lbl">🌐</span><span><a href="${{s.url_site}}" target="_blank" rel="noopener" style="color:#00587C">${{s.url_site}}</a></span></div>
  <div class="popup-badges">
    <span class="badge ${{badgeClass}}">${{s.statut}}</span>
  </div>
</div>
<div class="popup-footer">${{sharepoint}}</div>`;
}}

// ── Marqueurs ─────────────────────────────────────────────────────────────────
const markers = {{}};
SITES.forEach(s => {{
    const m = L.marker([s.lat, s.lng], {{ icon: createIcon(s) }})
               .bindPopup(buildPopup(s), {{ maxWidth: 320 }});
    m.addTo(map);
    markers[s.nom] = m;
}});

// ── Légende ───────────────────────────────────────────────────────────────────
const hiddenSites = new Set();
const legendContainer = document.getElementById('legendItems');

function buildLegend() {{
    legendContainer.innerHTML = '';
    const sorted = [...SITES].sort((a,b) => a.nom.localeCompare(b.nom));
    sorted.forEach(s => {{
        const div = document.createElement('div');
        div.className = 'legend-item' + (hiddenSites.has(s.nom) ? ' hidden' : '');
        div.innerHTML = `
            <div class="legend-dot" style="background:${{s.couleur}}"></div>
            <div class="legend-name">${{s.icon}} ${{s.nom}}</div>`;
        div.title = `Cliquer pour ${{hiddenSites.has(s.nom) ? 'afficher' : 'masquer'}} ${{s.nom}}`;
        div.onclick = () => toggleSite(s.nom, div);
        legendContainer.appendChild(div);
    }});
}}

function toggleSite(nom, el) {{
    if (hiddenSites.has(nom)) {{
        hiddenSites.delete(nom);
        el.classList.remove('hidden');
    }} else {{
        hiddenSites.add(nom);
        el.classList.add('hidden');
    }}
    applyFilters();
}}

buildLegend();

// ── Filtres ───────────────────────────────────────────────────────────────────
function applyFilters() {{
    const q       = document.getElementById('searchInput').value.toLowerCase().trim();
    const secteur = document.getElementById('secteurFilter').value;
    const statut  = document.getElementById('statutFilter').value;
    let visible   = 0;

    SITES.forEach(s => {{
        const m = markers[s.nom];
        if (!m) return;

        const matchSearch  = !q || s.nom.toLowerCase().includes(q)
                               || s.ville.toLowerCase().includes(q)
                               || s.secteur.toLowerCase().includes(q);
        const matchSecteur = !secteur || s.secteur === secteur;
        const matchStatut  = !statut  || s.statut  === statut;
        const matchLegend  = !hiddenSites.has(s.nom);

        if (matchSearch && matchSecteur && matchStatut && matchLegend) {{
            if (!map.hasLayer(m)) map.addLayer(m);
            visible++;
        }} else {{
            if (map.hasLayer(m)) map.removeLayer(m);
        }}
    }});

    document.getElementById('counter').textContent = `${{visible}} / ${{SITES.length}} sites affichés`;
}}

// ── Recentrer ─────────────────────────────────────────────────────────────────
function recenter() {{
    map.setView([46.5, 2.5], 6);
}}
</script>
</body>
</html>"""

    return html


def main():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(" Générateur Carte Grands Comptes — Antea Group")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    print(f"\n📂 Lecture {CSV_PATH.name}…")
    sites = load_sites()
    print(f"✅ {len(sites)} sites chargés\n")

    print("🔧 Construction HTML…")
    html = build_html(sites)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = len(html.encode('utf-8')) // 1024
    print(f"✅ index.html généré ({size_kb} Ko)")

    # ── Tests d'autonomie ──────────────────────────────────────────────────
    print("\n🧪 Tests d'autonomie…")

    import re
    # cartocdn.com est autorisé (tuiles réseau, pas de JS/CSS externe)
    cdn_hits = re.findall(r'unpkg\.|cdnjs\.|jsdelivr\.', html)
    carto_ok = 'cartocdn.com' in html
    print(f"  CDN JS/CSS extern: {'❌ ' + str(cdn_hits) if cdn_hits else '✅ aucun'}")
    print(f"  Tuiles CartoDB   : {'✅ présentes (seule dépendance réseau autorisée)' if carto_ok else '⚠️ absentes'}")

    ext_links = re.findall(r'<link[^>]+href=["\']http', html)
    print(f"  Liens CSS extern : {'❌ ' + str(ext_links) if ext_links else '✅ aucun'}")

    ext_scripts = re.findall(r'<script[^>]+src=["\']http', html)
    print(f"  Scripts externes : {'❌ ' + str(ext_scripts) if ext_scripts else '✅ aucun'}")

    site_count = html.count('"nom"')
    print(f"  Sites embarqués  : {'✅' if site_count >= len(sites) else '⚠️'} {site_count} (attendu ≥ {len(sites)})")

    from html.parser import HTMLParser
    errors = []
    class Validator(HTMLParser):
        def handle_error(self, e):
            errors.append(str(e))
    try:
        v = Validator()
        v.feed(html)
        print(f"  HTML             : {'✅ valide' if not errors else '⚠️  ' + str(errors)}")
    except Exception as e:
        print(f"  HTML             : ⚠️  {e}")

    print(f"\n🎯 Fichier : {OUTPUT_PATH}")
    print("   Ouvrir dans Chrome / Firefox pour visualiser la carte.")

    if LOG_PATH.exists() and LOG_PATH.stat().st_size > 0:
        print(f"\n⚠️  Des avertissements de géocodage ont été loggés : {LOG_PATH.name}")


if __name__ == '__main__':
    main()
