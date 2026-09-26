from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, urlopen


LANGUAGE_HINTS = {
    "tr": {"mühendis", "mühendisi", "solist", "korosu", "koro", "şarkı", "hakkımda", "savunma", "sanayi", "türk"},
    "en": {"engineer", "engineering", "soloist", "choir", "singer", "about", "defence", "music", "turkish"},
    "de": {"ingenieur", "elektronikingenieur", "solist", "chor", "sänger", "über", "musik", "türkische"},
}
STOPWORDS = {
    "burak", "akgul", "com", "www", "the", "and", "und", "der", "die", "das",
    "ile", "ve", "bir", "kimdir", "nedir",
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg"}:
            self.skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def normalize(value: str) -> str:
    value = value.casefold().replace("ı", "i")
    return "".join(
        char for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", normalize(value))
        if len(token) >= 3 and token not in STOPWORDS
    }


def infer_query_language(query: str) -> str | None:
    query_tokens = tokens(query)
    scores = {
        language: len(query_tokens & {normalize(word) for word in hints})
        for language, hints in LANGUAGE_HINTS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def page_language(url: str) -> str:
    path = urlparse(url).path.rstrip("/") + "/"
    if path.startswith("/en/"):
        return "en"
    if path.startswith("/de/"):
        return "de"
    return "tr"


def fetch_page_tokens(url: str) -> set[str]:
    request = Request(url, headers={"User-Agent": "burakakgul-seo-feedback/1.0"})
    with urlopen(request, timeout=10) as response:
        body = response.read(1_500_000).decode(
            response.headers.get_content_charset() or "utf-8", errors="replace"
        )
    parser = TextExtractor()
    parser.feed(body)
    return tokens(" ".join(parser.parts))


def has_topic_overlap(query: str, page_tokens: set[str]) -> bool:
    query_tokens = tokens(query)
    if not query_tokens:
        return True
    for query_token in query_tokens:
        for page_token in page_tokens:
            if query_token == page_token:
                return True
            if min(len(query_token), len(page_token)) >= 5 and (
                query_token.startswith(page_token[:5]) or page_token.startswith(query_token[:5])
            ):
                return True
    return False
