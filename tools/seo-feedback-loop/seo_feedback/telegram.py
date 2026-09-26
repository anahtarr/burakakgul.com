from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import Config


def send(config: Config, message: str) -> int:
    if not config.telegram_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    if not config.telegram_chat_ids:
        raise RuntimeError("TELEGRAM_CHAT_IDS is not set")
    sent = 0
    endpoint = f"https://api.telegram.org/bot{config.telegram_token}/sendMessage"
    for chat_id in config.telegram_chat_ids:
        payload = urlencode(
            {"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"}
        ).encode()
        request = Request(endpoint, data=payload, method="POST")
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram rejected the message for chat {chat_id}")
        sent += 1
    return sent
