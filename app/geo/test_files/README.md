# Test files for addresses, sales tax and drive times

Recorded-style answers the tests use instead of calling Google, the Census
geocoder or the Tennessee map service. Every street address is invented.
The boundaries are simplified squares placed around the invented points,
with the local rates the state's data listed on 2026-11-06 (Bradley 2.75%,
Hamilton and Knox 2.25%); they are not the real boundaries.

`place_new_street.json` and `search_new_street.json` stand for a street in a
new neighborhood that the Census map does not have yet: the Census geocoder
finds no match, and Google's Text Search returns the place's ID.
