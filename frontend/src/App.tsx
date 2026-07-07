import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "./api";
import { AppRoutes } from "./routes";

export default function App() {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
  });

  return (
    <>
      <header className="app-header">
        <h1>
          <Link to="/">Comic Lists</Link>
        </h1>
        <nav>
          <Link to="/">Lists</Link>
          <Link to="/missing">Missing</Link>
          <Link to="/settings">Settings</Link>
        </nav>
        {health && (
          <div className="status-badges">
            <span className={`badge ${health.comicvine_configured ? "ok" : "warn"}`}>
              ComicVine {health.comicvine_configured ? "OK" : "Not configured"}
            </span>
            <span className={`badge ${health.kapowarr_configured ? "ok" : "warn"}`}>
              Kapowarr {health.kapowarr_configured ? "OK" : "Not configured"}
            </span>
            <span className={`badge ${health.komga_configured ? "ok" : "warn"}`}>
              Komga {health.komga_configured ? "OK" : "Not configured"}
            </span>
          </div>
        )}
      </header>
      <main>
        <AppRoutes />
      </main>
    </>
  );
}
