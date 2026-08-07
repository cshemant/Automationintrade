# Corporate Actions Data Update Options

The Corporate Actions Tracker should stay simple on the front end:

- Upcoming Actions
- Today
- Next 7 Days
- Next 30 Days
- Event filter: Dividend / Bonus / Split / Rights / Buyback

Expired corporate actions are not shown on the tracker because they create clutter and reduce user trust for a page focused on upcoming investor action dates.

## Recommended update command

```powershell
python UpdateAllData.py --mode corporate-actions
```

This runs:

```powershell
python GenerateCorporateActionsJson.py --write-empty-on-fail
```

The generated JSON keeps upcoming/fresh rows only:

```text
market-data/corporate-actions.json
```

## Manual NSE CSV fallback

If NSE blocks the API or the GitHub Action cannot fetch fresh data:

1. Open the NSE Corporate Actions page.
2. Select the forthcoming window you want, such as All Forthcoming / Next 3 Months.
3. Download the CSV.
4. Run:

```powershell
python GenerateCorporateActionsJson.py --csv "C:\Users\YourName\Downloads\corporate_actions.csv"
```

## Front-end behavior

The page should display only active records that still matter to users:

- Today's ex-date / record-date
- Upcoming corporate actions
- Next 7 days
- Next 30 days
- Event type filters

Old/expired rows should not be linked from the main UI.
