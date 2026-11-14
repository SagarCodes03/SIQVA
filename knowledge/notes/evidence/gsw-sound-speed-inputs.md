# Evidence Audit: gsw-sound-speed-inputs

- **Source ID**: `gsw-sound-speed`
- **Section / Page**: `Section "USAGE" & Section "DESCRIPTION"`
- **Source Document Version**: `3.05`
- **Retrieved On**: `2026-11-14`

## Sentences and Evidence

### Sentence 1
- **Text**: "The Gibbs SeaWater function gsw_sound_speed requires three oceanographic inputs: Absolute Salinity (SA in g/kg), Conservative Temperature (CT in degrees Celsius on ITS-90), and sea pressure (p in dbar)."
- **Source File**: `knowledge/text/gsw-sound-speed.txt`
- **Location**: Section "USAGE"
- **Supporting Phrase**: "sound_speed = gsw_sound_speed(SA,CT,p)"
- **Numbers / Flag Values / Thresholds**: 90 (ITS-90)

### Sentence 2
- **Text**: "Sea pressure is gauge pressure relative to the surface, representing absolute pressure minus standard atmospheric pressure of 10.1325 dbar."
- **Source File**: `knowledge/text/gsw-sound-speed.txt`
- **Location**: Section "INPUT"
- **Supporting Phrase**: "absolute pressure - 10.1325 dbar"
- **Numbers / Flag Values / Thresholds**: 10.1325 (dbar)

### Sentence 3
- **Text**: "The function calculates speed of sound in seawater in meters per second using a computationally efficient 75-term polynomial expression for specific volume."
- **Source File**: `knowledge/text/gsw-sound-speed.txt`
- **Location**: Section "DESCRIPTION"
- **Supporting Phrase**: "Calculates the speed of sound in seawater"
- **Numbers / Flag Values / Thresholds**: 75 (term)

### Sentence 4
- **Text**: "This 75-term equation has been fitted in a restricted parameter range and is most accurate inside the oceanographic funnel described in McDougall et al. (2003)."
- **Source File**: `knowledge/text/gsw-sound-speed.txt`
- **Location**: Section "DESCRIPTION"
- **Supporting Phrase**: "is most accurate inside the "oceanographic funnel" described in McDougall et al. (2003)."
- **Numbers / Flag Values / Thresholds**: 75 (term), 2003 (year)
