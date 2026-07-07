import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  KomgaMatchCandidate,
  KomgaPreviewItem,
  KomgaSeriesResult,
} from "../api";

const STATUS_LABELS: Record<string, string> = {
  matched: "Matched",
  manual: "Manually matched",
  unmatched: "Not in library",
};

type ManualMapping = { bookId: string; label: string };

type VolumeGroup = {
  cvVolumeId: number;
  series: string;
  volumeYear: number | null;
  items: KomgaPreviewItem[];
};

function formatSeries(series: string, volumeYear: number | null | undefined) {
  return volumeYear ? `${series} (${volumeYear})` : series;
}

function normalizeIssueNumber(value: string) {
  const cleaned = value.trim().replace("½", ".5").replace(/^0+(?=\d)/, "");
  return cleaned || "0";
}

function extractIssueCandidatesFromFilename(filename: string): string[] {
  if (!filename) return [];
  const stem = filename.replace(/\.[^.]+$/, "");
  const candidates: string[] = [];
  const seen = new Set<string>();

  const add = (value: string) => {
    const normalized = normalizeIssueNumber(value);
    if (normalized && !seen.has(normalized)) {
      seen.add(normalized);
      candidates.push(value);
    }
  };

  for (const match of stem.matchAll(/#\s*(\d+(?:\.\d+)?(?:½)?)/gi)) {
    add(match[1]);
  }
  for (const match of stem.matchAll(
    /(?:issue|iss(?:ue)?|no\.?)\s*(\d+(?:\.\d+)?(?:½)?)/gi
  )) {
    add(match[1]);
  }
  for (const match of stem.matchAll(/[\s_\-](\d+(?:\.\d+)?(?:½)?)\s*\(\d{4}\)/g)) {
    add(match[1]);
  }
  for (const match of stem.matchAll(
    /(?:^|[\s_\-])(\d{1,4}(?:\.\d+)?(?:½)?)(?:[\s_\-]|$|\.)/g
  )) {
    const value = match[1];
    if (value.length === 4 && /^(19|20)\d{2}$/.test(value)) continue;
    add(value);
  }

  return candidates;
}

function bookMatchesIssue(book: { number: string; filename?: string | null }, target: string) {
  if (normalizeIssueNumber(book.number) === target) return true;
  const filename = book.filename ?? "";
  return extractIssueCandidatesFromFilename(filename).some(
    (candidate) => normalizeIssueNumber(candidate) === target
  );
}

function candidateLabel(candidate: KomgaMatchCandidate) {
  if (candidate.book_id) {
    const num = candidate.book_number ? `#${candidate.book_number}` : "";
    const title = candidate.book_title || candidate.series_title || "Book";
    return `${title} ${num}`.trim();
  }
  return candidate.series_title || "Series match";
}

function groupByVolume(items: KomgaPreviewItem[]): VolumeGroup[] {
  const order: number[] = [];
  const map = new Map<number, VolumeGroup>();
  for (const item of items) {
    if (!map.has(item.cv_volume_id)) {
      order.push(item.cv_volume_id);
      map.set(item.cv_volume_id, {
        cvVolumeId: item.cv_volume_id,
        series: item.series,
        volumeYear: item.volume_year,
        items: [],
      });
    }
    map.get(item.cv_volume_id)!.items.push(item);
  }
  return order.map((id) => map.get(id)!);
}

function isItemMatched(
  item: KomgaPreviewItem,
  manualMappings: Map<number, ManualMapping>
) {
  return Boolean(item.komga_book_id) || manualMappings.has(item.list_item_id);
}

function resolveItem(
  item: KomgaPreviewItem,
  manualMappings: Map<number, ManualMapping>
): KomgaPreviewItem {
  const mapping = manualMappings.get(item.list_item_id);
  if (mapping) {
    return {
      ...item,
      status: "manual",
      komga_book_id: mapping.bookId,
      message: mapping.label,
    };
  }
  return item;
}

function ManualMatchPanel({
  item,
  mapping,
  onSelect,
  onClear,
}: {
  item: KomgaPreviewItem;
  mapping: ManualMapping | undefined;
  onSelect: (bookId: string, label: string) => void;
  onClear: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState(item.series);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedSeries, setSelectedSeries] = useState<KomgaSeriesResult | null>(null);

  const seriesQuery = useQuery({
    queryKey: ["komgaSeriesSearch", searchTerm],
    queryFn: () => api.komgaSearchSeries(searchTerm),
    enabled: searchTerm.length > 0,
  });

  const booksQuery = useQuery({
    queryKey: ["komgaSeriesBooks", selectedSeries?.id],
    queryFn: () => api.komgaSeriesBooks(selectedSeries!.id),
    enabled: !!selectedSeries,
  });

  const targetNumber = normalizeIssueNumber(item.issue_number);

  const issueMatchesBook = (book: { number: string; filename?: string | null }) =>
    bookMatchesIssue(book, targetNumber);

  const selectCandidate = (candidate: KomgaMatchCandidate) => {
    if (!candidate.book_id) return;
    onSelect(candidate.book_id, candidateLabel(candidate));
  };

  const bookCandidates = item.candidates.filter((c) => c.book_id);

  return (
    <div className="komga-match-panel">
      {mapping ? (
        <div className="komga-match-selected">
          <span className="status-manual">{mapping.label}</span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClear}>
            Clear
          </button>
        </div>
      ) : (
        <>
          {bookCandidates.length > 0 && (
            <div className="komga-match-candidates">
              <p className="muted komga-match-label">Suggested matches</p>
              <div className="komga-match-options">
                {bookCandidates.map((candidate, idx) => (
                  <button
                    key={`${candidate.book_id}-${idx}`}
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => selectCandidate(candidate)}
                  >
                    {candidateLabel(candidate)}
                  </button>
                ))}
              </div>
            </div>
          )}

          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Hide manual search" : "Match this issue manually"}
          </button>

          {expanded && (
            <div className="komga-match-search">
              <form
                className="komga-match-search-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  setSearchTerm(query.trim());
                  setSelectedSeries(null);
                }}
              >
                <input
                  type="search"
                  value={query}
                  placeholder="Search series in Komga"
                  onChange={(e) => setQuery(e.target.value)}
                />
                <button type="submit" className="btn btn-secondary btn-sm">
                  Search
                </button>
              </form>

              {seriesQuery.isFetching && <p className="muted">Searching...</p>}

              {!selectedSeries && seriesQuery.data && seriesQuery.data.length > 0 && (
                <div className="komga-series-list">
                  {seriesQuery.data.map((series) => (
                    <button
                      key={series.id}
                      type="button"
                      className="komga-series-option"
                      onClick={() => setSelectedSeries(series)}
                    >
                      <span>{series.name}</span>
                      <span className="muted">
                        {series.books_count} book{series.books_count !== 1 ? "s" : ""}
                        {series.year ? ` · ${series.year}` : ""}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {selectedSeries && (
                <div className="komga-books-panel">
                  <p className="muted">
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => setSelectedSeries(null)}
                    >
                      ← Back to series
                    </button>
                    {" · "}
                    {selectedSeries.name}
                  </p>
                  {booksQuery.isFetching && <p className="muted">Loading books...</p>}
                  {booksQuery.data && booksQuery.data.length === 0 && (
                    <p className="muted">No books in this series.</p>
                  )}
                  {booksQuery.data && booksQuery.data.length > 0 && (
                    <div className="komga-book-list">
                      {booksQuery.data.map((book) => {
                        const highlight = issueMatchesBook(book);
                        return (
                          <button
                            key={book.id}
                            type="button"
                            className={`komga-book-option${highlight ? " komga-book-option-highlight" : ""}`}
                            onClick={() =>
                              onSelect(
                                book.id,
                                `${book.series_title || selectedSeries.name} #${book.number}`
                              )
                            }
                          >
                            <span>#{book.number}</span>
                            <span className="muted">{book.title || "Untitled"}</span>
                            {highlight && <span className="komga-book-tag">Issue match</span>}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function VolumeMatchPanel({
  group,
  manualMappings,
  onBulkMatch,
}: {
  group: VolumeGroup;
  manualMappings: Map<number, ManualMapping>;
  onBulkMatch: (
    mappings: { listItemId: number; bookId: string; label: string }[]
  ) => void;
}) {
  const unmatchedItems = useMemo(
    () => group.items.filter((item) => !isItemMatched(item, manualMappings)),
    [group.items, manualMappings]
  );

  const [query, setQuery] = useState(group.series);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedSeries, setSelectedSeries] = useState<KomgaSeriesResult | null>(null);
  const [matchMessage, setMatchMessage] = useState<string | null>(null);

  const seriesQuery = useQuery({
    queryKey: ["komgaSeriesSearch", searchTerm],
    queryFn: () => api.komgaSearchSeries(searchTerm),
    enabled: searchTerm.length > 0,
  });

  const seriesCandidates = useMemo(() => {
    const seen = new Set<string>();
    const result: KomgaMatchCandidate[] = [];
    for (const item of unmatchedItems) {
      for (const candidate of item.candidates) {
        if (candidate.series_id && !candidate.book_id && !seen.has(candidate.series_id)) {
          seen.add(candidate.series_id);
          result.push(candidate);
        }
      }
    }
    return result;
  }, [unmatchedItems]);

  const matchMutation = useMutation({
    mutationFn: (series: KomgaSeriesResult) =>
      api.komgaMatchVolume(
        series.id,
        unmatchedItems.map((item) => ({
          list_item_id: item.list_item_id,
          issue_number: item.issue_number,
        }))
      ),
    onSuccess: (result, series) => {
      onBulkMatch(
        result.mappings.map((m) => ({
          listItemId: m.list_item_id,
          bookId: m.komga_book_id,
          label: m.label,
        }))
      );
      if (result.unmatched.length === 0) {
        setMatchMessage(
          `Matched all ${result.mappings.length} issue${result.mappings.length !== 1 ? "s" : ""} in ${series.name}.`
        );
      } else {
        const nums = result.unmatched.map((u) => `#${u.issue_number}`).join(", ");
        setMatchMessage(
          `Matched ${result.mappings.length} of ${unmatchedItems.length} in ${series.name}. Not found: ${nums}`
        );
      }
    },
    onError: (err) => setMatchMessage((err as Error).message),
  });

  if (unmatchedItems.length === 0) return null;

  const pickSeries = (series: KomgaSeriesResult) => {
    setSelectedSeries(series);
    setMatchMessage(null);
  };

  return (
    <div className="komga-volume-match">
      <p className="muted komga-match-label">
        {unmatchedItems.length} issue{unmatchedItems.length !== 1 ? "s" : ""} need matching
        — pick the Komga series for this volume, then auto-match by issue number.
      </p>

      {seriesCandidates.length > 0 && (
        <div className="komga-match-candidates">
          <p className="muted komga-match-label">Suggested series</p>
          <div className="komga-match-options">
            {seriesCandidates.map((candidate, idx) => (
              <button
                key={`${candidate.series_id}-${idx}`}
                type="button"
                className={`btn btn-secondary btn-sm${selectedSeries?.id === candidate.series_id ? " komga-series-selected" : ""}`}
                onClick={() =>
                  pickSeries({
                    id: candidate.series_id!,
                    name: candidate.series_title || "Series",
                    books_count: 0,
                    year: group.volumeYear,
                  })
                }
              >
                {candidate.series_title}
              </button>
            ))}
          </div>
        </div>
      )}

      <form
        className="komga-match-search-form"
        onSubmit={(e) => {
          e.preventDefault();
          setSearchTerm(query.trim());
          setSelectedSeries(null);
          setMatchMessage(null);
        }}
      >
        <input
          type="search"
          value={query}
          placeholder="Search Komga series"
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="submit" className="btn btn-secondary btn-sm">
          Search
        </button>
      </form>

      {seriesQuery.isFetching && <p className="muted">Searching...</p>}

      {!selectedSeries && seriesQuery.data && seriesQuery.data.length > 0 && (
        <div className="komga-series-list">
          {seriesQuery.data.map((series) => (
            <button
              key={series.id}
              type="button"
              className="komga-series-option"
              onClick={() => pickSeries(series)}
            >
              <span>{series.name}</span>
              <span className="muted">
                {series.books_count} book{series.books_count !== 1 ? "s" : ""}
                {series.year ? ` · ${series.year}` : ""}
              </span>
            </button>
          ))}
        </div>
      )}

      {selectedSeries && (
        <div className="komga-volume-match-actions">
          <p className="muted">
            Selected: <strong>{selectedSeries.name}</strong>
            {" · "}
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setSelectedSeries(null);
                setMatchMessage(null);
              }}
            >
              Change
            </button>
          </p>
          <button
            type="button"
            className="btn"
            disabled={matchMutation.isPending}
            onClick={() => matchMutation.mutate(selectedSeries)}
          >
            {matchMutation.isPending
              ? "Matching..."
              : `Match ${unmatchedItems.length} issue${unmatchedItems.length !== 1 ? "s" : ""} in volume`}
          </button>
        </div>
      )}

      {matchMessage && (
        <p className={matchMessage.startsWith("Matched") ? "status-in_library" : "error"}>
          {matchMessage}
        </p>
      )}
    </div>
  );
}

function PreviewItems({
  items,
  manualMappings,
  onSelectMapping,
  onClearMapping,
  onBulkMatch,
}: {
  items: KomgaPreviewItem[];
  manualMappings: Map<number, ManualMapping>;
  onSelectMapping: (listItemId: number, bookId: string, label: string) => void;
  onClearMapping: (listItemId: number) => void;
  onBulkMatch: (
    mappings: { listItemId: number; bookId: string; label: string }[]
  ) => void;
}) {
  const volumeGroups = useMemo(() => groupByVolume(items), [items]);

  return (
    <div className="komga-preview-groups">
      {volumeGroups.map((group) => {
        const hasUnmatched = group.items.some(
          (item) => !isItemMatched(item, manualMappings)
        );

        return (
          <div key={group.cvVolumeId} className="komga-volume-group card">
            <h3>{formatSeries(group.series, group.volumeYear)}</h3>

            {hasUnmatched && (
              <VolumeMatchPanel
                group={group}
                manualMappings={manualMappings}
                onBulkMatch={onBulkMatch}
              />
            )}

            <div className="sync-item-list mobile-only">
              {group.items.map((item) => {
                const resolved = resolveItem(item, manualMappings);
                const needsManual = resolved.status === "unmatched";
                return (
                  <div key={item.list_item_id} className="sync-item">
                    <div className="sync-item-main">
                      <div className="sync-item-issue">#{item.issue_number}</div>
                      <div className={`sync-item-status status-${resolved.status}`}>
                        {STATUS_LABELS[resolved.status] ?? resolved.status}
                      </div>
                      {resolved.message && (
                        <div className="sync-item-note muted">{resolved.message}</div>
                      )}
                      {needsManual && (
                        <ManualMatchPanel
                          item={item}
                          mapping={manualMappings.get(item.list_item_id)}
                          onSelect={(bookId, label) =>
                            onSelectMapping(item.list_item_id, bookId, label)
                          }
                          onClear={() => onClearMapping(item.list_item_id)}
                        />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="table-scroll desktop-table">
              <table>
                <thead>
                  <tr>
                    <th>Issue</th>
                    <th>Status</th>
                    <th>Match</th>
                  </tr>
                </thead>
                <tbody>
                  {group.items.map((item) => {
                    const resolved = resolveItem(item, manualMappings);
                    const needsManual = resolved.status === "unmatched";
                    return (
                      <tr key={item.list_item_id}>
                        <td>#{item.issue_number}</td>
                        <td className={`status-${resolved.status}`}>
                          {STATUS_LABELS[resolved.status] ?? resolved.status}
                        </td>
                        <td>
                          {resolved.message && (
                            <div className="muted">{resolved.message}</div>
                          )}
                          {needsManual && (
                            <ManualMatchPanel
                              item={item}
                              mapping={manualMappings.get(item.list_item_id)}
                              onSelect={(bookId, label) =>
                                onSelectMapping(item.list_item_id, bookId, label)
                              }
                              onClear={() => onClearMapping(item.list_item_id)}
                            />
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function KomgaPush() {
  const { id } = useParams<{ id: string }>();
  const listId = Number(id);

  const [showOnlyUnmatched, setShowOnlyUnmatched] = useState(false);
  const [allowPartial, setAllowPartial] = useState(true);
  const [manualMappings, setManualMappings] = useState<Map<number, ManualMapping>>(
    new Map()
  );
  const [pushResult, setPushResult] = useState<Awaited<
    ReturnType<typeof api.komgaPush>
  > | null>(null);

  const previewQuery = useQuery({
    queryKey: ["komgaPreview", listId],
    queryFn: () => api.komgaPreview(listId),
    enabled: !isNaN(listId),
  });

  const pushMutation = useMutation({
    mutationFn: () =>
      api.komgaPush(listId, {
        allow_partial: allowPartial,
        manual_mappings: [...manualMappings.entries()].map(
          ([list_item_id, mapping]) => ({
            list_item_id,
            komga_book_id: mapping.bookId,
            label: mapping.label,
          })
        ),
      }),
    onSuccess: (data) => {
      setPushResult(data);
      previewQuery.refetch();
    },
  });

  const preview = previewQuery.data;

  const effectiveCounts = useMemo(() => {
    if (!preview) return { matched: 0, unmatched: 0 };
    let matched = 0;
    let unmatched = 0;
    for (const item of preview.items) {
      if (manualMappings.has(item.list_item_id) || item.komga_book_id) {
        matched += 1;
      } else {
        unmatched += 1;
      }
    }
    return { matched, unmatched };
  }, [preview, manualMappings]);

  const visibleItems = useMemo(() => {
    if (!preview) return [];
    if (!showOnlyUnmatched) return preview.items;
    return preview.items.filter((item) => {
      if (manualMappings.has(item.list_item_id)) return false;
      return !item.komga_book_id;
    });
  }, [preview, showOnlyUnmatched, manualMappings]);

  const setMapping = (listItemId: number, bookId: string, label: string) => {
    setManualMappings((prev) => {
      const next = new Map(prev);
      next.set(listItemId, { bookId, label });
      return next;
    });
  };

  const setBulkMappings = (
    mappings: { listItemId: number; bookId: string; label: string }[]
  ) => {
    setManualMappings((prev) => {
      const next = new Map(prev);
      for (const m of mappings) {
        next.set(m.listItemId, { bookId: m.bookId, label: m.label });
      }
      return next;
    });
  };

  const clearMapping = (listItemId: number) => {
    setManualMappings((prev) => {
      const next = new Map(prev);
      next.delete(listItemId);
      return next;
    });
  };

  if (previewQuery.isLoading) return <p className="muted">Loading preview...</p>;
  if (previewQuery.error)
    return <p className="error">{(previewQuery.error as Error).message}</p>;
  if (!preview) return null;

  const canPush =
    effectiveCounts.matched > 0 &&
    (allowPartial || effectiveCounts.unmatched === 0);

  return (
    <div>
      <p className="page-back">
        <Link to={`/lists/${listId}`}>← Back to list</Link>
      </p>

      <div className="card">
        <h2>Push to Komga</h2>
        <p className="muted">
          Issues are grouped by volume. Pick a Komga series once per volume to
          auto-match issue numbers, or match individual issues manually.
        </p>

        <div style={{ marginBottom: "1rem" }}>
          <p>
            <strong>{preview.list_name}</strong>
          </p>
          <p className="muted">
            {effectiveCounts.matched} matched · {effectiveCounts.unmatched} unmatched
            {manualMappings.size > 0 && ` (${manualMappings.size} manual)`}
          </p>
          {preview.existing_komga_read_list_id && (
            <p className="muted">
              A read list named &ldquo;{preview.existing_komga_read_list_name}&rdquo; already
              exists in Komga — pushing will update it.
            </p>
          )}
        </div>

        <div className="filters">
          <label>
            <input
              type="checkbox"
              checked={showOnlyUnmatched}
              onChange={(e) => setShowOnlyUnmatched(e.target.checked)}
            />
            Show only unmatched
          </label>
          <label>
            <input
              type="checkbox"
              checked={allowPartial}
              onChange={(e) => setAllowPartial(e.target.checked)}
            />
            Push matched books only (skip unmatched)
          </label>
        </div>

        <PreviewItems
          items={visibleItems}
          manualMappings={manualMappings}
          onSelectMapping={setMapping}
          onClearMapping={clearMapping}
          onBulkMatch={setBulkMappings}
        />

        <div className="row-actions" style={{ marginTop: "1rem" }}>
          <button
            className="btn"
            disabled={pushMutation.isPending || !canPush}
            onClick={() => pushMutation.mutate()}
          >
            {pushMutation.isPending ? "Pushing..." : "Push to Komga"}
          </button>
        </div>

        {!canPush && (
          <p className="error" style={{ marginTop: "0.75rem" }}>
            No matched books to push. Match volumes using the controls above, or check
            that series names and issue numbers align with your Komga library.
          </p>
        )}

        {pushMutation.error && (
          <p className="error">{(pushMutation.error as Error).message}</p>
        )}
      </div>

      {pushResult && (
        <div className="card">
          <h2>Push results</h2>
          <p className="status-in_library">
            Read list {pushResult.action}: {pushResult.komga_read_list_name} (
            {pushResult.books_pushed} book{pushResult.books_pushed !== 1 ? "s" : ""}
            {pushResult.books_skipped > 0
              ? `, ${pushResult.books_skipped} skipped`
              : ""}
            )
          </p>
          <PreviewItems
            items={pushResult.items}
            manualMappings={new Map()}
            onSelectMapping={() => {}}
            onClearMapping={() => {}}
            onBulkMatch={() => {}}
          />
        </div>
      )}
    </div>
  );
}
