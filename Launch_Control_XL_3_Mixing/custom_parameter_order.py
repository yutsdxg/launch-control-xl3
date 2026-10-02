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
CUSTOM_DEVICE_PARAMETER_OVERRIDES adds conditional changes to this base order.
Each rule has a when selector and assignments keyed by physical control name.
normalized_value compares (value - min) / (max - min), not display units.
Later matching rules win. Assignment entries use the same format as above.
Encoder options can add on_left to set a companion parameter on a physical
left turn, before applying invert_direction to the primary parameter:
{"on_left": {"parameter": "Source", "occurrence": 1, "normalized_value": 0.0}}.
The companion uses an exact name match and is unchanged by right turns or Shift.
on_left also accepts a tuple/list of these actions. relative_targets accepts
additional continuous controls with parameter, occurrence and invert_direction;
each moves from its own current value. Display/LED follow the primary parameter.
"""

# False: only assign entries listed below. Unspecified slots stay empty.
# True: append remaining Live parameters after the listed entries.
CUSTOM_PARAMETER_APPEND_REST = False

# Observed with the Omnisphere GUI, not Live's differing semitone labels.
# Raw ascending order: +24, +12, 0, -12, -24 semitones. These are observed
# points inside each pitch range, not measured boundaries or midpoints.
# The user confirmed the encoder behavior on hardware with these values.
OMNISPHERE_TRANSPOSE_VALUES = (0.0, 0.2519685, 0.5054741, 0.7407507, 0.984252)

# Diva VST3 uses normalized values: -24, -12, 0, +12, +24 semitones.
# Verified with Diva 1.4.8's controller API; display units are not raw values.
# Keep their normal direction: larger raw values raise the pitch.
DIVA_TUNE_VALUES = (0.1, 0.3, 0.5, 0.7, 0.9)

# OSC Model: Triple VCO=0, Dual VCO=0.25, DCO=0.5, Dual VCO Eco=0.75, Digital=1.
DIVA_TRIPLE_VCO = 0.0
DIVA_DCO = 0.5
DIVA_DUAL_DCO = 0.25
DIVA_DUAL_VCO_ECO = 0.75
DIVA_DIGITAL = 1.0

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
        "Main Vol",
        None,
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
        {"1 A Tune Octave": {"invert_direction": True, "discrete_count": 5}},
        "Master Gain",
        None,
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
        # Encoder upper: assigned per oscillator model below.
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "Feedback",
        # Encoder middle: assigned per oscillator model below.
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
        {"Mode": {"discrete_count": 5}},
        {"DepthMod Dpt1": {
            "occurrence": 1,
            "invert_direction": True,
            "relative_targets": (
                {"parameter": "DepthMod Dpt1", "occurrence": 2, "invert_direction": True},
            ),
            # Diva 1.4.8 controller API: normalized 0.0 displays "none".
            "on_left": (
                {"parameter": "DepthMod Src1", "occurrence": 1, "normalized_value": 0.0},
                {"parameter": "DepthMod Src1", "occurrence": 2, "normalized_value": 0.0},
            ),
        }},
        "Output",
        None,
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

CUSTOM_DEVICE_PARAMETER_OVERRIDES = {
    "Diva": (
        {
            # Triple VCO: keep OSC Model exposed in Configure.
            "when": {
                "parameter": "Model",
                "occurrence": 1,
                "normalized_value": DIVA_TRIPLE_VCO,
            },
            "assignments": {
                "encoder_1": {"Tune1": {"discrete_values": DIVA_TUNE_VALUES}},
                "encoder_2": "Shape1",
                "encoder_3": "Volume1",
                "encoder_4": None,
                "encoder_5": {"Tune2": {"discrete_values": DIVA_TUNE_VALUES}},
                "encoder_6": "Shape2",
                "encoder_7": "Volume2",
                # "encoder_8": None,
                "encoder_9": {"Tune3": {"discrete_values": DIVA_TUNE_VALUES}},
                "encoder_10": "Shape3",
                "encoder_11": "Volume3",
                "encoder_12": None,
                "encoder_13": None,
                "encoder_14": None,
                "encoder_15": None,
                "encoder_16": "NoiseVol",
            },
        },
        {
            "when": {
                "parameter": "Model",
                "occurrence": 1,
                "normalized_value": DIVA_DUAL_DCO,
            },
            "assignments": {
                "encoder_1": {"Tune1": {"discrete_values": DIVA_TUNE_VALUES}},
                "encoder_2": "PulseWidth",
                "encoder_3": "FM",
                "encoder_4": None,
                "encoder_5": {"Tune2": {"discrete_values": DIVA_TUNE_VALUES}},
                "encoder_6": {"Sync2": {"discrete_count": 2}},
                "encoder_7": "OscMix",
                # "encoder_8": None,
                "encoder_9": {"Triangle1On": {"discrete_count": 2}},
                "encoder_10": {"Saw1On": {"discrete_count": 2}},
                "encoder_11": {"Pwm1On": {"discrete_count": 2}},
                "encoder_12": {"Noise1On": {"discrete_count": 2}},
                "encoder_13": {"Triangle2On": {"discrete_count": 2}},
                "encoder_14": {"Saw2On": {"discrete_count": 2}},
                "encoder_15": {"Pulse2On": {"discrete_count": 2}},
                "encoder_16": {"Sine2On": {"discrete_count": 2}},
            },
        },
        {
            "when": {
                "parameter": "Model",
                "occurrence": 1,
                "normalized_value": DIVA_DCO,
            },
            "assignments": {
                "encoder_1": {"Tune1": {"discrete_values": DIVA_TUNE_VALUES}},
                "encoder_2": {"SawShape": {"discrete_count": 6}},
                "encoder_3": {"PulseShape": {"discrete_count": 4}},
                "encoder_4": {"SuboscShape": {"discrete_count": 6}},
                "encoder_5": None,
                "encoder_6": None,
                "encoder_7": None,
                # "encoder_8": None,
                "encoder_9": "PulseWidth",
                "encoder_10": None,
                "encoder_11": "Volume3",
                "encoder_12": "NoiseVol",
                "encoder_13": None,
                "encoder_14": None,
                "encoder_15": None,
                # "encoder_16": None,
            },
        },
        {
            # Configure must expose OSC Model as the first Model, plus both EcoWaves.
            "when": {
                "parameter": "Model",
                "occurrence": 1,
                "normalized_value": DIVA_DUAL_VCO_ECO,
            },
            "assignments": {
                "encoder_1": {"Tune1": {"discrete_values": DIVA_TUNE_VALUES}},
                "encoder_2": {"EcoWave1": {"discrete_count": 4}},
                "encoder_3": "Volume1",
                "encoder_4": None,
                "encoder_5": {"Tune2": {"discrete_values": DIVA_TUNE_VALUES}},
                "encoder_6": {"EcoWave2": {"discrete_count": 4}},
                "encoder_7": "Volume2",
                # "encoder_8": None,
                "encoder_9": "PulseWidth",
                "encoder_10": None,
                "encoder_11": None,
                "encoder_12": None,
                "encoder_13": None,
                "encoder_14": None,
                "encoder_15": None,
                # "encoder_16": None,
            },
        },
        {
            # Configure must expose OSC Model as the first Model, plus both EcoWaves.
            "when": {
                "parameter": "Model",
                "occurrence": 1,
                "normalized_value": DIVA_DIGITAL,
            },
            "assignments": {
                "encoder_1": {"Tune1": {"discrete_values": DIVA_TUNE_VALUES}},
                "encoder_2": {"DigitalType1": {"discrete_count": 7}},
                "encoder_3": "FM",
                "encoder_4": None,
                "encoder_5": {"Tune2": {"discrete_values": DIVA_TUNE_VALUES}},
                "encoder_6": {"DigitalType2": {"discrete_count": 7}},
                "encoder_7": "OscMix",
                # "encoder_8": None,
                "encoder_9": "PulseWidth",
                "encoder_10": "DigitalShape2",
                "encoder_11": None,
                "encoder_12": None,
                "encoder_13": "DigitalShape3",
                "encoder_14": "DigitalShape4",
                "encoder_15": None,
                # "encoder_16": None,
            },
        },
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
