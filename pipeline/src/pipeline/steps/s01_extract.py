"""STEP 01. 블로그 본문 추출 (Requests + BeautifulSoup).

- 네이버 블로그: iframe 안의 실제 글(PostView)로 다시 요청
- 티스토리·브런치·일반 블로그: 알려진 본문 선택자 → <article>/<main> → 가장 긴 텍스트 블록 순으로 시도
- URL 대신 원문 텍스트를 직접 넣을 수도 있음 (추출 실패 대비)
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from ..utils.logger import log

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
TIMEOUT = 15
MIN_CHARS = 200  # 이보다 짧으면 추출 실패로 판단

# 플랫폼별 본문 선택자 (위에서부터 먼저 시도)
CONTENT_SELECTORS = [
    "div.se-main-container",        # 네이버 스마트에디터 ONE
    "div#postViewArea",             # 네이버 구버전 에디터
    "div.tt_article_useless_p_margin",  # 티스토리
    "div.entry-content",            # 티스토리·워드프레스
    "div.article_view",             # 티스토리 일부 스킨
    "div.wrap_body",                # 브런치
    "article",
    "main",
]
NOISE_TAGS = ["script", "style", "noscript", "iframe", "header", "footer",
              "nav", "aside", "form", "button", "figure"]


class ExtractError(RuntimeError):
    pass


@dataclass
class Extracted:
    title: str
    text: str
    url: Optional[str] = None


def _fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    return BeautifulSoup(resp.text, "html.parser")


def _naver_latest_log_no(blog_id: str) -> Optional[str]:
    """블로그 홈 주소만 받았을 때: RSS에서 가장 최근 글 번호를 찾는다."""
    try:
        resp = requests.get(f"https://rss.blog.naver.com/{blog_id}.xml", headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    for link in re.findall(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", resp.text):
        m = re.search(rf"blog\.naver\.com/{re.escape(blog_id)}/(\d+)", link)
        if m:
            return m.group(1)
    return None


def _naver_postview_url(url: str) -> Optional[str]:
    """blog.naver.com/{id}/{logNo} 또는 ?blogId=&logNo= 형식을 PostView 주소로 변환.
    블로그 홈(blog.naver.com/{id})만 주면 가장 최근 글로 바꾼다."""
    u = urlparse(url)
    if "blog.naver.com" not in u.netloc:
        return None
    qs = parse_qs(u.query)
    parts = [p for p in u.path.split("/") if p]
    if "blogId" in qs and "logNo" in qs:
        blog_id, log_no = qs["blogId"][0], qs["logNo"][0]
    elif len(parts) >= 2 and parts[1].isdigit():
        blog_id, log_no = parts[0], parts[1]
    else:
        blog_id = qs["blogId"][0] if "blogId" in qs else (parts[0] if len(parts) == 1 else None)
        if not blog_id or blog_id.endswith(".naver"):
            return None
        log_no = _naver_latest_log_no(blog_id)
        if not log_no:
            return None
        log.info(f"[s01] 블로그 홈 주소라서 최근 글({blog_id}/{log_no})로 만듭니다")
    return f"https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"


def _clean(text: str) -> str:
    text = text.replace("​", "").replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def _title(soup: BeautifulSoup) -> str:
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    return soup.title.get_text(strip=True) if soup.title else "제목 없음"


def _content_text(soup: BeautifulSoup) -> str:
    for tag in soup(NOISE_TAGS):
        tag.decompose()

    for sel in CONTENT_SELECTORS:
        node = soup.select_one(sel)
        if node:
            text = _clean(node.get_text("\n"))
            if len(text) >= MIN_CHARS:
                return text

    # 최후 수단: 문단(<p>)이 가장 많이 모인 부모 블록
    best, best_len = None, 0
    for parent in {p.parent for p in soup.find_all("p") if p.parent}:
        length = sum(len(p.get_text(strip=True)) for p in parent.find_all("p", recursive=False))
        if length > best_len:
            best, best_len = parent, length
    return _clean(best.get_text("\n")) if best else ""


def extract_from_url(url: str) -> Extracted:
    target = _naver_postview_url(url) or url
    log.info(f"[s01] 본문 요청: {target}")
    try:
        soup = _fetch(target)
    except requests.RequestException as e:
        raise ExtractError(f"페이지 요청 실패: {e}") from e

    title = _title(soup)
    text = _content_text(soup)
    if len(text) < MIN_CHARS:
        raise ExtractError(
            f"본문이 너무 짧습니다({len(text)}자). 원문 텍스트를 직접 입력해 주세요."
        )
    return Extracted(title=title, text=text, url=url)


def run(job_dir: Path, url: Optional[str] = None, text: Optional[str] = None) -> Extracted:
    """URL 또는 원문 텍스트를 받아 job_dir/source.txt로 저장."""
    out = job_dir / "source.txt"
    if out.exists():
        log.info("[s01] source.txt 존재 → 건너뜀")
        first, _, body = out.read_text(encoding="utf-8").partition("\n\n")
        return Extracted(title=first.removeprefix("# "), text=body, url=url)

    if text:
        result = Extracted(title="직접 입력", text=_clean(text), url=None)
    elif url:
        result = extract_from_url(url)
    else:
        raise ValueError("url 또는 text 중 하나는 필요합니다")

    job_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# {result.title}\n\n{result.text}", encoding="utf-8")
    log.info(f"[s01] 추출 완료: '{result.title}' ({len(result.text)}자)")
    return result


if __name__ == "__main__":
    # 단독 테스트: python -m pipeline.steps.s01_extract <URL>
    import sys

    try:
        r = extract_from_url(sys.argv[1])
    except ExtractError as e:
        print(f"❌ 추출 실패: {e}")
        sys.exit(1)
    print(f"제목: {r.title}\n글자 수: {len(r.text)}\n" + "-" * 40)
    print(r.text[:800])