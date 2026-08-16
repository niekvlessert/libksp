if(NOT DEFINED TINYKSP_LIBVGM_SOURCE_DIR)
    message(FATAL_ERROR "TINYKSP_LIBVGM_SOURCE_DIR is required")
endif()

set(_ymf278b_c "${TINYKSP_LIBVGM_SOURCE_DIR}/emu/cores/ymf278b.c")
set(_ymf278b_h "${TINYKSP_LIBVGM_SOURCE_DIR}/emu/cores/ymf278b.h")
file(READ "${_ymf278b_c}" _c)
file(READ "${_ymf278b_h}" _h)

string(FIND "${_c}" "ymf278b_set_ds_reference_mode" _already_patched)
if(NOT _already_patched EQUAL -1)
    return()
endif()

string(REPLACE
    "\tUINT8 last_fm_data;\n\tOPL3FM fm;"
    "\tUINT8 last_fm_data;\n\t/* Keep normal YMF278B behavior by default. MWK 0E/0F can request\n\t * DS-style zero-order sample hold and unattenuated PCM output. */\n\tUINT8 ds_reference_mode;\n\tOPL3FM fm;"
    _c "${_c}")

string(REPLACE
    "\t\t\tsample = (ymf278b_getSample(chip, sl, sl->pos) * (0x10000 - sl->stepptr) +\n\t\t\t          ymf278b_getSample(chip, sl, ymf278b_nextPos(sl, sl->pos, 1)) * sl->stepptr) >> 16;"
    "\t\t\tif (chip->ds_reference_mode)\n\t\t\t{\n\t\t\t\t/* Nitro/DS playback uses sample hold rather than the YMF278B's\n\t\t\t\t * linear interpolation. Restrict this to explicit MWK 0E/0F data. */\n\t\t\t\tsample = ymf278b_getSample(chip, sl, sl->pos);\n\t\t\t}\n\t\t\telse\n\t\t\t{\n\t\t\t\tsample = (ymf278b_getSample(chip, sl, sl->pos) * (0x10000 - sl->stepptr) +\n\t\t\t\t          ymf278b_getSample(chip, sl, ymf278b_nextPos(sl, sl->pos, 1)) * sl->stepptr) >> 16;\n\t\t\t}"
    _c "${_c}")

string(REPLACE
    "\t\t\tsmplOut = (smplOut * 0x5A82) >> 17;\t// reduce volume by -15 db, should bring it into balance with FM"
    "\t\t\t/* libvgm reduces PCM by about 15 dB to balance it with OPL3 FM.\n\t\t\t * Nitro-derived packs are PCM references, so retain their native level. */\n\t\t\tif (! chip->ds_reference_mode)\n\t\t\t\tsmplOut = (smplOut * 0x5A82) >> 17;"
    _c "${_c}")

string(REPLACE
    "\treturn retVal;\n}\n\nstatic void ymf278b_alloc_rom(void* info, UINT32 memsize)"
    "\treturn retVal;\n}\n\nvoid ymf278b_set_ds_reference_mode(void* info, UINT8 enabled)\n{\n\tYMF278BChip* chip = (YMF278BChip*)info;\n\tif (chip != NULL)\n\t\tchip->ds_reference_mode = enabled ? 1 : 0;\n}\n\nstatic void ymf278b_alloc_rom(void* info, UINT32 memsize)"
    _c "${_c}")

string(REPLACE
    "extern const DEV_DECL sndDev_YMF278B;\n\n"
    "extern const DEV_DECL sndDev_YMF278B;\n\n/* TinyKSP extension: DS/Nitro reference rendering for MWK 0E/0F. */\nvoid ymf278b_set_ds_reference_mode(void* info, UINT8 enabled);\n\n"
    _h "${_h}")

file(WRITE "${_ymf278b_c}" "${_c}")
file(WRITE "${_ymf278b_h}" "${_h}")
