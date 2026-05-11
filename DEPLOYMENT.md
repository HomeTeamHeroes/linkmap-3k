# Step-by-step deployment to GitHub Pages

This guide walks through deploying linkmap to GitHub Pages with automated
weekly scans, public dashboard, and broken-link issue notifications.

**No Drupal authentication needed** — that's an optional later upgrade
documented at the end.

## Time required

15 minutes for setup. 10–15 minutes for the first scan to finish.

## Prerequisites

- A GitHub account (free is fine)
- `git` installed locally (or use GitHub web UI for all file edits)
- The `linkmap-3k-template.zip` from the previous chat message

## Steps

### 1. Create a new GitHub repository

1. Go to [github.com/new](https://github.com/new)
2. **Repository name:** `linkmap-3k` (or anything you prefer)
3. **Description:** `Automated link audit for kolmekampusta.fi`
4. **Public** — required for free GitHub Pages
5. Leave everything else unchecked (no README, no .gitignore — we provide our own)
6. Click **Create repository**

You'll land on the empty repo page. Keep this tab open.

### 2. Extract the template zip and push files

#### Option A — command line (faster)

```powershell
# Extract zip
cd D:\code_projects
Expand-Archive linkmap-3k-template.zip -DestinationPath .
cd repo-template

# Initialize git and push (replace YOUR-USERNAME)
git init
git add .
git commit -m "Initial linkmap setup"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/linkmap-3k.git
git push -u origin main
```

#### Option B — GitHub web UI (no command line needed)

1. On the empty repo page, click **uploading an existing file**
2. Drag all files from the unzipped `repo-template/` folder into the upload zone
3. **Important:** the `.github` folder needs to be uploaded as `.github/workflows/scan.yml`. Drag-and-drop preserves folder structure if you select the parent folder. Verify after upload that `.github/workflows/scan.yml` exists in your repo.
4. Scroll down, commit message: `Initial linkmap setup`
5. Click **Commit changes**

**Verify:** Your repo should now show these files at the root:

```
.github/workflows/scan.yml
linkmap.py
regen_html.py
drupal_authors.py        ← present but unused in this setup
index.html
requirements.txt
README.md
DEPLOYMENT.md
.gitignore
```

### 3. Enable GitHub Pages

1. In your repo, click **Settings** (top menu)
2. Left sidebar: **Pages**
3. **Source:** Deploy from a branch
4. **Branch:** Select `main`
5. **Folder:** `/ (root)`
6. Click **Save**

You'll see a yellow banner: "Your site is ready to be published". A green
checkmark appears once the first deploy finishes (~30 sec). The site URL
will be:

```
https://YOUR-USERNAME.github.io/linkmap-3k/
```

Visit it now — you'll see the dispatcher dashboard with "No scan data
yet — first run pending."

### 4. Configure the workflow for your site (optional tweaks)

The default workflow scans `https://www.kolmekampusta.fi/fi`. If you want a
different starting URL, different page limit, or different skip patterns,
edit `.github/workflows/scan.yml` in the GitHub web UI:

1. Click the file `.github/workflows/scan.yml`
2. Click the pencil icon (edit)
3. Find the `Run linkmap scan` step and adjust as needed
4. Scroll down, commit changes

For the dispatcher to show the correct GitHub link, also edit `index.html`
and replace `USERNAME/REPO_NAME` in the footer with your actual values:

```html
<a href="https://github.com/YOUR-USERNAME/linkmap-3k">github.com</a>
```

### 5. Run the first scan

1. Go to the **Actions** tab in your repo
2. If you see a "Workflows aren't being run on this forked repository" or
   similar banner, click "I understand my workflows, enable them"
3. Click **Weekly link scan** in the left sidebar
4. Click **Run workflow** (dropdown on the right) → **Run workflow** (green button)
5. Refresh after a few seconds — you'll see a yellow-circle "in progress" run

The scan runs for 10–15 minutes. You can watch progress by clicking on the
run and then the `scan` job — it shows each step's output in real time.

**What you'll see during the run:**

```
[   1/1000] https://www.kolmekampusta.fi/fi
[   2/1000] https://www.kolmekampusta.fi/fi/koulutus
[   3/1000] https://www.kolmekampusta.fi/fi/urheilu
...
[ 247/1000] https://www.kolmekampusta.fi/fi/yritykset/tyohyvinvointi

Checking 142 external link target(s)…
  · [   1/142] https://www.olympiakomitea.fi/
  · [   2/142] https://www.linkedin.com/...
  ✗ [   3/142] https://old-partner.example/  → DNS resolution failed
  ...
```

When the green checkmark appears, the scan is done. Go to your dashboard
URL (`https://YOUR-USERNAME.github.io/linkmap-3k/`). Stats now populate.

If broken links were found, **a GitHub Issue is automatically created**
in your repo (Issues tab), and you'll get an email notification because
you watch the repo by default.

### 6. Verify the outputs

Three files appear at the repo root after the scan:

- **`3k-fi.json`** — raw graph data (5–20 MB depending on site size)
- **`3k-fi.html`** — interactive viewer ([direct link from dashboard])
- **`3k-fi-broken.md`** — broken-links report (Markdown)

Open the interactive viewer and try:

- The **Layout** dropdown — switch between Force-directed and Hierarchy
- The **Color** dropdown — switch to "URL section" to see site sections
  color-coded
- **Look up URL** field — paste any URL from your site to see what links
  to it

## Schedule and manual runs

The workflow runs automatically every **Monday at 06:00 UTC** (08:00
Helsinki summer time). You can change the schedule by editing the cron in
`.github/workflows/scan.yml`:

```yaml
on:
  schedule:
    - cron: '0 6 * * 1'   # Monday 06:00 UTC
```

You can always trigger a manual run from the Actions tab → Run workflow.

## What you'll get over time

Every scan commits the latest JSON, HTML, and broken-links report. Repo
history acts as a journal:

- "Scan 2026-05-10: 234 pages, 12 broken"
- "Scan 2026-05-17: 238 pages, 8 broken" ← progress!

You can diff a previous JSON with the current to see what changed (new
broken links, fixed ones, new pages added).

## Notifications

By default you get **email when the GitHub Issue is opened or updated**
(this is GitHub's standard "watching" behavior for your own repos).

The issue title is `🔴 N broken link(s) — DATE`. The body contains the
full Markdown report with linked-from listing.

When the next scan finds 0 broken links, the issue auto-closes with a
comment saying so.

## Common issues

**"The workflow doesn't run on schedule"**
GitHub disables scheduled workflows after 60 days of repo inactivity. Make
any commit (even just editing a file in the web UI) to re-enable.

**"GitHub Pages shows 404"**
After enabling Pages, first deploy can take 5–10 minutes. Check
Settings → Pages — green checkmark with URL means it's live.

**"The first scan committed nothing"**
Check the Actions log. If you see "Permission denied" on the push step,
go to Settings → Actions → General → Workflow permissions → select
**Read and write permissions** → Save.

**"GitHub Issue wasn't created"**
Same fix: workflow permissions need "Read and write" enabled (allows
creating issues).

**"Crawl is finding 0 pages or only 1"**
This was the `www.` vs no-`www.` issue (now fixed in linkmap.py 1.1+).
Verify the URL in the workflow has `www.` if your site canonicalizes
to that.

## Optional: enable Drupal author lookup later

When you're ready to attribute broken links to specific content editors:

1. Create a dedicated Drupal user (`linkmap-audit`) with permissions:
   - Use the JSON:API
   - Access user profiles
   - View any unpublished content (if needed)
2. Add repository secrets in **Settings → Secrets and variables → Actions**:
   - `DRUPAL_USER`
   - `DRUPAL_PASS`
3. Uncomment the "Enrich with Drupal author info" step in
   `.github/workflows/scan.yml` (remove the `#` prefixes from those lines)
4. Add a link to the by-author report back into `index.html`:
   ```html
   <a href="3k-fi-broken-by-author.md">👤 By author</a>
   ```
5. Commit and run the workflow again

The next scan will produce `3k-fi-broken-by-author.md` grouped by author,
and the GitHub Issue body will use that report instead of the generic
broken-links one.

## What it costs

- **GitHub Actions:** ~15 min/week × 4 weeks = 60 min/month, within free
  tier (2000 min/month for private, unlimited for public repos)
- **GitHub Pages:** 100 GB/month bandwidth, well within free tier
- **Total:** 0 €

## Privacy

The repo is **public**, meaning scan results (URL list, link graph,
broken-links report) are publicly visible on GitHub. For
`kolmekampusta.fi` this is fine since the site is public anyway. Don't
run this against staging or auth-protected sites in a public repo.
