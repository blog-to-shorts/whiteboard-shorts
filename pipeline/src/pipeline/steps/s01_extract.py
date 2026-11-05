"""STEP 01. 블로그 본문 추출 (Requests + BeautifulSoup)."""
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; whiteboard-shorts/0.1)"}


def run(url: str) -> str:
    """URL에서 제목과 본문을 추출해 하나의 텍스트로 반환한다."""
    html = requests.get(url, headers=HEADERS, timeout=15).text
    soup = BeautifulSoup(html, "html.parser")

    # TODO: 네이버 블로그는 iframe#mainFrame의 src를 다시 요청
    # TODO: 플랫폼별 본문 셀렉터 (네이버 .se-main-container, 티스토리 .tt_article_useless_p_margin 등)
    raise NotImplementedError
