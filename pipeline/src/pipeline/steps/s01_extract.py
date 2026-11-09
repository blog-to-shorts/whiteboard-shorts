"""STEP 01. 블로그 본문 추출 (Requests + BeautifulSoup)."""
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; whiteboard-shorts/0.1)"}
BODY_SELECTORS = (
    ".se-main-container",
    "#postViewArea",
    ".tt_article_useless_p_margin",
    ".post-body",
    "article",
    "main",
)


def _fetch(url: str) -> tuple[BeautifulSoup, str]:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return BeautifulSoup(response.content, "html.parser"), response.url


def run(url: str) -> str:
    """URL에서 제목과 본문을 추출해 하나의 텍스트로 반환한다."""
    soup, page_url = _fetch(url)
    frame = soup.select_one("iframe#mainFrame[src]")
    if frame:
        soup, _ = _fetch(urljoin(page_url, frame["src"]))

    body = None
    for selector in BODY_SELECTORS:
        body = soup.select_one(selector)
        if body is not None:
            break
    if body is None:
        raise ValueError("블로그 본문 영역을 찾지 못했습니다. --text-file로 원문을 입력하세요.")

    for element in body.select(
        "script, style, noscript, nav, aside, footer, form, iframe, "
        "#comments, .comments, .related-posts, .post-footer, .adsbygoogle"
    ):
        element.decompose()

    heading = body.find("h1")
    metadata = soup.select_one('meta[property="og:title"][content]')
    title = metadata["content"].strip() if metadata else ""
    if not title:
        title_element = heading or soup.title
        title = title_element.get_text(" ", strip=True) if title_element else ""
    if heading and heading.get_text(" ", strip=True) == title:
        heading.decompose()

    for element in body.select("p, h1, h2, h3, h4, li, blockquote, pre, div, br, tr"):
        element.append("\n")
    content = "\n".join(line.strip() for line in body.get_text().splitlines() if line.strip())
    if not content:
        raise ValueError("블로그 본문이 비어 있습니다. --text-file로 원문을 입력하세요.")
    return f"{title}\n\n{content}" if title else content
