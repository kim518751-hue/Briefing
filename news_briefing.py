#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
글로벌 디지털 BIZ 데일리 브리핑 에이전트
- 전일자(KST) 뉴스를 Naver 뉴스 검색 API로 수집
- Claude API로 카테고리별 요약 + 시사점(우리은행 글로벌디지털 관점) 생성
- 모바일 반응형 HTML 대시보드(index.html) 발행 → GitHub Pages
- GitHub Actions 크론으로 매일 자동 실행

환경변수(=GitHub Secrets):
  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET   (필수)
  ANTHROPIC_API_KEY                      (선택: 없으면 추출요약 폴백)
  CLAUDE_MODEL                           (선택: 기본 claude-haiku-4-5-20251001)

사용:
  python news_briefing.py            # 실제 수집/발행
  python news_briefing.py --demo     # 샘플 데이터로 HTML만 생성(키 불필요)
"""

import os
import re
import sys
import json
import html
import time
import datetime
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

KST = datetime.timezone(datetime.timedelta(hours=9))

# ---------------------------------------------------------------------------
# 1) 수집 카테고리 & 키워드 (자유롭게 편집)
#    각 키워드는 Naver 뉴스 검색에 그대로 던져집니다.
# ---------------------------------------------------------------------------
CATEGORIES = {
    "국내은행 글로벌·디지털": [
        "신한은행 글로벌", "신한은행 해외", "KB국민은행 글로벌", "하나은행 글로벌",
        "우리은행 글로벌", "우리은행 디지털", "농협은행 글로벌", "카카오뱅크 해외",
        "케이뱅크 디지털", "은행 동남아 진출", "은행 디지털 전환", "은행 해외법인",
    ],
    "국제정세·금융": [
        "미국 금리 연준", "중국 경제 위안화", "일본 금융 엔화", "유럽 ECB 금리",
        "러시아 제재", "동남아 경제", "베트남 경제", "인도네시아 금융", "환율 시장",
    ],
    "국내기업 해외사업": [
        "한국기업 해외진출", "삼성 해외사업", "현대차 해외", "K-금융 수출",
        "한국 동남아 투자", "스타트업 해외진출",
    ],
    "글로벌 핀테크": [
        "글로벌 핀테크", "디지털뱅킹", "스테이블코인", "CBDC", "임베디드 금융",
        "BaaS 뱅킹", "크로스보더 결제", "디지털 지갑", "AI 금융",
    ],
}

# 카테고리별 최대 노출 기사 수
MAX_PER_CATEGORY = 8
# 키워드당 Naver 조회 개수
DISPLAY_PER_QUERY = 15

# ---------------------------------------------------------------------------
# 2) Naver 뉴스 수집
# ---------------------------------------------------------------------------
def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    return html.unescape(s).strip()


def search_naver(query, client_id, client_secret, display=15, sort="date"):
    url = "https://openapi.naver.com/v1/search/news.json?" + urllib.parse.urlencode(
        {"query": query, "display": display, "sort": sort}
    )
    req = urllib.request.Request(url)
    req.add_header("X-Naver-Client-Id", client_id)
    req.add_header("X-Naver-Client-Secret", client_secret)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("items", [])
    except urllib.error.HTTPError as e:
        print(f"  [WARN] '{query}' HTTP {e.code}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  [WARN] '{query}' {e}", file=sys.stderr)
        return []


def parse_pubdate(s):
    try:
        return parsedate_to_datetime(s).astimezone(KST)
    except Exception:
        return None


def parse_google_rss(xml_bytes):
    """구글 뉴스 RSS 바이트 → 표준 항목 리스트(테스트 가능하도록 분리)."""
    out = []
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        # 구글은 제목 끝에 " - 매체명"을 붙임 → 정리
        if source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)].strip()
        out.append({"title": title, "link": link, "pubDate": pub,
                    "description": "", "source": source})
    return out


def fetch_google_news_rss(query, n=15):
    """API 키 불필요. 구글 뉴스 RSS에서 한국어 기사 수집."""
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return parse_google_rss(resp.read())[:n]
    except Exception as e:
        print(f"  [WARN] RSS '{query}' {e}", file=sys.stderr)
        return []


def collect(target_day):
    """target_day(KST)에 해당하는 기사만 카테고리별로 수집/중복제거.
    네이버 키가 있으면 네이버를, 없으면 자동으로 구글뉴스 RSS(키 불필요)를 사용."""
    cid = os.environ.get("NAVER_CLIENT_ID")
    csec = os.environ.get("NAVER_CLIENT_SECRET")
    use_naver = bool(cid and csec)
    print("  뉴스 소스:", "네이버" if use_naver else "구글뉴스 RSS (API 키 불필요)")

    grouped = {}
    seen_titles = set()
    for cat, keywords in CATEGORIES.items():
        bucket = []
        for kw in keywords:
            if use_naver:
                rows = [{
                    "title": strip_tags(x.get("title", "")),
                    "link": x.get("originallink") or x.get("link", ""),
                    "pubDate": x.get("pubDate", ""),
                    "description": strip_tags(x.get("description", "")),
                    "source": domain_of(x.get("originallink") or x.get("link", "")),
                } for x in search_naver(kw, cid, csec, DISPLAY_PER_QUERY)]
            else:
                rows = fetch_google_news_rss(kw, DISPLAY_PER_QUERY)

            for it in rows:
                pub = parse_pubdate(it.get("pubDate", ""))
                if pub is None or pub.date() != target_day:
                    continue
                title = it.get("title", "")
                norm = re.sub(r"\s+", "", title)[:40]
                if not title or norm in seen_titles:
                    continue
                seen_titles.add(norm)
                bucket.append({
                    "title": title,
                    "desc": it.get("description", ""),
                    "link": it.get("link", ""),
                    "source": it.get("source") or domain_of(it.get("link", "")),
                    "pub": pub.strftime("%H:%M"),
                    "pub_sort": pub,
                    "category": cat,
                })
            time.sleep(0.1)
        bucket.sort(key=lambda x: x["pub_sort"], reverse=True)
        grouped[cat] = bucket[:MAX_PER_CATEGORY]
        print(f"  {cat}: {len(grouped[cat])}건")
    return grouped


def domain_of(link):
    try:
        host = urllib.parse.urlparse(link).netloc
        return host.replace("www.", "")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 3) Claude 요약 + 시사점
# ---------------------------------------------------------------------------
def summarize_with_claude(grouped, api_key, model):
    """각 기사에 summary, implication 필드를 추가."""
    flat = [a for items in grouped.values() for a in items]
    if not flat:
        return grouped

    # 토큰 절약 위해 청크 처리
    CHUNK = 12
    for i in range(0, len(flat), CHUNK):
        chunk = flat[i:i + CHUNK]
        payload = [
            {"idx": j, "category": a["category"], "title": a["title"], "desc": a["desc"][:300]}
            for j, a in enumerate(chunk)
        ]
        prompt = (
            "당신은 우리은행 글로벌전략부 글로벌디지털팀의 리서치 애널리스트입니다.\n"
            "아래 뉴스 각각에 대해 (1) 핵심 요약 1~2문장, (2) 우리은행 글로벌 디지털 사업 관점의 "
            "시사점 1문장을 작성하세요. 과장 없이 사실 기반으로 간결하게.\n"
            "반드시 아래 JSON 배열 형식만 출력(설명/마크다운/코드펜스 금지):\n"
            '[{"idx":0,"summary":"...","implication":"..."}, ...]\n\n'
            f"뉴스:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        try:
            result = _call_anthropic(prompt, api_key, model)
            parsed = _safe_json(result)
            by_idx = {int(o["idx"]): o for o in parsed if "idx" in o}
            for j, a in enumerate(chunk):
                o = by_idx.get(j, {})
                a["summary"] = o.get("summary") or a["desc"][:120]
                a["implication"] = o.get("implication") or ""
        except Exception as e:
            print(f"  [WARN] 요약 실패(청크 {i}): {e}", file=sys.stderr)
            for a in chunk:
                a["summary"] = a["desc"][:120]
                a["implication"] = ""
    return grouped


def _call_anthropic(prompt, api_key, model):
    body = json.dumps({
        "model": model,
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body)
    req.add_header("content-type", "application/json")
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", "2023-06-01")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def _safe_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def fallback_summary(grouped):
    for items in grouped.values():
        for a in items:
            a.setdefault("summary", a["desc"][:120])
            a.setdefault("implication", "")
    return grouped


# ---------------------------------------------------------------------------
# 4) 모바일 반응형 HTML
# ---------------------------------------------------------------------------
def build_html(date_label, grouped, generated_at):
    total = sum(len(v) for v in grouped.values())
    date_js = json.dumps(date_label.split(" (")[0], ensure_ascii=False)
    cat_icons = {
        "국내은행 글로벌·디지털": "🏦",
        "국제정세·금융": "🌐",
        "국내기업 해외사업": "📦",
        "글로벌 핀테크": "💳",
    }

    nav = "".join(
        f'<a class="chip" href="#cat{i}">{cat_icons.get(c, "•")} {html.escape(c)}'
        f'<span class="cnt">{len(grouped[c])}</span></a>'
        for i, c in enumerate(grouped)
    )

    def attr(s):
        return html.escape(s or "", quote=True)

    sections = []
    for i, (cat, items) in enumerate(grouped.items()):
        cards = []
        if not items:
            cards.append('<p class="empty">전일자 신규 기사가 없습니다.</p>')
        for a in items:
            impl = (
                f'<div class="impl"><span class="impl-tag">시사점</span>{html.escape(a["implication"])}</div>'
                if a.get("implication") else ""
            )
            src = html.escape(a["source"]) if a["source"] else "출처"
            cards.append(f"""
        <article class="card"
          data-title="{attr(a['title'])}"
          data-link="{attr(a['link'])}"
          data-summary="{attr(a.get('summary',''))}"
          data-impl="{attr(a.get('implication',''))}">
          <div class="meta">
            <span class="src">{src} · {a["pub"]}</span>
            <button class="share1" onclick="shareOne(this)" aria-label="이 기사 공유">↗ 공유</button>
          </div>
          <a class="title" href="{html.escape(a["link"])}" target="_blank" rel="noopener">{html.escape(a["title"])}</a>
          <p class="summary">{html.escape(a.get("summary",""))}</p>
          {impl}
          <label class="pickrow">
            <input type="checkbox" class="pick" onchange="onPick(this)"> 공유 목록에 담기
          </label>
        </article>""")
        sections.append(f"""
      <section id="cat{i}" class="cat">
        <h2>{cat_icons.get(cat,"•")} {html.escape(cat)} <span class="badge">{len(items)}</span></h2>
        {''.join(cards)}
      </section>""")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>글로벌 디지털 데일리 브리핑 · {html.escape(date_label)}</title>
<style>
  :root {{
    --blue:#0067AC; --blue-d:#0E4194; --ink:#16202C; --muted:#6B7785;
    --bg:#F4F6F9; --card:#FFFFFF; --line:#E6EBF1; --accent:#0067AC;
  }}
  * {{ box-sizing:border-box; -webkit-tap-highlight-color:transparent; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Apple SD Gothic Neo","Malgun Gothic",sans-serif;
    line-height:1.5; }}
  header {{ position:sticky; top:0; z-index:10;
    background:linear-gradient(135deg,var(--blue-d),var(--blue));
    color:#fff; padding:18px 16px 14px; box-shadow:0 2px 10px rgba(14,65,148,.18); }}
  header .eyebrow {{ font-size:12px; letter-spacing:.08em; opacity:.85; }}
  header h1 {{ margin:2px 0 4px; font-size:19px; font-weight:800; }}
  header .date {{ font-size:13px; opacity:.92; }}
  header .stat {{ font-size:12px; opacity:.82; margin-top:6px; }}
  nav {{ display:flex; gap:8px; overflow-x:auto; padding:12px 16px;
    background:#fff; border-bottom:1px solid var(--line); position:sticky; top:0; }}
  .chip {{ flex:0 0 auto; display:flex; align-items:center; gap:6px;
    background:#EEF4FA; color:var(--blue-d); text-decoration:none;
    padding:7px 12px; border-radius:20px; font-size:13px; font-weight:600; white-space:nowrap; }}
  .chip .cnt {{ background:var(--blue); color:#fff; border-radius:10px;
    font-size:11px; padding:1px 7px; }}
  main {{ max-width:760px; margin:0 auto; padding:8px 14px 60px; }}
  .cat {{ margin-top:18px; scroll-margin-top:72px; }}
  .cat h2 {{ font-size:16px; font-weight:800; color:var(--blue-d);
    display:flex; align-items:center; gap:8px; margin:14px 2px 10px;
    padding-bottom:8px; border-bottom:2px solid var(--blue); }}
  .badge {{ font-size:12px; background:var(--blue-d); color:#fff;
    border-radius:10px; padding:1px 8px; font-weight:700; }}
  .card {{ background:var(--card); border:1px solid var(--line);
    border-radius:14px; padding:14px 15px; margin-bottom:11px;
    box-shadow:0 1px 3px rgba(20,32,44,.04); }}
  .meta {{ display:flex; justify-content:space-between; font-size:11.5px;
    color:var(--muted); margin-bottom:5px; }}
  .src {{ font-weight:600; }}
  .title {{ display:block; font-size:15px; font-weight:700; color:var(--ink);
    text-decoration:none; line-height:1.4; }}
  .title:active {{ color:var(--blue); }}
  .summary {{ font-size:13.5px; color:#33414F; margin:7px 0 0; }}
  .impl {{ margin-top:9px; background:#F0F6FB; border-left:3px solid var(--blue);
    border-radius:6px; padding:8px 10px; font-size:13px; color:#1B3A5C; }}
  .impl-tag {{ display:inline-block; background:var(--blue); color:#fff;
    font-size:10.5px; font-weight:700; padding:1px 6px; border-radius:5px; margin-right:6px; }}
  .empty {{ color:var(--muted); font-size:13px; padding:6px 2px; }}
  /* 선택/공유 컨트롤 */
  .meta {{ align-items:center; }}
  .share1 {{ border:1px solid var(--line); background:#fff; color:var(--blue);
    font-size:11.5px; font-weight:700; padding:3px 9px; border-radius:14px; cursor:pointer; }}
  .share1:active {{ background:var(--blue); color:#fff; }}
  .pickrow {{ display:flex; align-items:center; gap:7px; margin-top:11px;
    padding-top:10px; border-top:1px dashed var(--line);
    font-size:12.5px; font-weight:600; color:var(--muted); cursor:pointer; user-select:none; }}
  .pick {{ width:18px; height:18px; accent-color:var(--blue); cursor:pointer; }}
  .card.sel {{ border-color:var(--blue); box-shadow:0 0 0 2px rgba(0,103,172,.18); }}
  .card.sel .pickrow {{ color:var(--blue); }}
  /* 하단 공유 바 */
  .sharebar {{ position:fixed; left:0; right:0; bottom:0; z-index:30;
    transform:translateY(120%); transition:transform .28s ease;
    background:var(--blue-d); color:#fff; padding:11px 14px calc(11px + env(safe-area-inset-bottom));
    display:flex; align-items:center; gap:10px; box-shadow:0 -3px 14px rgba(14,65,148,.3); }}
  .sharebar.on {{ transform:translateY(0); }}
  .sharebar .cntbox {{ font-size:13px; font-weight:700; white-space:nowrap; }}
  .sharebar .cntbox b {{ font-size:16px; }}
  .sharebar .grow {{ flex:1; }}
  .sharebar button {{ border:0; border-radius:10px; font-size:13px; font-weight:700;
    padding:9px 14px; cursor:pointer; }}
  .btn-clear {{ background:rgba(255,255,255,.16); color:#fff; }}
  .btn-copy {{ background:#fff; color:var(--blue-d); }}
  .btn-share {{ background:#FFD23F; color:#3A2E00; }}
  .toast {{ position:fixed; left:50%; bottom:78px; transform:translateX(-50%) translateY(20px);
    background:#16202C; color:#fff; font-size:13px; padding:10px 16px; border-radius:22px;
    opacity:0; pointer-events:none; transition:opacity .25s, transform .25s; z-index:40; }}
  .toast.on {{ opacity:.96; transform:translateX(-50%) translateY(0); }}
  footer {{ text-align:center; color:var(--muted); font-size:11.5px; padding:24px 16px 90px; }}
  @media (min-width:640px) {{ header h1 {{ font-size:22px; }} }}
  @media (prefers-reduced-motion:reduce) {{ * {{ transition:none!important; }} }}
</style>
</head>
<body>
  <header>
    <div class="eyebrow">WOORI BANK · GLOBAL DIGITAL TEAM</div>
    <h1>글로벌 디지털 데일리 브리핑</h1>
    <div class="date">📅 {html.escape(date_label)} (전일자 기준)</div>
    <div class="stat">총 {total}건 · 4개 카테고리</div>
  </header>
  <nav>{nav}</nav>
  <main>
    {''.join(sections)}
  </main>
  <footer>
    자동 생성 {html.escape(generated_at)} · Naver News API + Claude<br>
    내부 참고용 · 원문 링크의 저작권은 각 언론사에 있습니다.
  </footer>

  <div class="toast" id="toast"></div>
  <div class="sharebar" id="sharebar">
    <span class="cntbox"><b id="selcnt">0</b>건 담음</span>
    <span class="grow"></span>
    <button class="btn-clear" onclick="clearPicks()">비우기</button>
    <button class="btn-copy" onclick="shareSelected('copy')">복사</button>
    <button class="btn-share" onclick="shareSelected('share')">공유</button>
  </div>

<script>
  var DATE_LABEL = {date_js};

  function cardText(el){{
    var d = el.dataset, out = ['📌 ' + d.title];
    if (d.summary) out.push('🔎 ' + d.summary);
    if (d.impl)    out.push('💡 ' + d.impl);
    out.push('🔗 ' + d.link);
    return out.join('\\n');
  }}

  function onPick(box){{
    box.closest('.card').classList.toggle('sel', box.checked);
    refreshBar();
  }}
  function refreshBar(){{
    var n = document.querySelectorAll('.pick:checked').length;
    document.getElementById('selcnt').textContent = n;
    document.getElementById('sharebar').classList.toggle('on', n > 0);
  }}
  function clearPicks(){{
    document.querySelectorAll('.pick:checked').forEach(function(b){{
      b.checked = false; b.closest('.card').classList.remove('sel');
    }});
    refreshBar();
  }}

  function buildSelectedText(){{
    var cards = [].slice.call(document.querySelectorAll('.pick:checked'))
      .map(function(b){{ return b.closest('.card'); }});
    if (!cards.length) return '';
    var head = '[글로벌 디지털 브리핑 · ' + DATE_LABEL + '] 주요 기사 ' + cards.length + '건';
    return head + '\\n\\n' + cards.map(cardText).join('\\n\\n');
  }}

  async function shareSelected(mode){{
    var text = buildSelectedText();
    if (!text) {{ toast('담은 기사가 없습니다'); return; }}
    await deliver(text, mode);
  }}
  async function shareOne(btn){{
    var text = cardText(btn.closest('.card'));
    await deliver(text, 'share');
  }}

  async function deliver(text, mode){{
    if (mode === 'share' && navigator.share) {{
      try {{ await navigator.share({{ title: '글로벌 디지털 브리핑', text: text }}); return; }}
      catch (e) {{ if (e && e.name === 'AbortError') return; }}  // 사용자가 닫음
    }}
    copyText(text);
  }}

  function copyText(text){{
    if (navigator.clipboard && window.isSecureContext) {{
      navigator.clipboard.writeText(text)
        .then(function(){{ toast('복사됨 · 붙여넣기로 공유하세요'); }})
        .catch(function(){{ legacyCopy(text); }});
    }} else {{ legacyCopy(text); }}
  }}
  function legacyCopy(text){{
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try {{ document.execCommand('copy'); toast('복사됨 · 붙여넣기로 공유하세요'); }}
    catch (e) {{ toast('복사 실패 — 길게 눌러 복사하세요'); }}
    document.body.removeChild(ta);
  }}

  var _t;
  function toast(msg){{
    var el = document.getElementById('toast');
    el.textContent = msg; el.classList.add('on');
    clearTimeout(_t); _t = setTimeout(function(){{ el.classList.remove('on'); }}, 2200);
  }}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 5) 데모 데이터
# ---------------------------------------------------------------------------
def demo_grouped():
    samples = {
        "국내은행 글로벌·디지털": [
            ("신한은행, 베트남 디지털뱅킹 'SOL' 가입자 100만 돌파",
             "신한베트남은행이 모바일 플랫폼 SOL의 누적 가입자가 100만명을 넘어섰다고 밝혔다.",
             "경쟁사 동남아 디지털 채널 선점이 가속화되는 만큼 우리은행도 현지 슈퍼앱 전략 점검 필요."),
            ("하나은행, 인도네시아 법인 통합 마무리…디지털 전환 본격화",
             "하나은행이 현지 통합법인 시스템 통합을 완료하고 디지털 리테일을 확대한다.",
             "OJK Single Presence 정책 대응 사례로, BWS 중장기 전략 벤치마킹 포인트."),
            ("KB국민은행, 캄보디아 프라삭과 모바일 여신 자동화 추진",
             "KB가 프라삭은행 디지털 여신심사 자동화에 AI 신용평가를 도입한다.",
             "WBCH AI 신용평가 도입 시점·NPL 관리 연계 검토 필요."),
        ],
        "국제정세·금융": [
            ("美 연준, 기준금리 동결…연내 인하 신호 유지",
             "연준이 기준금리를 동결하며 인플레이션 둔화 시 인하 가능성을 시사했다.",
             "달러 약세 전환 시 동남아 현지통화 자산 환헤지 전략 재점검."),
            ("中 위안화 국제결제 비중 확대…CIPS 거래 증가",
             "위안화 국경간 결제 시스템 CIPS 거래액이 전년 대비 크게 늘었다.",
             "한·중 송금(TenPay/WeChat) 구조에서 위안화 직거래 옵션 검토 여지."),
        ],
        "국내기업 해외사업": [
            ("삼성전자, 동남아 전자지갑 제휴 확대…핀테크 협력 가속",
             "삼성월렛이 동남아 현지 결제망과 제휴를 넓히고 있다.",
             "삼성월렛-우리은행 베트남/필리핀 제휴 모델과 직접 연계 가능성."),
        ],
        "글로벌 핀테크": [
            ("스테이블코인 규제 명확화…아시아 결제 인프라 경쟁 점화",
             "주요국이 스테이블코인 결제 활용을 위한 규제 프레임을 정비 중이다.",
             "다낭 IFC D-VND 샌드박스 구상의 규제 환경 근거로 활용 가능."),
            ("임베디드 금융·BaaS, 비금융 플랫폼으로 빠르게 확산",
             "유통·여행 플랫폼이 BaaS로 금융기능을 내재화하는 사례가 늘고 있다.",
             "의료관광·POP MART 등 우리은행 임베디드 금융 모델 정합성 확인."),
        ],
    }
    grouped = {}
    for cat, rows in samples.items():
        grouped[cat] = [{
            "title": t, "summary": s, "implication": impl,
            "link": "https://example.com", "source": "데모뉴스",
            "pub": f"{9+i:02d}:30", "desc": s, "category": cat,
        } for i, (t, s, impl) in enumerate(rows)]
    return grouped


# ---------------------------------------------------------------------------
# 6) 로컬 .env 로더 (노트북 실행용 — 추가 패키지 불필요)
# ---------------------------------------------------------------------------
def load_dotenv(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ---------------------------------------------------------------------------
# 7) 카카오톡 '나에게 보내기' 연동
# ---------------------------------------------------------------------------
def _kakao_refresh_access_token(rest_key, refresh_token):
    """저장된 refresh_token으로 access_token 갱신.
    (access_token 유효 약 6시간, refresh_token 약 2개월)"""
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": rest_key,
        "refresh_token": refresh_token,
    }).encode("utf-8")
    req = urllib.request.Request("https://kauth.kakao.com/oauth/token", data=data)
    req.add_header("Content-Type", "application/x-www-form-urlencoded;charset=utf-8")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def build_kakao_digest(date_label, grouped):
    """카카오 텍스트 템플릿용 요약(200자 이내)."""
    icons = {"국내은행 글로벌·디지털": "🏦", "국제정세·금융": "🌐",
             "국내기업 해외사업": "📦", "글로벌 핀테크": "💳"}
    total = sum(len(v) for v in grouped.values())
    short = date_label.split(" (")[0].replace("년 ", ".").replace("월 ", ".").replace("일", "")
    parts = [f"{icons.get(c,'•')}{len(v)}" for c, v in grouped.items()]
    # 대표 헤드라인 1건
    head = ""
    for v in grouped.values():
        if v:
            head = "\n▶ " + v[0]["title"][:40]
            break
    return f"📊 {short} 글로벌 디지털 브리핑 (총 {total}건)\n" + " ".join(parts) + head


def send_kakao(text, link_url, rest_key, refresh_token):
    token = _kakao_refresh_access_token(rest_key, refresh_token)
    access = token.get("access_token")
    if not access:
        print(f"  [WARN] 카카오 토큰 갱신 실패: {token}", file=sys.stderr)
        return
    if token.get("refresh_token"):
        print("  [INFO] 새 refresh_token 발급됨 → .env의 KAKAO_REFRESH_TOKEN 갱신 권장:")
        print("         " + token["refresh_token"])

    template = {"object_type": "text", "text": text[:198]}
    if link_url:
        template["link"] = {"web_url": link_url, "mobile_web_url": link_url}
        template["button_title"] = "브리핑 열기"
    else:
        template["link"] = {}

    body = urllib.parse.urlencode({
        "template_object": json.dumps(template, ensure_ascii=False)
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send", data=body)
    req.add_header("Authorization", f"Bearer {access}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded;charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.loads(r.read().decode("utf-8"))
        if res.get("result_code") == 0:
            print("  카카오톡 발송 완료")
        else:
            print(f"  [WARN] 카카오 응답: {res}", file=sys.stderr)
    except urllib.error.HTTPError as e:
        print(f"  [WARN] 카카오 발송 실패 HTTP {e.code}: {e.read().decode()}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 8) main
# ---------------------------------------------------------------------------
def main():
    load_dotenv()  # 로컬 실행 시 .env 자동 로드 (Actions에서는 무시됨)
    demo = "--demo" in sys.argv
    now = datetime.datetime.now(KST)
    yesterday = (now - datetime.timedelta(days=1)).date()
    date_label = yesterday.strftime("%Y년 %m월 %d일 (%a)")
    generated_at = now.strftime("%Y-%m-%d %H:%M KST")

    if demo:
        grouped = demo_grouped()
    else:
        print(f"[{date_label}] 뉴스 수집 시작…")
        grouped = collect(yesterday)   # 키 없으면 자동으로 구글뉴스 RSS 사용
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        model = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        if api_key:
            print("Claude 요약/시사점 생성…")
            grouped = summarize_with_claude(grouped, api_key, model)
        else:
            print("[INFO] ANTHROPIC_API_KEY 없음 → 제목·링크 위주로 생성")
            grouped = fallback_summary(grouped)

    out = build_html(date_label, grouped, generated_at)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(out)
    print(f"index.html 생성 완료 (총 {sum(len(v) for v in grouped.values())}건)")

    # 카카오톡 '나에게 보내기' (KAKAO_REST_KEY + KAKAO_REFRESH_TOKEN 있을 때만)
    kakao_key = os.environ.get("KAKAO_REST_KEY")
    kakao_refresh = os.environ.get("KAKAO_REFRESH_TOKEN")
    if kakao_key and kakao_refresh and not demo:
        digest = build_kakao_digest(date_label, grouped)
        send_kakao(digest, os.environ.get("PAGES_URL", ""), kakao_key, kakao_refresh)


if __name__ == "__main__":
    main()
