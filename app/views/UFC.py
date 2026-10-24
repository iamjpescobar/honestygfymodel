"""UFC (10-24) — the next card, every fight, and DraftKings' own chances
with its cut removed (engines/ufc): who wins, how (KO / TKO, submission,
decision), total rounds and going the distance.

STEP ONE, said on the page: these are the BOOK's numbers, cleaned of its
cut — not the site's. The site's own fighter model comes after the
backfill and its test against these moneylines (rule 1). Read live from
ESPN's feed at page time (cached 10 minutes), so the card is current on
fight night without waiting for a nightly.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import model_math as mm
from engines import ufc
from engines.live_sync import sync_latest_button

page_header("UFC", "The card, and what DraftKings' prices really say", eyebrow="UFC",
            align="left")
sync_latest_button(key="sync_ufc", include_data_package=False)


@st.cache_data(ttl=600, show_spinner=False)
def _load(_bucket):
    from engines import espn_feed as ef
    return ufc.build(ef.get_json)


import time as _time  # noqa: E402
with st.spinner("Reading the card and DraftKings' odds…"):
    try:
        c = _load(int(_time.time() // 600))
    except Exception as exc:  # noqa: BLE001
        c = None
        st.caption(f"ESPN's UFC feed did not answer ({type(exc).__name__}).")

st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'Every chance on this page is <b>DraftKings&rsquo; own</b>, with its cut taken out (their '
    f'prices on each market scaled to add up to 100%). That is the cleanest read of what the '
    f'book thinks &mdash; and the bar the site&rsquo;s own fighter model has to beat. '
    f'<span style="color:{COLOR["warn"]}; font-weight:700;">The site&rsquo;s model is not here '
    f'yet:</span> it is being built on past fights and will only appear once it has beaten these '
    f'numbers on fights it never saw.</div>', unsafe_allow_html=True)

if not c or not c.get("fights"):
    st.info("No UFC card on ESPN's feed right now.")
    footer()
    st.stop()

st.markdown(f"### {c.get('name')}")
st.caption(f"{len(c['fights'])} fights · main event first · DraftKings via ESPN, refreshed every "
           f"10 minutes.")


def _pc(p):
    return "—" if p is None else f"{100 * p:.0f}%"


def _am(a):
    return "—" if a is None else mm.fmt_american(int(a))


for i, f in enumerate(reversed(c["fights"])):
    a, b, o = f["a"], f["b"], f.get("odds") or {}
    with card(f"ufc_{f['id']}"):
        head = (f'{a["name"]} <span style="color:{COLOR["text_muted"]};">vs</span> {b["name"]}')
        st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                    f'{"MAIN EVENT · " if i == 0 else ""}{head}</div>'
                    f'<div class="pf-card-subtitle">{f.get("weight") or ""}'
                    f'{" · " + a["record"] if a.get("record") else ""}'
                    f'{" vs " + b["record"] if b.get("record") else ""}'
                    + (f' · <b>{f.get("detail")}</b>' if f.get("done") else "") + '</div>',
                    unsafe_allow_html=True)
        if f.get("done"):
            w = a if a.get("winner") else (b if b.get("winner") else None)
            st.markdown(f"**Result:** {w['name'] + ' won' if w else 'see ESPN'}"
                        f" · {f.get('detail') or ''}")
        if not o or not o.get("win"):
            st.caption("No DraftKings price on this fight yet.")
            continue
        win = o["win"]
        st.markdown(
            '<div style="display:flex; gap:12px; flex-wrap:wrap; margin:6px 0 10px;">'
            + "".join(
                f'<div style="flex:1 1 200px; padding:12px 14px; border-radius:12px; '
                f'border:1px solid {COLOR["stat_high"] if p >= 0.5 else "rgba(152,163,173,0.25)"};">'
                f'<div style="font-weight:800;">{x["name"]}</div>'
                f'<div style="font-size:2.2em; font-weight:800; line-height:1.1; '
                f'color:{COLOR["stat_high"] if p >= 0.5 else COLOR["text"]};">{_pc(p)}</div>'
                f'<div style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]};">'
                f'to win · DraftKings {_am(o["ml"][k])}</div></div>'
                for k, x, p in (("a", a, win["a"]), ("b", b, win["b"])))
            + '</div>', unsafe_allow_html=True)
        rows = []
        m = o.get("method")
        if m:
            for k_, lab in ufc.METHODS:
                rows.append({"How it ends": lab,
                             a["name"]: f'{_pc(m["a"][k_])}  ({_am(m["prices"]["a"][k_])})',
                             b["name"]: f'{_pc(m["b"][k_])}  ({_am(m["prices"]["b"][k_])})'})
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         key=f"ufc_m_{f['id']}")
        bits = []
        r = o.get("rounds")
        if r and r.get("p_over") is not None:
            bits.append(f'Over {r["line"]:g} rounds <b>{_pc(r["p_over"])}</b> ({_am(r["over"])}) · '
                        f'under <b>{_pc(1 - r["p_over"])}</b> ({_am(r["under"])})')
        d = o.get("distance")
        if d:
            bits.append(f'Goes the distance <b>{_pc(d["p_yes"])}</b> ({_am(d["yes"])}) · '
                        f'doesn&rsquo;t <b>{_pc(1 - d["p_yes"])}</b> ({_am(d["no"])})')
        if m:
            fin = sum(m[s_][k_] for s_ in ("a", "b") for k_ in ("koTkoDq", "submission"))
            bits.append(f'Ends inside the distance (method market) <b>{_pc(fin)}</b>')
        if bits:
            st.markdown('<div style="font-size:var(--lc-text-body); line-height:1.8;">'
                        + "<br>".join(bits) + '</div>', unsafe_allow_html=True)

st.caption("% = DraftKings' chance with its cut removed; the price in brackets is theirs. The "
           "method table's six outcomes add to 100% together. A fight that ends is marked with "
           "its result. Not the site's model — see the note at the top.")
footer()
