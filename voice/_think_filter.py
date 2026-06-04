"""Streaming filter that strips <think>…</think> blocks from token output."""


class ThinkFilter:
    """Removes inline <think>…</think> blocks from a token-by-token stream."""

    def __init__(self) -> None:
        self._buf = ""
        self._thinking = False

    def feed(self, token: str) -> str:
        self._buf += token
        out = ""
        while True:
            if self._thinking:
                i = self._buf.find("</think>")
                if i == -1:
                    keep = min(len(self._buf), 8)
                    self._buf = self._buf[-keep:]
                    break
                self._buf = self._buf[i + 8:]
                self._thinking = False
            else:
                i = self._buf.find("<think>")
                if i == -1:
                    safe = max(0, len(self._buf) - 6)
                    out += self._buf[:safe]
                    self._buf = self._buf[safe:]
                    break
                out += self._buf[:i]
                self._buf = self._buf[i + 7:]
                self._thinking = True
        return out

    def flush(self) -> str:
        if self._thinking:
            self._buf = ""
            return ""
        out, self._buf = self._buf, ""
        return out
