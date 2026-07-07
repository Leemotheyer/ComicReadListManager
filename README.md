# Comic Read List Manager

A self-hosted web app for building comic reading lists from ComicVine or League of Comic Geeks (LoCG), exporting them as ComicRack `.cbl` files or pushing directly to Komga, and syncing missing issues to Kapowarr with a review step before anything runs.

## Features

- Search ComicVine volumes and add issues to ordered read lists
- Import issues from LoCG community lists and collected-edition pages (matched to ComicVine)
- Add issues by ComicVine ID (`4000-12345`)
- Tags, per-issue notes, collection gap detection, and list copy
- Export lists as Komga-compatible `.cbl` files (with ComicVine ID metadata)
- Push read lists directly to Komga via the API (with manual matching for edge cases)
- Preview Kapowarr sync status per list or across all lists on the **Missing** page
- Background Kapowarr sync jobs with live queue and download history
- Backup and restore lists, items, tags, notes, and settings as JSON
- Docker deployment with persistent SQLite database and export storage

## Quick start (Docker)

1. Copy the environment file and add your API keys:

```bash
cp .env.example .env
```

Edit `.env`:

```env
COMICVINE_API_KEY=your_comicvine_key
KAPOWARR_URL=http://host.docker.internal:5656
KAPOWARR_API_KEY=your_kapowarr_api_key
KAPOWARR_ROOT_FOLDER_ID=1
KOMGA_URL=http://host.docker.internal:25600
KOMGA_API_KEY=your_komga_api_key
```

2. Start the stack:

```bash
docker compose up -d --build
```

3. Open the app at [http://localhost:8080](http://localhost:8080)

The UI and API run in a single container on port 8080.

### Kapowarr or Komga on the same Docker host

If Kapowarr or Komga runs in Docker, put the app on the same network and set:

```env
KAPOWARR_URL=http://kapowarr:5656
KOMGA_URL=http://komga:25600
```

Add to `docker-compose.yml` under the `app` service:

```yaml
networks:
  - your-media-network
```

## Local development

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
set COMICVINE_API_KEY=your_key
set DATA_DIR=..\data
mkdir ..\data
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://localhost:8000`.

## Settings

Open **Settings** in the app header to configure:

- ComicVine API key
- Kapowarr URL, API key, and root folder ID
- Komga URL and API key

Settings are stored in the app database. API keys are never shown again after saving — leave a key field blank to keep the current value.

Environment variables (`.env` or `docker-compose`) seed the initial values on first run. After that, changes made in the UI take precedence.

### Backup & restore

From **Settings**, export all lists, items, tags, notes, and settings as a single JSON file. Import a backup to merge with existing data or replace everything.

## ComicVine API key

1. Create an account at [comicvine.gamespot.com](https://comicvine.gamespot.com/)
2. Visit [comicvine.gamespot.com/api](https://comicvine.gamespot.com/api/) while logged in
3. Enter your API key in **Settings** (or set `COMICVINE_API_KEY` in `.env` before first run)

ComicVine limits requests to roughly 200 per hour per endpoint. The app caches responses and spaces requests at least 1 second apart.

## Building a read list

1. **Create a list** on the home page
2. **Add issues** via:
   - ComicVine volume search (issue checkboxes, range selection, or direct issue ID)
   - LoCG import (community list or collected-edition URL)
3. **Edit metadata** — set tags, description, and per-issue notes in the list editor
4. **Reorder** issues by dragging rows
5. **Check gaps** — the editor shows missing issue numbers within each volume
6. **Copy list** — duplicate a list with all its items
7. **Export CBL** — downloads a `.cbl` file and saves a copy under `/data/exports/` in the container

## LoCG import

1. Open a list → **Add issues** → **LoCG import**
2. Paste a League of Comic Geeks URL:
   - Community list: `leagueofcomicgeeks.com/profile/user/lists/12345/...`
   - Collected edition: `leagueofcomicgeeks.com/comic/4413027/...`
3. Preview matches — resolve ambiguous items by picking a candidate or entering a ComicVine issue ID
4. Import — matched issues are appended; duplicates are skipped

For community lists you can optionally copy the LoCG list name and description into your read list.

## Importing into Komga

### Option A: CBL export (manual upload)

1. In the list editor, click **Export CBL**
2. In Komga, go to **Import → Read List**
3. Upload the exported `.cbl` file
4. Match books to your library and create the read list

Komga matches on **series name**, **volume (start year)**, and **issue number**. ComicVine IDs in the CBL are ignored by Komga but kept for your reference.

**Tip:** If your library uses “Append volume to series title”, Komga will try both `Series (1963)` and bare `Series` when matching. Align Kapowarr/Komga naming with ComicVine volume names for best results.

### Option B: Direct API push

1. Configure `KOMGA_URL` and `KOMGA_API_KEY` in **Settings**
2. Open a list → **Push to Komga**
3. Review the preview — issues are grouped by volume and auto-matched to Komga books
4. Manually match any unmatched issues (search Komga series, pick books, or bulk-match a volume)
5. Click **Push to Komga**

The push creates or updates a read list in Komga. List description, tags, and issue notes are included in the Komga summary. Enable **Allow partial push** to create the list even when some issues are unmatched.

### Komga API key

Create an API key in Komga under **Settings → Users → your user → API keys**. The user must have admin role to create read lists.

## Kapowarr sync

Kapowarr sync runs as a background job. After starting a sync from a list or the **Missing** page, track progress under **Missing → Queue**.

### Per-list sync

1. Configure `KAPOWARR_URL`, `KAPOWARR_API_KEY`, and `KAPOWARR_ROOT_FOLDER_ID`
2. Ensure at least one **root folder** exists in Kapowarr (Settings → Root Folders)
3. Open a list → **Kapowarr sync**
4. Review the preview:
   - **Volume not in Kapowarr** — select volumes to add
   - **Missing file** — select issues to queue for download
   - **In library** — already downloaded
5. Click **Approve & run sync** — you are redirected to the Missing page queue

### Missing issues (all lists)

The **Missing** page aggregates every issue across all read lists and shows Kapowarr status:

- **Missing** tab — preview and sync volumes/issues that need action
- **Queue** tab — live Kapowarr download queue and running sync jobs
- **History** tab — download history, Kapowarr task log, and recent sync runs

Kapowarr searches GetComics for downloads; a missing file may remain if no match is found. Downloads are not guaranteed.

### Kapowarr API key

Find it in Kapowarr under **Settings → General → API Key**.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health and config status |
| GET/PUT | `/api/settings` | View/update app settings |
| GET/POST | `/api/lists` | List CRUD |
| GET/PATCH/DELETE | `/api/lists/{id}` | Single list |
| POST | `/api/lists/{id}/copy` | Duplicate a list |
| POST | `/api/lists/{id}/items` | Add issues |
| PATCH | `/api/lists/{id}/items/reorder` | Reorder |
| PATCH | `/api/lists/{id}/items/{item_id}` | Update item notes |
| DELETE | `/api/lists/{id}/items/{item_id}` | Remove issue |
| GET | `/api/lists/{id}/gaps` | Collection gap detection |
| GET | `/api/comicvine/volumes/search?q=` | Search volumes |
| GET | `/api/comicvine/volumes/{id}/issues` | List issues |
| GET | `/api/comicvine/issues/{id}` | Lookup issue by CV ID |
| POST | `/api/lists/{id}/locg/preview` | Preview LoCG import |
| POST | `/api/lists/{id}/locg/import` | Import matched LoCG issues |
| GET | `/api/lists/{id}/export.cbl` | Download CBL |
| POST | `/api/lists/{id}/kapowarr/preview` | Preview Kapowarr sync |
| POST | `/api/lists/{id}/kapowarr/sync` | Start Kapowarr sync job |
| POST | `/api/lists/{id}/komga/preview` | Preview Komga push |
| POST | `/api/lists/{id}/komga/push` | Push read list to Komga |
| GET | `/api/komga/series/search?q=` | Search Komga series |
| GET | `/api/komga/series/{id}/books` | List books in a series |
| POST | `/api/komga/series/{id}/match-issues` | Bulk-match issues to books |
| GET | `/api/missing/preview` | Missing issues across all lists |
| GET | `/api/missing/activity` | Kapowarr queue and history |
| POST | `/api/missing/sync` | Start global Kapowarr sync job |
| GET | `/api/missing/sync/jobs/{job_id}` | Sync job status |
| GET | `/api/backup/export` | Download JSON backup |
| POST | `/api/backup/import` | Restore from JSON backup |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| ComicVine “Not configured” badge | Set `COMICVINE_API_KEY` and restart the backend |
| ComicVine rate limit errors | Wait an hour; cached volume/issue data reduces repeat calls |
| Kapowarr “Not configured” | Set `KAPOWARR_URL` and `KAPOWARR_API_KEY` |
| Komga “Not configured” | Set `KOMGA_URL` and `KOMGA_API_KEY` |
| Volume add fails | Verify `KAPOWARR_ROOT_FOLDER_ID` matches an existing root folder |
| Issue not found in Kapowarr metadata | Refresh the volume in Kapowarr, then re-run preview |
| LoCG import shows “No match” | Pick a candidate manually or enter the ComicVine issue ID |
| Komga won’t match books | Use manual matching on the push page; check series title and start year |
| Komga push fails with 403 | Ensure the API key user has admin role |
| Downloads don’t start | Confirm issue is monitored and GetComics has a match; check Kapowarr queue on **Missing → Queue** |

## Data persistence

Docker volume `app-data` stores:

- SQLite database: `/data/app.db`
- Exported CBL files: `/data/exports/`

## License

MIT
