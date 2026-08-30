#!/usr/bin/env python3
"""T-014 acceptance criterion: symmetry/rotation invariants verified by unit test.

Bit layout is defined in generate_lut.py's module docstring — 8 compass
neighbors, clockwise from N, 45 degrees apart, LSB = N.

Rotating the 3x3 neighborhood 90 degrees clockwise moves every neighbor two
positions further clockwise in that list (each step is 45 degrees), so it
must correspond to a left bit-rotation of the index by 2. The resulting
edge_dir must be the same rotation applied to the original edge_dir.

Mirroring horizontally (flip E/W) fixes N and S (bits 0 and 4) and swaps each
other pair symmetric about the vertical axis: NE<->NW, E<->W, SE<->SW. That
must correspond to bit i -> bit (8-i) mod 8, and edge_dir.x must negate while
edge_dir.y is unchanged.

Run: python3 tools/lut/lut_test.py
"""
import math
import sys
import unittest

from generate_lut import build_table, encode_channel, encode_confidence, edge_geometry, popcount


def rotate_bits_90cw(index: int) -> int:
    # Left-rotate by 2 within 8 bits: bit i moves to bit (i+2) mod 8.
    return ((index << 2) | (index >> 6)) & 0xFF


def mirror_bits_horizontal(index: int) -> int:
    out = 0
    for bit in range(8):
        if index & (1 << bit):
            out |= 1 << ((8 - bit) % 8)
    return out


def rotate_vec_90cw(x: float, y: float):
    # Screen space (+x right, +y down): rotating 90 deg clockwise on screen
    # maps (x,y) -> (-y, x).
    return -y, x


TOL = 1e-6


class TestTopologyLUT(unittest.TestCase):
    def test_all_256_entries_present(self):
        table = build_table()
        self.assertEqual(len(table), 256)
        for r, g, b, a in table:
            for ch in (r, g, b, a):
                self.assertTrue(0 <= ch <= 255)

    def test_rotation_invariant(self):
        for index in range(256):
            dx0, dy0, conf0 = edge_geometry(index)
            rotated_index = rotate_bits_90cw(index)
            dx1, dy1, conf1 = edge_geometry(rotated_index)

            exp_dx, exp_dy = rotate_vec_90cw(dx0, dy0)
            self.assertAlmostEqual(dx1, exp_dx, delta=TOL, msg=f"index={index:#010b}")
            self.assertAlmostEqual(dy1, exp_dy, delta=TOL, msg=f"index={index:#010b}")
            # Rotation must not change how many neighbors differ.
            self.assertAlmostEqual(conf1, conf0, delta=TOL, msg=f"index={index:#010b}")

    def test_mirror_invariant(self):
        for index in range(256):
            dx0, dy0, conf0 = edge_geometry(index)
            mirrored_index = mirror_bits_horizontal(index)
            dx1, dy1, conf1 = edge_geometry(mirrored_index)

            self.assertAlmostEqual(dx1, -dx0, delta=TOL, msg=f"index={index:#010b}")
            self.assertAlmostEqual(dy1, dy0, delta=TOL, msg=f"index={index:#010b}")
            self.assertAlmostEqual(conf1, conf0, delta=TOL, msg=f"index={index:#010b}")

    def test_four_rotations_return_to_start(self):
        for index in range(256):
            r = index
            for _ in range(4):
                r = rotate_bits_90cw(r)
            self.assertEqual(r, index)

    def test_degenerate_cases_have_zero_direction(self):
        # index 0 (no neighbor differs) and 255 (all differ) must report the
        # zero vector -- there is no usable edge direction in either case.
        for index in (0, 255):
            dx, dy, conf = edge_geometry(index)
            self.assertAlmostEqual(dx, 0.0, delta=TOL)
            self.assertAlmostEqual(dy, 0.0, delta=TOL)

    def test_confidence_matches_popcount(self):
        for index in range(256):
            _, _, conf = edge_geometry(index)
            self.assertAlmostEqual(conf, popcount(index) / 8.0, delta=TOL)

    def test_encode_channel_roundtrips_endpoints(self):
        self.assertEqual(encode_channel(-1.0), 0)
        self.assertEqual(encode_channel(1.0), 255)
        self.assertEqual(encode_confidence(0.0), 0)
        self.assertEqual(encode_confidence(1.0), 255)


if __name__ == "__main__":
    sys.path.insert(0, ".")
    unittest.main()
