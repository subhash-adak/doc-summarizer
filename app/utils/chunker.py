from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Approximate characters per token
CHARS_PER_TOKEN = 4

# Gemini 2.5 Flash context window 
GEMINI_SAFE_TOKEN_LIMIT = 900_000


def estimate_tokens(text: str) -> int:
    """Rough token estimate based on character count."""
    return len(text) // CHARS_PER_TOKEN


def needs_chunking(text: str) -> bool:
    """
    Returns True if the text is too large for a single Gemini API call.
    For most documents this will be False.
    """
    return estimate_tokens(text) > GEMINI_SAFE_TOKEN_LIMIT


def split_text(text: str) -> list[str]:
    """
    Split text into overlapping chunks using LangChain's recursive splitter.
    Tries to split on paragraph boundaries before falling back to sentence/word.

    Returns a list of chunk strings. If the text fits in one call, returns [text].
    """
    settings = get_settings()

    if not needs_chunking(text):
        logger.debug("chunking_not_needed", estimated_tokens=estimate_tokens(text))
        return [text]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.max_chunk_size * CHARS_PER_TOKEN,
        chunk_overlap=settings.chunk_overlap * CHARS_PER_TOKEN,
        separators=["\n\n\n", "\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )

    chunks = splitter.split_text(text)
    logger.info(
        "text_chunked",
        total_chars=len(text),
        chunk_count=len(chunks),
        avg_chunk_chars=len(text) // len(chunks) if chunks else 0,
    )
    return chunks
