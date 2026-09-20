import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes, useParams, type Params } from "react-router-dom";
import Layout from "./components/Layout";
import AuditDetail from "./pages/AuditDetail";
import Audits from "./pages/Audits";
import Browse from "./pages/Browse";
import Home from "./pages/Home";
import PageView from "./pages/PageView";
import Rollback from "./pages/Rollback";
import RunAudit from "./pages/RunAudit";
import Search from "./pages/Search";
import Settings from "./pages/Settings";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 10_000 } } });

/** Remounts the page when its route params change so per-page state never leaks between entities. */
function Keyed({ component: Component, by }: { component: React.ComponentType; by: (params: Params) => string }) {
  const params = useParams();
  return <Component key={by(params)} />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/kb" element={<Browse />} />
        <Route path="/kb/:section" element={<Keyed component={Browse} by={(p) => p.section ?? ""} />} />
        <Route path="/kb/page/*" element={<Keyed component={PageView} by={(p) => p["*"] ?? ""} />} />
        <Route path="/search" element={<Search />} />
        <Route path="/audits" element={<Audits />} />
        <Route path="/audits/new" element={<RunAudit />} />
        <Route path="/audits/:id" element={<Keyed component={AuditDetail} by={(p) => p.id ?? ""} />} />
        <Route path="/audits/:id/actions/:actionId/rollback" element={<Keyed component={Rollback} by={(p) => `${p.id}/${p.actionId}`} />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  // One router only: the console is always served with a server-side SPA fallback (the bundled API
  // server or the platform's static host), mounted at the build's BASE_URL when it lives under a prefix.
  const basename = import.meta.env.BASE_URL.replace(/\/$/, "") || "/";
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={basename}>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
