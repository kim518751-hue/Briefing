#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Actions 전용 브리핑 스크립트
- config.py 대신 환경변수 사용
- output/index.html 생성 → GitHub Pages가 자동 배포
"""

import sys, os, json, time, base64, smtplib
import http.client, ssl
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── 환경변수에서 설정 로드 ─────────────────────────────────
NAVER_CLIENT_ID     = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
EMAIL_FROM          = os.environ.get("EMAIL_FROM", "")
EMAIL_TO            = os.environ.get("EMAIL_FROM", "")  # 자신에게 발송
EMAIL_PASSWORD      = os.environ.get("NAVER_EMAIL_PASSWORD", "")
GITHUB_USERNAME     = "kim518751-hue"
GITHUB_REPO         = "briefing"

# ══════════════════════════════════════════════════════════════
#  검색 쿼리
# ══════════════════════════════════════════════════════════════

SEARCH_QUERIES = [
    # ── 4대금융 직접 ─────────────────────────────────────────
    {"section": "direct", "label": "신한금융 해외",          "query": "신한금융 해외"},
    {"section": "direct", "label": "신한금융 글로벌",        "query": "신한금융 글로벌"},
    {"section": "direct", "label": "신한금융 해외점포",      "query": "신한금융 해외점포"},
    {"section": "direct", "label": "신한은행 해외",          "query": "신한은행 해외"},
    {"section": "direct", "label": "신한은행 글로벌",        "query": "신한은행 글로벌"},
    {"section": "direct", "label": "하나금융 해외",          "query": "하나금융 해외"},
    {"section": "direct", "label": "하나금융 글로벌",        "query": "하나금융 글로벌"},
    {"section": "direct", "label": "하나금융 해외점포",      "query": "하나금융 해외점포"},
    {"section": "direct", "label": "하나은행 해외",          "query": "하나은행 해외"},
    {"section": "direct", "label": "하나은행 글로벌",        "query": "하나은행 글로벌"},
    {"section": "direct", "label": "KB금융 해외",            "query": "KB금융 해외"},
    {"section": "direct", "label": "KB금융 글로벌",          "query": "KB금융 글로벌"},
    {"section": "direct", "label": "KB금융 해외점포",        "query": "KB금융 해외점포"},
    {"section": "direct", "label": "국민은행 해외",          "query": "국민은행 해외"},
    {"section": "direct", "label": "국민은행 글로벌",        "query": "국민은행 글로벌"},
    {"section": "direct", "label": "농협금융 해외",          "query": "농협금융 해외"},
    {"section": "direct", "label": "농협금융 글로벌",        "query": "농협금융 글로벌"},
    {"section": "direct", "label": "농협은행 해외",          "query": "농협은행 해외"},
    {"section": "direct", "label": "4대금융지주 해외",       "query": "4대금융지주 해외"},
    {"section": "direct", "label": "4대은행 해외진출",       "query": "4대은행 해외진출"},
    {"section": "direct", "label": "시중은행 해외점포",      "query": "시중은행 해외점포"},
    {"section": "direct", "label": "국내은행 해외진출",      "query": "국내은행 해외진출"},
    {"section": "direct", "label": "글로벌디지털 금융",      "query": "글로벌디지털 금융"},

    # ── 국가별 ───────────────────────────────────────────────
    {"section": "country", "label": "신한 미국",             "query": "신한 미국 금융"},
    {"section": "country", "label": "하나 미국",             "query": "하나 미국 금융"},
    {"section": "country", "label": "KB 미국",               "query": "KB 미국 금융"},
    {"section": "country", "label": "농협 미국",             "query": "농협 미국 금융"},
    {"section": "country", "label": "한국계은행 미국",       "query": "한국계은행 미국"},
    {"section": "country", "label": "신한 베트남",           "query": "신한 베트남"},
    {"section": "country", "label": "하나 베트남",           "query": "하나 베트남"},
    {"section": "country", "label": "KB 베트남",             "query": "KB 베트남"},
    {"section": "country", "label": "한국계은행 베트남",     "query": "한국계은행 베트남"},
    {"section": "country", "label": "베트남 은행 진출",      "query": "베트남 은행 진출"},
    {"section": "country", "label": "신한 일본",             "query": "신한 일본"},
    {"section": "country", "label": "하나 일본",             "query": "하나 일본"},
    {"section": "country", "label": "한국계은행 일본",       "query": "한국계은행 일본"},
    {"section": "country", "label": "신한 중국",             "query": "신한 중국"},
    {"section": "country", "label": "하나 중국",             "query": "하나 중국"},
    {"section": "country", "label": "한국계은행 중국",       "query": "한국계은행 중국"},
    {"section": "country", "label": "신한 인도네시아",       "query": "신한 인도네시아"},
    {"section": "country", "label": "하나 인도네시아",       "query": "하나 인도네시아"},
    {"section": "country", "label": "한국계은행 인도네시아", "query": "한국계은행 인도네시아"},
    {"section": "country", "label": "한국계은행 싱가포르",   "query": "한국계은행 싱가포르"},
    {"section": "country", "label": "한국계은행 홍콩",       "query": "한국계은행 홍콩"},

    # ── 정책·규제 ─────────────────────────────────────────────
    {"section": "policy", "label": "해외점포 규제",          "query": "해외점포 규제"},
    {"section": "policy", "label": "금융위원회 해외",        "query": "금융위원회 해외"},
    {"section": "policy", "label": "금융감독원 해외",        "query": "금융감독원 해외"},
    {"section": "policy", "label": "외국계은행 인허가",      "query": "외국계은행 인허가"},
    {"section": "policy", "label": "은행 해외 AML",          "query": "은행 해외 AML"},
    {"section": "policy", "label": "국제금융 규제",          "query": "국제금융 규제"},

    # ── 디지털·결제 ───────────────────────────────────────────
    {"section": "digital", "label": "은행 해외송금",         "query": "은행 해외송금"},
    {"section": "digital", "label": "디지털금융 해외",       "query": "디지털금융 해외"},
    {"section": "digital", "label": "핀테크 해외진출",       "query": "핀테크 해외진출"},
    {"section": "digital", "label": "CBDC 은행",             "query": "CBDC 은행"},
    {"section": "digital", "label": "스테이블코인 금융",     "query": "스테이블코인 금융"},
    {"section": "digital", "label": "QR결제 해외",           "query": "QR결제 해외"},
    {"section": "digital", "label": "블록체인 금융 해외",    "query": "블록체인 금융 해외"},

    # ── 거시·환율 ─────────────────────────────────────────────
    {"section": "macro", "label": "환율 국내은행",           "query": "환율 국내은행"},
    {"section": "macro", "label": "연준 금리 은행",          "query": "연준 금리 은행"},
    {"section": "macro", "label": "아시아 금융시장",         "query": "아시아 금융시장"},
    {"section": "macro", "label": "국제금융 동향",           "query": "국제금융 동향"},
]

SECTION_LABELS = {
    "direct":  ("🏦", "01", "4대금융지주 직접 기사"),
    "country": ("🌏", "02", "국가별 해외사업 동향"),
    "policy":  ("📋", "03", "해외 정책·규제 이슈"),
    "digital": ("💳", "04", "디지털·결제·핀테크"),
    "macro":   ("📊", "05", "거시·환율·금리"),
}

# ══════════════════════════════════════════════════════════════
#  유틸
# ══════════════════════════════════════════════════════════════

def pad(n): return str(n).zfill(2)

def parse_pub_date(s):
    try:
        dt = datetime.strptime(s.strip(), "%a, %d %b %Y %H:%M:%S %z")
        return dt.strftime("%Y%m%d")
    except:
        return ""

def clean_html(text):
    import re
    text = re.sub(r"<[^>]+>", "", text)
    for a, b in [("&quot;",'"'),("&amp;","&"),("&lt;","<"),("&gt;",">"),("&#39;","'"),("&nbsp;"," ")]:
        text = text.replace(a, b)
    return text.strip()

def extract_source(url):
    MAP = {
        "g-enews.com":"글로벌이코노미","thebell.co.kr":"더벨","newspim.com":"뉴스핌",
        "yna.co.kr":"연합뉴스","hankyung.com":"한국경제","mk.co.kr":"매일경제",
        "edaily.co.kr":"이데일리","mt.co.kr":"머니투데이","asiae.co.kr":"아시아경제",
        "sedaily.com":"서울경제","fnnews.com":"파이낸셜뉴스","newsis.com":"뉴시스",
        "news1.kr":"뉴스1","fntimes.com":"한국금융신문",
    }
    for domain, name in MAP.items():
        if domain in url: return name
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.","").split(".")[0]
    except: return "기타"

def score_article(title, summary=""):
    text = (title + " " + summary).lower()
    score = 0
    if any(k in text for k in ["신한금융","하나금융","kb금융","농협금융","국민은행","4대금융"]):
        score += 3
    if any(k in text for k in ["해외","국외","글로벌","해외점포","현지법인"]):
        score += 2
    if any(k in text for k in ["규제","정책","인허가","감독","제재"]):
        score += 2
    if any(k in text for k in ["결제","디지털","핀테크","송금","cbdc"]):
        score += 2
    if any(k in text for k in ["연준","금리","환율","통화"]):
        score += 1
    if any(k in text for k in ["미국","중국","베트남","일본","인도네시아","싱가포르"]):
        score += 1
    return score

def deduplicate(articles):
    seen_links, seen_titles, result = set(), set(), []
    for a in articles:
        link = a["link"].split("?")[0]
        title_key = a["title"][:20]
        if link in seen_links or title_key in seen_titles:
            continue
        seen_links.add(link)
        seen_titles.add(title_key)
        result.append(a)
    return result

# ══════════════════════════════════════════════════════════════
#  네이버 API (http.client 사용 - 인코딩 문제 없음)
# ══════════════════════════════════════════════════════════════

def search_naver_news(query, target_date, display=100):
    try:
        q_bytes = query.encode("utf-8")
        q_enc = "".join(f"%{b:02X}" for b in q_bytes)
        path = f"/v1/search/news.json?query={q_enc}&display={display}&sort=date"
        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection("openapi.naver.com", 443, context=ctx, timeout=8)
        conn.request("GET", path, headers={
            "X-Naver-Client-Id":     NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        })
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        if resp.status != 200:
            return []
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        print(f"Error: {e}")
        return []

    target_dt = datetime.strptime(target_date, "%Y%m%d")
    valid = {
        (target_dt - timedelta(days=1)).strftime("%Y%m%d"),
        target_date,
        (target_dt + timedelta(days=1)).strftime("%Y%m%d"),
    }

    matched = []
    for item in data.get("items", []):
        pd = parse_pub_date(item.get("pubDate", ""))
        if pd in valid:
            matched.append({
                "title":   clean_html(item.get("title", "")),
                "link":    item.get("originallink") or item.get("link", ""),
                "summary": clean_html(item.get("description", ""))[:150],
                "pub_date": pd,
                "source":  extract_source(item.get("originallink", "")),
            })
    return matched

# ══════════════════════════════════════════════════════════════
#  브리핑 실행
# ══════════════════════════════════════════════════════════════

def run_briefing(target_date):
    print(f"Briefing date: {target_date}")
    results = {}
    for i, q in enumerate(SEARCH_QUERIES):
        sec, label, query = q["section"], q["label"], q["query"]
        print(f"[{i+1}/{len(SEARCH_QUERIES)}] {label}")
        arts = search_naver_news(query, target_date)
        if sec not in results: results[sec] = []
        for a in arts:
            a["score"] = score_article(a["title"], a["summary"])
            a["query_label"] = label
        results[sec].extend(arts)

    for sec in results:
        results[sec] = deduplicate(results[sec])
        results[sec].sort(key=lambda x: x["score"], reverse=True)

    total = sum(len(v) for v in results.values())
    print(f"Total: {total} articles")
    return results

# ══════════════════════════════════════════════════════════════
#  HTML 생성
# ══════════════════════════════════════════════════════════════

def generate_html(results, target_date):
    date_fmt = f"{target_date[:4]}.{target_date[4:6]}.{target_date[6:]}"
    total = sum(len(v) for v in results.values())
    now_str = datetime.now().strftime("%Y.%m.%d %H:%M")
    gh_url = f"https://{GITHUB_USERNAME}.github.io/{GITHUB_REPO}"

    sections_html = ""
    for sec in ["direct","country","policy","digital","macro"]:
        if sec not in results: continue
        icon, num, sec_title = SECTION_LABELS[sec]
        arts = results[sec]
        rows = ""
        if not arts:
            rows = '<tr><td colspan="3" style="text-align:center;color:#aaa;padding:20px;">해당 기사 없음</td></tr>'
        else:
            for a in arts:
                score = a["score"]
                if score >= 6:
                    badge = '<span style="background:#8b0000;color:white;padding:2px 6px;border-radius:3px;font-size:.62rem;font-weight:700;">HIGH</span>'
                elif score >= 4:
                    badge = '<span style="background:#003366;color:white;padding:2px 6px;border-radius:3px;font-size:.62rem;font-weight:700;">MID</span>'
                else:
                    badge = '<span style="background:#ddd;color:#888;padding:2px 6px;border-radius:3px;font-size:.62rem;">LOW</span>'
                src_color = {"글로벌이코노미":"#c0392b","더벨":"#1a1a2e","뉴스핌":"#005b99","연합뉴스":"#cc0000","한국경제":"#0055a5"}.get(a["source"],"#555")
                rows += f"""<tr>
<td style="white-space:nowrap;color:{src_color};font-weight:700;font-size:.7rem;padding:10px 8px;vertical-align:top;">{a['source']}</td>
<td style="padding:10px 8px;vertical-align:top;">
  <a href="{a['link']}" target="_blank" style="font-size:.88rem;font-weight:600;color:#0d1117;text-decoration:none;line-height:1.5;display:block;">{a['title']}</a>
  <div style="font-size:.72rem;color:#888;margin-top:3px;">{a['summary']}</div>
</td>
<td style="white-space:nowrap;vertical-align:top;padding:10px 8px;">{badge}</td>
</tr>"""

        sec_color = {"direct":"#003366","country":"#1b5e20","policy":"#7a0000","digital":"#4a1a80","macro":"#7a4f00"}.get(sec,"#333")
        sections_html += f"""<div class="section">
<div class="section-header" style="border-bottom-color:{sec_color}">
  <span>{icon}</span><span style="font-family:monospace;font-size:.65rem;color:#888;">{num}</span>
  <span class="sec-title">{sec_title}</span>
  <span class="sec-count">{len(arts)}건</span>
</div>
<table class="article-table">
<thead><tr><th style="width:80px;">언론사</th><th>제목 / 요약</th><th style="width:50px;">영향도</th></tr></thead>
<tbody>{rows}</tbody>
</table></div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta property="og:title" content="글로벌사업 뉴스 브리핑 {date_fmt}">
<meta property="og:description" content="4대금융지주 해외사업 모니터링 · {total}건">
<title>글로벌 브리핑 {date_fmt}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Malgun Gothic',sans-serif;background:#f5f0e8;color:#0d1117;font-size:14px;}}
.masthead{{background:#0d1117;color:white;padding:18px 20px 14px;border-bottom:4px solid #d4a017;}}
.mh-title{{font-size:1.5rem;font-weight:700;}}
.mh-title span{{color:#d4a017;}}
.mh-meta{{font-size:.68rem;color:#aaa;margin-top:6px;line-height:1.8;}}
.share-bar{{background:#003366;color:white;padding:10px 20px;font-size:.75rem;}}
.share-url{{font-family:monospace;font-size:.7rem;color:#d4a017;}}
.info-bar{{background:#ede8dc;border-bottom:2px solid #c8b99a;padding:8px 20px;display:flex;gap:16px;flex-wrap:wrap;font-size:.7rem;color:#6b5f4a;}}
.info-bar strong{{color:#0d1117;}}
.main{{max-width:900px;margin:0 auto;padding:16px;}}
.section{{margin-bottom:28px;}}
.section-header{{display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:2px solid #0d1117;margin-bottom:8px;}}
.sec-title{{font-size:.92rem;font-weight:700;}}
.sec-count{{margin-left:auto;font-family:monospace;font-size:.65rem;background:#0d1117;color:white;padding:2px 8px;border-radius:10px;}}
.article-table{{width:100%;border-collapse:collapse;}}
.article-table th{{background:#0d1117;color:white;font-size:.68rem;font-weight:500;padding:6px 8px;text-align:left;}}
.article-table td{{border-bottom:1px solid #c8b99a;}}
.article-table tr:hover td{{background:#ede8dc;}}
@media(max-width:600px){{
  .article-table th:last-child,.article-table td:last-child{{display:none;}}
}}
</style>
</head>
<body>
<div class="masthead">
  <div class="mh-title">글로벌사업 <span>뉴스 브리핑</span></div>
  <div class="mh-meta">📅 {date_fmt} 기준 · 총 {total}건 · 생성 {now_str} · 부행장 보고용</div>
</div>
<div class="share-bar">
  🔗 공유 URL: <span class="share-url">{gh_url}</span>
</div>
<div class="info-bar">
  <span>📰 총 기사: <strong>{total}건</strong></span>
  <span>🔴 HIGH: <strong>{sum(1 for v in results.values() for a in v if a['score']>=6)}건</strong></span>
  <span>🟡 MID: <strong>{sum(1 for v in results.values() for a in v if 4<=a['score']<6)}건</strong></span>
</div>
<div class="main">
{sections_html}
<div style="margin-top:24px;padding:12px 16px;background:#ede8dc;border-left:4px solid #d4a017;font-size:.68rem;color:#6b5f4a;line-height:1.8;">
  🔴 HIGH(6+점) · 🟡 MID(4-5점) · ⚪ LOW · 자동생성 {now_str}
</div>
</div>
</body>
</html>"""

# ══════════════════════════════════════════════════════════════
#  이메일 발송
# ══════════════════════════════════════════════════════════════

def send_email(results, target_date):
    if not EMAIL_FROM or not EMAIL_PASSWORD:
        print("Email config missing, skipping")
        return

    date_fmt = f"{target_date[:4]}.{target_date[4:6]}.{target_date[6:]}"
    total = sum(len(v) for v in results.values())
    gh_url = f"https://{GITHUB_USERNAME}.github.io/{GITHUB_REPO}"

    body = f"""<html><body style="font-family:'Malgun Gothic',sans-serif;max-width:680px;margin:0 auto;">
<div style="background:#0d1117;color:white;padding:16px 20px;border-bottom:4px solid #d4a017;">
  <h2 style="margin:0;font-size:1.1rem;">글로벌사업 뉴스 브리핑 {date_fmt}</h2>
  <div style="color:#aaa;font-size:.72rem;margin-top:4px;">총 {total}건 · 부행장 보고용</div>
</div>
<div style="background:#003366;color:white;padding:10px 20px;font-size:.82rem;">
  공유 URL: <a href="{gh_url}" style="color:#d4a017;font-weight:700;">{gh_url}</a>
</div>
<div style="padding:16px 20px;">"""

    for sec in ["direct","country","policy","digital","macro"]:
        if sec not in results or not results[sec]: continue
        icon, num, sec_title = SECTION_LABELS[sec]
        arts = results[sec]
        body += f'<h3 style="font-size:.88rem;border-bottom:2px solid #0d1117;padding-bottom:4px;margin:16px 0 8px;">{icon} {num} {sec_title} ({len(arts)}건)</h3>'
        for a in arts:
            dot = "🔴" if a["score"]>=6 else "🟡" if a["score"]>=4 else "⚪"
            body += f"""<div style="padding:7px 0;border-bottom:1px solid #eee;">
  <span style="font-size:.68rem;color:#555;">[{a['source']}] {dot}</span><br>
  <a href="{a['link']}" style="font-size:.86rem;font-weight:600;color:#0d1117;text-decoration:none;">{a['title']}</a><br>
  <span style="font-size:.7rem;color:#aaa;">{a['summary'][:100]}</span>
</div>"""

    body += f'</div><div style="background:#f5f0e8;padding:10px 20px;font-size:.65rem;color:#888;">자동생성 {date_fmt}</div></body></html>'

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[글로벌브리핑] {date_fmt} 해외사업 뉴스 ({total}건)"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.naver.com", 465) as smtp:
            smtp.login(EMAIL_FROM, EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print("Email sent successfully")
    except Exception as e:
        print(f"Email error: {e}")

# ══════════════════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    target_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    print(f"Starting briefing for {target_date}")

    # 기사 수집
    results = run_briefing(target_date)

    # HTML 생성
    Path("output").mkdir(exist_ok=True)
    html = generate_html(results, target_date)
    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML saved: output/index.html")

    # 이메일 발송
    send_email(results, target_date)

    print("Done!")
