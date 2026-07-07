import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, BackupImportResult } from "../api";

export default function Settings() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
  });

  const [kapowarrUrl, setKapowarrUrl] = useState("");
  const [kapowarrRootFolderId, setKapowarrRootFolderId] = useState("1");
  const [comicvineApiKey, setComicvineApiKey] = useState("");
  const [kapowarrApiKey, setKapowarrApiKey] = useState("");
  const [komgaUrl, setKomgaUrl] = useState("");
  const [komgaApiKey, setKomgaApiKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [importResult, setImportResult] = useState<BackupImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (data) {
      setKapowarrUrl(data.kapowarr_url);
      setKapowarrRootFolderId(String(data.kapowarr_root_folder_id));
      setKomgaUrl(data.komga_url);
    }
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateSettings({
        kapowarr_url: kapowarrUrl.trim(),
        kapowarr_root_folder_id: parseInt(kapowarrRootFolderId, 10) || 1,
        komga_url: komgaUrl.trim(),
        comicvine_api_key: comicvineApiKey.trim() || undefined,
        kapowarr_api_key: kapowarrApiKey.trim() || undefined,
        komga_api_key: komgaApiKey.trim() || undefined,
      }),
    onSuccess: () => {
      setComicvineApiKey("");
      setKapowarrApiKey("");
      setKomgaApiKey("");
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["health"] });
      setTimeout(() => setSaved(false), 3000);
    },
  });

  const importMutation = useMutation({
    mutationFn: ({ data, replace }: { data: object; replace: boolean }) =>
      api.backupImport(data, replace),
    onSuccess: (result) => {
      setImportResult(result);
      setImportError(null);
      queryClient.invalidateQueries({ queryKey: ["lists"] });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => {
      setImportError((err as Error).message);
      setImportResult(null);
    },
  });

  const handleImportFile = async (file: File, replace: boolean) => {
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      importMutation.mutate({ data, replace });
    } catch {
      setImportError("Invalid backup file — expected JSON.");
    }
  };

  if (isLoading) return <p className="muted">Loading settings...</p>;
  if (error) return <p className="error">{(error as Error).message}</p>;
  if (!data) return null;

  return (
    <div>
      <p className="page-back">
        <Link to="/">← Back to lists</Link>
      </p>

      <div className="card">
        <h2>Settings</h2>
        <p className="muted">
          Configure API keys and service URLs. Keys are stored in the app database and
          are not shown again after saving. Leave key fields blank to keep existing
          values.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            saveMutation.mutate();
          }}
        >
          <div className="settings-section">
            <h3>ComicVine</h3>
            <label className="settings-label">
              API key
              {data.comicvine_api_key_set && (
                <span className="muted"> (currently set)</span>
              )}
              <input
                type="password"
                placeholder={
                  data.comicvine_api_key_set
                    ? "Leave blank to keep current key"
                    : "Enter ComicVine API key"
                }
                value={comicvineApiKey}
                onChange={(e) => setComicvineApiKey(e.target.value)}
                autoComplete="off"
              />
            </label>
            <p className="muted">
              Get a key at{" "}
              <a
                href="https://comicvine.gamespot.com/api/"
                target="_blank"
                rel="noreferrer"
              >
                comicvine.gamespot.com/api
              </a>
            </p>
          </div>

          <div className="settings-section">
            <h3>Kapowarr</h3>
            <label className="settings-label">
              URL
              <input
                type="url"
                placeholder="http://kapowarr:5656"
                value={kapowarrUrl}
                onChange={(e) => setKapowarrUrl(e.target.value)}
              />
            </label>
            <label className="settings-label">
              API key
              {data.kapowarr_api_key_set && (
                <span className="muted"> (currently set)</span>
              )}
              <input
                type="password"
                placeholder={
                  data.kapowarr_api_key_set
                    ? "Leave blank to keep current key"
                    : "Enter Kapowarr API key"
                }
                value={kapowarrApiKey}
                onChange={(e) => setKapowarrApiKey(e.target.value)}
                autoComplete="off"
              />
            </label>
            <label className="settings-label">
              Root folder ID
              <input
                type="number"
                min={1}
                value={kapowarrRootFolderId}
                onChange={(e) => setKapowarrRootFolderId(e.target.value)}
              />
            </label>
            <p className="muted">
              Find the API key in Kapowarr under Settings → General. Root folder ID
              must match an existing folder in Kapowarr.
            </p>
          </div>

          <div className="settings-section">
            <h3>Komga</h3>
            <label className="settings-label">
              URL
              <input
                type="url"
                placeholder="http://komga:25600"
                value={komgaUrl}
                onChange={(e) => setKomgaUrl(e.target.value)}
              />
            </label>
            <label className="settings-label">
              API key
              {data.komga_api_key_set && (
                <span className="muted"> (currently set)</span>
              )}
              <input
                type="password"
                placeholder={
                  data.komga_api_key_set
                    ? "Leave blank to keep current key"
                    : "Enter Komga API key"
                }
                value={komgaApiKey}
                onChange={(e) => setKomgaApiKey(e.target.value)}
                autoComplete="off"
              />
            </label>
            <p className="muted">
              Create an API key in Komga under Settings → Users → your user → API keys.
              The user must have admin role to create read lists.
            </p>
          </div>

          <div className="row-actions">
            <button className="btn" type="submit" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? "Saving..." : "Save settings"}
            </button>
            {saved && <span className="status-in_library">Saved</span>}
          </div>
          {saveMutation.error && (
            <p className="error">{(saveMutation.error as Error).message}</p>
          )}
        </form>
      </div>

      <div className="card">
        <h2>Backup & restore</h2>
        <p className="muted">
          Export all lists, items, tags, notes, and settings as a single JSON file.
        </p>
        <div className="row-actions">
          <a className="btn btn-secondary" href={api.backupExportUrl()} download>
            Export backup
          </a>
          <button
            className="btn btn-secondary"
            disabled={importMutation.isPending}
            onClick={() => fileInputRef.current?.click()}
          >
            {importMutation.isPending ? "Importing..." : "Import backup"}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              const replace = confirm(
                "Replace all existing lists and settings with this backup?\n\nOK = replace everything\nCancel = merge (keep existing, add imported)"
              );
              handleImportFile(file, replace);
              e.target.value = "";
            }}
          />
        </div>
        {importResult && (
          <p className="status-in_library" style={{ marginTop: "0.75rem" }}>
            Imported {importResult.lists_imported} list
            {importResult.lists_imported !== 1 ? "s" : ""} and{" "}
            {importResult.items_imported} item
            {importResult.items_imported !== 1 ? "s" : ""}.
          </p>
        )}
        {importError && <p className="error">{importError}</p>}
      </div>
    </div>
  );
}
