from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


VOID_TAGS = {"br", "img", "meta", "link", "input", "hr", "source", "wbr"}


@dataclass(frozen=True)
class SourcePost:
    channel: str
    message_id: int
    text: str
    published_at: datetime
    url: str

    @property
    def post_key(self) -> str:
        return f"{self.channel}/{self.message_id}"


class TelegramPreviewParser(HTMLParser):
    def __init__(self, channel: str):
        super().__init__(convert_charrefs=True)
        self.channel = channel
        self.posts: list[SourcePost] = []
        self.missing_publication_time = False
        self._post_id: int | None = None
        self._post_url = ""
        self._published_at: datetime | None = None
        self._message_depth = 0
        self._text_depth = 0
        self._text_parts: list[str] = []

    @staticmethod
    def _classes(attrs: dict[str, str | None]) -> set[str]:
        return set((attrs.get("class") or "").split())

    def handle_starttag(self, tag: str, raw_attrs: list[tuple[str, str | None]]) -> None:
        attrs = dict(raw_attrs)
        classes = self._classes(attrs)
        data_post = attrs.get("data-post")
        if data_post and "tgme_widget_message" in classes:
            if self._post_id is not None:
                self._finish_post()
            try:
                channel, message_id = data_post.rsplit("/", 1)
                self._post_id = int(message_id)
                self._post_url = f"https://t.me/{channel}/{message_id}"
                self._published_at = None
                self._text_parts = []
                self._message_depth = 1
            except (TypeError, ValueError):
                self._post_id = None
                self._message_depth = 0
        elif self._post_id is not None and tag not in VOID_TAGS:
            self._message_depth += 1

        if self._post_id is not None and "tgme_widget_message_text" in classes:
            self._text_depth = 1
        elif self._text_depth and tag not in VOID_TAGS:
            self._text_depth += 1
        if self._text_depth and tag in {"br", "p", "div", "li"}:
            self._text_parts.append("\n")
        if self._post_id is not None and tag == "time" and attrs.get("datetime"):
            try:
                self._published_at = datetime.fromisoformat(
                    attrs["datetime"].replace("Z", "+00:00")
                )
            except ValueError:
                self._published_at = None

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._text_depth:
            self._text_depth -= 1
        if self._post_id is not None:
            self._message_depth -= 1
            if self._message_depth <= 0:
                self._finish_post()

    def handle_data(self, data: str) -> None:
        if self._text_depth:
            self._text_parts.append(data)

    def close(self) -> None:
        super().close()
        if self._post_id is not None:
            self._finish_post()

    def _finish_post(self) -> None:
        if self._post_id is None:
            return
        text = "\n".join(
            part.strip()
            for part in "".join(self._text_parts).splitlines()
            if part.strip()
        )
        if text and self._published_at is None:
            self.missing_publication_time = True
        if text and self._published_at is not None:
            self.posts.append(
                SourcePost(
                    channel=self.channel,
                    message_id=self._post_id,
                    text=html.unescape(text),
                    published_at=self._published_at,
                    url=self._post_url,
                )
            )
        self._post_id = None
        self._post_url = ""
        self._published_at = None
        self._message_depth = 0
        self._text_parts = []
        self._text_depth = 0


def content_hash(post: SourcePost) -> str:
    return hashlib.sha256(post.text.encode("utf-8")).hexdigest()[:16]


class PublicTelegramSource:
    def __init__(self, channel: str, timeout: int = 15):
        self.channel = channel.strip().lstrip("@")
        self.timeout = timeout

    def fetch(self) -> list[SourcePost]:
        request = Request(
            f"https://t.me/s/{self.channel}",
            headers={
                "User-Agent": "EnergyHub-Telegram-Family-Assistant/2.1",
                "Accept": "text/html,application/xhtml+xml",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raise RuntimeError(f"Telegram preview returned HTTP {exc.code}") from None
        except URLError as exc:
            raise RuntimeError(
                f"Telegram preview connection failed: {exc.reason}"
            ) from None

        parser = TelegramPreviewParser(self.channel)
        parser.feed(body)
        parser.close()
        if not parser.posts or parser.missing_publication_time:
            raise RuntimeError("Telegram preview contains no timestamped posts")
        return sorted(parser.posts, key=lambda post: post.message_id)
