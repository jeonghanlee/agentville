"""Opaque pixels of Chromium screenshots without image libraries, for figure overlap checks."""

import struct
import zlib


def alpha_mask(data, threshold=128):
    """Opaque pixels (x, y) of an 8-bit RGBA, non-interlaced PNG, as produced by Chromium screenshots."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks, width = 8, [], 0
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
            assert depth == 8 and color == 6 and not interlace, (depth, color, interlace)
        elif kind == b"IDAT":
            chunks.append(body)
        pos += 12 + length
    raw, stride, previous, opaque = zlib.decompress(b"".join(chunks)), width * 4, bytearray(width * 4), set()
    for y in range(height):
        start = y * (stride + 1)
        mode, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            left = line[i - 4] if i >= 4 else 0
            up, corner = previous[i], previous[i - 4] if i >= 4 else 0
            if mode == 1:
                line[i] = (line[i] + left) & 255
            elif mode == 2:
                line[i] = (line[i] + up) & 255
            elif mode == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif mode == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                line[i] = (line[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)) & 255
        opaque.update((x, y) for x in range(width) if line[x * 4 + 3] >= threshold)
        previous = line
    return opaque
