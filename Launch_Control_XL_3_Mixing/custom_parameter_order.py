"""
Device-specific parameter ordering for fixed instrument assignments.

Add device names to CUSTOM_DEVICE_PARAMETER_ORDER when you want physical Param
numbers to use a custom order instead of Live's raw parameter order.

Device keys can be display names, class names, or class display names. Trailing
numbers are ignored by the resolver. Use None or "SKIP" for an empty slot.
Instrument entries can use invert_direction for encoders and invert_led for
buttons: {"Parameter": {"invert_direction": True}}.
Encoders can add discrete_count for a fixed number of evenly spaced
values, or discrete_values for explicit raw values in ascending order. Both
use the same two-input threshold as Saturn's style control.
Use {"Attack": {"occurrence": 2}} to select the second same-named parameter
in Live's parameter order (the Configure order for plug-ins).
"""

# False: only assign entries listed below. Unspecified slots stay empty.
# True: append remaining Live parameters after the listed entries.
CUSTOM_PARAMETER_APPEND_REST = False

# Observed with the Omnisphere GUI, not Live's differing semitone labels.
# Raw ascending order: +24, +12, 0, -12, -24 semitones. These are observed
# points inside each pitch range, not measured boundaries or midpoints.
# The user confirmed the encoder behavior on hardware with these values.
OMNISPHERE_TRANSPOSE_VALUES = (0.0, 0.2519685, 0.5054741, 0.7407507, 0.984252)

# Diva exposes Tune1/Tune2 in semitones, so use the desired pitches directly.
# Keep their normal direction: larger raw values raise the pitch.
DIVA_TUNE_VALUES = (-24.0, -12.0, 0.0, 12.0, 24.0)

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
        {"1 A Transpose Semitones": {
            "invert_direction": True, "discrete_values": OMNISPHERE_TRANSPOSE_VALUES
        }},
        "1 A Level",
        {"1 B Transpose Semitones": {
            "invert_direction": True, "discrete_values": OMNISPHERE_TRANSPOSE_VALUES
        }},
        "1 B Level",
        {"1 C Transpose Semitones": {
            "invert_direction": True, "discrete_values": OMNISPHERE_TRANSPOSE_VALUES
        }},
        "1 C Level",
        {"1 D Transpose Semitones": {
            "invert_direction": True, "discrete_values": OMNISPHERE_TRANSPOSE_VALUES
        }},
        "1 D Level",
        # Encoder middle
        "1 A Shape",
        "1 A Symmetry",
        "1 B Shape",
        "1 B Symmetry",
        "1 C Shape",
        "1 C Symmetry",
        "1 D Shape",
        "1 D Symmetry",
        # Encoder lower
        "1 Global Filt Cut",
        "1 Global Filt Res",
        "1 Global Filt Env",
        "1 Global Flt Env Vel",
        "1 Global Ambi Amount",
        "1 Polyphony",
        {"1 A Tune Octave": {"invert_direction": True, "discrete_count": 5}},
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
        {"1 Bypass All Effects": {"invert_led": True}},
        "1 Arp On",
        None,
        None,
    ),
    "Diva": (
        # Encoder upper
        {"Tune1": {"discrete_values": DIVA_TUNE_VALUES}},
        "Shape1",
        "Volume1",
        {"Tune2": {"discrete_values": DIVA_TUNE_VALUES}},
        "Shape2",
        "Volume2",
        "Feedback1",
        "NoiseVol",
        # Encoder middle
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        # Encoder lower
        "Frequency",
        "Resonance",
        "Freq Mod Depth",
        "KeyFollow",
        "Filter FM",
        "Mode",
        None,
        "Output",
        # Configure order: filter envelope first, amp envelope second.
        # occurrence follows Live's order, not Diva's internal ENV number.
        # Fader 1-4: Filter envelope
        {"Attack": {"occurrence": 1}},
        {"Decay": {"occurrence": 1}},
        {"Sustain": {"occurrence": 1}},
        {"Release": {"occurrence": 1}},
        # Fader 5-8: Amp envelope
        {"Attack": {"occurrence": 2}},
        {"Decay": {"occurrence": 2}},
        {"Sustain": {"occurrence": 2}},
        {"Release": {"occurrence": 2}},
        # Button upper
        "OnOff",
        "Active #FX1",
        "Active #FX2",
        None,
        None,
        None,
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
