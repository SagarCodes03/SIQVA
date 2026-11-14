# Evidence Audit: argo-measurement-accuracy

- **Source ID**: `argo-faq`
- **Section / Page**: `Section "*  How accurate is the Argo data?"`
- **Source Document Version**: ``
- **Retrieved On**: `2026-11-14`

## Sentences and Evidence

### Sentence 1
- **Text**: "In Argo profile data, temperature measurements have an accuracy of plus or minus 0.002 degrees Celsius, and pressure measurements are accurate to plus or minus 2.4 dbar."
- **Source File**: `knowledge/text/argo-faq.txt`
- **Location**: Section "*  How accurate is the Argo data?"
- **Supporting Phrase**: "The temperatures in the Argo profiles are accurate to ± 0.002°C"
- **Numbers / Flag Values / Thresholds**: 0.002 (°C), 2.4 (dbar)

### Sentence 2
- **Text**: "Real-time salinity measurements from newly deployed instruments are initially accurate to plus or minus 0.01 psu before sensor drift accumulates."
- **Source File**: `knowledge/text/argo-faq.txt`
- **Location**: Section "*  How accurate is the Argo data?"
- **Supporting Phrase**: "the uncorrected salinities are accurate to ± .01 psu."
- **Numbers / Flag Values / Thresholds**: 0.01 (psu)

### Sentence 3
- **Text**: "At a later stage, delayed-mode scientific adjustments by human experts correct for sensor drift and thermal lag errors using shipboard reference data."
- **Source File**: `knowledge/text/argo-faq.txt`
- **Location**: Section "*  How accurate is the Argo data?"
- **Supporting Phrase**: "salinities are corrected by expert examination, comparing older floats with newly deployed instruments"
- **Numbers / Flag Values / Thresholds**: None

### Sentence 4
- **Text**: "Estimated post-adjustment salinity uncertainties are recorded in the PSAL_ADJUSTED_ERROR fields, while measurements deemed bad and unadjustable are assigned QC flags 3 or 4."
- **Source File**: `knowledge/text/argo-faq.txt`
- **Location**: Section "*  How accurate is the Argo data?"
- **Supporting Phrase**: "delayed mode quality controlled salinity can be found in the PSAL_ADJUSTED_ERROR fields"
- **Numbers / Flag Values / Thresholds**: 3, 4 (QC flags)
