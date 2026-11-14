# Evidence Audit: adjusted-vs-raw-variables

- **Source ID**: `argo-user-manual`
- **Section / Page**: `Pages 23–25, Section 2.2.5 "Measurements for each profile"`
- **Source Document Version**: `3.44.0`
- **Retrieved On**: `2026-11-14`

## Sentences and Evidence

### Sentence 1
- **Text**: "In Argo netCDF profile files, the <PARAM> variable contains the raw values transmitted by the float, which should never be altered."
- **Source File**: `knowledge/text/argo-user-manual.txt`
- **Location**: Page 23, Section 2.2.5
- **Supporting Phrase**: "<PARAM> contains the raw values transmitted by the float."
- **Numbers / Flag Values / Thresholds**: None

### Sentence 2
- **Text**: "The variable <PARAM>_QC records quality control flags that pertain to the raw values in <PARAM>."
- **Source File**: `knowledge/text/argo-user-manual.txt`
- **Location**: Page 23, Section 2.2.5
- **Supporting Phrase**: "<PARAM>_QC contains QC flags that pertain to the values in <PARAM>."
- **Numbers / Flag Values / Thresholds**: None

### Sentence 3
- **Text**: "The mandatory variable <PARAM>_ADJUSTED contains values derived from the original parameter after applying sensor adjustments."
- **Source File**: `knowledge/text/argo-user-manual.txt`
- **Location**: Page 24, Section 2.2.5
- **Supporting Phrase**: "<PARAM>_ADJUSTED contains the adjusted values derived from the original values"
- **Numbers / Flag Values / Thresholds**: None

### Sentence 4
- **Text**: "When no adjustment has been performed on a parameter, the FillValue is inserted into <PARAM>_ADJUSTED and <PARAM>_ADJUSTED_ERROR."
- **Source File**: `knowledge/text/argo-user-manual.txt`
- **Location**: Page 24, Section 2.2.5
- **Supporting Phrase**: "When no adjustment is performed, the FillValue is inserted."
- **Numbers / Flag Values / Thresholds**: None
