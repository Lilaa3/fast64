goddard_import_enum = [
    ("C", "C", "C"),
    ("Binary", "Binary", "Binary"),
    ("Insertable Binary", "Insertable Binary", "Insertable Binary"),
]

goddard_import_addresses = [
    (hex(0x2739a0 + 0x4f90), "Mario Master", "dynlist_mario_master"),
    ("", "Unused", ""),
    (hex(0x2739a0), "Test Cube", "dynlist_test_cube"),
    (hex(0x2739d0 + 0x0650), "Spot Shape", "dynlist_spot_shape"),
    ("", "Individual Mario Shapes", ""),
    (hex(0x2739d0 + 0x31f0), "Face Shape", "dynlist_mario_face_shape"),
    (hex(0x2739d0 + 0x39d8), "Eye Right Shape", "dynlist_mario_eye_right_shape"),
    (hex(0x2739d0 + 0x4040), "Eye Left Shape", "dynlist_mario_eye_left_shape"),
    (hex(0x2739d0 + 0x44b4), "Eyebrow Right Shape", "dynlist_mario_eyebrow_right_shape"),
    (hex(0x2739d0 + 0x4808), "Eyebrow Left Shape", "dynlist_mario_eyebrow_left_shape"),
    (hex(0x2739d0 + 0x4e10), "Mustache Shape", "dynlist_mario_mustache_shape"),
]
MARIO_HEAD_DYNLIST_NAME = "dynlist_mario_master.c"

DYNLIST_CMD_SIZE = 3 * 4 + (3 * 4)