# -*- coding: utf-8 -*-
"""離線測試：用四個網站 2026-09 抓下來的真實文字片段驗證解析器。"""
from em_conferences import (parse_acep, parse_saem, parse_ifem, parse_eusem,
                            parse_date_range, parse_generic_society)

ACEP_TXT = """Future Dates
ACEP27 Scientific Assembly
10/25/2027 - 10/28/2027
Boston, Massachusetts
ACEP28 Scientific Assembly
9/17/2028 - 9/20/2028
Las Vegas, Nevada
ACEP29 Scientific Assembly
10/1/2029 - 10/4/2029
Philadelphia, Pennsylvania
ACEP30 Scientific Assembly
10/17/2030 - 10/20/2030
San Francisco, California
ACEP31 Scientific Assembly
10/27/2031 - 10/30/2031
Chicago, Illinois
ACEP32 Scientific Assembly
10/4/2032 - 10/7/2032
Dallas, Texas"""

ACEP_CURRENT_TXT = """ACEP Scientific Assembly 2026
Join Us for ACEP26 | October 5-8, 2026
We're excited to be in | Chicago, Illinois, United States | for ACEP26"""

SAEM_TXT = """Future Meetings
Annual Meeting
SAEM27
May 18-21, 2027 (Tuesday - Friday)
San Francisco, CA
San Francisco Marriott Marquis
SAEM28
May 16-19, 2028 (Tuesday - Friday)
Austin, TX
JW Marriott Austin
SAEM29
May 15-18 (Tuesday - Friday)
Las Vegas, NV
Paris Las Vegas
Regional Meetings"""

IFEM_TXT = """Upcoming IFEM Global Congress
ICEM 2026 - HAMBURG, GERMANY
9-13 JUNE 2026
25th International Conference on Emergency Medicine
Host: German Association for Emergency Medicine (DGINA)
IFEM2027 - MALAYSIA
JUNE 2027
26th IFEM Global Congress on Emergency Medicine
Host: Malaysian College of Emergency Medicine
IFEM2028 - BRAZIL
JUNE 2028
27th IFEM Global Congress on Emergency Medicine
Host: Brazilian Association of Emergency Medicine
Previous Congress
ICEM 2024 - TAIPEI, TAIWAN
19 - 23 JUNE 2024"""

EUSEM_TXT = """EUSEM Congress 2026
The EUSEM 2025 Congress was held in Vienna, Austria, from 28 September to 1 October 2025.
The Standard Rate Registration Deadline is 7 September 2026
23-24 September - Pre-courses
25-27 September - Congress
Get ready for a thrilling time in Paris! Catch you there!"""


def show(rows):
    for r in rows:
        print(f"  {r.society:6} {str(r.year):5} {r.start or '?':10} {r.end or '?':10} "
              f"{r.city + ', ' + r.country_or_state:32} | {r.name[:44]}")


print("ACEP"); show(parse_acep(ACEP_TXT))
acep_current = parse_acep(ACEP_CURRENT_TXT)
assert len(acep_current) == 1
assert acep_current[0].year == 2026
assert acep_current[0].start == "2026-10-05"
assert acep_current[0].end == "2026-10-08"
assert acep_current[0].city == "Chicago"
print("SAEM"); show(parse_saem(SAEM_TXT))
print("IFEM"); show(parse_ifem(IFEM_TXT))
print("EUSEM"); show(parse_eusem(EUSEM_TXT))

print("\n日期解析單元測試")
cases = [
    ("10/25/2027 - 10/28/2027", None),
    ("May 18-21, 2027 (Tuesday - Friday)", None),
    ("May 15-18 (Tuesday - Friday)", 2029),
    ("9-13 JUNE 2026", None),
    ("19 – 23 JUNE 2024", None),
    ("23-27 September 2026", None),
    ("from 28 September to 1 October 2025", None),
    ("September 28 - October 1, 2025", None),
    ("June 12, 2026", None),
    ("JUNE 2027", 2027),
]
for s, dy in cases:
    print(f"  {s!r:40} -> {parse_date_range(s, dy)}")

print("\n通用學會 parser：只保留未來急診活動")
assert not parse_generic_society(
    "13th ACEM\n10-13 Dec 2025\n32nd Annual Scientific Meeting of Hong Kong College of Radiologists\n23-24 November 2024",
    "HKCEM", "https://hkcem.org.hk/")[0].start
assert len(parse_generic_society(
    "Joint Clinical Meeting & Didactic Lectures (JCM)\nScientific Affairs Committee",
    "HKCEM", "https://hkcem.org.hk/")) == 1
asian = parse_generic_society("13th ACEM\n10-13 Dec 2025\n14th ACEM\n20-25 Oct 2028",
                              "ASIANSEM", "https://www.asiansem.org/")
assert len(asian) == 1 and asian[0].year == 2028
