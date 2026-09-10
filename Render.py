#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render.py — 把爬到的年會資料算成 (1) 一頁儀表板 HTML (2) 一個 .ics 行事曆檔。

儀表板的主角是「季節格線」：橫軸十二個月、縱軸年份，一眼就看得出
主要學會的年度節奏（SAEM 五月、IFEM 六月、EuSEM 九月底、ACEP 十月），
這正是排投稿死線與出國預算時真正需要知道的事。
"""

from __future__ import annotations

import hashlib
import html
import json
from datetime import date, datetime, timezone
from pathlib import Path

SOCIETY_META = {
    "ACEP":  {"full": "American College of Emergency Physicians",
              "meeting": "Scientific Assembly", "hue": "acep",
              "logo": "https://www.acep.org/siteassets/sites/-comms-global/media/acep-logo3x.png"},
    "SAEM":  {"full": "Society for Academic Emergency Medicine",
              "meeting": "Annual Meeting", "hue": "saem",
              "logo": "https://www.saem.org/images/default-source/siteimages/logos/logo-2.png?sfvrsn=74156739_4"},
    "IFEM":  {"full": "International Federation for Emergency Medicine",
              "meeting": "Global Congress / ICEM", "hue": "ifem"},
    "EUSEM": {"full": "European Society for Emergency Medicine",
              "meeting": "European EM Congress", "hue": "eusem",
              "logo": "https://eusem.org/images/2024/EUSEM_CAST_LOGO_SQUARE_WHITE%20%28002%29.png"},
    "ASIANSEM": {"full": "Asian Society for Emergency Medicine",
                  "meeting": "Asian Conference on Emergency Medicine", "hue": "asiansem",
                  "logo": "https://static.wixstatic.com/media/d30827_5fa9ceca05fe446b801aa15557200887~mv2.png/v1/fill/w_114,h_80,al_c,q_85,usm_0.66_1.00_0.01,enc_avif,quality_auto/banner_logo_edited.png"},
    "HKCEM": {"full": "Hong Kong College of Emergency Medicine",
              "meeting": "Annual Congress", "hue": "hkcem",
              "logo": "https://hkcem.org.hk/wp-content/uploads/2022/10/HKCEM-Logo-icon.png"},
    "SEMS": {"full": "Society for Emergency Medicine in Singapore",
             "meeting": "Annual Conference", "hue": "sems",
             "logo": "https://i0.wp.com/sems-online.com/wp-content/uploads/2013/03/cropped-semslogo-copy.png?fit=200%2C192&ssl=1"},
}

MONTH_ABBR = ["一", "二", "三", "四", "五", "六",
              "七", "八", "九", "十", "十一", "十二"]


# --------------------------------------------------------------------------
# 資料整理
# --------------------------------------------------------------------------

def _d(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def prepare(rows: list[dict]) -> list[dict]:
    """補上排序鍵、月份、是否已過期。無確切日期者用 date_text 的月份估位。"""
    out = []
    for r in rows:
        if r.get("name") == "(fetch failed)":
            continue
        start, end = _d(r.get("start", "")), _d(r.get("end", ""))
        month = start.month if start else _month_from_text(r.get("date_text", ""))
        r = dict(r)
        r["_start"] = start
        r["_end"] = end or start
        r["_month"] = month
        r["_confirmed"] = bool(start)
        r["_sort"] = (r.get("year") or 9999, month or 13)
        out.append(r)
    out.sort(key=lambda x: x["_sort"])
    return out


def _month_from_text(text: str) -> int | None:
    names = ["jan", "feb", "mar", "apr", "may", "jun",
             "jul", "aug", "sep", "oct", "nov", "dec"]
    low = (text or "").lower()
    for i, n in enumerate(names, start=1):
        if n in low:
            return i
    return None


def next_up(rows: list[dict], today: date) -> dict | None:
    future = [r for r in rows if r["_end"] and r["_end"] >= today]
    return future[0] if future else None


def assign_lanes(rows_in_year: list[dict]) -> dict[str, int]:
    """同一年同一個月有兩場會時，把第二場排到下一條 lane，避免疊在一起。"""
    lanes: list[set[int]] = []
    result = {}
    for r in rows_in_year:
        m = r["_month"] or 13
        for i, taken in enumerate(lanes):
            if m not in taken:
                taken.add(m)
                result[_key(r)] = i
                break
        else:
            lanes.append({m})
            result[_key(r)] = len(lanes) - 1
    return result


def _key(r: dict) -> str:
    return f'{r["society"]}-{r.get("year")}-{r.get("start") or r.get("date_text")}'


# --------------------------------------------------------------------------
# ICS 行事曆
# --------------------------------------------------------------------------

def build_ics(rows: list[dict], deadlines: list[dict] | None = None) -> str:
    """全天事件的 .ics。訂閱後年會就會自動出現在 Google Calendar 裡。"""
    def esc(s: str) -> str:
        return (s or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//EM Conference Tracker//TW//ZH",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:急診國際年會",
             "X-WR-TIMEZONE:Asia/Taipei"]
    for r in rows:
        if not r["_confirmed"]:
            continue                       # 日期未定的不進行事曆，免得誤導
        uid = hashlib.md5(_key(r).encode()).hexdigest() + "@em-conf-tracker"
        place = ", ".join(x for x in (r.get("city"), r.get("country_or_state")) if x)
        dtend = date.fromordinal(r["_end"].toordinal() + 1)   # DTEND 為排他性
        desc = f'{SOCIETY_META.get(r["society"], {}).get("full", r["society"])}'
        if r.get("venue"):
            desc += f'\\n會場：{r["venue"]}'
        if r.get("note"):
            desc += f'\\n備註：{r["note"]}'
        desc += f'\\n來源：{r.get("source_url","")}'
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f'DTSTART;VALUE=DATE:{r["_start"].strftime("%Y%m%d")}',
            f'DTEND;VALUE=DATE:{dtend.strftime("%Y%m%d")}',
            f'SUMMARY:{esc(r["society"] + " — " + r.get("name", ""))}',
            f"LOCATION:{esc(place)}",
            f"DESCRIPTION:{desc}",
            f'URL:{r.get("source_url","")}',
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    # 死線事件：加 30／7／1 天三段提醒。這是整套工具最實際的產出——
    # 死線會主動在你的日曆上敲門，不必記得去看網頁。
    for d in (deadlines or []):
        if d.get("kind") == "open" or not d.get("date_iso"):
            continue
        if d.get("confidence") == "low":
            continue                       # 信心不足的不設提醒，避免假死線誤導
        try:
            day = date.fromisoformat(d["date_iso"])
        except ValueError:
            continue
        uid = hashlib.md5(
            f'dl-{d.get("society")}-{d.get("track")}-{d["date_iso"]}'.encode()
        ).hexdigest() + "@em-conf-tracker"
        title = f'死線：{d.get("society","")} {d.get("track","")}'
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f'DTSTART;VALUE=DATE:{day.strftime("%Y%m%d")}',
            f'DTEND;VALUE=DATE:{date.fromordinal(day.toordinal() + 1).strftime("%Y%m%d")}',
            f"SUMMARY:{esc(title)}",
            f'DESCRIPTION:{esc(d.get("cycle",""))}\\n{esc((d.get("note") or "")[:150])}'
            f'\\n來源：{d.get("source_url","")}',
            f'URL:{d.get("source_url","")}',
            "TRANSP:TRANSPARENT",
        ]
        for trigger, label in (("-P30D", "30 天"), ("-P7D", "7 天"), ("-P1D", "1 天")):
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY",
                      f"TRIGGER:{trigger}",
                      f"DESCRIPTION:{esc(title)}（還有 {label}）",
                      "END:VALARM"]
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# --------------------------------------------------------------------------
# HTML 儀表板
# --------------------------------------------------------------------------

CSS = """
:root{
        --paper:#f4f6f3; --surface:#ffffff; --ink:#17252b; --muted:#65767b;
        --navy:#102d36; --navy-soft:#214650; --mint:#dceee8;
        --rule:#d8e1df; --rule-soft:#e8eeec;
    --acep:#9d3a2e; --saem:#2f6a56; --ifem:#8a6820; --eusem:#33518c;
    --asiansem:#9b5d2d; --hkcem:#6b4c78; --sems:#2d6870;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
    margin:0; background:var(--paper); color:var(--ink);
    font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;
    font-size:15px; line-height:1.6; font-variant-numeric:tabular-nums;
}
.wrap{max-width:1180px; margin:0 auto; padding:0 1.5rem 5rem}
a{color:inherit; text-decoration-thickness:1px; text-underline-offset:3px}
a:focus-visible,summary:focus-visible{outline:2px solid var(--ink); outline-offset:3px}

.masthead{display:flex; justify-content:space-between; align-items:center; gap:1.5rem;
    min-height:4.6rem; color:#eaf4f1; background:var(--navy); margin:0 -1.5rem;
    padding:.9rem 1.5rem}
.masthead h1{font-size:1.05rem; font-weight:700; margin:0; letter-spacing:.02em}
.masthead .stamp{color:#b9cfca; font-size:.76rem; margin-left:auto}
.masthead nav{display:flex; gap:.45rem; align-items:center}
.masthead nav a{border:1px solid #527078; border-radius:999px; padding:.35rem .75rem;
    color:#eaf4f1; font-size:.76rem; text-decoration:none}
.masthead nav a:hover{background:#315862; border-color:#84a9a2}

.hero{position:relative; overflow:hidden; margin:0 -1.5rem 3.5rem; padding:4.2rem 1.5rem 4rem;
    color:#f5fbf8; background:var(--navy)}
.hero:after{content:""; position:absolute; inset:0 0 0 52%; opacity:.16;
    background-image:linear-gradient(rgba(174,220,207,.55) 1px,transparent 1px),
        linear-gradient(90deg,rgba(174,220,207,.55) 1px,transparent 1px);
    background-size:28px 28px; mask-image:linear-gradient(90deg,transparent,#000)}
.hero>*{position:relative; z-index:1}
.hero .lede{color:#a9d2c5; font-size:.76rem; letter-spacing:.16em; text-transform:uppercase; margin:0 0 .8rem}
.hero .title{font-size:clamp(2rem,5vw,4.4rem); line-height:1.04;
    font-weight:700; margin:0 0 1rem; max-width:13ch; letter-spacing:-.04em}
.hero .meta{font-size:1rem; color:#d3e4df; margin:0}
.hero .count{display:inline-flex; align-items:baseline; gap:.45rem; color:#b9cfca;
    font-size:.86rem; margin:1.6rem 0 0; padding-top:1rem; border-top:1px solid #42636b}
.hero .count b{color:#f5fbf8; font-weight:700; font-size:1.4rem}

h2{font-size:1.35rem; font-weight:700; margin:0 0 1.2rem; letter-spacing:-.02em}
section{margin-top:3.5rem}
section>h2:before{content:""; display:inline-block; width:.45rem; height:.45rem;
    margin:0 .55rem .14rem 0; background:var(--navy); border-radius:50%}

/* 季節格線 */
.grid{background:var(--surface); border:1px solid var(--rule); border-radius:1rem;
    padding:1rem .9rem 1.2rem; overflow-x:auto; box-shadow:0 8px 24px rgba(28,55,58,.04)}
.gridrow{display:grid; grid-template-columns:3.4rem repeat(12,1fr);
  column-gap:2px; row-gap:3px; min-width:640px}
.months{margin-bottom:.4rem; border-bottom:1px solid var(--rule-soft); padding-bottom:.3rem}
.months span{font-size:.72rem; color:var(--muted); text-align:center}
.months span:first-child{text-align:left}
.yr{font-size:.9rem; color:var(--muted); align-self:center}
.yr.now{color:var(--ink); font-weight:600}
.bar{grid-row:auto; border-left:3px solid currentColor; background:#fbfdfc;
  padding:.18rem .35rem; font-size:.73rem; line-height:1.25; min-width:0;
  border-top:1px solid var(--rule-soft); border-right:1px solid var(--rule-soft);
  border-bottom:1px solid var(--rule-soft)}
.bar b{display:block; font-weight:600; font-size:.78rem}
.bar span{color:var(--muted); display:block; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis}
.bar.tba{border-left-style:dashed; background:transparent}
.bar.past{opacity:.4}
.acep{color:var(--acep)} .saem{color:var(--saem)}
.ifem{color:var(--ifem)} .eusem{color:var(--eusem)}
.asiansem{color:var(--asiansem)} .hkcem{color:var(--hkcem)}
.sems{color:var(--sems)}
.yearband{grid-column:1/-1; height:1px; background:var(--rule-soft); margin:.25rem 0}

.legend{display:flex; gap:1.2rem; flex-wrap:wrap; margin:.9rem 0 0; font-size:.8rem}
.legend i{display:inline-block; width:.75rem; height:.75rem; margin-right:.35rem;
  background:currentColor; vertical-align:-1px}
.legend em{font-style:normal; color:var(--muted)}

/* Event cards */
.event-switcher{display:flex; align-items:center; justify-content:space-between; gap:1rem;
    margin:-.35rem 0 1.4rem; flex-wrap:wrap}
.year-tabs{display:flex; gap:.35rem; padding:.25rem; background:#e4ece9; border-radius:999px}
.year-tab{border:0; border-radius:999px; padding:.45rem .9rem; background:transparent;
    color:var(--muted); font:inherit; font-size:.8rem; font-weight:600; cursor:pointer}
.year-tab:hover,.year-tab.active{background:var(--navy); color:#f5fbf8}
.event-count{color:var(--muted); font-size:.8rem; margin:0}
.event-grid{display:flex; flex-direction:column; gap:1.25rem}
.event-card{display:grid; grid-template-columns:minmax(18rem,42%) 1fr; min-height:17rem;
        color:var(--ink); text-decoration:none; background:var(--surface);
        border:1px solid var(--rule); border-radius:1rem; overflow:hidden;
        transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease}
.event-card:hover{transform:translateY(-3px); box-shadow:0 12px 26px rgba(19,34,42,.11)}
.event-card[hidden]{display:none}
.event-card:focus-visible{outline:2px solid var(--ink); outline-offset:3px}
.event-card.past{opacity:.62}
.event-card.tba .event-visual{filter:saturate(.35)}
.event-visual{display:flex; align-items:flex-end; min-height:17rem; padding:1.5rem;
    color:#fff; background:linear-gradient(135deg,currentColor,#102d36 75%); position:relative; overflow:hidden}
.event-visual:after{content:""; position:absolute; width:16rem; height:16rem; right:-5rem; top:-5rem;
    border:1px solid rgba(255,255,255,.32); border-radius:50%; box-shadow:0 0 0 2rem rgba(255,255,255,.08),0 0 0 4rem rgba(255,255,255,.05)}
.event-visual strong{position:relative; z-index:1; max-width:8ch; font-size:clamp(2rem,4vw,3.4rem);
    line-height:.95; letter-spacing:-.05em}
.event-visual.has-logo{align-items:center; justify-content:center; padding:1.5rem;
    background:#f8fbfa}
.event-visual.has-logo:after{border-color:rgba(16,45,54,.12); box-shadow:0 0 0 2rem rgba(16,45,54,.04),0 0 0 4rem rgba(16,45,54,.025)}
.event-logo{position:relative; z-index:1; display:block; width:min(82%,20rem); height:9rem;
    object-fit:contain; mix-blend-mode:multiply}
.event-body{display:flex; flex-direction:column; min-width:0; padding:2rem 2.2rem}
.event-org{font-size:.75rem; letter-spacing:.12em; color:currentColor; font-weight:700}
.event-title{margin:.55rem 0 1.1rem; font-size:clamp(1.35rem,2.4vw,2rem); line-height:1.15; font-weight:700}
.event-meta{display:grid; gap:.65rem; color:#52666b; font-size:.95rem}
.event-meta span{display:block}
.event-meta b{display:inline-block; min-width:3.4rem; margin-right:.45rem; color:var(--ink); font-size:.78rem; letter-spacing:.05em}
.event-place{color:var(--muted); font-size:.86rem; white-space:nowrap;
    overflow:hidden; text-overflow:ellipsis}
.event-action{align-self:flex-start; margin-top:auto; padding:.55rem .95rem; border:1px solid #aabac6;
    border-radius:999px; color:#617894; font-size:.82rem; font-weight:600}
.event-card:hover .event-action{border-color:currentColor; color:currentColor}
.event-status{margin-top:.7rem; color:var(--muted); font-size:.73rem}
.event-card.upcoming .event-status{color:var(--ink); font-weight:600}
.tba-tag{color:var(--muted); font-style:italic}

.dl{background:var(--surface); border:1px solid var(--rule); border-radius:1rem;
    padding:.2rem 1.1rem .8rem; box-shadow:0 8px 24px rgba(28,55,58,.04)}
.dl ol{list-style:none; margin:0; padding:0}
.dl li{display:grid; grid-template-columns:5.2rem 1fr auto; gap:.8rem;
  align-items:baseline; padding:.6rem 0; border-bottom:1px solid var(--rule-soft)}
.dl li:last-child{border-bottom:0}
.dl .when{font-size:.88rem; color:var(--muted); white-space:nowrap}
.dl .what b{font-weight:600}
.dl .what span{color:var(--muted); font-size:.85rem; display:block}
.dl .left{font-size:.85rem; white-space:nowrap; text-align:right}
.dl .left b{font-size:1.05rem; font-weight:600}
.dl li.urgent .left{color:#a3251c} .dl li.urgent .left b{font-size:1.25rem}
.dl li.soon .left{color:#8a5a11}
.dl li.tba .when,.dl li.tba .left{color:var(--muted); font-style:italic}
.dl .flag{font-size:.72rem; color:var(--muted); border:1px solid var(--rule);
  padding:0 .3rem; margin-left:.4rem; white-space:nowrap}
.dl .note{margin:.7rem 0 0; font-size:.8rem; color:var(--muted)}

footer{margin-top:4rem; padding-top:1.2rem; border-top:1px solid var(--rule);
  font-size:.82rem; color:var(--muted)}
footer p{margin:.35rem 0}
footer ul{margin:.4rem 0; padding-left:1.1rem}

@media (max-width:640px){
  body{font-size:16px}
    .wrap{padding:0 1rem 3rem}
    .masthead{margin:0 -1rem; padding:.9rem 1rem; flex-wrap:wrap}
    .masthead nav{order:3; width:100%; margin-top:.2rem}
    .masthead nav a{flex:1; text-align:center}
    .hero{margin:0 -1rem 2.8rem; padding:3.3rem 1rem 3.2rem}
    .hero:after{right:-8rem}
    section{margin-top:2.8rem}
    .year-tabs{width:100%; overflow-x:auto; justify-content:flex-start}
    .year-tab{flex:0 0 auto}
    .event-card{grid-template-columns:1fr; min-height:0}
    .event-visual{min-height:10rem; padding:1.2rem}
    .event-body{padding:1.3rem 1.2rem 1.4rem; min-height:14rem}
}
@media (prefers-reduced-motion:no-preference){
  .hero .count b{transition:none}
}
"""


TRACK_ZH = {
    "Abstracts": "摘要",
    "Late-breaking Abstracts": "Late-breaking 摘要",
    "Research Forum Abstracts": "Research Forum 摘要",
    "Clinical Images": "臨床影像",
    "Didactics": "教學課程",
    "Innovations": "創新",
    "IGNITE!": "IGNITE!",
    "Advanced EM Workshops": "進階工作坊",
}
CONF_ZH = {"high": "", "medium": "來源為敘述句", "low": "需人工確認"}


def deadline_section(deadlines: list[dict], today: date) -> str:
    """只顯示還沒過期的死線，最近的排最前面；已公布的排在未定的前面。"""
    live, tba = [], []
    for d in deadlines:
        if d.get("kind") == "open":
            continue                       # 開放日不是死線，不佔版面
        iso = d.get("date_iso") or ""
        if iso:
            try:
                left = (date.fromisoformat(iso) - today).days
            except ValueError:
                continue
            if left < 0:
                continue
            live.append((left, d))
        elif d.get("status") == "tba":
            tba.append(d)

    live.sort(key=lambda x: x[0])
    if not live and not tba:
        return ('<div class="dl"><p class="note">目前支援的學會都沒有開放中的投稿。'
                '死線一公布就會出現在這裡。</p></div>')

    items = []
    for left, d in live:
        cls = "urgent" if left <= 7 else ("soon" if left <= 30 else "")
        track = TRACK_ZH.get(d.get("track", ""), d.get("track", "投稿"))
        flag = CONF_ZH.get(d.get("confidence", "low"), "")
        flag_html = f'<span class="flag">{flag}</span>' if flag else ""
        items.append(
            f'<li class="{cls}">'
            f'<span class="when">{iso_short(d["date_iso"])}</span>'
            f'<span class="what"><b>{html.escape(d.get("society",""))} · '
            f'{html.escape(track)}</b>{flag_html}'
            f'<span>{html.escape(d.get("cycle") or "")}</span></span>'
            f'<span class="left"><b>{left}</b> 天</span></li>')

    for d in tba:
        track = TRACK_ZH.get(d.get("track", ""), d.get("track", "投稿"))
        items.append(
            f'<li class="tba"><span class="when">未公布</span>'
            f'<span class="what"><b>{html.escape(d.get("society",""))} · '
            f'{html.escape(track)}</b>'
            f'<span>{html.escape(d.get("note") or d.get("cycle") or "")[:70]}</span></span>'
            f'<span class="left">—</span></li>')

    return ('<div class="dl"><ol>' + "".join(items) + "</ol>"
            '<p class="note">日期以各學會官方公告為準。標記「需人工確認」者為從自由'
            '文字擷取，不會寫入行事曆提醒。</p></div>')


def iso_short(s: str) -> str:
    d = _d(s)
    return f"{d.month}/{d.day}<br>{d.year}" if d else html.escape(s)


def render_html(rows: list[dict], today: date, generated: str,
                deadlines: list[dict] | None = None) -> str:
    nxt = next_up(rows, today)
    years = sorted({r["year"] for r in rows if r.get("year")})

    # --- 季節格線 ---
    grid = ['<div class="grid"><div class="gridrow months"><span>月份</span>'
            + "".join(f"<span>{m}</span>" for m in MONTH_ABBR) + "</div>"]
    for y in years:
        in_year = [r for r in rows if r.get("year") == y]
        lanes = assign_lanes(in_year)
        n_lanes = max(lanes.values()) + 1 if lanes else 1
        cls = "yr now" if y == today.year else "yr"
        cells = [f'<span class="{cls}" style="grid-row:span {n_lanes}">{y}</span>']
        for r in in_year:
            m = r["_month"] or 12
            hue = SOCIETY_META.get(r["society"], {}).get("hue", "")
            past = " past" if r["_end"] and r["_end"] < today else ""
            tba = "" if r["_confirmed"] else " tba"
            when = (f'{r["_start"].month}/{r["_start"].day}–'
                    f'{r["_end"].month}/{r["_end"].day}') if r["_confirmed"] else "日期未定"
            place = r.get("city") or r.get("country_or_state") or "—"
            cells.append(
                f'<div class="bar {hue}{past}{tba}" '
                f'style="grid-column:{m + 1};grid-row:{lanes[_key(r)] + 1}" '
                f'title="{html.escape(r.get("name",""))}">'
                f'<b>{html.escape(r["society"])}</b>'
                f'<span>{html.escape(when)}</span>'
                f'<span>{html.escape(place)}</span></div>')
        grid.append('<div class="gridrow">' + "".join(cells) + "</div>")
    grid.append("</div>")

    legend = '<p class="legend">' + "".join(
        f'<span class="{v["hue"]}"><i></i>{k} <em>{v["meeting"]}</em></span>'
        for k, v in SOCIETY_META.items()) + "</p>"

    # --- Event cards ---
    cards = []
    event_years = sorted({r.get("year") for r in rows if r.get("year")})
    year_tabs = ['<button class="year-tab active" type="button" data-year="all">全部</button>']
    year_tabs += [f'<button class="year-tab" type="button" data-year="{year}">{year}</button>'
                  for year in event_years]
    for r in rows:
        hue = SOCIETY_META.get(r["society"], {}).get("hue", "")
        past = bool(r["_end"] and r["_end"] < today)
        upcoming = bool(r["_start"] and r["_start"] >= today)
        state = "past" if past else ("upcoming" if upcoming else "tba")
        year_attr = html.escape(str(r.get("year") or "unknown"))
        visual = html.escape(r["society"])
        logo_url = SOCIETY_META.get(r["society"], {}).get("logo", "")
        if r["_confirmed"]:
            start = r["_start"]
            end = r["_end"]
            date_block = (f'<span class="month">{start.strftime("%b")}</span>'
                          f'<span class="day">{start.day}</span>'
                          f'<span class="year">{start.year}'
                          f'{f"–{end.strftime("%b ")}{end.day}" if end != start else ""}'
                          f'</span>')
            date_text = f'{start.strftime("%b %-d, %Y")} – {end.strftime("%b %-d, %Y")}'
        else:
            date_block = '<span class="tba-date">待公布</span>'
            date_text = r.get("date_text") or "日期尚未公布"
        place = ", ".join(x for x in (r.get("city"), r.get("country_or_state")) if x)
        src = r.get("source_url", "")
        status = "已結束" if past else ("即將舉行" if upcoming else "日期待定")
        cards.append(
            f'<a class="event-card {hue} {state}" data-year="{year_attr}" href="{html.escape(src)}">'
            f'<span class="event-visual{" has-logo" if logo_url else ""}">'
            f'{f"<img class=\"event-logo\" src=\"{html.escape(logo_url)}\" alt=\"{visual} logo\" loading=\"lazy\" onerror=\"this.closest(\'.event-visual\').classList.remove(\'has-logo\');this.remove()\">" if logo_url else f"<strong>{visual}</strong>"}'
            f'</span>'
            f'<span class="event-body">'
            f'<span class="event-org">{html.escape(r["society"])}</span>'
            f'<span class="event-title">{html.escape(r.get("name", ""))}</span>'
            f'<span class="event-meta">'
            f'<span><b>日期</b>{html.escape(date_text)}</span>'
            f'<span><b>地點</b>{html.escape(place or "地點待定")}</span>'
            f'</span>'
            f'<span class="event-status">{status}</span>'
            f'<span class="event-action">查看官方活動</span>'
            f'</span></a>')

    # --- Hero ---
    if nxt:
        place = ", ".join(x for x in (nxt.get("city"), nxt.get("country_or_state")) if x)
        hero = (
            '<section class="hero">'
            '<p class="lede">下一場</p>'
            f'<p class="title">{html.escape(nxt.get("name", ""))}</p>'
            f'<p class="meta">{nxt["_start"].isoformat()} – {nxt["_end"].isoformat()}'
            f'{"　·　" + html.escape(place) if place else ""}</p>'
            f'<p class="count" data-start="{nxt["_start"].isoformat()}">'
            f'<b>—</b> 天後開幕</p></section>')
    else:
        hero = ('<section class="hero"><p class="lede">下一場</p>'
                '<p class="title">目前支援的學會都沒有公布未來場次。</p>'
                '<p class="meta">下次自動更新時會重新檢查。</p></section>')

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>急診國際年會追蹤</title>
<meta name="description" content="七個急診醫學會年會的日期與地點，每週自動更新。">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<header class="masthead">
  <h1>急診國際年會追蹤</h1>
  <p class="stamp">最後更新 {generated}</p>
    <nav aria-label="快速連結">
        <a href="conferences.ics">加入日曆</a>
        <a href="conferences.csv">下載 CSV</a>
    </nav>
</header>

{hero}

<section style="margin-top:3rem">
  <h2>年度節奏</h2>
  {"".join(grid)}
  {legend}
</section>

<section style="margin-top:3rem">
    <div class="event-switcher">
        <h2>Upcoming events</h2>
        <div class="year-tabs" role="tablist" aria-label="選擇活動年份">{"".join(year_tabs)}</div>
    </div>
    <p class="event-count" data-event-count></p>
    <div class="event-grid">{"".join(cards)}</div>
</section>

<footer>
  <p>資料每月自動擷取自各學會官方頁面：</p>
  <ul>
        <li>ACEP — acep.org/sa 與 future-dates</li>
        <li>SAEM — saem.org/meetings-and-events/future-meetings</li>
        <li>IFEM — ifem.cc/about_congress 與 ifem.cc/events</li>
        <li>EuSEM — eusem.org 導向的 eusemcongress.org</li>
        <li>AsianSEM — asiansem.org</li>
        <li>HKCEM — hkcem.org.hk</li>
        <li>SEMS — sems-online.com</li>
  </ul>
  <p>虛線框代表學會只公布了月份、尚未定案確切日期。訂閱
     <a href="conferences.ics">行事曆檔</a>，或下載
     <a href="conferences.csv">CSV</a>／<a href="conferences.json">JSON</a>。</p>
    <p>資料來源為各學會官方頁面；本頁只追蹤年會日期與地點。</p>
</footer>

</div>
<script>
(function(){{
  var el = document.querySelector('.count[data-start]');
  if(!el) return;
  var start = new Date(el.dataset.start + 'T00:00:00');
  var days = Math.ceil((start - new Date()) / 86400000);
  el.querySelector('b').textContent = days > 0 ? days : 0;
  if (days <= 0) el.innerHTML = '<b>進行中</b>';
}})();
(function(){{
    var tabs = document.querySelectorAll('.year-tab');
    var cards = document.querySelectorAll('.event-card');
    var count = document.querySelector('[data-event-count]');
    function select(year){{
        var visible = 0;
        tabs.forEach(function(tab){{
            tab.classList.toggle('active', tab.dataset.year === year);
        }});
        cards.forEach(function(card){{
            var show = year === 'all' || card.dataset.year === year;
            card.hidden = !show;
            if(show) visible += 1;
        }});
        count.textContent = visible + ' 個活動';
    }}
    tabs.forEach(function(tab){{
        tab.addEventListener('click', function(){{ select(tab.dataset.year); }});
    }});
    select('all');
}})();
</script>
</body>
</html>
"""


def write_all(rows_raw: list[dict], outdir: Path, today: date | None = None,
              deadlines: list[dict] | None = None) -> None:
    today = today or date.today()
    rows = prepare(rows_raw)
    deadlines = deadlines or []
    outdir.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    (outdir / "index.html").write_text(
        render_html(rows, today, generated, deadlines), encoding="utf-8")
    (outdir / "conferences.ics").write_text(build_ics(rows, deadlines), encoding="utf-8")
    (outdir / "deadlines.json").write_text(
        json.dumps(deadlines, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "conferences.json").write_text(
        json.dumps(rows_raw, ensure_ascii=False, indent=2), encoding="utf-8")
