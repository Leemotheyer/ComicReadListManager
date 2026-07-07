import { Link, useParams } from "react-router-dom";

type AddIssuesMode = "comicvine" | "locg";

export function AddIssuesNav({ mode }: { mode: AddIssuesMode }) {
  const { id } = useParams<{ id: string }>();
  const listId = Number(id);

  return (
    <nav className="add-issues-nav" aria-label="Add issues">
      <Link
        to={`/lists/${listId}/add`}
        className={`add-issues-nav-item ${mode === "comicvine" ? "add-issues-nav-item-active" : ""}`}
      >
        ComicVine search
      </Link>
      <Link
        to={`/lists/${listId}/locg`}
        className={`add-issues-nav-item ${mode === "locg" ? "add-issues-nav-item-active" : ""}`}
      >
        Import from LoCG
      </Link>
    </nav>
  );
}
