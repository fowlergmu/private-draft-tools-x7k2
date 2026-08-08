# private-draft-tools-x7k2

## Current injury feed

`Data/Current Injuries.csv` is a short-term availability snapshot maintained
separately from `Data/Injury Risk.csv`, which remains the long-term durability
model. The website fetches both files and displays a current-status badge beside
affected players without changing their historical risk rating.

Required columns are `name` and `status`. Supported statuses are `Monitor`,
`Day-to-day`, `Questionable`, `Doubtful`, `Out`, `IR`, `PUP`, `NFI`, and
`Active`. Optional columns are `pos`, `injury`, `updated`, `source`, and `notes`.
The file is treated as a complete snapshot, so removing a player removes their
badge on the next site sync.
