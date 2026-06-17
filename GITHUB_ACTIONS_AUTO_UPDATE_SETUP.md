# Automation In Trade: GitHub Actions → Python Script → JSON Update → Cloudflare Pages Auto Deploy

This package includes:

- `.github/workflows/update-market-json.yml`
- `requirements.txt`
- your existing `GenerateMarketToolsJson.py`
- existing website files and `market-data/*.json`

## What the workflow does

1. GitHub Actions runs on schedule after market close.
2. It installs Python dependencies.
3. It runs:

   ```bash
   python GenerateMarketToolsJson.py --mode all
   ```

4. It updates JSON files inside `market-data/`.
5. It commits and pushes only changed `market-data` files.
6. Cloudflare Pages auto-deploys the site after the GitHub push.

## Schedule

The workflow is scheduled at:

```yaml
cron: "45 10 * * 1-5"
```

That means 10:45 UTC = 4:15 PM IST, Monday to Friday.

## GitHub upload steps

1. Create a new GitHub repository, for example:

   `automationintrade-site`

2. Extract this ZIP.

3. Open the extracted folder. Upload the files INSIDE the website folder to GitHub root.

   Correct GitHub root should look like this:

   ```text
   .github/workflows/update-market-json.yml
   GenerateMarketToolsJson.py
   index.html
   style.css
   script.js
   market-data/
   market-tools/
   assets/
   robots.txt
   sitemap.xml
   requirements.txt
   ```

   Do not upload it as:

   ```text
   V98/GenerateMarketToolsJson.py
   V98/index.html
   ```

4. In GitHub, enable workflow write permission:

   `Repository → Settings → Actions → General → Workflow permissions → Read and write permissions → Save`

5. Go to:

   `Actions → Update Market JSON → Run workflow`

6. For the first test, select:

   `market-snapshot`

   This is faster than running the full update.

7. If successful, run again with:

   `all`

## Cloudflare Pages setup

1. Go to Cloudflare Dashboard.
2. Open Workers & Pages.
3. Create or connect a Pages project with GitHub.
4. Select this GitHub repository.
5. Use these settings:

   ```text
   Framework preset: None
   Build command: leave blank
   Build output directory: /
   Root directory: /
   ```

6. Deploy once.
7. After every GitHub push, Cloudflare Pages will deploy automatically.

## Important note

If your current Cloudflare Pages project was created using Direct Upload and Cloudflare does not let you attach GitHub to the same project, create a new Git-connected Pages project and then move the custom domain to that new project after testing.

## Manual run modes

Available modes:

```bash
python GenerateMarketToolsJson.py --mode all
python GenerateMarketToolsJson.py --mode 52w
python GenerateMarketToolsJson.py --mode market-snapshot
python GenerateMarketToolsJson.py --mode fii-dii
python GenerateMarketToolsJson.py --mode index-performance
python GenerateMarketToolsJson.py --mode stock-strength
python GenerateMarketToolsJson.py --mode momentum-scanner
python GenerateMarketToolsJson.py --mode volume-surge
python GenerateMarketToolsJson.py --mode near-breakout
```

The GitHub Actions manual dropdown supports the same modes.
