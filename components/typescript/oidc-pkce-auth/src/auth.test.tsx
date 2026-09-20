import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthProvider, useAuth } from "./AuthProvider";
import { PRINCIPALS } from "./fixtures";
import { createMockClient } from "./mock";
import { RequireAuth } from "./RequireAuth";

function app(start: string, persona?: string, forbid = false) {
  const client = createMockClient();
  if (persona) window.sessionStorage.setItem("crai.hub.mockPersona", persona);
  else window.sessionStorage.clear();
  const fetchPrincipal = async () => {
    const id = (await client.getAccessToken())?.slice(5) ?? "";
    if (forbid) throw Object.assign(new Error("Your role does not allow this."), { status: 403 });
    return PRINCIPALS[id];
  };
  const Page = () => {
    const { principal, can } = useAuth();
    return <h1>{principal?.name} · lead:{String(can("brief.file"))}</h1>;
  };
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[start]}>
        <AuthProvider deps={{ client, fetchPrincipal }}>
          <Routes>
            <Route path="/signin" element={<p>sign in page</p>} />
            <Route path="/403" element={<p>forbidden page</p>} />
            <Route path="/workspace" element={<RequireAuth action="hub.workspace"><Page /></RequireAuth>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AuthProvider + RequireAuth", () => {
  it("sends a signed-out person to sign in with a return path", async () => {
    app("/workspace");
    await waitFor(() => expect(screen.getByText("sign in page")).toBeTruthy());
  });
  it("renders the page once the principal resolves and exposes permits", async () => {
    app("/workspace", "gk");
    await waitFor(() => expect(screen.getByText("Gil K. · lead:true")).toBeTruthy());
  });
  it("sends a person the platform refuses to the forbidden page", async () => {
    app("/workspace", "employee", true);
    await waitFor(() => expect(screen.getByText("forbidden page")).toBeTruthy());
  });
});
