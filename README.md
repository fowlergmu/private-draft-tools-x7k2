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

## Manual NFL Daily News refresh

The injury dashboard includes two controls:

1. **Search NFL Daily News** opens the manually triggered GitHub Action. Choose
   **Run workflow** there to scan the public Bluesky feed and update the current
   injuries CSV.
2. **Refresh Display** reloads only that CSV in the website without resetting a
   draft or re-importing rankings.

The workflow uses Bluesky's public author-feed API and requires no Bluesky
credentials. It matches posts to fantasy players in the rankings CSV, keeps
recent unresolved statuses for a limited period, and removes players when a
newer post reports that they returned or were activated.
