# -*- coding: utf-8 -*-
# This file is part of Xpra.
# Copyright (C) 2017-2021 Antoine Martin <antoine@xpra.org>
# Xpra is released under the terms of the GNU GPL v2, or, at your option, any
# later version. See the file COPYING for details.

import struct

from xpra.server.rfb.rfb_const import RFBEncoding
from xpra.net.protocol import PACKET_JOIN_SIZE
from xpra.os_util import memoryview_to_bytes, hexstr
from xpra.log import Logger

log = Logger("rfb")

def make_header(encoding, x, y, w, h):
    fbupdate = struct.pack(b"!BBH", 0, 0, 1)
    rect = struct.pack(b"!HHHHi", x, y, w, h, encoding)
    return fbupdate+rect

def raw_encode(window, x, y, w, h):
    img = window.get_image(x, y, w, h)
    window.acknowledge_changes()
    if not img:
        return
    if img.get_rowstride()!=w*4:
        img.restride(w*4)
    pixels = img.get_pixels()
    assert len(pixels)>=4*w*h
    data = pixels[:4*w*h]
    header = make_header(RFBEncoding.RAW, x, y, w, h)
    if len(data)<=PACKET_JOIN_SIZE:
        return [header+memoryview_to_bytes(data),]
    return [header, data]

def tight_encode(window, x, y, w, h):
    img = window.get_image(x, y, w, h)
    window.acknowledge_changes()
    if not img:
        return
    #try jpeg:
    from xpra.codecs.pillow.encoder import encode
    data = encode("jpeg", img, 90, 100, False, False, None)[1].data
    header = make_header(RFBEncoding.TIGHT, x, y, w, h)+struct.pack(b"!B", 0x80+0x1F)
    #length header is weird:
    length = len(data)
    if length<128:
        header += struct.pack(b"!B", length)
    elif length<16383:
        header += struct.pack(b"!BB", 0x80+(length&0x7F), length>>7)
    else:
        assert length<4194303
        header += struct.pack(b"!BBB", 0x80+(length&0x7F), 0x80+((length>>7)&0x7F), length>>14)
    log("header=%s for %i bytes of JPEG", hexstr(header), len(data))
    if len(data)<=PACKET_JOIN_SIZE:
        return [header+memoryview_to_bytes(data),]
    return [header, data]
