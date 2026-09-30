"""
Build the static web version of the Halo Dashboard (index.html) for GitHub Pages.

The page layout, styling and charts all come from DASHBOARD_HTML in
halo_dashboard.py, so the local app and the website never drift apart.
The only difference: instead of calling the local Flask server, the web
version reads the Google Sheet directly from the browser, so it shows
new games as soon as the sheet is updated.

Usage:
    python3 build_static.py
"""

import re
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "halo_dashboard.py"
OUT = HERE / "index.html"

SITE_URL = "https://maximhoeft94.github.io/halo-dashboard/"
REPO_URL = "https://github.com/maximhoeft94/halo-dashboard"

src = SRC.read_text(encoding="utf-8")

html = re.search(r'DASHBOARD_HTML = r"""(.*?)"""', src, re.S).group(1).strip() + "\n"
sheet_id = re.search(r'^SHEET_ID = "([^"]+)"', src, re.M).group(1)
tab_name = re.search(r'^TAB_NAME = "([^"]+)"', src, re.M).group(1)

# ---------------------------------------------------------------------------
# 1. Browser-side data loader (mirrors load_data() + build_payload() in Python)
# ---------------------------------------------------------------------------
LOADER = """
// ===== Static build: read the Google Sheet directly from the browser =====
const SHEET_ID = %(sheet_id)r;
const TAB_NAME = %(tab_name)r;
const SHEET_CSV_URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent(TAB_NAME)}`;

function parseCSV(text) {
  const rows = []; let row = [], field = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; }
      else field += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\\n' || c === '\\r') {
      if (c === '\\r' && text[i + 1] === '\\n') i++;
      row.push(field); rows.push(row); row = []; field = '';
    } else field += c;
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row); }
  return rows.filter(r => r.some(v => v.trim() !== ''));
}

async function fetchHaloData() {
  const resp = await fetch(SHEET_CSV_URL, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`Google Sheets returned ${resp.status}`);
  const rows = parseCSV(await resp.text());
  const header = rows.shift().map(h => h.trim());
  const NUM = ['Game', 'Good Guys', 'Bad Guys', 'Kills', 'Assists', 'Deaths', 'Diff', 'Ratio'];
  const toNum = v => { const n = parseFloat(String(v).replace(/,/g, '')); return isNaN(n) ? null : n; };
  const games = rows.map(r => {
    const g = {};
    header.forEach((h, i) => { g[h] = (r[i] ?? '').trim(); });
    NUM.forEach(k => { g[k] = toNum(g[k]); });
    g['Game Type'] = g['Game Type'] || '(unspecified)';
    return g;
  }).filter(g => g.Game !== null && g.Result);
  games.forEach(g => {
    g.Margin = (g['Good Guys'] ?? 0) - (g['Bad Guys'] ?? 0);
    if (g.Ratio === null) g.Ratio = g.Deaths ? g.Kills / g.Deaths : (g.Kills || 0);
  });
  return {
    games,
    maps: [...new Set(games.map(g => g.Map))].sort(),
    game_types: [...new Set(games.map(g => g['Game Type']))].sort(),
  };
}
""" % {"sheet_id": sheet_id, "tab_name": tab_name}

FETCH_BLOCK = re.compile(
    r"const resp = await fetch\('/api/data'\);\s*"
    r"if \(!resp\.ok\) throw new Error\(`Server returned \$\{resp\.status\}`\);\s*"
    r"const d = await resp\.json\(\);"
)
html, n = FETCH_BLOCK.subn("const d = await fetchHaloData();", html)
assert n == 2, f"expected 2 fetch blocks, found {n}"

anchor = "async function loadAndRender()"
assert html.count(anchor) == 1
html = html.replace(anchor, LOADER + "\n" + anchor)

# ---------------------------------------------------------------------------
# 2. Link-preview tags (LinkedIn, Slack, etc.) and a small credit footer
# ---------------------------------------------------------------------------
META = f"""<meta name="description" content="Live Halo 3 performance dashboard: win rates, K/D trends, map and team-side analysis, built from a Google Sheet.">
<meta property="og:type" content="website">
<meta property="og:title" content="Halo Dashboard · Combat Telemetry">
<meta property="og:description" content="Live Halo 3 performance analytics: win rates, K/D trends, map and team-side breakdowns.">
<meta property="og:url" content="{SITE_URL}">
<meta property="og:image" content="{SITE_URL}screenshots/overview.png">
<meta name="twitter:card" content="summary_large_image">
"""
html = html.replace("<title>Halo Dashboard</title>", "<title>Halo Dashboard</title>\n" + META, 1)

FOOTER = f"""
<footer style="max-width:1200px;margin:0 auto;padding:10px 16px 40px;font-family:var(--font-body);font-size:14px;color:var(--muted);letter-spacing:0.5px;text-align:center;position:relative;z-index:2;">
  Built by Maxim Hoeft · Data syncs live from Google Sheets ·
  <a href="{REPO_URL}" style="color:var(--hud);text-decoration:none;">View source on GitHub</a>
</footer>
"""
html = html.replace("</main>", "</main>\n" + FOOTER, 1)

OUT.write_text(html, encoding="utf-8")
print(f"Wrote {OUT.name} ({len(html):,} bytes) · sheet {sheet_id} / tab '{tab_name}'")
