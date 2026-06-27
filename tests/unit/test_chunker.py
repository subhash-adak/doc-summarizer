import pytest

from app.utils.chunker import estimate_tokens, needs_chunking, split_text

class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_short_text(self):
        assert estimate_tokens("Hello world") == 2  # 11 chars // 4

    def test_proportional_to_length(self):
        assert estimate_tokens("a" * 400) == 100


class TestNeedsChunking:
    def test_short_text_does_not_need_chunking(self):
        assert needs_chunking("Short document text.") is False

    def test_very_large_text_needs_chunking(self):
        # 900k tokens * 4 chars/token + 1 = exceeds limit
        huge_text = "a" * (900_000 * 4 + 1)
        assert needs_chunking(huge_text) is True


class TestSplitText:
    def test_short_text_returns_single_chunk(self):
        text = "This is a short document."
        chunks = split_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_large_text_is_split(self, monkeypatch):
        # Monkeypatch needs_chunking to force splitting
        monkeypatch.setattr("app.utils.chunker.needs_chunking", lambda _: True)
        text = " ".join(["word"] * 5000)
        chunks = split_text(text)
        assert len(chunks) > 1

    def test_chunks_cover_all_content(self, monkeypatch):
        monkeypatch.setattr("app.utils.chunker.needs_chunking", lambda _: True)
        words = [f"word{i}" for i in range(2000)]
        text = " ".join(words)
        chunks = split_text(text)
        combined = " ".join(chunks)
        # All original words should appear somewhere in the chunks
        for word in words[::100]:  # sample every 100th word
            assert word in combined
