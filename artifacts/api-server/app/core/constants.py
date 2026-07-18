# ─────────────────────────────────────────────
# Recognised E.164 country-code strings (no leading +)
# Add more as needed; default is "91" (India).
# ─────────────────────────────────────────────
VALID_COUNTRY_CODES: set[str] = {
    "1",    # USA / Canada
    "7",    # Russia / Kazakhstan
    "20",   # Egypt
    "27",   # South Africa
    "30",   # Greece
    "31",   # Netherlands
    "32",   # Belgium
    "33",   # France
    "34",   # Spain
    "36",   # Hungary
    "39",   # Italy
    "40",   # Romania
    "41",   # Switzerland
    "43",   # Austria
    "44",   # United Kingdom
    "45",   # Denmark
    "46",   # Sweden
    "47",   # Norway
    "48",   # Poland
    "49",   # Germany
    "51",   # Peru
    "52",   # Mexico
    "53",   # Cuba
    "54",   # Argentina
    "55",   # Brazil
    "56",   # Chile
    "57",   # Colombia
    "58",   # Venezuela
    "60",   # Malaysia
    "61",   # Australia
    "62",   # Indonesia
    "63",   # Philippines
    "64",   # New Zealand
    "65",   # Singapore
    "66",   # Thailand
    "81",   # Japan
    "82",   # South Korea
    "84",   # Vietnam
    "86",   # China
    "90",   # Turkey
    "91",   # India  ← default
    "92",   # Pakistan
    "93",   # Afghanistan
    "94",   # Sri Lanka
    "95",   # Myanmar
    "98",   # Iran
    "212",  # Morocco
    "213",  # Algeria
    "216",  # Tunisia
    "218",  # Libya
    "220",  # Gambia
    "221",  # Senegal
    "222",  # Mauritania
    "230",  # Mauritius
    "234",  # Nigeria
    "254",  # Kenya
    "255",  # Tanzania
    "256",  # Uganda
    "260",  # Zambia
    "263",  # Zimbabwe
    "351",  # Portugal
    "352",  # Luxembourg
    "353",  # Ireland
    "354",  # Iceland
    "355",  # Albania
    "356",  # Malta
    "357",  # Cyprus
    "358",  # Finland
    "359",  # Bulgaria
    "370",  # Lithuania
    "371",  # Latvia
    "372",  # Estonia
    "380",  # Ukraine
    "381",  # Serbia
    "385",  # Croatia
    "386",  # Slovenia
    "420",  # Czech Republic
    "421",  # Slovakia
    "966",  # Saudi Arabia
    "967",  # Yemen
    "968",  # Oman
    "971",  # UAE
    "972",  # Israel
    "973",  # Bahrain
    "974",  # Qatar
    "975",  # Bhutan
    "976",  # Mongolia
    "977",  # Nepal
    "992",  # Tajikistan
    "993",  # Turkmenistan
    "994",  # Azerbaijan
    "995",  # Georgia
    "996",  # Kyrgyzstan
    "998",  # Uzbekistan
}

DEFAULT_COUNTRY_CODE = "91"
