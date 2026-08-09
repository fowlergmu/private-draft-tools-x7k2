# private-draft-tools-x7k2

## Current injury feed

`Data/Current Injuries.csv` is a short-term availability snapshot maintained
separately from `Data/Injury Risk.csv`, which remains the long-term durability
model. The website fetches both files and displays a current-status badge beside
affected players without changing their historical risk rating.

Required columns are `name` and `status`. Supported statuses are `Monitor`,
`Day-to-day`, `Questionable`, `Doubtful`, `Out`, `IR`, `PUP`, `NFI`, and
`Active`. Optional columns are `pos`, `injury`, `updated`, `source`, `provider`,
and `notes`.
The file is treated as a complete snapshot, so removing a player removes their
badge on the next site sync.

## Injury refresh

The injury dashboard includes two controls:

1. **Update Injury Sources** opens the GitHub Action. Choose **Run workflow**
   there to pull structured injury statuses from Sleeper and scan the public
   NFL Daily News feed on Bluesky.
2. **Refresh Display** reloads only that CSV in the website without resetting a
   draft or re-importing rankings.

The same workflow runs automatically once daily. Neither source requires login
credentials. Sleeper supplies the structured status and injured body part;
NFL Daily News supplies breaking-report context and links. The updater matches
both sources to fantasy players in the rankings CSV, rejects stale short-term
statuses, keeps longer-term IR/PUP/NFI designations, and honors newer reports
that a player returned or was activated.
