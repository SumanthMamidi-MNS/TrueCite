"""Generate README badges in the same style as the hand-made ones in this folder:
dark rounded shell, 18px icon, white label, glossy gradient value pill.

Run from anywhere:  python docs/assets/badges/make_badges.py
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHAR_W = 6.35  # approx. advance width of 11.5px semibold system sans


def badge(slug, label, value, g0, g1, g2, border, icon):
    label_w = len(label) * CHAR_W
    value_w = round(len(value) * 6.95 + 16)
    pill_x = round(32 + label_w + 10)
    width = pill_x + value_w + 4
    cx = pill_x + value_w / 2
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 32" width="{width}" height="32" fill="none">
  <defs>
    <linearGradient id="{slug}-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{g0}"/>
      <stop offset="50%" stop-color="{g1}"/>
      <stop offset="100%" stop-color="{g2}"/>
    </linearGradient>
    <linearGradient id="{slug}-gloss" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0.0"/>
    </linearGradient>
  </defs>
  <style>
    .badge-label {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 11.5px; font-weight: 600; fill: #FFFFFF; }}
    .badge-value {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 11.5px; font-weight: 700; fill: #FFFFFF; }}
  </style>
  <rect x="0.5" y="0.5" width="{width - 1}" height="31" rx="6" fill="#161B22" stroke="{border}" stroke-width="1"/>
  <g transform="translate(8, 7)">{icon}</g>
  <text x="32" y="20" class="badge-label">{label}</text>
  <rect x="{pill_x}" y="3.5" width="{value_w}" height="25" rx="4.5" fill="url(#{slug}-grad)" stroke="rgba(255,255,255,0.25)" stroke-width="0.8"/>
  <rect x="{pill_x}" y="3.5" width="{value_w}" height="12.5" rx="4.5" fill="url(#{slug}-gloss)"/>
  <text x="{cx}" y="20" text-anchor="middle" class="badge-value">{value}</text>
</svg>
"""


ICONS = {
    # lightning bolt, same as the original FastAPI badge
    "fastapi": '<circle cx="9" cy="9" r="8.5" fill="#009688"/><path d="M10 3 L5 10.5 H9.5 L8.5 15 L14 8.5 H9.5 L10.5 3 Z" fill="#FFFFFF"/>',
    # magnifier over text lines: keyword search
    "bm25": '<rect x="1" y="3" width="10" height="1.8" rx="0.9" fill="#FDBA74"/><rect x="1" y="7" width="7" height="1.8" rx="0.9" fill="#FDBA74"/><rect x="1" y="11" width="5" height="1.8" rx="0.9" fill="#FDBA74"/><circle cx="12" cy="10" r="3.6" stroke="#FFFFFF" stroke-width="1.8"/><path d="M14.6 12.6 L17 15" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>',
    # llama-ish head silhouette kept abstract: a chat bubble with a spark
    "llm": '<path d="M2 3.5 A2 2 0 0 1 4 1.5 H14 A2 2 0 0 1 16 3.5 V10.5 A2 2 0 0 1 14 12.5 H8 L4.5 16 V12.5 H4 A2 2 0 0 1 2 10.5 Z" fill="#E2E8F0"/><path d="M9 4 L9.9 6.6 L12.5 7.5 L9.9 8.4 L9 11 L8.1 8.4 L5.5 7.5 L8.1 6.6 Z" fill="#7C3AED"/>',
    # two overlapping speech bubbles: bilingual
    "lang": '<rect x="1" y="2" width="10" height="8" rx="2" fill="#38BDF8"/><rect x="7" y="7" width="10" height="8" rx="2" fill="#FFFFFF"/><text x="12" y="13.3" font-size="6" font-weight="700" fill="#0369A1" text-anchor="middle" font-family="Arial">हि</text><text x="6" y="8.2" font-size="5.5" font-weight="700" fill="#FFFFFF" text-anchor="middle" font-family="Arial">A</text>',
    # three connected nodes: knowledge graph
    "graph": '<path d="M4 13 L9 4 L14 13 Z" stroke="#FDE68A" stroke-width="1.4" fill="none"/><circle cx="9" cy="4" r="2.6" fill="#FBBF24"/><circle cx="4" cy="13" r="2.6" fill="#FFFFFF"/><circle cx="14" cy="13" r="2.6" fill="#FFFFFF"/>',
    # document with seal: licence
    "license": '<rect x="3" y="1.5" width="11" height="14" rx="1.6" fill="#E5E7EB"/><rect x="5" y="4.5" width="7" height="1.4" rx="0.7" fill="#6B7280"/><rect x="5" y="7.5" width="5" height="1.4" rx="0.7" fill="#6B7280"/><circle cx="13" cy="13" r="3.4" fill="#A3A3A3" stroke="#FFFFFF" stroke-width="1"/>',
}

BADGES = [
    ("fastapi", "FastAPI", "0.141", "#2DD4BF", "#0D9488", "#047857", "rgba(45, 212, 191, 0.45)", ICONS["fastapi"]),
    ("bm25", "Hybrid search", "BM25 + RRF", "#FDBA74", "#EA580C", "#9A3412", "rgba(251, 146, 60, 0.45)", ICONS["bm25"]),
    ("llm", "LLM", "Ollama · Gemini · Claude", "#C4B5FD", "#7C3AED", "#5B21B6", "rgba(167, 139, 250, 0.45)", ICONS["llm"]),
    ("lang", "Languages", "English · Hindi", "#7DD3FC", "#0284C7", "#075985", "rgba(56, 189, 248, 0.45)", ICONS["lang"]),
    ("graph", "Knowledge graph", "Legal links", "#FDE68A", "#D97706", "#92400E", "rgba(251, 191, 36, 0.45)", ICONS["graph"]),
    ("license", "License", "MIT", "#D4D4D4", "#737373", "#404040", "rgba(163, 163, 163, 0.45)", ICONS["license"]),
]

if __name__ == "__main__":
    for slug, *rest in BADGES:
        (HERE / f"{slug}.svg").write_text(badge(slug, *rest), encoding="utf-8")
        print("wrote", slug + ".svg")
