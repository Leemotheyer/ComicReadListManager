import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, AddItemsResult, IssueResult, ReadListItem, VolumeSearchResult } from "../api";
import { AddIssuesNav } from "../components/AddIssuesNav";
import { CoverThumb } from "../components/CoverThumb";

function coverYear(coverDate: string | null): number | null {
  if (!coverDate || coverDate.length < 4) return null;
  const y = parseInt(coverDate.slice(0, 4), 10);
  return isNaN(y) ? null : y;
}

function issueToItem(issue: IssueResult) {
  return {
    cv_volume_id: issue.volume_id,
    cv_issue_id: issue.id,
    series: issue.volume_name || "Unknown",
    issue_number: issue.issue_number,
    volume_year: issue.volume_start_year,
    cover_year: coverYear(issue.cover_date),
    issue_title: issue.name,
    publisher: issue.publisher,
    cover_image_url: issue.image_url,
    notes: null,
  };
}

export default function AddIssues() {
  const { id } = useParams<{ id: string }>();
  const listId = Number(id);
  const queryClient = useQueryClient();
  const volumePanelRef = useRef<HTMLDivElement>(null);

  const [query, setQuery] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedVolume, setSelectedVolume] = useState<VolumeSearchResult | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [issueIdInput, setIssueIdInput] = useState("");
  const [offset, setOffset] = useState(0);
  const [allIssues, setAllIssues] = useState<IssueResult[]>([]);
  const [addResult, setAddResult] = useState<AddItemsResult | null>(null);
  const [loadingAll, setLoadingAll] = useState(false);

  const { data: list } = useQuery({
    queryKey: ["list", listId],
    queryFn: () => api.getList(listId),
    enabled: !isNaN(listId),
  });

  const existingIssueIds = useMemo(
    () => new Set(list?.items.map((i) => i.cv_issue_id) ?? []),
    [list]
  );

  const { data: searchResults, isFetching: searching } = useQuery({
    queryKey: ["volumeSearch", searchTerm],
    queryFn: () => api.searchVolumes(searchTerm),
    enabled: searchTerm.length > 0,
  });

  const { data: issuesPage, isFetching: loadingIssues } = useQuery({
    queryKey: ["volumeIssues", selectedVolume?.id, offset],
    queryFn: async () => {
      const page = await api.getVolumeIssues(selectedVolume!.id, offset);
      if (offset === 0) {
        setAllIssues(page.issues);
      } else {
        setAllIssues((prev) => [...prev, ...page.issues]);
      }
      return page;
    },
    enabled: !!selectedVolume,
  });

  const handleAddSuccess = (result: AddItemsResult) => {
    setAddResult(result);
    setSelected(new Set());
    queryClient.invalidateQueries({ queryKey: ["list", listId] });
    queryClient.invalidateQueries({ queryKey: ["lists"] });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const addMutation = useMutation({
    mutationFn: (issues: IssueResult[]) =>
      api.addItems(listId, issues.map(issueToItem)),
    onSuccess: handleAddSuccess,
  });

  const addByIdMutation = useMutation({
    mutationFn: async (rawId: string) => {
      const issue = await api.getIssue(rawId);
      return api.addItems(listId, [issueToItem(issue)]);
    },
    onSuccess: (result) => {
      setIssueIdInput("");
      handleAddSuccess(result);
    },
  });

  useEffect(() => {
    if (selectedVolume && volumePanelRef.current) {
      volumePanelRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [selectedVolume?.id]);

  const toggle = (issueId: number) => {
    if (existingIssueIds.has(issueId)) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(issueId)) next.delete(issueId);
      else next.add(issueId);
      return next;
    });
  };

  const selectAll = () =>
    setSelected(
      new Set(allIssues.filter((i) => !existingIssueIds.has(i.id)).map((i) => i.id))
    );

  const selectRange = () => {
    const start = parseFloat(rangeStart);
    const end = parseFloat(rangeEnd);
    if (isNaN(start) || isNaN(end)) return;
    const ids = allIssues
      .filter((i) => {
        if (existingIssueIds.has(i.id)) return false;
        const n = parseFloat(i.issue_number);
        return !isNaN(n) && n >= start && n <= end;
      })
      .map((i) => i.id);
    setSelected(new Set(ids));
  };

  const loadAllIssues = async () => {
    if (!selectedVolume || !issuesPage) return;
    let offset = allIssues.length;
    let combined = [...allIssues];
    while (issuesPage.has_more || offset < (issuesPage.total ?? 0)) {
      const page = await api.getVolumeIssues(selectedVolume.id, offset);
      combined = [...combined, ...page.issues];
      offset += page.issues.length;
      if (!page.has_more) break;
    }
    setAllIssues(combined);
    setOffset(offset);
  };

  const addAllInVolume = async () => {
    if (!selectedVolume) return;
    let issues = allIssues;
    if (issuesPage?.has_more) {
      let offset = allIssues.length;
      let combined = [...allIssues];
      let hasMore: boolean = true;
      while (hasMore) {
        const page = await api.getVolumeIssues(selectedVolume.id, offset);
        combined = [...combined, ...page.issues];
        offset += page.issues.length;
        hasMore = page.has_more;
      }
      setAllIssues(combined);
      setOffset(offset);
      issues = combined;
    }
    const toAdd = issues.filter((i) => !existingIssueIds.has(i.id));
    if (toAdd.length === 0) {
      setAddResult({
        read_list: list ?? {
          id: listId,
          name: "",
          description: null,
          tags: [],
          created_at: "",
          updated_at: "",
          last_exported_at: null,
          item_count: 0,
          items: [],
        },
        added_count: 0,
        skipped_count: issues.length,
        added_items: [],
      });
      return;
    }
    addMutation.mutate(toAdd);
  };

  const applyRangePreset = (start: number, end: number) => {
    setRangeStart(String(start));
    setRangeEnd(String(end));
    const ids = allIssues
      .filter((i) => {
        if (existingIssueIds.has(i.id)) return false;
        const n = parseFloat(i.issue_number);
        return !isNaN(n) && n >= start && n <= end;
      })
      .map((i) => i.id);
    setSelected(new Set(ids));
  };

  const selectedIssues = useMemo(
    () => allIssues.filter((i) => selected.has(i.id)),
    [allIssues, selected]
  );

  const openVolume = (vol: VolumeSearchResult) => {
    setSelectedVolume(vol);
    setOffset(0);
    setAllIssues([]);
    setSelected(new Set());
    setAddResult(null);
  };

  const loadingAllIssues = loadingIssues && offset === 0;

  return (
    <div>
      <p className="page-back">
        <Link to={`/lists/${listId}`}>← Back to list</Link>
      </p>

      <div className="card add-issues-header">
        <h2>Add issues{list ? ` — ${list.name}` : ""}</h2>
        <AddIssuesNav mode="comicvine" />
      </div>

      {addResult && (
        <div
          className={`toast-banner ${addResult.added_count > 0 ? "toast-success" : "toast-info"}`}
        >
          {addResult.added_count > 0 ? (
            <>
              <strong>
                Added {addResult.added_count} issue{addResult.added_count !== 1 ? "s" : ""} to
                the list
              </strong>
              {addResult.skipped_count > 0 && (
                <span className="muted">
                  {" "}
                  ({addResult.skipped_count} already in list)
                </span>
              )}
              <div className="toast-covers">
                {addResult.added_items.map((item: ReadListItem) => (
                  <div key={item.cv_issue_id} className="toast-cover-item">
                    <CoverThumb
                      src={item.cover_image_url}
                      alt={`${item.series} #${item.issue_number}`}
                      size="md"
                    />
                    <span>#{item.issue_number}</span>
                  </div>
                ))}
              </div>
              <Link className="btn" to={`/lists/${listId}`} style={{ marginTop: "0.75rem" }}>
                View list
              </Link>
            </>
          ) : (
            <strong>All selected issues are already in the list.</strong>
          )}
          <button
            className="toast-dismiss"
            onClick={() => setAddResult(null)}
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      )}

      <div className="card">
        <h2>Add by ComicVine issue ID</h2>
        <div className="form-row">
          <input
            placeholder="4000-12345 or 12345"
            value={issueIdInput}
            onChange={(e) => setIssueIdInput(e.target.value)}
          />
          <button
            className="btn"
            disabled={!issueIdInput.trim() || addByIdMutation.isPending || addMutation.isPending}
            onClick={() => addByIdMutation.mutate(issueIdInput.trim())}
          >
            {addByIdMutation.isPending ? "Adding..." : "Add issue"}
          </button>
        </div>
        {addByIdMutation.error && (
          <p className="error">{(addByIdMutation.error as Error).message}</p>
        )}
      </div>

      {selectedVolume && (
        <div className="card volume-panel" ref={volumePanelRef}>
          <h2>
            {selectedVolume.name}
            {selectedVolume.start_year ? ` (${selectedVolume.start_year})` : ""} — select issues
          </h2>
          <div className="volume-panel-header">
            {selectedVolume.image_url && (
              <CoverThumb
                src={selectedVolume.image_url}
                alt={selectedVolume.name}
                size="lg"
              />
            )}
            <div style={{ flex: 1 }}>
              <p className="muted">
                {selectedVolume.publisher ?? "Unknown publisher"} ·{" "}
                {selectedVolume.count_of_issues ?? "?"} issues
              </p>
            </div>
            <button
              className="btn btn-secondary"
              onClick={() => setSelectedVolume(null)}
            >
              Close
            </button>
          </div>

          <div className="bulk-add-panel">
            <h3>Bulk add</h3>
            <div className="row-actions">
              <button
                className="btn"
                disabled={addMutation.isPending || loadingAll}
                onClick={async () => {
                  setLoadingAll(true);
                  try {
                    await addAllInVolume();
                  } finally {
                    setLoadingAll(false);
                  }
                }}
              >
                {loadingAll || addMutation.isPending
                  ? "Adding..."
                  : "Add all issues in volume"}
              </button>
              {issuesPage?.has_more && (
                <button
                  className="btn btn-secondary"
                  disabled={loadingAll}
                  onClick={async () => {
                    setLoadingAll(true);
                    try {
                      await loadAllIssues();
                    } finally {
                      setLoadingAll(false);
                    }
                  }}
                >
                  {loadingAll ? "Loading..." : `Load all (${issuesPage.total})`}
                </button>
              )}
            </div>
            <div className="range-presets">
              <span className="muted">Quick range:</span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => applyRangePreset(1, 12)}
              >
                1–12
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => applyRangePreset(1, 50)}
              >
                1–50
              </button>
            </div>
          </div>

          <div className="issue-picker-toolbar">
            <button className="btn btn-secondary" onClick={selectAll}>
              Select all loaded
            </button>
            <div className="range-inputs">
              <span className="muted">Range:</span>
              <input
                placeholder="From"
                value={rangeStart}
                onChange={(e) => setRangeStart(e.target.value)}
              />
              <span>–</span>
              <input
                placeholder="To"
                value={rangeEnd}
                onChange={(e) => setRangeEnd(e.target.value)}
              />
              <button className="btn btn-secondary" onClick={selectRange}>
                Select range
              </button>
            </div>
            <button
              className="btn"
              disabled={selectedIssues.length === 0 || addMutation.isPending}
              onClick={() => addMutation.mutate(selectedIssues)}
            >
              {addMutation.isPending
                ? "Adding..."
                : `Add ${selectedIssues.length} selected`}
            </button>
          </div>

          {loadingAllIssues && (
            <p className="muted">Loading issues (sorting by issue number)...</p>
          )}

          <div className="issue-grid">
            {allIssues.map((issue) => {
              const inList = existingIssueIds.has(issue.id);
              const isSelected = selected.has(issue.id);
              return (
                <div
                  key={issue.id}
                  className={`issue-select-card${isSelected ? " issue-select-card-selected" : ""}${inList ? " issue-select-card-in-list" : ""}`}
                  onClick={() => !inList && toggle(issue.id)}
                  role="button"
                  tabIndex={inList ? -1 : 0}
                  onKeyDown={(e) => {
                    if (!inList && (e.key === "Enter" || e.key === " ")) {
                      e.preventDefault();
                      toggle(issue.id);
                    }
                  }}
                >
                  {!inList && (
                    <input
                      type="checkbox"
                      className="issue-select-check"
                      checked={isSelected}
                      readOnly
                      tabIndex={-1}
                      aria-label={`Issue #${issue.issue_number}`}
                    />
                  )}
                  <CoverThumb
                    src={issue.image_url}
                    alt={`#${issue.issue_number}`}
                    size="fill"
                  />
                  <span className="issue-number">#{issue.issue_number}</span>
                  {issue.name && (
                    <span className="issue-series muted">{issue.name}</span>
                  )}
                  {inList && <span className="in-list-badge">In list</span>}
                </div>
              );
            })}
          </div>

          {issuesPage?.has_more && (
            <button
              className="btn btn-secondary"
              style={{ marginTop: "0.75rem" }}
              disabled={loadingIssues}
              onClick={() => setOffset((o) => o + 100)}
            >
              {loadingIssues
                ? "Loading..."
                : `Load more (${allIssues.length} / ${issuesPage.total})`}
            </button>
          )}

          {addMutation.error && (
            <p className="error">{(addMutation.error as Error).message}</p>
          )}
        </div>
      )}

      <div className="card">
        <h2>Search ComicVine volumes</h2>
        <div className="form-row">
          <input
            placeholder="Series name (e.g. Amazing Spider-Man)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && setSearchTerm(query.trim())}
          />
          <button
            className="btn"
            disabled={!query.trim()}
            onClick={() => setSearchTerm(query.trim())}
          >
            Search
          </button>
        </div>
        {searching && <p className="muted">Searching...</p>}
        <div className="volume-grid">
          {searchResults?.map((vol) => (
            <div key={vol.id} className="volume-card">
              <CoverThumb src={vol.image_url} alt={vol.name} size="fill" />
              <span className="volume-card-title">{vol.name}</span>
              <span className="volume-card-meta muted">
                {vol.start_year ?? "?"} · {vol.publisher ?? "Unknown"} ·{" "}
                {vol.count_of_issues ?? "?"} issues
              </span>
              <button className="btn" onClick={() => openVolume(vol)}>
                Select
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
