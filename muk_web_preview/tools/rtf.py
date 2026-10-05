from __future__ import annotations

import codecs
import re
import struct

COMPRESSED = 0x75465A4C
UNCOMPRESSED = 0x414C454D

DICTIONARY_SIZE = 4096
PREBUILT_DICTIONARY = (
    b'{\\rtf1\\ansi\\mac\\deff0\\deftab720{\\fonttbl;}{\\f0\\fnil \\froman '
    b'\\fswiss \\fmodern \\fscript \\fdecor MS Sans SerifSymbolArialTimes New '
    b'RomanCourier{\\colortbl\\red0\\green0\\blue0\r\n\\par '
    b'\\pard\\plain\\f0\\fs20\\b\\i\\u\\tab\\tx'
)

TOKEN = re.compile(
    rb"\\'([0-9a-fA-F]{2})"
    rb'|\\([a-zA-Z]+)(-?\d+)? ?'
    rb'|\\(.)'
    rb'|([{}])'
    rb'|[\r\n]+'
    rb'|([^\\{}\r\n]+)',
    re.DOTALL,
)

CODEPAGE_CODECS = {
    65001: 'utf-8',
    20127: 'ascii',
    20866: 'koi8_r',
    21866: 'koi8_u',
    50220: 'iso2022_jp',
    50221: 'iso2022_jp',
    50222: 'iso2022_jp',
    51932: 'euc_jp',
    51949: 'euc_kr',
    52936: 'hz',
    54936: 'gb18030',
    **{28590 + part: f'iso8859_{part}' for part in range(1, 16)},
}

CHARSET_CODEPAGES = {
    0: 1252,
    77: 10000,
    128: 932,
    129: 949,
    130: 1361,
    134: 936,
    136: 950,
    161: 1253,
    162: 1254,
    163: 1258,
    177: 1255,
    178: 1256,
    186: 1257,
    204: 1251,
    222: 874,
    238: 1250,
    254: 437,
}

SKIPPED_DESTINATIONS = {
    b'colortbl',
    b'fonttbl',
    b'info',
    b'pict',
    b'stylesheet',
    b'listtable',
    b'listoverridetable',
    b'rsidtbl',
    b'generator',
    b'header',
    b'footer',
    b'object',
}

CONTROL_TEXT = {
    b'par': '\r\n',
    b'line': '\r\n',
    b'tab': '\t',
    b'lquote': chr(0x2018),
    b'rquote': chr(0x2019),
    b'ldblquote': chr(0x201C),
    b'rdblquote': chr(0x201D),
    b'bullet': chr(0x2022),
    b'endash': chr(0x2013),
    b'emdash': chr(0x2014),
}

SYMBOL_TEXT = {
    b'\\': '\\',
    b'{': '{',
    b'}': '}',
    b'~': '\xa0',
    b'_': chr(0x2011),
}


def decompress(data: bytes) -> bytes:
    """Decompress an Outlook compressed RTF stream (MS-OXRTFCP).

    :raise ValueError: when the stream is neither compressed nor raw RTF
    """
    if len(data) < 16:
        message = 'Compressed RTF header is truncated'
        raise ValueError(message)
    size, raw_size, kind, _crc = struct.unpack_from('<4I', data)
    if kind == UNCOMPRESSED:
        return data[16 : 16 + raw_size]
    if kind != COMPRESSED:
        message = 'Unknown compressed RTF type'
        raise ValueError(message)
    dictionary = bytearray(DICTIONARY_SIZE)
    dictionary[: len(PREBUILT_DICTIONARY)] = PREBUILT_DICTIONARY
    position = len(PREBUILT_DICTIONARY)
    output = bytearray()
    source = memoryview(data)[16 : size + 4]
    index = 0
    while index < len(source):
        control = source[index]
        index += 1
        for bit in range(8):
            if index >= len(source):
                break
            if not control & (1 << bit):
                byte = source[index]
                index += 1
                output.append(byte)
                dictionary[position] = byte
                position = (position + 1) % DICTIONARY_SIZE
                continue
            if index + 1 >= len(source):
                return bytes(output)
            token = (source[index] << 8) | source[index + 1]
            index += 2
            offset, length = token >> 4, (token & 0xF) + 2
            if offset == position:
                return bytes(output)
            for step in range(length):
                byte = dictionary[(offset + step) % DICTIONARY_SIZE]
                output.append(byte)
                dictionary[position] = byte
                position = (position + 1) % DICTIONARY_SIZE
    return bytes(output)


def codec_name(codepage: int | None) -> str:
    """Return the Python codec of a Windows codepage, defaulting to cp1252."""
    name = CODEPAGE_CODECS.get(codepage, f'cp{codepage}')
    try:
        return codecs.lookup(name).name
    except LookupError:
        return 'cp1252'


class _HtmlExtractor:
    """Walk the RTF tokens and collect the encapsulated HTML."""

    def __init__(self) -> None:
        """Start with an empty output and the RTF default state."""
        self.output = []
        self.pending = bytearray()
        self.pending_codec = 'cp1252'
        self.codec = 'cp1252'
        self.charsets = {}
        self.defining = None
        self.state = {
            'skip': False,
            'suppress': False,
            'fonttbl': False,
            'font': None,
            'uc': 1,
        }
        self.stack = []
        self.skip_chars = 0

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _font_codec(self) -> str:
        """Return the codec of the current font, falling back to the document's."""
        charset = self.charsets.get(self.state['font'])
        if charset in CHARSET_CODEPAGES:
            return codec_name(CHARSET_CODEPAGES[charset])
        return self.codec

    def _flush(self) -> None:
        """Decode the collected bytes with the codec they were written in."""
        if self.pending:
            self.output.append(
                self.pending.decode(self.pending_codec, errors='replace')
            )
            self.pending.clear()

    def _emit(self, text: str) -> None:
        """Append decoded text to the output."""
        self._flush()
        self.output.append(text)

    def _append_bytes(self, data: bytes) -> None:
        """Collect bytes for decoding with the current font's codec."""
        codec = self._font_codec()
        if codec != self.pending_codec:
            self._flush()
            self.pending_codec = codec
        self.pending.extend(data)

    def _consume_skipped(self, text: bytes | None) -> bytes | None:
        """Drop the fallback characters that follow a unicode control word.

        :return: the text left to process, or ``None`` when nothing is left
        """
        if text:
            remainder = text[self.skip_chars :]
            self.skip_chars = max(self.skip_chars - len(text), 0)
            return remainder or None
        self.skip_chars -= 1
        return None

    def _control_word(
        self, word: bytes, number: int | None, starts_group: bool
    ) -> None:
        """Apply a control word to the state or the output."""
        state = self.state
        if starts_group and word in (b'htmltag', b'mhtmltag'):
            state['skip'] = word == b'mhtmltag'
        elif starts_group and word == b'fonttbl':
            state['fonttbl'] = state['skip'] = True
        elif starts_group and word in SKIPPED_DESTINATIONS:
            state['skip'] = True
        elif word == b'f' and number is not None:
            if state['fonttbl']:
                self.defining = number
            else:
                state['font'] = number
        elif word == b'fcharset' and state['fonttbl']:
            self.charsets[self.defining] = number
        elif word == b'ansicpg' and number:
            self.codec = codec_name(number)
        elif word == b'htmlrtf':
            state['suppress'] = number != 0
        elif word == b'uc' and number is not None:
            state['uc'] = number
        elif state['skip'] or state['suppress']:
            return
        elif word == b'u' and number is not None:
            self._emit(chr(number % 0x10000))
            self.skip_chars = state['uc']
        elif word in CONTROL_TEXT:
            self._emit(CONTROL_TEXT[word])

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def feed(self, rtf: bytes) -> str:
        """Process the whole RTF document and return the HTML."""
        group_start = False
        for match in TOKEN.finditer(rtf):
            hex_byte, word, param, symbol, brace, text = match.groups()
            starts_group, group_start = group_start, False
            if brace:
                self._flush()
                if brace == b'{':
                    self.stack.append(dict(self.state))
                    group_start = True
                elif self.stack:
                    self.state = self.stack.pop()
                continue
            if self.skip_chars and (hex_byte or text):
                text = self._consume_skipped(text)
                if not text:
                    continue
                hex_byte = None
            if symbol == b'*' and starts_group:
                self.state['skip'] = group_start = True
            elif word is not None:
                self._control_word(word, int(param) if param else None, starts_group)
            elif self.state['skip'] or self.state['suppress']:
                continue
            elif hex_byte:
                self._append_bytes(bytes([int(hex_byte, 16)]))
            elif symbol in SYMBOL_TEXT:
                self._emit(SYMBOL_TEXT[symbol])
            elif text:
                self._append_bytes(text)
        self._flush()
        units = ''.join(self.output).encode('utf-16-le', 'surrogatepass')
        return units.decode('utf-16-le', errors='replace')


def extract_html(rtf: bytes) -> str | None:
    """Return the HTML encapsulated in an RTF body (MS-OXRTFEX).

    :return: the HTML, or ``None`` when the RTF does not wrap HTML
    """
    if b'\\fromhtml' not in rtf[:1024]:
        return None
    return _HtmlExtractor().feed(rtf)
