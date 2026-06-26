"""
Device-specific parameter ordering for fixed instrument assignments.

Add device names to CUSTOM_DEVICE_PARAMETER_ORDER when you want physical Param
numbers to use a custom order instead of Live's raw parameter order.

Device keys can be display names, class names, or class display names. Trailing
numbers are ignored by the resolver. Use None or "SKIP" for an empty slot.
"""

# False: only assign entries listed below. Unspecified slots stay empty.
# True: append remaining Live parameters after the listed entries.
CUSTOM_PARAMETER_APPEND_REST = False

CUSTOM_DEVICE_PARAMETER_ORDER = {
    "Serum 2": (
        # Encoder upper
        "A Octave",
        "A Unison",
        "A Uni Detune",
        "B Octave",
        "B Unison",
        "B Uni Detune",
        None,
        None,
        # Encoder middle
        "A WT Pos",
        "A Warp",
        "A Level",
        "B WT Pos",
        "B Warp",
        "B Level",
        None,
        None,
        # Encoder lower
        "Filter 1 Freq",
        "Filter 1 Res",
        "Mod 1 Amount",
        "Filter 1 Drive",
        None,
        None,
        None,
        "Main Vol",
        # Fader
        "Env 2 Attack",
        "Env 2 Decay",
        "Env 2 Sustain",
        "Env 2 Release",
        "Env 1 Attack",
        "Env 1 Decay",
        "Env 1 Sustain",
        "Env 1 Release",
        # Button upper
        "Sub Enable",
        "A Enable",
        "B Enable",
        "C Enable",
        "Noise Enable",
        "Clip Player Enable",
        "Arp Enable",
        None,
    ),
    "Omnisphere": (
        # Encoder upper
        "1 A Transpose Semitones",
        None,
        "1 B Transpose Semitones",
        None,
        "1 C Transpose Semitones",
        None,
        "1 D Transpose Semitones",
        None,
        # Encoder middle
        "1 A Shape",
        "1 A Level",
        "1 B Shape",
        "1 B Level",
        "1 C Shape",
        "1 C Level",
        "1 D Shape",
        "1 D Level",
        # Encoder lower
        "1 Global Filt Cut",
        "1 Global Filt Res",
        "1 Global Filt Env",
        None,
        None,
        None,
        None,
        "Master Gain",
        # Fader
        "1 Global Flt Env Atk",
        "1 Global Flt Env Dcy",
        "1 Global Flt Env Sus",
        "1 Global Flt Env Rls",
        "1 Global Amp Env Atk",
        "1 Global Amp Env Dcy",
        "1 Global Amp Env Sus",
        "1 Global Amp Env Rls",
        # Button upper
        "1 A Layer On",
        "1 B Layer On",
        "1 C Layer On",
        "1 D Layer On",
        "1 Bypass All Effects",
        "1 Arp On",
        None,
        None,
    ),
    "Delay": (
        "Dry/Wet",
        "L 16th",
        "Feedback",
    ),
    "ADPTR MetricAB": (
        "Selected Track",
        "Selected Cue",
        "AB Switch",
    ),
}
"""
    "Some Device": (
        "Attack",
        {"Attack": {"occurrence": 2}},
        "Release",
        None,
        "SKIP",
    ),
"""
