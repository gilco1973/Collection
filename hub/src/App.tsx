import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { BrowserRouter, HashRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { queryClient } from "./api";
import { AuthProvider, CALLBACK_PATH } from "./auth/AuthProvider";
import { RequireAuth } from "./auth/RequireAuth";
import { env } from "./config/env";
import HubShell from "./HubShell";
import { ROUTES, SCREEN_TITLES } from "./routes";
import Assistant from "./features/assistant/Assistant";
import Discover from "./features/discover/Discover";
import Listing from "./features/discover/Listing";
import IntakeBrief from "./features/intake/IntakeBrief";
import Settings from "./features/settings/Settings";
import Workspace from "./features/workspace/Workspace";
import { PaletteProvider } from "./ui/CommandPalette";
import Learn from "./screens/Learn";
import SignIn from "./screens/SignIn";
import { Forbidden, NotFound } from "./screens/Status";
import { ErrorBoundary } from "./ui/ErrorBoundary";
import { PageState } from "./ui/PageState";
import { ThemeProvider } from "./ui/ThemeProvider";
import { ToastProvider } from "./ui/Toast";

const Router = env.VITE_ROUTER === "hash" ? HashRouter : BrowserRouter;

function DocumentTitle() {
  const { pathname } = useLocation();
  useEffect(() => {
    // Live pages set their own title (useTitle); this covers the rest.
    const screen = SCREEN_TITLES[pathname];
    if (screen) document.title = `${screen} · CrossRiver AI Hub`;
    else if (!document.title.includes("·")) document.title = "CrossRiver AI Hub";
  }, [pathname]);
  return null;
}

/** Moves focus to the main region on navigation so keyboard and screen-reader users land on the new page. */
function FocusOnNavigate() {
  const { pathname } = useLocation();
  useEffect(() => {
    const main = document.getElementById("main");
    if (main && document.activeElement !== main) main.focus({ preventScroll: true });
  }, [pathname]);
  return null;
}

const guarded = (el: JSX.Element) => <RequireAuth>{el}</RequireAuth>;

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <ToastProvider>
          <AuthProvider>
            <ThemeProvider>
              <PaletteProvider>
                <DocumentTitle />
                <FocusOnNavigate />
                <a className="skip-link" href="#main">
                  Skip to content
                </a>
                <ErrorBoundary>
                  <div id="main" tabIndex={-1} style={{ display: "contents" }}>
                    <HubShell>
                      <Routes>
                        <Route path="/" element={<Navigate to={ROUTES.discover} replace />} />
                        <Route path="/signin" element={<SignIn />} />
                        <Route path={CALLBACK_PATH} element={<PageState kind="loading" text="Finishing sign-in…" />} />
                        <Route path="/403" element={<Forbidden />} />
                        <Route path={ROUTES.discover} element={guarded(<Discover />)} />
                        <Route path="/discover/:kind/:slug" element={guarded(<Listing />)} />
                        <Route path={ROUTES.assistant} element={guarded(<Assistant />)} />
                        <Route path={`${ROUTES.assistant}/:consumerId`} element={guarded(<Assistant />)} />
                        <Route path={ROUTES.workspace} element={guarded(<Workspace />)} />
                        <Route path={ROUTES.intake} element={guarded(<IntakeBrief />)} />
                        <Route path={`${ROUTES.intake}/:briefId`} element={guarded(<IntakeBrief />)} />
                        <Route path={ROUTES.learn} element={guarded(<Learn />)} />
                        <Route path={ROUTES.settings} element={guarded(<Settings />)} />
                        <Route path="*" element={<NotFound />} />
                      </Routes>
                    </HubShell>
                  </div>
                </ErrorBoundary>
              </PaletteProvider>
            </ThemeProvider>
          </AuthProvider>
        </ToastProvider>
      </Router>
    </QueryClientProvider>
  );
}
