import http.client
import ipaddress
import re
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urlsplit


MAX_ARTICLE_BYTES = 2_000_000
MAX_ARTICLE_CHARS = 20_000
SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header"}


class ArticleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        elif tag in {"p", "br", "div", "article", "h1", "h2", "h3"} and not self.skip_depth:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif tag in {"p", "br", "div", "article", "h1", "h2", "h3"} and not self.skip_depth:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


class PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout)
        self.address = address

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def extract_article_text(raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 80, 443}
    ):
        raise ValueError("Use a public HTTP or HTTPS article URL on the standard web port.")

    host = parsed.hostname.rstrip(".")
    try:
        addresses = {
            result[4][0]
            for result in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        }
    except socket.gaierror as exc:
        raise ValueError("The article host could not be reached. Paste the article text instead.") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("This URL does not resolve to a public address. Paste the article text instead.")

    address = sorted(addresses)[0]
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    connection_type = PinnedHTTPSConnection if parsed.scheme == "https" else PinnedHTTPConnection
    connection = connection_type(host, port, address, timeout=8)
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    try:
        connection.request(
            "GET",
            path,
            headers={"Host": host, "User-Agent": "TruthLens/1.0 (public article text extraction)", "Accept": "text/html"},
        )
        response = connection.getresponse()
        if response.status in {301, 302, 303, 307, 308}:
            raise ValueError("This article redirects and was not fetched. Paste the article text instead.")
        if response.status != 200:
            raise ValueError("The article could not be accessed. Paste the article text instead.")
        if "text/html" not in response.getheader("Content-Type", "").lower():
            raise ValueError("The URL did not return an HTML article. Paste the article text instead.")
        body = response.read(MAX_ARTICLE_BYTES + 1)
        if len(body) > MAX_ARTICLE_BYTES:
            raise ValueError("The article is too large to retrieve. Paste a shorter excerpt instead.")
    except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
        raise ValueError("The article could not be fetched safely. Paste the article text instead.") from exc
    finally:
        connection.close()

    parser = ArticleTextParser()
    parser.feed(body.decode(response.headers.get_content_charset() or "utf-8", errors="replace"))
    text = " ".join(" ".join(parser.parts).split())[:MAX_ARTICLE_CHARS]
    if len(text) < 30:
        raise ValueError("Readable article text was not found. Paste the article text instead.")
    return text


def extract_claim_sentence(article_text: str) -> str:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", article_text)
        if len(sentence.strip()) >= 40
    ]
    return sentences[0] if sentences else article_text[:6000].strip()
