import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { CoverThumb } from "../components/CoverThumb";

export default function ListsHome() {
  const [name, setName] = useState("");
  const queryClient = useQueryClient();

  const { data: lists, isLoading, error } = useQuery({
    queryKey: ["lists"],
    queryFn: api.listLists,
  });

  const createMutation = useMutation({
    mutationFn: () => api.createList(name.trim()),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["lists"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteList(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["lists"] }),
  });

  return (
    <div>
      <div className="card">
        <h2>Create read list</h2>
        <div className="form-row">
          <input
            placeholder="List name (e.g. Civil War Reading Order)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && name.trim() && createMutation.mutate()}
          />
          <button
            className="btn"
            disabled={!name.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            Create
          </button>
        </div>
        {createMutation.error && (
          <p className="error">{(createMutation.error as Error).message}</p>
        )}
      </div>

      <div className="card">
        <h2>Your lists</h2>
        {isLoading && <p className="muted">Loading...</p>}
        {error && <p className="error">{(error as Error).message}</p>}
        {!isLoading && lists?.length === 0 && (
          <p className="muted">No lists yet. Create one above.</p>
        )}
        <div className="list-grid">
          {lists?.map((list) => (
            <div key={list.id} className="list-card card">
              <Link to={`/lists/${list.id}`} className="list-card-link">
                <CoverThumb src={list.thumbnail_url} alt={list.name} size="fill" />
                <span className="list-card-title">{list.name}</span>
                {list.tags.length > 0 && (
                  <div className="tag-list tag-list-compact">
                    {list.tags.map((tag) => (
                      <span key={tag} className="tag-pill">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
                <span className="list-card-meta muted">
                  {list.item_count} issue{list.item_count !== 1 ? "s" : ""}
                  {list.last_exported_at &&
                    ` · Exported ${new Date(list.last_exported_at).toLocaleDateString()}`}
                </span>
              </Link>
              <button
                className="btn btn-secondary btn-sm btn-danger list-card-delete"
                onClick={() => {
                  if (confirm(`Delete "${list.name}"?`)) deleteMutation.mutate(list.id);
                }}
                aria-label={`Delete ${list.name}`}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
