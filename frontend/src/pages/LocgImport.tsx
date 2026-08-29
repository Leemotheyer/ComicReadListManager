import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  api,
  LocgMatchCandidate,
  LocgPreview,
  LocgPreviewItem,
} from "../api";
import { CoverThumb } from "../components/CoverThumb";
import { AddIssuesNav } from "../components/AddIssuesNav";

const STATUS_LABELS: Record<string, string> = {
  matched: "Matched",
  ambiguous: "Needs review",
  failed: "No match",
  manual: "Selected",
};

const SOURCE_LABELS: Record<LocgPreview["source_type"], string> = {
  community_list: "Community list",
  collected_edition: "Collected edition",
  single_issue: "Single issue",
};

function candidateLabel(candidate: LocgMatchCandidate) {
  const year = candidate.volume_year ? ` (${candidate.volume_year})` : "";
  return `${candidate.series}${year} #${candidate.issue_number}`;
}

function resolveItem(
  item: LocgPreviewItem,
  manualSelections: Map<number, LocgMatchCandidate>,
  existingIssueIds: Set<number>
): LocgPreviewItem & { resolved: boolean; importable: boolean } {
  const manual = manualSelections.get(item.index);
  if (manual) {
    const alreadyInList = existingIssueIds.has(manual.cv_issue_id);
    return {
      ...item,
      status: "manual",
      cv_volume_id: manual.cv_volume_id,
      cv_issue_id: manual.cv_issue_id,
      series: manual.series,
      issue_number: manual.issue_number,
      volume_year: manual.volume_year,
      cover_year: manual.cover_year,
      issue_title: manual.issue_title,
      publisher: manual.publisher,
      cover_image_url: manual.cover_image_url,
      message: candidateLabel(manual),
      already_in_list: alreadyInList,
      resolved: true,
      importable: !alreadyInList,
    };
  }

  const resolved = item.status === "matched" && !!item.cv_issue_id;
  return {
    ...item,
    resolved,
    importable: resolved && !item.already_in_list,
  };
}

function CandidatePicker({
  item,
  selection,
  onSelect,
  onClear,
}: {
  item: LocgPreviewItem;
  selection: LocgMatchCandidate | undefined;
  onSelect: (candidate: LocgMatchCandidate) => void;
  onClear: () => void;
}) {
  const [issueIdInput, setIssueIdInput] = useState("");
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [lookingUp, setLookingUp] = useState(false);

  const lookupIssue = async () => {
    setLookupError(null);
    setLookingUp(true);
    try {
      const issue = await api.getIssue(issueIdInput.trim());
      onSelect({
        cv_volume_id: issue.volume_id,
        cv_issue_id: issue.id,
        series: issue.volume_name || item.series,
        issue_number: issue.issue_number,
        volume_year: issue.volume_start_year,
        cover_year: issue.cover_date ? parseInt(issue.cover_date.slice(0, 4), 10) : null,
        issue_title: issue.name,
        publisher: issue.publisher,
        cover_image_url: issue.image_url,
      });
      setIssueIdInput("");
    } catch (err) {
      setLookupError((err as Error).message);
    } finally {
      setLookingUp(false);
    }
  };

  return (
    <div className="komga-match-panel">
      {selection ? (
        <div className="komga-match-selected">
          <span>{candidateLabel(selection)}</span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClear}>
            Clear
          </button>
        </div>
      ) : (
        <>
          {item.candidates.length > 0 && (
            <div className="komga-match-options">
              {item.candidates.map((candidate) => (
                <button
                  key={candidate.cv_issue_id}
                  type="button"
                  className="komga-book-option"
                  onClick={() => onSelect(candidate)}
                >
                  {candidateLabel(candidate)}
                  {candidate.issue_title && (
                    <span className="muted"> — {candidate.issue_title}</span>
                  )}
                </button>
              ))}
            </div>
          )}
          <div className="komga-match-search-form" style={{ marginTop: "0.5rem" }}>
            <input
              placeholder="ComicVine issue ID (4000-12345)"
              value={issueIdInput}
              onChange={(e) => setIssueIdInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && lookupIssue()}
            />
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={lookingUp || !issueIdInput.trim()}
              onClick={lookupIssue}
            >
              {lookingUp ? "Looking up..." : "Use ID"}
            </button>
          </div>
          {lookupError && <p className="error">{lookupError}</p>}
        </>
      )}
    </div>
  );
}

export default function LocgImport() {
  const { id } = useParams<{ id: string }>();
  const listId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [url, setUrl] = useState("");
  const [preview, setPreview] = useState<LocgPreview | null>(null);
  const [manualSelections, setManualSelections] = useState<
    Map<number, LocgMatchCandidate>
  >(new Map());
  const [includeNotes, setIncludeNotes] = useState(true);
  const [updateListMeta, setUpdateListMeta] = useState(false);
  const [showOnlyUnresolved, setShowOnlyUnresolved] = useState(false);

  const { data: list } = useQuery({
    queryKey: ["list", listId],
    queryFn: () => api.getList(listId),
    enabled: !isNaN(listId),
  });

  const existingIssueIds = useMemo(
    () => new Set(list?.items.map((item) => item.cv_issue_id) ?? []),
    [list]
  );

  const previewMutation = useMutation({
    mutationFn: () => api.locgPreview(listId, url.trim()),
    onSuccess: (data) => {
      setPreview(data);
      setManualSelections(new Map());
      setUpdateListMeta(false);
      setIncludeNotes(data.source_type === "community_list");
    },
  });

  const importMutation = useMutation({
    mutationFn: () => {
      if (!preview) throw new Error("No preview loaded");
      const items = preview.items
        .map((item) => resolveItem(item, manualSelections, existingIssueIds))
        .filter((item) => item.importable && item.cv_issue_id && item.cv_volume_id)
        .map((item) => ({
          index: item.index,
          cv_volume_id: item.cv_volume_id!,
          cv_issue_id: item.cv_issue_id!,
          series: item.series,
          issue_number: item.issue_number,
          volume_year: item.volume_year,
          cover_year: item.cover_year,
          issue_title: item.issue_title,
          publisher: item.publisher,
          cover_image_url: item.cover_image_url,
          notes: item.notes,
        }));

      return api.locgImport(listId, {
        items,
        include_notes: includeNotes,
        update_list_meta:
          preview.source_type === "community_list" && updateListMeta,
        list_name: updateListMeta ? preview.list_name : undefined,
        list_description: updateListMeta ? preview.list_description : undefined,
      });
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["list", listId] });
      navigate(`/lists/${listId}`, {
        state: {
          importMessage: `Added ${result.added_count} issue(s) to the list${
            result.skipped_count ? ` (${result.skipped_count} already present)` : ""
          }.`,
        },
      });
    },
  });

  const resolvedItems = useMemo(() => {
    if (!preview) return [];
    return preview.items.map((item) =>
      resolveItem(item, manualSelections, existingIssueIds)
    );
  }, [preview, manualSelections, existingIssueIds]);

  const stats = useMemo(() => {
    const importable = resolvedItems.filter((item) => item.importable).length;
    const unresolved = resolvedItems.filter((item) => !item.resolved).length;
    const duplicates = resolvedItems.filter(
      (item) => item.resolved && item.already_in_list
    ).length;
    return { importable, unresolved, duplicates, total: resolvedItems.length };
  }, [resolvedItems]);

  const visibleItems = useMemo(() => {
    if (!showOnlyUnresolved) return resolvedItems;
    return resolvedItems.filter((item) => !item.resolved);
  }, [resolvedItems, showOnlyUnresolved]);

  const existingCount = preview?.existing_item_count ?? list?.items.length ?? 0;

  return (
    <div className="page">
      <p className="page-back">
        <Link to={`/lists/${listId}`}>← Back to list</Link>
      </p>

      <div className="card add-issues-header">
        <h2>Add issues{list ? ` — ${list.name}` : ""}</h2>
        <AddIssuesNav mode="locg" />
        <p className="muted add-issues-header-desc">
          Paste a LoCG community list or comic URL. Matched issues are appended
          to this list — existing items are kept.
          {existingCount > 0 && (
            <>
              {" "}
              This list currently has {existingCount} issue
              {existingCount !== 1 ? "s" : ""}.
            </>
          )}
        </p>
      </div>

      <div className="card">
        <h2>LoCG URL</h2>
        <div className="form-row">
          <input
            placeholder="Community list or comic URL..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && url.trim() && previewMutation.mutate()}
          />
          <button
            className="btn"
            disabled={!url.trim() || previewMutation.isPending}
            onClick={() => previewMutation.mutate()}
          >
            {previewMutation.isPending ? "Loading..." : "Preview import"}
          </button>
        </div>
        <p className="muted locg-url-hints">
          Community list:{" "}
          <code>leagueofcomicgeeks.com/profile/user/lists/12345/...</code>
          <br />
          Collected edition or single issue:{" "}
          <code>leagueofcomicgeeks.com/comic/4413027/invincible-vol-1-new-edition-tp</code>
        </p>
        {previewMutation.error && (
          <p className="error">{(previewMutation.error as Error).message}</p>
        )}
      </div>

      {preview && (
        <>
          <div className="card">
            <div className="locg-preview-header">
              <h2>{preview.list_name}</h2>
              <span className="tag-pill">{SOURCE_LABELS[preview.source_type]}</span>
            </div>
            {preview.list_description && (
              <p className="muted">{preview.list_description}</p>
            )}
            <div className="status-badges">
              <span>{preview.item_count} issues from LoCG</span>
              <span className="status-matched">{preview.matched_count} matched</span>
              <span className="status-unmatched">
                {preview.ambiguous_count} need review
              </span>
              <span className="status-issue_not_found">
                {preview.failed_count} unmatched
              </span>
              {stats.duplicates > 0 && (
                <span className="status-manual">
                  {stats.duplicates} already on this list
                </span>
              )}
              <span>{stats.importable} will be added</span>
            </div>

            {preview.source_type === "community_list" && (
              <>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={includeNotes}
                    onChange={(e) => setIncludeNotes(e.target.checked)}
                  />
                  Import LoCG list annotations as issue notes
                </label>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={updateListMeta}
                    onChange={(e) => setUpdateListMeta(e.target.checked)}
                  />
                  Update this list&apos;s name and description from LoCG
                </label>
              </>
            )}

            <div className="row-actions">
              <button
                className="btn"
                disabled={stats.importable === 0 || importMutation.isPending}
                onClick={() => importMutation.mutate()}
              >
                {importMutation.isPending
                  ? "Adding..."
                  : `Add ${stats.importable} issue${stats.importable !== 1 ? "s" : ""} to list`}
              </button>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={showOnlyUnresolved}
                  onChange={(e) => setShowOnlyUnresolved(e.target.checked)}
                />
                Show only unresolved
              </label>
            </div>
            {importMutation.error && (
              <p className="error">{(importMutation.error as Error).message}</p>
            )}
          </div>

          <div className="card table-scroll">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>LoCG issue</th>
                  <th>Status</th>
                  <th>ComicVine match</th>
                </tr>
              </thead>
              <tbody>
                {visibleItems.map((item) => {
                  const needsManual =
                    !item.resolved &&
                    (item.status === "ambiguous" || item.status === "failed");
                  const statusLabel = item.already_in_list
                    ? "Already on list"
                    : STATUS_LABELS[item.status] ?? item.status;
                  const statusClass = item.already_in_list
                    ? "status-manual"
                    : `status-${item.status}`;

                  return (
                    <tr key={item.index}>
                      <td>{item.index + 1}</td>
                      <td>
                        <div className="locg-source-cell">
                          <strong>{item.title}</strong>
                          {item.publisher && (
                            <div className="muted">{item.publisher}</div>
                          )}
                          {item.store_date && (
                            <div className="muted">{item.store_date}</div>
                          )}
                          {item.notes && (
                            <div className="muted locg-note-preview">{item.notes}</div>
                          )}
                        </div>
                      </td>
                      <td className={statusClass}>{statusLabel}</td>
                      <td>
                        {item.resolved && item.cover_image_url && (
                          <CoverThumb
                            src={item.cover_image_url}
                            alt={item.title}
                            size="sm"
                          />
                        )}
                        {item.message && <div className="muted">{item.message}</div>}
                        {needsManual && (
                          <CandidatePicker
                            item={item}
                            selection={manualSelections.get(item.index)}
                            onSelect={(candidate) =>
                              setManualSelections((prev) => {
                                const next = new Map(prev);
                                next.set(item.index, candidate);
                                return next;
                              })
                            }
                            onClear={() =>
                              setManualSelections((prev) => {
                                const next = new Map(prev);
                                next.delete(item.index);
                                return next;
                              })
                            }
                          />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
