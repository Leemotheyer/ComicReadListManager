import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ReadListItem, VolumeGapInfo } from "../api";
import { CoverThumb } from "../components/CoverThumb";

type DropTarget = { id: number; before: boolean };

function parseTagsInput(raw: string): string[] {
  return raw
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

function reorderIds(
  ids: number[],
  dragId: number,
  targetId: number,
  before: boolean
): number[] | null {
  const from = ids.indexOf(dragId);
  let to = ids.indexOf(targetId);
  if (from < 0 || to < 0 || from === to) return null;

  const next = [...ids];
  next.splice(from, 1);
  if (from < to) to--;
  const insertAt = before ? to : to + 1;
  next.splice(insertAt, 0, dragId);
  return next;
}

function formatGapRanges(gapNumbers: string[]): string[] {
  if (gapNumbers.length === 0) return [];

  const parsed = gapNumbers
    .map((raw) => ({ raw, num: parseFloat(raw.replace("½", ".5")) }))
    .filter((entry) => !Number.isNaN(entry.num))
    .sort((a, b) => a.num - b.num);

  if (parsed.length === 0) return gapNumbers.map((num) => `#${num}`);

  const ranges: string[] = [];
  let rangeStart = parsed[0];
  let rangeEnd = parsed[0];

  const flushRange = () => {
    if (rangeStart.num === rangeEnd.num) {
      ranges.push(`#${rangeStart.raw}`);
      return;
    }
    ranges.push(`#${rangeStart.raw}-${rangeEnd.raw}`);
  };

  for (let i = 1; i < parsed.length; i += 1) {
    const current = parsed[i];
    if (current.num === rangeEnd.num + 1) {
      rangeEnd = current;
    } else {
      flushRange();
      rangeStart = current;
      rangeEnd = current;
    }
  }
  flushRange();

  return ranges;
}

function GapVolumeCard({ volume }: { volume: VolumeGapInfo }) {
  const gapRanges = formatGapRanges(volume.gaps);

  return (
    <div className="gap-volume-card">
      <div className="gap-volume-header">
        <strong>
          {volume.series}
          {volume.volume_year ? ` (${volume.volume_year})` : ""}
        </strong>
        <span className="muted">
          {volume.collected_count} collected · {volume.gaps.length} gap
          {volume.gaps.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="gap-badges">
        {gapRanges.map((range) => (
          <span key={range} className="gap-badge" title={`Missing ${range}`}>
            {range}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ListEditor() {
  const { id } = useParams<{ id: string }>();
  const listId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [dragId, setDragId] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<DropTarget | null>(null);
  const [editingMeta, setEditingMeta] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editTags, setEditTags] = useState("");
  const [listFilter, setListFilter] = useState("");
  const [notesFilter, setNotesFilter] = useState<"" | "with" | "without">("");
  const [editingNotesId, setEditingNotesId] = useState<number | null>(null);
  const [notesDraft, setNotesDraft] = useState("");

  const { data: list, isLoading, error } = useQuery({
    queryKey: ["list", listId],
    queryFn: () => api.getList(listId),
    enabled: !isNaN(listId),
  });

  const { data: gapsData } = useQuery({
    queryKey: ["listGaps", listId],
    queryFn: () => api.getListGaps(listId),
    enabled: !isNaN(listId),
  });

  const reorderMutation = useMutation({
    mutationFn: (itemIds: number[]) => api.reorderItems(listId, itemIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["list", listId] });
      queryClient.invalidateQueries({ queryKey: ["lists"] });
    },
  });

  const removeMutation = useMutation({
    mutationFn: (itemId: number) => api.removeItem(listId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["list", listId] });
      queryClient.invalidateQueries({ queryKey: ["lists"] });
      queryClient.invalidateQueries({ queryKey: ["listGaps", listId] });
    },
  });

  const updateListMutation = useMutation({
    mutationFn: (data: { name?: string; description?: string; tags?: string[] }) =>
      api.updateList(listId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["list", listId] });
      queryClient.invalidateQueries({ queryKey: ["lists"] });
      setEditingMeta(false);
    },
  });

  const copyMutation = useMutation({
    mutationFn: () => api.copyList(listId),
    onSuccess: (copied) => navigate(`/lists/${copied.id}`),
  });

  const updateItemMutation = useMutation({
    mutationFn: ({ itemId, notes }: { itemId: number; notes: string | null }) =>
      api.updateItem(listId, itemId, { notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["list", listId] });
      setEditingNotesId(null);
      setNotesDraft("");
    },
  });

  const applyReorder = useCallback(
    (ids: number[] | null) => {
      if (ids) reorderMutation.mutate(ids);
    },
    [reorderMutation]
  );

  const moveItem = useCallback(
    (itemId: number, direction: -1 | 1) => {
      if (!list) return;
      const ids = list.items.map((i) => i.id);
      const idx = ids.indexOf(itemId);
      const swapWith = idx + direction;
      if (idx < 0 || swapWith < 0 || swapWith >= ids.length) return;
      [ids[idx], ids[swapWith]] = [ids[swapWith], ids[idx]];
      applyReorder(ids);
    },
    [list, applyReorder]
  );

  const handleDragOver = useCallback((e: React.DragEvent, itemId: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const rect = e.currentTarget.getBoundingClientRect();
    const before = e.clientY < rect.top + rect.height / 2;
    setDropTarget({ id: itemId, before });
  }, []);

  const handleDrop = useCallback(
    (targetId: number) => {
      if (!list || dragId === null) return;
      const before = dropTarget?.id === targetId ? dropTarget.before : true;
      const ids = reorderIds(
        list.items.map((i) => i.id),
        dragId,
        targetId,
        before
      );
      applyReorder(ids);
      setDragId(null);
      setDropTarget(null);
    },
    [list, dragId, dropTarget, applyReorder]
  );

  const clearDrag = useCallback(() => {
    setDragId(null);
    setDropTarget(null);
  }, []);

  const startEditMeta = () => {
    if (!list) return;
    setEditName(list.name);
    setEditDescription(list.description ?? "");
    setEditTags(list.tags.join(", "));
    setEditingMeta(true);
  };

  const saveMeta = () => {
    const trimmedDesc = editDescription.trim();
    updateListMutation.mutate({
      name: editName.trim() || list!.name,
      description: trimmedDesc ? trimmedDesc : undefined,
      tags: parseTagsInput(editTags),
    });
  };

  const startEditNotes = (item: ReadListItem) => {
    setEditingNotesId(item.id);
    setNotesDraft(item.notes ?? "");
  };

  const filteredItems = useMemo(() => {
    if (!list) return [];
    const q = listFilter.trim().toLowerCase();
    return list.items.filter((item) => {
      if (notesFilter === "with" && !item.notes?.trim()) return false;
      if (notesFilter === "without" && item.notes?.trim()) return false;
      if (!q) return true;
      const haystack = [
        item.series,
        item.issue_number,
        item.issue_title ?? "",
        item.publisher ?? "",
        item.notes ?? "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [list, listFilter, notesFilter]);

  const volumesWithGaps = gapsData?.volumes.filter((v) => v.gaps.length > 0) ?? [];

  if (isLoading) return <p className="muted">Loading...</p>;
  if (error) return <p className="error">{(error as Error).message}</p>;
  if (!list) return <p className="error">List not found</p>;

  return (
    <div>
      <p className="page-back">
        <Link to="/">← Back to lists</Link>
      </p>

      <div className="card">
        {editingMeta ? (
          <>
            <label className="settings-label">
              Name
              <input value={editName} onChange={(e) => setEditName(e.target.value)} />
            </label>
            <label className="settings-label">
              Description
              <textarea
                rows={3}
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
              />
            </label>
            <label className="settings-label">
              Tags (comma-separated)
              <input
                placeholder="event, reread"
                value={editTags}
                onChange={(e) => setEditTags(e.target.value)}
              />
            </label>
            <div className="row-actions">
              <button
                className="btn"
                disabled={updateListMutation.isPending}
                onClick={saveMeta}
              >
                Save
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setEditingMeta(false)}
              >
                Cancel
              </button>
            </div>
          </>
        ) : (
          <div className="list-editor-head">
            <h2>{list.name}</h2>
            {list.description && <p className="muted">{list.description}</p>}
            {list.tags.length > 0 && (
              <div className="tag-list">
                {list.tags.map((tag) => (
                  <span key={tag} className="tag-pill">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="list-editor-toolbar">
          <div className="action-group">
            <span className="action-group-label">Add</span>
            <div className="action-group-buttons">
              <Link className="btn" to={`/lists/${listId}/add`}>
                Add issues
              </Link>
            </div>
          </div>

          <div className="action-group">
            <span className="action-group-label">Export</span>
            <div className="action-group-buttons">
              <a className="btn btn-secondary" href={api.exportCblUrl(listId)}>
                Export CBL
              </a>
            </div>
          </div>

          <div className="action-group">
            <span className="action-group-label">Library sync</span>
            <div className="action-group-buttons">
              <Link className="btn btn-secondary" to={`/lists/${listId}/kapowarr`}>
                Kapowarr sync
              </Link>
              <Link className="btn btn-secondary" to={`/lists/${listId}/komga`}>
                Push to Komga
              </Link>
            </div>
          </div>

          <div className="action-group">
            <span className="action-group-label">List</span>
            <div className="action-group-buttons">
              <button
                className="btn btn-secondary"
                disabled={copyMutation.isPending}
                onClick={() => copyMutation.mutate()}
              >
                {copyMutation.isPending ? "Copying..." : "Copy list"}
              </button>
              {!editingMeta && (
                <button className="btn btn-secondary" onClick={startEditMeta}>
                  Edit details
                </button>
              )}
            </div>
          </div>
        </div>
        {copyMutation.error && (
          <p className="error">{(copyMutation.error as Error).message}</p>
        )}
      </div>

      {volumesWithGaps.length > 0 && (
        <div className="card">
          <h2>Collection gaps</h2>
          <p className="muted">
            Missing issue numbers in volumes you are collecting on this list.
          </p>
          <div className="gap-volume-list">
            {volumesWithGaps.map((vol) => (
              <GapVolumeCard key={vol.cv_volume_id} volume={vol} />
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <h2>
          {filteredItems.length === list.items.length
            ? `${list.items.length} issue${list.items.length !== 1 ? "s" : ""}`
            : `${filteredItems.length} of ${list.items.length} issues`}
        </h2>

        {list.items.length > 0 && (
          <div className="filters">
            <input
              placeholder="Search series, issue #, notes..."
              value={listFilter}
              onChange={(e) => setListFilter(e.target.value)}
              style={{ flex: 1, minWidth: "12rem" }}
            />
            <select
              value={notesFilter}
              onChange={(e) =>
                setNotesFilter(e.target.value as "" | "with" | "without")
              }
              aria-label="Filter by notes"
            >
              <option value="">All items</option>
              <option value="with">With notes</option>
              <option value="without">Without notes</option>
            </select>
          </div>
        )}

        {list.items.length === 0 ? (
          <p className="muted">
            No issues yet.{" "}
            <Link to={`/lists/${listId}/add`}>Search ComicVine to add some</Link>.
          </p>
        ) : filteredItems.length === 0 ? (
          <p className="muted">No issues match your search.</p>
        ) : (
          <>
            <div className="issue-list">
              {filteredItems.map((item: ReadListItem) => {
                const idx = list.items.findIndex((i) => i.id === item.id);
                const isDragging = dragId === item.id;
                const isDropBefore =
                  dropTarget?.id === item.id && dropTarget.before;
                const isDropAfter =
                  dropTarget?.id === item.id && !dropTarget.before;

                return (
                  <div
                    key={item.id}
                    className={[
                      "issue-list-row",
                      isDragging ? "issue-list-row-dragging" : "",
                      isDropBefore ? "issue-list-row-drop-before" : "",
                      isDropAfter ? "issue-list-row-drop-after" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    onDragOver={(e) => handleDragOver(e, item.id)}
                    onDrop={(e) => {
                      e.preventDefault();
                      handleDrop(item.id);
                    }}
                  >
                    <button
                      type="button"
                      className="issue-drag-handle"
                      draggable
                      aria-label={`Drag issue ${idx + 1} to reorder`}
                      onDragStart={(e) => {
                        e.dataTransfer.effectAllowed = "move";
                        e.dataTransfer.setData("text/plain", String(item.id));
                        setDragId(item.id);
                      }}
                      onDragEnd={clearDrag}
                    >
                      <span className="issue-drag-grip" aria-hidden />
                    </button>

                    <span className="issue-list-order">{idx + 1}</span>

                    <CoverThumb
                      src={item.cover_image_url}
                      alt={`${item.series} #${item.issue_number}`}
                      size="md"
                    />

                    <div className="issue-list-info">
                      <span className="issue-number">
                        {item.series}
                        {item.volume_year ? ` (${item.volume_year})` : ""} #{item.issue_number}
                      </span>
                      {editingNotesId === item.id ? (
                        <div className="item-notes-editor">
                          <input
                            placeholder="Notes (e.g. read after House of M)"
                            value={notesDraft}
                            onChange={(e) => setNotesDraft(e.target.value)}
                          />
                          <div className="row-actions">
                            <button
                              type="button"
                              className="btn btn-sm"
                              disabled={updateItemMutation.isPending}
                              onClick={() =>
                                updateItemMutation.mutate({
                                  itemId: item.id,
                                  notes: notesDraft.trim() || null,
                                })
                              }
                            >
                              Save
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => setEditingNotesId(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="item-notes-row">
                          {item.notes ? (
                            <span className="item-notes">{item.notes}</span>
                          ) : (
                            <span className="muted item-notes-empty">No notes</span>
                          )}
                          <button
                            type="button"
                            className="link-button"
                            onClick={() => startEditNotes(item)}
                          >
                            {item.notes ? "Edit notes" : "Add notes"}
                          </button>
                        </div>
                      )}
                    </div>

                    <div className="issue-list-actions">
                      <button
                        type="button"
                        className="btn btn-secondary btn-icon"
                        disabled={idx === 0 || reorderMutation.isPending}
                        aria-label={`Move issue ${idx + 1} up`}
                        onClick={() => moveItem(item.id, -1)}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-icon"
                        disabled={
                          idx === list.items.length - 1 ||
                          reorderMutation.isPending
                        }
                        aria-label={`Move issue ${idx + 1} down`}
                        onClick={() => moveItem(item.id, 1)}
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm btn-danger"
                        onClick={() => removeMutation.mutate(item.id)}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="muted issue-list-hint">
              Drag the handle to reorder, or use the arrows. Reading order is top to bottom.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
