"""
NBA Trends' research cards (11-02): the shot profile court + zone table and
the team ranks (engines/nba_research builds the numbers in the nightly).

The court is drawn as SVG (a half court, baseline on top): each zone is
tinted by how much of his shooting comes from it, with his share and
tonight's defense's rank there (1st = toughest — red; 30th = softest —
green, the same reading as Overall D).

Display only — nothing here moves a projection or a letter.
"""
from engines import nba_research as nr

# heat: least frequent -> most frequent
_LO, _HI = (0x2B, 0x5C, 0xC8), (0xE8, 0x7A, 0x2E)


def _heat(share, top):
    if share is None or not top:
        return "#2a3138"
    t = max(0.0, min(1.0, share / top))
    c = tuple(int(a + (b - a) * t) for a, b in zip(_LO, _HI))
    return "#%02x%02x%02x" % c


def rank_colour(rank, of):
    """Tough (top third) red, soft (bottom third) green, else neutral."""
    if not rank or not of:
        return "#5b6670"
    if rank <= of / 3:
        return "#D6304A"
    if rank > 2 * of / 3:
        return "#1f9d6b"
    return "#3a4550"


def ordinal(n):
    if n is None:
        return "—"
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def zone_cells(prof, dtab_team):
    """{zone: {"share", "fg", "rank", "of", "opp_fg"}} merged for drawing."""
    out = {}
    for z in prof:
        d = (dtab_team or {}).get(z["zone"]) or {}
        out[z["zone"]] = {"share": z["share"], "fg": z["fg"], "att": z["att"],
                          "rank": d.get("rank"), "of": d.get("of"), "opp_fg": d.get("fg")}
    return out


def court_svg(cells):
    """A half court (500 x 470, 10 px a foot, basket at 250,52.5)."""
    known3 = any(z in cells for z in ("corner3", "above3"))
    shares = [c["share"] for c in cells.values() if c.get("share") is not None]
    top = max(shares) if shares else 0

    def fill(z):
        if z in ("corner3", "above3") and not known3:
            z = "three"
        return _heat((cells.get(z) or {}).get("share"), top)

    def label(x, y, title, z):
        c = cells.get(z) or {}
        sh = c.get("share")
        rk, of = c.get("rank"), c.get("of")
        sh_t = "—" if sh is None else f"{100 * sh:.1f}%"
        rk_t = "" if not rk else f"#{rk}"
        w_sh = 14 + 9 * len(sh_t)
        w_rk = 12 + 10 * len(rk_t) if rk_t else 0
        x0 = x - (w_sh + w_rk) / 2
        g = (f'<text x="{x}" y="{y - 10}" text-anchor="middle" font-size="17" '
             f'font-weight="600" fill="#ffffff">{title}</text>'
             f'<rect x="{x0}" y="{y}" width="{w_sh}" height="26" rx="4" fill="#f4f4f4"/>'
             f'<text x="{x0 + w_sh / 2}" y="{y + 19}" text-anchor="middle" font-size="16" '
             f'font-weight="700" fill="#111">{sh_t}</text>')
        if rk_t:
            g += (f'<rect x="{x0 + w_sh}" y="{y}" width="{w_rk}" height="26" rx="4" '
                  f'fill="{rank_colour(rk, of)}"/>'
                  f'<text x="{x0 + w_sh + w_rk / 2}" y="{y + 19}" text-anchor="middle" '
                  f'font-size="16" font-weight="700" fill="#fff">{rk_t}</text>')
        return g

    three_z = "above3" if known3 else "three"
    parts = [
        '<svg viewBox="0 0 500 470" xmlns="http://www.w3.org/2000/svg" '
        'style="width:100%;max-width:520px;display:block;margin:auto;">',
        f'<rect x="0" y="0" width="500" height="470" fill="{fill(three_z)}"/>',
        f'<path d="M30,0 L30,142 A237.5,237.5 0 0 0 470,142 L470,0 Z" fill="{fill("mid")}"/>',
        f'<rect x="0" y="0" width="30" height="142" fill="{fill("corner3")}"/>',
        f'<rect x="470" y="0" width="30" height="142" fill="{fill("corner3")}"/>',
        f'<rect x="170" y="0" width="160" height="190" fill="{fill("paint")}"/>',
        f'<path d="M210,0 L210,52.5 A40,40 0 0 0 290,52.5 L290,0 Z" fill="{fill("rim")}"/>',
        '<g fill="none" stroke="#ffffff" stroke-opacity="0.85" stroke-width="2">',
        '<rect x="1" y="1" width="498" height="468"/>',
        '<path d="M30,0 L30,142 A237.5,237.5 0 0 0 470,142 L470,0"/>',
        '<rect x="170" y="0" width="160" height="190"/>',
        '<path d="M210,0 L210,52.5 A40,40 0 0 0 290,52.5 L290,0"/>',
        '<circle cx="250" cy="52.5" r="7.5"/>',
        '<line x1="220" y1="40" x2="280" y2="40"/>',
        '</g>',
        label(250, 150, "In the paint", "paint"),
        label(250, 228, "Mid-range", "mid"),
    ]
    if known3:
        parts += [label(75, 60, "Corner 3", "corner3"), label(425, 60, "Corner 3", "corner3"),
                  label(250, 400, "Above break 3", "above3")]
    else:
        parts += [label(250, 400, "Three (side unknown)", "three")]
    # the rim label sits just under the hoop so it never covers it
    parts += [label(250, 86, "Rim", "rim"), "</svg>"]
    return "".join(parts)


def court_img(cells):
    """The court as an <img> (base64 SVG): renders the same in every
    Streamlit version, which raw inline SVG in markdown does not."""
    import base64
    b = base64.b64encode(court_svg(cells).encode()).decode()
    return (f'<img src="data:image/svg+xml;base64,{b}" alt="shot profile" '
            f'style="width:100%;max-width:520px;display:block;margin:auto;"/>')


def zone_rows(prof, dtab_team, league, opp):
    rows = []
    for z in prof:
        d = (dtab_team or {}).get(z["zone"]) or {}
        lg = (league or {}).get(z["zone"]) or {}
        rows.append({"Zone": z["label"],
                     "His share": "—" if z["share"] is None else f"{100 * z['share']:.1f}%",
                     "His FG%": "—" if z["fg"] is None else f"{100 * z['fg']:.1f}%",
                     "Shots": z["att"],
                     f"{opp} FG% allowed": "—" if d.get("fg") is None else f"{100 * d['fg']:.1f}%",
                     f"{opp} rank": (f"{ordinal(d['rank'])} of {d['of']}" if d.get("rank")
                                     else "—"),
                     "League FG%": "—" if lg.get("fg") is None else f"{100 * lg['fg']:.1f}%"})
    return rows


def rank_rows(ranks, team, opp, team_abbr, opp_abbr, flip=False):
    """[{metric, team side, opp side}] — default: his team's OFFENSE vs the
    opponent's DEFENSE; flip: his team's defense vs their offense."""
    a, b = (ranks or {}).get(team) or {}, (ranks or {}).get(opp) or {}
    s1, s2 = ("def", "off") if flip else ("off", "def")
    out = []
    for k, lab, desc in nr.METRICS:
        x, y = a.get(k) or {}, b.get(k) or {}
        out.append({"metric": lab, "desc": desc,
                    "left": x.get(s1), "left_rank": x.get(f"{s1}_rank"), "of": x.get("of") or y.get("of"),
                    "right": y.get(s2), "right_rank": y.get(f"{s2}_rank")})
    return out
