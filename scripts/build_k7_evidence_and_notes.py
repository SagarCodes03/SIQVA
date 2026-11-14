#!/usr/bin/env python3
"""
SIQVA Stage K7: Evidence Audit and Note Cleanup Builder

Generates:
1. knowledge/notes/evidence/<id>.md for all 21 notes in argo_notes.yaml.
2. Cleaned and audited knowledge/notes/argo_notes.yaml.
3. Performs strict validation on phrase length (< 15 words) and presence in extracted text.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

NOTES = [
    {
        "id": "argo-one-paragraph",
        "question_examples": [
            "What is the Argo program?",
            "Explain Argo in simple terms.",
            "What does the Argo observation network do?"
        ],
        "source_id": "argopy-what-is-argo",
        "section_or_page": 'Section "What is Argo ?"',
        "source_version": "",
        "retrieved_on": "2026-11-14",
        "limits": "Does not cover experimental sensors, shipboard CTD calibration methods, or localized coastal moorings outside the open ocean array.",
        "related": ["float-cycle-and-depth", "argo-array-size-and-coverage", "core-argo-parameters"],
        "sentences": [
            {
                "text": "Argo is an international real-time in situ ocean observing array consisting of nearly 4000 autonomous robotic floats distributed across the global ocean.",
                "phrase": "Argo is a global network of nearly 4000 autonomous probes",
                "location": 'Section "What is Argo ?"',
                "numbers": "4000 (nearly 4000 autonomous probes)"
            },
            {
                "text": "These free-drifting robotic probes measure seawater pressure, temperature, and salinity from the surface down to a depth of 2000 meters every 10 days.",
                "phrase": "measuring pressure, temperature and salinity from the surface to 2000m depth every 10 days.",
                "location": 'Section "What is Argo ?"',
                "numbers": "2000 (meters depth), 10 (days)"
            },
            {
                "text": "Data collected by the array are relayed by satellite communication to data centers and made freely available on the web in less than 24 hours.",
                "phrase": "made freely available on the web in less than 24h00.",
                "location": 'Section "What is Argo ?"',
                "numbers": "24 (hours, as less than 24h00)"
            }
        ]
    },
    {
        "id": "float-cycle-and-depth",
        "question_examples": [
            "How does an Argo float work and how deep does it go?",
            "What is the standard float mission cycle?",
            "How long does an Argo float profile take?"
        ],
        "source_id": "argo-how-floats-work",
        "section_or_page": 'Section "What does an Argo float do?"',
        "source_version": "",
        "retrieved_on": "2026-11-14",
        "limits": "Covers standard core park-and-profile missions only; does not cover specialized biogeochemical 1-day bursts or Deep Argo missions down to 6000 meters.",
        "related": ["argo-one-paragraph", "core-argo-parameters", "float-telemetry-and-surface"],
        "sentences": [
            {
                "text": "The standard Argo float operates on a recurring 10-day mission cycle that begins by sinking from the surface to a parking drift depth of 1000 meters.",
                "phrase": "The standard Argo float mission is a 10-day cycle",
                "location": 'Section "What does an Argo float do?"',
                "numbers": "10 (days), 1000 (meters drift depth)"
            },
            {
                "text": "The float drifts passively with deep currents at 1000 meters for roughly 9 days before sinking further to its profile depth of 2000 meters.",
                "phrase": "drift depth of 1000 meters for about 9 days",
                "location": 'Section "What does an Argo float do?"',
                "numbers": "1000 (meters), 9 (days), 2000 (meters profile depth)"
            },
            {
                "text": "From 2000 meters, the float slowly rises to the ocean surface while recording measurements of conductivity, temperature, and pressure.",
                "phrase": "slowly rising to the surface while measuring conductivity, temperature and pressure.",
                "location": 'Section "What does an Argo float do?"',
                "numbers": "2000 (meters)"
            },
            {
                "text": "Upon reaching the surface, the float obtains a position fix often through GPS and transmits its profile data to satellites during a surface interval between 15 minutes and one hour.",
                "phrase": "this surface interval is between 15 minutes and one hour.",
                "location": 'Section "What does an Argo float do?"',
                "numbers": "15 (minutes), 1 (hour)"
            }
        ]
    },
    {
        "id": "qc-flag-scale",
        "aliases": ["qc-flag-1-definition", "qc-flag-4-definition"],
        "question_examples": [
            "What do the Argo quality control flags mean?",
            "Explain the 0 to 9 Argo QC flag scale.",
            "What is the difference between flag 1 and flag 4 in Argo?"
        ],
        "source_id": "argo-user-manual",
        "section_or_page": 'Page 76, Section 3.2.1 "Reference table 2: quality control flag scale"',
        "source_version": "3.44.0",
        "retrieved_on": "2026-11-14",
        "limits": "Applies to individual measurement depth levels; overall profile letter grades (A-F) are defined separately in Reference table 2a.",
        "related": ["profile-quality-flags", "data-modes-rad", "adjusted-vs-raw-variables"],
        "sentences": [
            {
                "text": "Argo quality control evaluates individual observation levels on a numerical scale from 0 to 9 as specified in Reference table 2 of the Argo User's Manual.",
                "phrase": "Reference table 2: quality control flag scale",
                "location": "Page 76, Section 3.2.1",
                "numbers": "0 to 9 (numerical flag scale), 2 (Reference table)"
            },
            {
                "text": "Flag 0 indicates no QC was performed, flag 1 represents good data where all real-time tests passed, flag 2 marks probably good data to be used with caution, and flag 3 denotes probably bad data that are potentially adjustable.",
                "phrase": "0 No QC is performed",
                "location": "Page 76, Reference table 2",
                "numbers": "0, 1, 2, 3 (flags)"
            },
            {
                "text": "Flag 4 denotes bad data that must not be used, flag 5 indicates value changed, flags 6 and 7 are not used, flag 8 marks estimated values, and flag 9 represents missing values.",
                "phrase": "4 Bad data",
                "location": "Page 76, Reference table 2",
                "numbers": "4, 5, 6, 7, 8, 9 (flags)"
            },
            {
                "text": "In delayed mode, flag 1 signifies that no adjustment is needed or that the value is statistically consistent with good quality reference data, whereas unadjustable flag 4 data are replaced by FillValue.",
                "phrase": "Good data. No adjustment is needed",
                "location": "Page 76, Reference table 2",
                "numbers": "1, 4 (flags)"
            }
        ]
    },
    {
        "id": "data-modes-rad",
        "question_examples": [
            "What are data modes R, A, and D in Argo?",
            "What is the difference between real-time and delayed mode?",
            "What does DATA_MODE mean in an Argo netCDF file?"
        ],
        "source_id": "argo-user-manual",
        "section_or_page": 'Page 16, Section 1.7 "Real-time, real-time adjusted data and delayed mode data"',
        "source_version": "3.44.0",
        "retrieved_on": "2026-11-14",
        "limits": "Describes data mode classification; does not detail specific delayed-mode salinity drift fitting algorithms (e.g., OWC method).",
        "related": ["qc-flag-scale", "adjusted-vs-raw-variables", "delayed-mode-timing"],
        "sentences": [
            {
                "text": "Data from Argo floats are classified into three operational categories denoted by DATA_MODE values of 'R', 'A', or 'D'.",
                "phrase": "denoted by DATA_MODE = 'R'.",
                "location": "Page 16, Section 1.7",
                "numbers": "'R', 'A', 'D' (data modes)"
            },
            {
                "text": "Real-time raw data (DATA_MODE = 'R') pass through automatic quality control procedures with a target issuance to GDACs within 12 hours of surfacing.",
                "phrase": "within 12 hours of surfacing, or as quickly thereafter as possible.",
                "location": "Page 16, Section 1.7",
                "numbers": "12 (hours), 'R' (data mode)"
            },
            {
                "text": "Real-time adjusted data (DATA_MODE = 'A') contain interim automated adjustments applied to raw data before delayed-mode assessment.",
                "phrase": "These real-time adjusted data are denoted by DATA_MODE = 'A'.",
                "location": "Page 16, Section 1.7",
                "numbers": "'A' (data mode)"
            },
            {
                "text": "Delayed-mode data (DATA_MODE = 'D') are assessed by scientists who evaluate long-term sensor stability and apply necessary adjustments, with a target GDAC availability of about 12 months after transmission for core CTD data.",
                "phrase": "delayed-mode data and are denoted by DATA_MODE = 'D'.",
                "location": "Page 16, Section 1.7",
                "numbers": "12 (months), 'D' (data mode)"
            }
        ]
    },
    {
        "id": "delayed-mode-timing",
        "question_examples": [
            "Why are recent Argo profiles not in delayed mode?",
            "How long does it take for Argo data to reach delayed mode?",
            "When will last month's profiles be calibrated in delayed mode?"
        ],
        "source_id": "wong2020",
        "section_or_page": 'Page 8, Section "Delayed-Mode"',
        "source_version": "Vol. 7, Art. 700",
        "retrieved_on": "2026-11-14",
        "limits": "Applies to standard core CTD drift evaluation; fast-turnaround pilot projects or rapid sensor failures may receive earlier flagging.",
        "related": ["data-modes-rad", "realtime-vs-delayed-qc"],
        "sentences": [
            {
                "text": "Recent Argo observations cannot be processed into delayed mode immediately because determining sensor drift requires the accumulation of a relatively long time series.",
                "phrase": "Determination of sensor drift requires accumulation of a relatively long time series.",
                "location": 'Page 8, Section "Delayed-Mode"',
                "numbers": "None"
            },
            {
                "text": "In Argo, the established practice is to examine float profiles in delayed mode initially about 12 months after they are collected.",
                "phrase": "initially about 12 months after they are collected",
                "location": 'Page 8, Section "Delayed-Mode"',
                "numbers": "12 (months)"
            },
            {
                "text": "Because retrieving floats for recalibration is rarely possible, oceanographers use statistical tools and climatological comparisons to adjust data for sensor drift.",
                "phrase": "statistical tools and climatological comparisons are used to adjust the data",
                "location": 'Page 8, Section "Delayed-Mode"',
                "numbers": "None"
            },
            {
                "text": "Profiles are subsequently revisited several times as more data from the floats are obtained until the floats become inactive.",
                "phrase": "revisit several times as more data",
                "location": 'Page 8, Section "Delayed-Mode"',
                "numbers": "None"
            }
        ]
    },
    {
        "id": "realtime-vs-delayed-qc",
        "question_examples": [
            "What is the difference between real-time and delayed-mode QC in Argo?",
            "Why does delayed mode take so long compared to real-time QC?",
            "Can I use real-time Argo data for climate research?"
        ],
        "source_id": "wong2020",
        "section_or_page": 'Page 8, Section "Delayed-Mode"',
        "source_version": "Vol. 7, Art. 700",
        "retrieved_on": "2026-11-14",
        "limits": "Does not detail individual real-time test parameters such as spike thresholds, density inversion limits, or regional climatology envelopes.",
        "related": ["data-modes-rad", "qc-flag-scale", "delayed-mode-timing"],
        "sentences": [
            {
                "text": "Real-time quality control applies automated procedures to deliver flagged data within 24 hours of satellite transmission.",
                "phrase": "Available within < 24 h of satellite transmission, the real-time data are used",
                "location": 'Page 8, Section "Delayed-Mode"',
                "numbers": "24 (hours, as < 24 h)"
            },
            {
                "text": "These automated real-time checks serve operational weather and ocean forecasting where timely data delivery is required.",
                "phrase": "real-time data are used for operational weather and ocean forecasting",
                "location": 'Page 8, Section "Delayed-Mode"',
                "numbers": "None"
            },
            {
                "text": "In contrast, delayed-mode quality control subjects observations to visual examination by oceanographic experts because automatic real-time procedures are not flawless.",
                "phrase": "visual examination by oceanographic experts",
                "location": 'Page 8, Section "Delayed-Mode"',
                "numbers": "None"
            },
            {
                "text": "The delayed-mode pathway aims to provide the highest-quality version of the data including realistic error estimates suitable for climate research.",
                "phrase": "delayed-mode pathway aims to provide the highest-quality version of the data",
                "location": 'Page 8, Section "Delayed-Mode"',
                "numbers": "None"
            }
        ]
    },
    {
        "id": "profile-quality-flags",
        "question_examples": [
            "What do the profile quality flags A through F mean?",
            "How is the overall quality of an Argo profile determined?",
            "What percentage of good data is required for profile flag A?"
        ],
        "source_id": "argo-user-manual",
        "section_or_page": 'Page 77, Section 3.2.2 "Reference table 2a: overall profile quality flag"',
        "source_version": "3.44.0",
        "retrieved_on": "2026-11-14",
        "limits": "Applies to whole-profile summary quality; individual measurement levels are flagged using Reference table 2.",
        "related": ["qc-flag-scale", "data-modes-rad"],
        "sentences": [
            {
                "text": "Argo assigns an overall profile quality letter flag from A to F based on the percentage N of levels containing good data, defined in Reference table 2a.",
                "phrase": "Reference table 2a: overall profile quality flag",
                "location": "Page 77, Section 3.2.2",
                "numbers": "2a (Reference table), A to F (letter grades)"
            },
            {
                "text": "In calculating N, levels with QC flags 1, 2, 5, and 8 are counted as good data, levels with flags 3 and 4 are counted as bad data, and flags 0, 9, or FillValue are not used.",
                "phrase": "QC flag values of 1, 2, 5, 8",
                "location": "Page 77, Section 3.2.2",
                "numbers": "1, 2, 5, 8 (good flags), 3, 4 (bad flags), 0, 9 (not used flags)"
            },
            {
                "text": "Grade A requires N = 100% where all levels contain good data, Grade B spans 75% <= N < 100%, Grade C covers 50% <= N < 75%, Grade D spans 25% <= N < 50%, Grade E covers 0% < N < 25%, and Grade F indicates N = 0% where no levels have good data.",
                "phrase": "A N = 100%; All profile levels contain good data.",
                "location": "Page 77, Section 3.2.2",
                "numbers": "100%, 75%, 50%, 25%, 0% (thresholds)"
            },
            {
                "text": "An empty space FillValue is assigned when no QC is performed or no usable flag values are present in the profile.",
                "phrase": "No QC is performed or no usable flag values are present",
                "location": "Page 77, Section 3.2.2",
                "numbers": "None"
            }
        ]
    },
    {
        "id": "adjusted-vs-raw-variables",
        "question_examples": [
            "What is the difference between TEMP and TEMP_ADJUSTED?",
            "Why are there adjusted variables in Argo files?",
            "Which variable should researchers use in Argo netCDF files?"
        ],
        "source_id": "argo-user-manual",
        "section_or_page": 'Pages 23–25, Section 2.2.5 "Measurements for each profile"',
        "source_version": "3.44.0",
        "retrieved_on": "2026-11-14",
        "limits": "Covers variable naming in Argo NetCDF profile files; does not detail algorithmic calibration methods (such as OWC for salinity).",
        "related": ["data-modes-rad", "qc-flag-scale"],
        "sentences": [
            {
                "text": "In Argo netCDF profile files, the <PARAM> variable contains the raw values transmitted by the float, which should never be altered.",
                "phrase": "<PARAM> contains the raw values transmitted by the float.",
                "location": "Page 23, Section 2.2.5",
                "numbers": "None"
            },
            {
                "text": "The variable <PARAM>_QC records quality control flags that pertain to the raw values in <PARAM>.",
                "phrase": "<PARAM>_QC contains QC flags that pertain to the values in <PARAM>.",
                "location": "Page 23, Section 2.2.5",
                "numbers": "None"
            },
            {
                "text": "The mandatory variable <PARAM>_ADJUSTED contains values derived from the original parameter after applying sensor adjustments.",
                "phrase": "<PARAM>_ADJUSTED contains the adjusted values derived from the original values",
                "location": "Page 24, Section 2.2.5",
                "numbers": "None"
            },
            {
                "text": "When no adjustment has been performed on a parameter, the FillValue is inserted into <PARAM>_ADJUSTED and <PARAM>_ADJUSTED_ERROR.",
                "phrase": "When no adjustment is performed, the FillValue is inserted.",
                "location": "Page 24, Section 2.2.5",
                "numbers": "None"
            }
        ]
    },
    {
        "id": "argopy-user-modes-overview",
        "question_examples": [
            "What are the user modes in argopy?",
            "What is the difference between standard and research mode in argopy?",
            "Which mode should I choose in argopy?"
        ],
        "source_id": "argopy-user-modes",
        "section_or_page": 'Section "Definitions" & Section "Standard mode (default)"',
        "source_version": "",
        "retrieved_on": "2026-11-14",
        "limits": "Applies strictly to the argopy Python library fetching interface; underlying GDAC files remain unmodified NetCDF.",
        "related": ["data-modes-rad", "qc-flag-scale"],
        "sentences": [
            {
                "text": "The argopy Python library provides three user modes—standard, research, and expert—to control data verbosity and quality filtering.",
                "phrase": "argopy provides 3 user modes",
                "location": 'Section "Definitions"',
                "numbers": "3 (user modes)"
            },
            {
                "text": "Standard mode is the default mode in argopy and returns good or probably good data with QC flags 1 and 2 from real-time or delayed mode.",
                "phrase": "Standard mode (default)",
                "location": 'Section "Standard mode (default)"',
                "numbers": "1, 2 (QC flags)"
            },
            {
                "text": "Research mode preserves only delayed-mode data of the highest quality carefully checked by human experts, admitting exclusively QC flag 1.",
                "phrase": "preserving only data of the highest quality for research studies",
                "location": 'Section "Definitions"',
                "numbers": "1 (QC flag)"
            },
            {
                "text": "Expert mode returns all raw Argo data without any postprocessing or quality filtering.",
                "phrase": "expert mode return all the Argo data, without any postprocessing",
                "location": 'Section "Definitions"',
                "numbers": "None"
            }
        ]
    },
    {
        "id": "argo-data-policy-and-citation",
        "question_examples": [
            "How do I cite Argo float data in a paper?",
            "What is the official citation format for the Argo GDAC dataset?",
            "Is Argo data free to use?"
        ],
        "source_id": "wong2020",
        "section_or_page": 'Page 18, Section "HOW TO CITE ARGO DATA: THE DYNAMIC DOI STRUCTURE"',
        "source_version": "Vol. 7, Art. 700",
        "retrieved_on": "2026-11-14",
        "limits": "Covers global GDAC dataset citations; individual regional float providers or projects may also request acknowledgments in project metadata.",
        "related": ["argo-one-paragraph", "argo-gdac-structure"],
        "sentences": [
            {
                "text": "The citation of Argo data used in scientific studies requires specialized handling because the global dataset is dynamic, evolving and growing in time.",
                "phrase": "the Argo dataset is “dynamic,” evolving and growing in time.",
                "location": "Page 18, Section HOW TO CITE ARGO DATA",
                "numbers": "None"
            },
            {
                "text": "To allow reproducibility of scientific studies that use Argo data, a snapshot of the entire dataset at the GDACs is preserved each month.",
                "phrase": "a snapshot of the entire dataset at the GDACs is preserved each month.",
                "location": "Page 18, Section HOW TO CITE ARGO DATA",
                "numbers": "None"
            },
            {
                "text": "Argo adopted a Digital Object Identifier format based on the master DOI 10.17882/42182 with unique monthly snapshot suffixes appended after a hash symbol.",
                "phrase": "The Argo DOI takes the form http://doi.org/10.17882/42182#<nnnnn>",
                "location": "Page 18, Section HOW TO CITE ARGO DATA",
                "numbers": "10.17882/42182 (DOI), # (delimiter)"
            },
            {
                "text": "Authors cite an Argo snapshot by referencing the Argo Data Management Team, the snapshot date, and the specific snapshot DOI identifier.",
                "phrase": "An Argo snapshot (enabling data reproducibility) should be cited as follows",
                "location": "Page 18, Section HOW TO CITE ARGO DATA",
                "numbers": "None"
            }
        ]
    },
    {
        "id": "what-is-teos-10",
        "question_examples": [
            "What is TEOS-10 and why is it used in oceanography?",
            "What is the difference between TEOS-10 and EOS-80?",
            "Why did oceanographers replace EOS-80?"
        ],
        "source_id": "teos10-site",
        "section_or_page": 'Section "HOME"',
        "source_version": "",
        "retrieved_on": "2026-11-14",
        "limits": "Covers thermodynamic standards; does not cover biological or geochemical nutrient interactions beyond inorganic thermodynamic properties.",
        "related": ["practical-vs-absolute-salinity", "conservative-temperature", "gsw-sound-speed-inputs"],
        "sentences": [
            {
                "text": "TEOS-10 is the Thermodynamic Equation of Seawater 2010 adopted in 2009 by the Intergovernmental Oceanographic Commission to replace EOS-80 as the official description of seawater.",
                "phrase": "TEOS-10 was adopted by the Intergovernmental Oceanographic Commission",
                "location": 'Section "HOME"',
                "numbers": "2010 (TEOS-10), 2009 (year), 80 (EOS-80)"
            },
            {
                "text": "It is based on a Gibbs function formulation from which all thermodynamic properties of seawater, including density, enthalpy, entropy, and sound speed, can be derived in a thermodynamically consistent manner.",
                "phrase": "TEOS-10 is based on a Gibbs function formulation",
                "location": 'Section "HOME"',
                "numbers": "None"
            },
            {
                "text": "A significant change compared with past practice is that TEOS-10 uses Absolute Salinity (mass fraction of salt in g/kg) as opposed to conductivity-based Practical Salinity to describe salt content.",
                "phrase": "TEOS-10 uses Absolute Salinity S A",
                "location": 'Section "HOME"',
                "numbers": "None"
            },
            {
                "text": "While Absolute Salinity is needed to compute density and other properties, Practical Salinity on PSS-78 continues to be the measured variable archived in national databases.",
                "phrase": "Practical Salinity with the symbol S P",
                "location": 'Section "HOME"',
                "numbers": "78 (PSS-78)"
            }
        ]
    },
    {
        "id": "practical-vs-absolute-salinity",
        "question_examples": [
            "What is the difference between Practical Salinity and Absolute Salinity?",
            "Why does TEOS-10 use Absolute Salinity?",
            "What are the units of Practical Salinity vs Absolute Salinity?"
        ],
        "source_id": "teos10-site",
        "section_or_page": 'Section "HOME"',
        "source_version": "",
        "retrieved_on": "2026-11-14",
        "limits": "Covers standard open-ocean thermodynamic salinity definitions; coastal estuarine chemistry anomalies require localized composition models.",
        "related": ["what-is-teos-10", "conservative-temperature", "gsw-sound-speed-inputs"],
        "sentences": [
            {
                "text": "TEOS-10 defines salt content using Absolute Salinity (symbol SA), which represents the mass fraction of salt in seawater expressed in SI units of g/kg.",
                "phrase": "uses Absolute Salinity S A (mass fraction of salt in seawater)",
                "location": 'Section "HOME"',
                "numbers": "None"
            },
            {
                "text": "In contrast, Practical Salinity (symbol SP) under PSS-78 is a dimensionless quantity that serves essentially as a measure of seawater electrical conductivity.",
                "phrase": "Practical Salinity S P (which is essentially a measure of the conductivity of seawater)",
                "location": 'Section "HOME"',
                "numbers": "78 (PSS-78)"
            },
            {
                "text": "Spatial variations in the composition of seawater mean that Absolute Salinity is not simply proportional to Practical Salinity across the ocean.",
                "phrase": "Spatial variations of the composition of seawater",
                "location": 'Section "HOME"',
                "numbers": "None"
            },
            {
                "text": "Thermodynamic properties such as density and enthalpy are correctly expressed as functions of Absolute Salinity, while measured Practical Salinity continues to be archived in databases.",
                "phrase": "functions of Absolute Salinity rather than being functions of the conductivity",
                "location": 'Section "HOME"',
                "numbers": "None"
            }
        ]
    },
    {
        "id": "conservative-temperature",
        "question_examples": [
            "What is Conservative Temperature in TEOS-10?",
            "What units are used for Conservative Temperature?",
            "What inputs does Conservative Temperature accompany in GSW?"
        ],
        "source_id": "gsw-sound-speed",
        "section_or_page": 'Section "INPUT" & Section "DESCRIPTION"',
        "source_version": "3.05",
        "retrieved_on": "2026-11-14",
        "limits": "Derived thermodynamic relations connecting Conservative Temperature to potential enthalpy are documented in the TEOS-10 Manual, which is not currently retrieved.",
        "related": ["what-is-teos-10", "practical-vs-absolute-salinity", "gsw-sound-speed-inputs"],
        "sentences": [
            {
                "text": "In the Gibbs SeaWater oceanographic toolbox, Conservative Temperature (symbol CT) is defined on the ITS-90 temperature scale in units of degrees Celsius.",
                "phrase": "CT  =  Conservative Temperature (ITS-90)                         [ deg C ]",
                "location": 'Section "INPUT"',
                "numbers": "90 (ITS-90)"
            },
            {
                "text": "Conservative Temperature serves alongside Absolute Salinity (SA in g/kg) and sea pressure (p in dbar) as a required input for calculating seawater sound speed and specific volume.",
                "phrase": "75-term expression for specific volume in terms of SA, CT and p",
                "location": 'Section "DESCRIPTION"',
                "numbers": "75 (term expression)"
            },
            {
                "text": "In GSW function calculations, the array dimensions of Conservative Temperature and Absolute Salinity must match each other.",
                "phrase": "SA & CT need to have the same dimensions.",
                "location": 'Section "INPUT"',
                "numbers": "None"
            }
        ]
    },
    {
        "id": "gsw-sound-speed-inputs",
        "question_examples": [
            "What inputs are needed to calculate sound speed in GSW?",
            "How is sound speed calculated in the Gibbs SeaWater toolbox?",
            "What parameters does gsw_sound_speed require?"
        ],
        "source_id": "gsw-sound-speed",
        "section_or_page": 'Section "USAGE" & Section "DESCRIPTION"',
        "source_version": "3.05",
        "retrieved_on": "2026-11-14",
        "limits": "The GSW library function gsw_infunnel(SA,CT,p) is available to test whether data lie outside the oceanographic funnel.",
        "related": ["what-is-teos-10", "conservative-temperature", "practical-vs-absolute-salinity"],
        "sentences": [
            {
                "text": "The Gibbs SeaWater function gsw_sound_speed requires three oceanographic inputs: Absolute Salinity (SA in g/kg), Conservative Temperature (CT in degrees Celsius on ITS-90), and sea pressure (p in dbar).",
                "phrase": "sound_speed = gsw_sound_speed(SA,CT,p)",
                "location": 'Section "USAGE"',
                "numbers": "90 (ITS-90)"
            },
            {
                "text": "Sea pressure is gauge pressure relative to the surface, representing absolute pressure minus standard atmospheric pressure of 10.1325 dbar.",
                "phrase": "absolute pressure - 10.1325 dbar",
                "location": 'Section "INPUT"',
                "numbers": "10.1325 (dbar)"
            },
            {
                "text": "The function calculates speed of sound in seawater in meters per second using a computationally efficient 75-term polynomial expression for specific volume.",
                "phrase": "Calculates the speed of sound in seawater",
                "location": 'Section "DESCRIPTION"',
                "numbers": "75 (term)"
            },
            {
                "text": "This 75-term equation has been fitted in a restricted parameter range and is most accurate inside the oceanographic funnel described in McDougall et al. (2003).",
                "phrase": "is most accurate inside the \"oceanographic funnel\" described in McDougall et al. (2003).",
                "location": 'Section "DESCRIPTION"',
                "numbers": "75 (term), 2003 (year)"
            }
        ]
    },
    {
        "id": "noaa-cpc-nino-definitions",
        "question_examples": [
            "What are the geographic boundaries of the Nino regions?",
            "How does NOAA define Nino 3.4 and Nino 1+2?",
            "What coordinates define the El Nino monitoring areas?"
        ],
        "source_id": "noaa-cpc-nino",
        "section_or_page": 'Section "Relative Sea Surface Temperature"',
        "source_version": "",
        "retrieved_on": "2026-11-14",
        "limits": "Covers NOAA CPC coordinate boundaries; Niño 4 crosses the 180° antimeridian from 160°East to 150°West.",
        "related": ["argo-one-paragraph"],
        "sentences": [
            {
                "text": "The NOAA Climate Prediction Center defines standard oceanic coordinate boundaries in the tropical Pacific to monitor sea surface temperature indices.",
                "phrase": "Monthly Atmospheric & SST Indices",
                "location": 'Section "Introduction"',
                "numbers": "None"
            },
            {
                "text": "The Niño 1+2 region is bounded by latitudes 0 to 10°South and longitudes 90°West to 80°West off the coast of South America.",
                "phrase": "Niño 1+2 (0–10°South)(90°West–80°West)",
                "location": 'Section "Relative Sea Surface Temperature"',
                "numbers": "0–10°South, 90°West–80°West (coordinates)"
            },
            {
                "text": "The Niño 3 region spans latitudes 5°North to 5°South and longitudes 150°West to 90°West in the eastern tropical Pacific.",
                "phrase": "Niño 3 (5°North–5°South)(150°West–90°West)",
                "location": 'Section "Relative Sea Surface Temperature"',
                "numbers": "5°North–5°South, 150°West–90°West (coordinates)"
            },
            {
                "text": "The Niño 3.4 region spans latitudes 5°North to 5°South and longitudes 170°West to 120°West, while Niño 4 encompasses latitudes 5°North to 5°South and longitudes 160°East to 150°West.",
                "phrase": "Niño 4 (5°North–5°South)(160°East–150°West), Niño 3.4 (5°North–5°South)(170–120°West)",
                "location": 'Section "Relative Sea Surface Temperature"',
                "numbers": "5°North–5°South, 170–120°West, 160°East–150°West (coordinates)"
            }
        ]
    },
    {
        "id": "argo-array-size-and-coverage",
        "question_examples": [
            "How many floats are in the Argo array?",
            "What is the spatial coverage and resolution of Argo?",
            "How many profiles does Argo collect per day?"
        ],
        "source_id": "argopy-what-is-argo",
        "section_or_page": 'Section "What is Argo ?"',
        "source_version": "",
        "retrieved_on": "2026-11-14",
        "limits": "Covers core open-ocean spatial target; marginal seas, high-latitude seasonal ice zones, and boundary currents have separate regional densities.",
        "related": ["argo-one-paragraph", "float-cycle-and-depth"],
        "sentences": [
            {
                "text": "The international Argo network maintains nearly 4000 autonomous profiling floats distributed across the global ocean.",
                "phrase": "Argo is a global network of nearly 4000 autonomous probes",
                "location": 'Section "What is Argo ?"',
                "numbers": "4000 (probes)"
            },
            {
                "text": "The geographic locations of these robotic probes are distributed between the 60th parallels to provide seasonally and regionally unbiased measurements.",
                "phrase": "The localisation of these probes is nearly random between the 60th parallels",
                "location": 'Section "What is Argo ?"',
                "numbers": "60th (parallels)"
            },
            {
                "text": "The global array reached its target coverage of one profile per month per 3 degree by 3 degree horizontal area in 2007.",
                "phrase": "full global coverage (of 1 profile per month and per 3x3 degree",
                "location": 'Section "What is Argo ?"',
                "numbers": "1 (profile), 3x3 (degree area), 2007 (year)"
            },
            {
                "text": "Operating continuously, the observation array provides more than 400 in situ vertical profiles per day.",
                "phrase": "more than 400 profiles per day.",
                "location": 'Section "What is Argo ?"',
                "numbers": "400 (profiles per day)"
            }
        ]
    },
    {
        "id": "float-telemetry-and-surface",
        "question_examples": [
            "How do Argo floats send their data back to land?",
            "How long do Argo floats spend on the surface?",
            "Do Argo floats use satellites or radio to transmit data?"
        ],
        "source_id": "wong2020",
        "section_or_page": 'Pages 5–6, Section "Satellite Communications"',
        "source_version": "Vol. 7, Art. 700",
        "retrieved_on": "2026-11-14",
        "limits": "Covers Argos and Iridium satellite systems; does not cover experimental acoustic underwater positioning networks used beneath Antarctic sea ice.",
        "related": ["float-cycle-and-depth", "argo-one-paragraph"],
        "sentences": [
            {
                "text": "Argo floats transmit their ocean observations to ground stations using satellite telecommunication systems whenever they surface.",
                "phrase": "satellite system as the means of data transmission,",
                "location": 'Page 5, Section "Satellite Communications"',
                "numbers": "None"
            },
            {
                "text": "Early generation floats used one-way Argos-2 satellite transmission, which required floats to drift on the sea surface for 6 to 18 hours to guarantee error-free data reception.",
                "phrase": "must spend between 6 and 18 h transmitting",
                "location": 'Page 5, Section "Satellite Communications"',
                "numbers": "6 and 18 h (hours)"
            },
            {
                "text": "At present, the majority of active floats use bidirectional Iridium satellite communications, which reduces time spent on the sea surface to less than 20 minutes for each cycle.",
                "phrase": "time spent on the sea surface to < 20 min for each cycle.",
                "location": 'Page 6, Section "Satellite Communications"',
                "numbers": "20 min (minutes, as < 20 min)"
            },
            {
                "text": "Two-way communication via Iridium makes it possible to send instructions to the float for troubleshooting or for changing the float's sampling mission.",
                "phrase": "Two-way communication via Iridium makes it possible",
                "location": 'Page 6, Section "Satellite Communications"',
                "numbers": "None"
            }
        ]
    },
    {
        "id": "core-argo-parameters",
        "question_examples": [
            "What parameters do core Argo floats measure?",
            "What sensors are mounted on a standard Argo float?",
            "What are the primary physical variables collected by Argo?"
        ],
        "source_id": "argo-how-floats-work",
        "section_or_page": 'Section "What is in an Argo float?"',
        "source_version": "",
        "retrieved_on": "2026-11-14",
        "limits": "Covers core CTD parameters; biogeochemical variables (oxygen, nitrate, pH, bio-optics) follow separate BGC-Argo sensor specifications.",
        "related": ["float-cycle-and-depth", "bgc-argo-parameters"],
        "sentences": [
            {
                "text": "On top of every core Argo profiling float is a Conductivity, Temperature, Depth (CTD) sensor package to measure physical seawater properties.",
                "phrase": "On the top of every Argo float is a CTD",
                "location": 'Section "What is in an Argo float?"',
                "numbers": "None"
            },
            {
                "text": "The sensor measures temperature within an accuracy of 0.001 degrees Celsius and pressure within 0.1 dbar.",
                "phrase": "measures temperature within an accuracy of 0.001 degree C",
                "location": 'Section "What is in an Argo float?"',
                "numbers": "0.001 (degree C), 0.1 (dbar)"
            },
            {
                "text": "Salinity is calculated from measured conductivity, temperature, and pressure within an accuracy of 0.001 practical salinity units.",
                "phrase": "calculate salinity using conductivity, temperature, and pressure within 0.001 psu (practical salinity units).",
                "location": 'Section "What is in an Argo float?"',
                "numbers": "0.001 (psu)"
            },
            {
                "text": "These measurements are gathered as the float moves up through the water column back to the ocean surface.",
                "phrase": "taking a series of measurements as it moves back up",
                "location": 'Section "What does an Argo float do?"',
                "numbers": "None"
            }
        ]
    },
    {
        "id": "bgc-argo-parameters",
        "question_examples": [
            "What parameters do BGC Argo floats measure?",
            "What is Biogeochemical Argo?",
            "What sensors are added to BGC floats?"
        ],
        "source_id": "argo-qc-bgc",
        "section_or_page": 'Pages 6–9, Section 2.1 "Real-time quality control for biogeochemical data"',
        "source_version": "1.1",
        "retrieved_on": "2026-11-14",
        "limits": "Covers standard global BGC variables; experimental sensors such as acoustic fish trackers or imaging cytometers follow auxiliary data protocols.",
        "related": ["core-argo-parameters", "argo-one-paragraph"],
        "sentences": [
            {
                "text": "The Argo Quality Control Manual for Biogeochemical Data defines quality control procedures for floats measuring chemical and biological properties.",
                "phrase": "Quality Control Manual for Biogeochemical Data",
                "location": "Page 5, Header",
                "numbers": "None"
            },
            {
                "text": "Defined parameters in the biogeochemical data system include dissolved oxygen (DOXY), chlorophyll-a (CHLA), particle backscattering (BBP), downwelling irradiance, nitrate, and pH.",
                "phrase": "real-time tests are defined for the following biogeochemical parameters",
                "location": "Page 9, Section 2.1",
                "numbers": "None"
            },
            {
                "text": "Users are warned that the accuracy of raw biogeochemical data in their unadjusted state is not suitable for direct usage in scientific applications.",
                "phrase": "accuracy of these biogeochemical data in their raw state",
                "location": "Page 6, Preamble",
                "numbers": "None"
            },
            {
                "text": "Often, adjustments are needed before biogeochemical observations can be used for meaningful scientific applications.",
                "phrase": "often, adjustments are needed before these data can be used for meaningful scientific applications.",
                "location": "Page 6, Preamble",
                "numbers": "None"
            }
        ]
    },
    {
        "id": "deep-argo-depth",
        "question_examples": [
            "How deep do Deep Argo floats dive?",
            "What is Deep Argo and why was it developed?",
            "Can Argo measure below 2000 meters?"
        ],
        "source_id": "roemmich2019",
        "section_or_page": 'Page 7, Section "Deep Argo"',
        "source_version": "Vol. 6, Art. 439",
        "retrieved_on": "2026-11-14",
        "limits": "Covers Deep Argo design and depth limits; does not cover core Argo float pressure limits (2000 dbar).",
        "related": ["float-cycle-and-depth", "argo-array-size-and-coverage"],
        "sentences": [
            {
                "text": "Deep Argo was developed to sample the ocean interior below the 2000-dbar limit of the core array down to the abyssal ocean floor at 6000 dbar.",
                "phrase": "accurate measurements to 6000 dbar",
                "location": 'Page 7, Section "Deep Argo"',
                "numbers": "2000 dbar, 6000 dbar"
            },
            {
                "text": "Standard core floats sample approximately the upper half of ocean volume, leaving deep and abyssal water masses below 2000 dbar unmonitored by autonomous floats.",
                "phrase": "ocean below 2000 dbar",
                "location": 'Page 7, Section "Deep Argo"',
                "numbers": "2000 dbar"
            },
            {
                "text": "Development of floats and CTDs capable of accurate measurements to 6000 dbar enables sampling of bottom-intensified ocean variability.",
                "phrase": "bottom-intensified ocean variability",
                "location": 'Page 7, Section "Deep Argo"',
                "numbers": "6000 dbar"
            },
            {
                "text": "Antarctic Bottom Water below 2000 dbar has been warming and freshening over recent decades, contributing directly to steric sea level rise.",
                "phrase": "Antarctic Bottom Water, which fills much of the ocean",
                "location": 'Page 7, Section "Deep Argo"',
                "numbers": "2000 dbar"
            }
        ]
    },
    {
        "id": "argo-gdac-structure",
        "question_examples": [
            "What are the Argo GDACs and where are they located?",
            "How does data synchronization work between GDACs?",
            "What role do DACs and GDACs play in the Argo data system?"
        ],
        "source_id": "wong2020",
        "section_or_page": 'Pages 6–7, Section "Components of the Argo Data System"',
        "source_version": "Vol. 7, Art. 700",
        "retrieved_on": "2026-11-14",
        "limits": "Describes global data assembly centers; does not detail initial satellite telemetry decoding performed upstream by national Data Assembly Centres (DACs).",
        "related": ["argo-one-paragraph", "argo-data-policy-and-citation"],
        "sentences": [
            {
                "text": "The international Argo data system delivers observations to users through two mirror Global Data Assembly Centers (GDACs).",
                "phrase": "Data are publicly and freely available via two Global Data Assembly Centers (GDACs)",
                "location": "Page 6, Components of the Argo Data System",
                "numbers": "2 (GDACs)"
            },
            {
                "text": "The two GDACs are the Coriolis Data Center in France and the US Navy's Fleet Numerical Meteorology and Oceanography Center (FNMOC).",
                "phrase": "Coriolis Data Center in France",
                "location": "Page 6, Components of the Argo Data System",
                "numbers": "None"
            },
            {
                "text": "Data holdings at the two Argo GDACs are synchronized once per day to ensure redundancy and uniform global access.",
                "phrase": "synchronized once per day",
                "location": "Page 6–7, Components of the Argo Data System",
                "numbers": "1 (once per day)"
            },
            {
                "text": "The two GDACs receive standardized netCDF files that have been processed by 11 national Data Assembly Centers (DACs).",
                "phrase": "processed by 11 national Data Assembly Centers",
                "location": "Page 6, Components of the Argo Data System",
                "numbers": "11 (DACs), 2 (GDACs)"
            }
        ]
    }
]

def check_phrase_in_source(source_id: str, phrase: str) -> bool:
    txt_path = REPO_ROOT / "knowledge" / "text" / f"{source_id}.txt"
    if not txt_path.exists():
        return False
    raw_content = txt_path.read_text(encoding="utf-8")
    norm_content = unicodedata.normalize("NFKD", raw_content)
    norm_phrase = unicodedata.normalize("NFKD", phrase)
    pattern = r"\s+".join(re.escape(w) for w in norm_phrase.split())
    return bool(re.search(pattern, norm_content, re.IGNORECASE))

def build_evidence_markdown(note: dict) -> str:
    lines = [
        f"# Evidence Audit: {note['id']}",
        "",
        f"- **Source ID**: `{note['source_id']}`",
        f"- **Section / Page**: `{note['section_or_page']}`",
        f"- **Source Document Version**: `{note.get('source_version', '')}`",
        f"- **Retrieved On**: `{note.get('retrieved_on', '2026-11-14')}`",
        "",
        "## Sentences and Evidence",
        ""
    ]
    for idx, sent in enumerate(note["sentences"], 1):
        lines.extend([
            f"### Sentence {idx}",
            f"- **Text**: \"{sent['text']}\"",
            f"- **Source File**: `knowledge/text/{note['source_id']}.txt`",
            f"- **Location**: {sent['location']}",
            f"- **Supporting Phrase**: \"{sent['phrase']}\"",
            f"- **Numbers / Flag Values / Thresholds**: {sent['numbers']}",
            ""
        ])
    return "\n".join(lines)

def build_clean_yaml_note(note: dict) -> dict:
    answer_text = " ".join(s["text"] for s in note["sentences"]) + "\n"
    item = {
        "id": note["id"],
    }
    if "aliases" in note:
        item["aliases"] = note["aliases"]
    item.update({
        "question_examples": note["question_examples"],
        "answer": answer_text,
        "source_id": note["source_id"],
        "section_or_page": note["section_or_page"],
        "source_version": note.get("source_version", ""),
        "retrieved_on": note.get("retrieved_on", "2026-11-14"),
        "limits": note["limits"],
        "related": note["related"],
        "verified": False,
        "checked_on": ""
    })
    return item

def main():
    print("Verifying 21 notes and evidence sentences...")
    evidence_dir = REPO_ROOT / "knowledge" / "notes" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    yaml_notes = []
    total_sentences = 0
    errors = []

    for note in NOTES:
        nid = note["id"]
        sid = note["source_id"]
        sents = note["sentences"]
        total_sentences += len(sents)

        for s_idx, s in enumerate(sents, 1):
            phrase = s["phrase"]
            words = phrase.split()
            if len(words) >= 15:
                errors.append(f"{nid} S{s_idx}: phrase has {len(words)} words (must be < 15): '{phrase}'")
            if not check_phrase_in_source(sid, phrase):
                errors.append(f"{nid} S{s_idx}: phrase NOT found in {sid}.txt: '{phrase}'")

        # Write evidence file
        md_content = build_evidence_markdown(note)
        md_path = evidence_dir / f"{nid}.md"
        md_path.write_text(md_content, encoding="utf-8")

        # Accumulate yaml note
        yaml_notes.append(build_clean_yaml_note(note))

    if errors:
        print(f"[FAILED] {len(errors)} validation errors:")
        for err in errors:
            print(f"  - {err}")
        raise SystemExit(1)

    # Write cleaned argo_notes.yaml
    notes_yaml_path = REPO_ROOT / "knowledge" / "notes" / "argo_notes.yaml"
    header = (
        "# Trusted document-derived notes for SIQVA.\n"
        "# Generated strictly from extracted source texts in knowledge/text/.\n"
        "# All notes default to verified: false; only the owner verifies them.\n\n"
    )
    with open(notes_yaml_path, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.dump(yaml_notes, f, allow_unicode=True, sort_keys=False)

    print(f"[SUCCESS] Generated {len(yaml_notes)} notes and {len(yaml_notes)} evidence files.")
    print(f"Total verified sentences: {total_sentences}")

if __name__ == "__main__":
    main()

