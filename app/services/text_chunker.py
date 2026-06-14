"""
Text Chunker — Engine-aware text splitting for TTS.

OmniVoice / VieNeu models work best with short chunks (~200 chars).
Edge TTS / Google TTS can handle longer segments (~500 chars).
"""
import re


# ── Character limits per engine ────────────────────────────────────────
ENGINE_MAX_CHARS = {
    "omnivoice": 200,
    "vieneu":    200,
    "edge":      500,
    "google":    500,
}
DEFAULT_MAX_CHARS = 500


def get_engine_from_voice_id(voice_id: str) -> str:
    """Derive the engine name from a voice_id string."""
    if voice_id.startswith("vieneu"):
        return "vieneu"
    elif voice_id.startswith("omnivoice"):
        return "omnivoice"
    elif "|" in voice_id:
        return "google"
    else:
        return "edge"


def chunk_text(text: str, engine: str = "edge") -> list[str]:
    """
    Split text into TTS-appropriate chunks for the given engine.

    For OmniVoice/VieNeu: shorter chunks (~200 chars max), split on
    sentence → clause → word boundaries.

    For Edge/Google: longer chunks (~500 chars max), sentence-level.

    Returns a list of non-empty stripped strings.
    """
    max_chars = ENGINE_MAX_CHARS.get(engine, DEFAULT_MAX_CHARS)

    # 1. Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 2. Split into paragraphs on blank lines or single newlines
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    # 3. Split each paragraph into sentences
    raw_sentences = []
    for para in paragraphs:
        raw_sentences.extend(_split_into_sentences(para))

    # 4. Enforce max length — break long sentences on clause boundaries
    sized_chunks = []
    for sentence in raw_sentences:
        if len(sentence) <= max_chars:
            sized_chunks.append(sentence)
        else:
            sized_chunks.extend(_break_long_sentence(sentence, max_chars))

    # 5. Merge very short chunks (< 15 chars) with neighbours
    merged = _merge_short_chunks(sized_chunks, min_chars=15, max_chars=max_chars)

    return [c for c in merged if c.strip()]


# ── Sentence Splitting ─────────────────────────────────────────────────

# Abbreviations that should NOT trigger a sentence split.
# Covers English and Vietnamese common abbreviations.
_ABBREVS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "etc",
    "e.g", "i.e", "st", "ave", "dept", "inc", "ltd", "co",
    "fig", "vol", "no", "pp", "ed", "rev", "gen", "gov",
    # Vietnamese
    "tp", "pgs", "ts", "ths", "cn", "bs", "ks", "đc",
    "tr", "th", "tx", "tt",
}


def _split_into_sentences(text: str) -> list[str]:
    """
    Split a paragraph into sentences using regex.
    Handles:
      - Standard sentence-ending punctuation (. ? !)
      - Ellipsis (... or …) treated as sentence end
      - Abbreviations (Dr., TP., etc.) NOT treated as sentence ends
      - Quoted sentences
    """
    # Regex: split after sentence-ending punctuation followed by space + uppercase
    # or end-of-string.  But NOT after known abbreviations.
    #
    # Strategy: use a regex to find split points, then assemble sentences.
    #
    # Pattern matches: (sentence-ending punctuation)(optional quotes/parens)(space)
    # We split AFTER the punctuation+space.

    # First, handle ellipsis as a sentence boundary
    text = re.sub(r'\.{3,}', '…', text)

    # Python's re module doesn't support variable-length lookbehinds (the ? quantifier in lookbehind).
    # Instead, we split and capture the punctuation/quotes, then combine them back.
    # We split on \s+ but only if it's preceded by sentence-ending punctuation + optional quotes.
    # By capturing the punctuation/quotes, we can re-attach it to the sentence.
    
    parts = re.split(r'([.!?…][\"\'\)\]]?)\s+', text)
    
    # re.split with a capture group returns: [text1, punct1, text2, punct2, ...]
    # We need to combine textN + punctN
    combined_parts = []
    for i in range(0, len(parts) - 1, 2):
        combined_parts.append(parts[i] + parts[i+1])
    
    # If there's a leftover part without trailing punctuation (e.g., end of string)
    if len(parts) % 2 != 0 and parts[-1]:
        combined_parts.append(parts[-1])

    # Re-join parts that were split on abbreviations
    result = []
    buffer = ""
    for part in combined_parts:
        if buffer:
            candidate = buffer + " " + part
        else:
            candidate = part

        # Check if the part ends with an abbreviation followed by period
        if _ends_with_abbreviation(candidate):
            buffer = candidate
        else:
            result.append(candidate)
            buffer = ""

    if buffer:
        result.append(buffer)

    return [s.strip() for s in result if s.strip()]


def _ends_with_abbreviation(text: str) -> bool:
    """Check if text ends with a known abbreviation + period."""
    # Match trailing "Word." pattern
    m = re.search(r'(\w+)\.\s*$', text)
    if m:
        word = m.group(1).lower()
        if word in _ABBREVS:
            return True
        # Single uppercase letter followed by period (e.g., "A.", "B.")
        if len(word) == 1 and word.isalpha():
            return True
    return False


# ── Breaking Long Sentences ────────────────────────────────────────────

def _break_long_sentence(text: str, max_chars: int) -> list[str]:
    """
    Break a sentence that exceeds max_chars into smaller chunks.
    Priority: clause boundaries (;,:) → then word boundaries.
    """
    # Try splitting on clause-level punctuation first
    clause_parts = re.split(r'(?<=[;,:])\s+', text)

    if len(clause_parts) > 1:
        # Greedily merge clause parts up to max_chars
        chunks = []
        current = ""
        for part in clause_parts:
            candidate = (current + " " + part).strip() if current else part
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # If a single clause part is still too long, break on words
                if len(part) > max_chars:
                    chunks.extend(_break_on_words(part, max_chars))
                    current = ""
                else:
                    current = part
        if current:
            chunks.append(current)
        return chunks

    # No clause boundaries — break on word boundaries
    return _break_on_words(text, max_chars)


def _break_on_words(text: str, max_chars: int) -> list[str]:
    """Break text on word boundaries to fit within max_chars."""
    words = text.split()
    chunks = []
    current = ""

    for word in words:
        candidate = (current + " " + word).strip() if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = word

    if current:
        chunks.append(current)

    return chunks


# ── Merge Short Chunks ─────────────────────────────────────────────────

def _merge_short_chunks(
    chunks: list[str], min_chars: int = 15, max_chars: int = 500
) -> list[str]:
    """
    Merge chunks shorter than min_chars with the next chunk,
    as long as the merged result doesn't exceed max_chars.
    """
    if not chunks:
        return []

    merged = []
    buffer = ""

    for chunk in chunks:
        if buffer:
            candidate = buffer + " " + chunk
            if len(candidate) <= max_chars:
                buffer = candidate
            else:
                merged.append(buffer)
                buffer = chunk
        else:
            buffer = chunk

        # Flush if buffer is long enough
        if len(buffer) >= min_chars:
            merged.append(buffer)
            buffer = ""

    if buffer:
        # Try merging with the last item
        if merged and len(merged[-1] + " " + buffer) <= max_chars:
            merged[-1] = merged[-1] + " " + buffer
        else:
            merged.append(buffer)

    return merged
