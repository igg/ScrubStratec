This program modifies the headers of Stratec pQCT files to zero-out
the Patient Name and round the DOB to the 1st of the nearest month.

Month rounding causes a DOB of 1956-12-17 to be changed to 1957-01-01,
and 1956-12-16 to be changed to 1956-12-01 (birth month is favored for midway dates)

