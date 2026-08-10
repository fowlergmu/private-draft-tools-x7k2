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
   there to pull FantasyPros injury reports and injury news, refresh Sleeper's
   structured statuses, and scan the public NFL Daily News feed on Bluesky.
2. **Refresh Display** reloads only that CSV in the website without resetting a
   draft or re-importing rankings.

The same workflow runs automatically once daily. FantasyPros is the primary
source and supplies injury designations, practice reports, probability of
playing when available, and direct injury-news links. Sleeper is the structured
fallback; NFL Daily News supplies supplemental breaking-report context. The
updater matches all sources to fantasy players in the rankings CSV, rejects
stale short-term statuses, keeps longer-term IR/PUP/NFI designations, and honors
newer explicit reports that a player returned or was activated. On same-day
conflicts, the structured FantasyPros injury report has priority.

### Enable FantasyPros

1. Request a personal API key at
   <https://secure.fantasypros.com/api-keys/request/>. A production key is
   required for the live site; free keys are intended for testing.
2. Open the repository's **Settings → Secrets and variables → Actions** page.
3. Add a repository secret named `FANTASYPROS_API_KEY` containing the key.
4. Run **Refresh NFL injuries** once from the Actions tab.

The key is read only by GitHub Actions and is never sent to the browser or
stored in a published CSV. If the key is missing or FantasyPros is temporarily
unavailable, the workflow continues with Sleeper and Bluesky. If no structured
source is available, the updater fails safely without replacing the CSV.
