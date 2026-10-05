from __future__ import annotations

import struct

SIGNATURE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'

END_OF_CHAIN = 0xFFFFFFFE
NO_STREAM = 0xFFFFFFFF
MAX_SECTOR = 0xFFFFFFFA

HEADER_DIFAT_ENTRIES = 109
DIRECTORY_ENTRY_SIZE = 128

TYPE_STORAGE = 1
TYPE_STREAM = 2
TYPE_ROOT = 5


class CompoundFileError(ValueError):
    """Raised when the data is not a readable compound file."""


class CompoundFile:
    """Read the storages and streams of an OLE2 compound file (MS-CFB)."""

    def __init__(self, data: bytes) -> None:
        """Parse the header, the allocation tables and the directory."""
        if len(data) < 512 or not data.startswith(SIGNATURE):
            message = 'Not a compound file'
            raise CompoundFileError(message)
        self._data = data
        (
            sector_shift,
            mini_sector_shift,
        ) = struct.unpack_from('<HH', data, 0x1E)
        (
            fat_count,
            directory_start,
            _transaction,
            self._mini_cutoff,
            mini_fat_start,
            mini_fat_count,
            difat_start,
            difat_count,
        ) = struct.unpack_from('<8I', data, 0x2C)
        if sector_shift not in (9, 12) or mini_sector_shift != 6:
            message = 'Unsupported sector size'
            raise CompoundFileError(message)
        self._sector_size = 1 << sector_shift
        self._mini_sector_size = 1 << mini_sector_shift
        self._max_sectors = len(data) // self._sector_size + 1
        difat = self._read_difat(difat_start, difat_count)
        self._fat = self._read_table(difat[:fat_count])
        self._entries = self._read_directory(directory_start)
        root = self._entries[0]
        self._mini_stream = self._read_chain(root['start'], root['size'])
        mini_fat_sectors = self._chain(mini_fat_start) if mini_fat_count else []
        self._mini_fat = self._read_table(mini_fat_sectors)

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _sector(self, index: int) -> bytes:
        """Return the bytes of the sector with the given index."""
        offset = (index + 1) * self._sector_size
        sector = self._data[offset : offset + self._sector_size]
        if not sector:
            message = 'Sector outside of the file'
            raise CompoundFileError(message)
        return sector

    def _unpack_ids(self, raw: bytes) -> list[int]:
        """Unpack a run of little-endian sector ids."""
        return list(struct.unpack(f'<{len(raw) // 4}I', raw[: len(raw) // 4 * 4]))

    def _read_difat(self, start: int, count: int) -> list[int]:
        """Collect the FAT sector ids from the header and the DIFAT chain."""
        ids = self._unpack_ids(self._data[0x4C : 0x4C + HEADER_DIFAT_ENTRIES * 4])
        sector = start
        for _index in range(min(count, self._max_sectors)):
            entries = self._unpack_ids(self._sector(sector))
            ids.extend(entries[:-1])
            sector = entries[-1]
        return [sector_id for sector_id in ids if sector_id <= MAX_SECTOR]

    def _read_table(self, sectors: list[int]) -> list[int]:
        """Concatenate the sector ids stored in the given table sectors."""
        return self._unpack_ids(b''.join(self._sector(index) for index in sectors))

    def _chain(self, start: int, table: list[int] | None = None) -> list[int]:
        """Follow a sector chain through an allocation table."""
        table = self._fat if table is None else table
        chain = []
        sector = start
        while sector != END_OF_CHAIN:
            if sector >= len(table) or len(chain) > len(table):
                message = 'Broken sector chain'
                raise CompoundFileError(message)
            chain.append(sector)
            sector = table[sector]
        return chain

    def _read_chain(self, start: int, size: int) -> bytes:
        """Read a stream stored in regular sectors."""
        if start == END_OF_CHAIN or not size:
            return b''
        data = b''.join(self._sector(index) for index in self._chain(start))
        return data[:size]

    def _read_mini_chain(self, start: int, size: int) -> bytes:
        """Read a stream stored in the mini stream."""
        step = self._mini_sector_size
        data = b''.join(
            self._mini_stream[index * step : (index + 1) * step]
            for index in self._chain(start, self._mini_fat)
        )
        return data[:size]

    def _read_directory(self, start: int) -> list[dict]:
        """Parse every directory entry of the directory chain."""
        raw = b''.join(self._sector(index) for index in self._chain(start))
        entries = []
        for offset in range(0, len(raw), DIRECTORY_ENTRY_SIZE):
            chunk = raw[offset : offset + DIRECTORY_ENTRY_SIZE]
            name_size, kind = struct.unpack_from('<HB', chunk, 0x40)
            left, right, child = struct.unpack_from('<3I', chunk, 0x44)
            start_sector, size = struct.unpack_from('<II', chunk, 0x74)
            entries.append(
                {
                    'name': chunk[: max(name_size - 2, 0)].decode(
                        'utf-16-le', errors='replace'
                    ),
                    'type': kind,
                    'left': left,
                    'right': right,
                    'child': child,
                    'start': start_sector,
                    'size': size,
                }
            )
        if not entries or entries[0]['type'] != TYPE_ROOT:
            message = 'Missing root storage'
            raise CompoundFileError(message)
        return entries

    def _children(self, index: int) -> dict[str, int]:
        """Map the names of a storage's children to their entry index."""
        children = {}
        pending = [self._entries[index]['child']]
        while pending:
            current = pending.pop()
            if current == NO_STREAM or current >= len(self._entries):
                continue
            entry = self._entries[current]
            if entry['name'] in children:
                continue
            children[entry['name']] = current
            pending.extend((entry['left'], entry['right']))
        return children

    def _resolve(self, path: str) -> int | None:
        """Return the entry index of a slash separated path."""
        index = 0
        for name in filter(None, path.split('/')):
            index = self._children(index).get(name)
            if index is None:
                return None
        return index

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def listdir(self, path: str = '') -> list[str]:
        """Return the names of the entries inside a storage."""
        index = self._resolve(path)
        if index is None or self._entries[index]['type'] == TYPE_STREAM:
            return []
        return sorted(self._children(index))

    def is_storage(self, path: str) -> bool:
        """Tell whether the path names a storage."""
        index = self._resolve(path)
        return index is not None and self._entries[index]['type'] == TYPE_STORAGE

    def read(self, path: str) -> bytes | None:
        """Return the content of a stream, or ``None`` when it is missing."""
        index = self._resolve(path)
        if index is None or self._entries[index]['type'] != TYPE_STREAM:
            return None
        entry = self._entries[index]
        if entry['size'] < self._mini_cutoff:
            return self._read_mini_chain(entry['start'], entry['size'])
        return self._read_chain(entry['start'], entry['size'])
