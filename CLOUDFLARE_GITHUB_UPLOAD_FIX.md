# Cloudflare Pages CSS / Images Fix

This version uses root-absolute asset paths everywhere:

- `/style.css?v=99`
- `/script.js?v=99`
- `/logo.png`
- `/assets/...`

This prevents CSS and image breakage on nested URLs such as:

- `/market-tools/`
- `/about-us/`
- `/market-tools/stock-strength-ranker/`

## Important upload rule

Upload/commit the **full contents inside the V99 folder** to your GitHub repository root. The repository root must include folders as well as files:

```text
.github/
about-us/
assets/
market-data/
market-tools/
result-scanner/
index.html
style.css
script.js
logo.png
requirements.txt
```

If you upload only root files and miss folders like `assets/`, `market-tools/`, or `.github/`, subpages, images, and GitHub Actions will not work correctly.

## Best upload method

Use GitHub Desktop or Git command instead of browser upload, because hidden folders like `.github` can be missed in browser upload.

```bash
git add .
git commit -m "Fix Cloudflare Pages asset paths and automation workflow"
git push origin main
```

Cloudflare Pages will auto-deploy after the push.
