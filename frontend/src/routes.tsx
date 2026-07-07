import { Route, Routes } from "react-router-dom";
import AddIssues from "./pages/AddIssues";
import KapowarrSync from "./pages/KapowarrSync";
import KomgaPush from "./pages/KomgaPush";
import ListEditor from "./pages/ListEditor";
import ListsHome from "./pages/ListsHome";
import LocgImport from "./pages/LocgImport";
import MissingIssues from "./pages/MissingIssues";
import Settings from "./pages/Settings";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/settings" element={<Settings />} />
      <Route path="/" element={<ListsHome />} />
      <Route path="/missing" element={<MissingIssues />} />
      <Route path="/lists/:id" element={<ListEditor />} />
      <Route path="/lists/:id/add" element={<AddIssues />} />
      <Route path="/lists/:id/locg" element={<LocgImport />} />
      <Route path="/lists/:id/kapowarr" element={<KapowarrSync />} />
      <Route path="/lists/:id/komga" element={<KomgaPush />} />
    </Routes>
  );
}
