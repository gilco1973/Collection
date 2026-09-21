import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthProvider, useAuth } from "./AuthProvider";
import type { AuthClient } from "./provider";
import { RequireAuth } from "./RequireAuth";

// An OIDC client whose redirect fails (discovery document unreachable, misconfigured authority).
const failing: AuthClient = {
  initialize: async () => ({ status: "signed-out" }),
  signIn: async () => {
    throw new Error("Failed to fetch .well-known/openid-configuration");
  },
  completeSignIn: async () => ({ snapshot: { status: "signed-out" } }),
  signOut: async () => {},
  getAccessToken: async () => undefined,
  subscribe: () => () => {},
  isCallbackUrl: () => false,
};

describe("signIn failure", () => {
  it("does not leave the app stuck on 'Signing you in…': the snapshot records the error and signIn rejects", async () => {
    const rejections: string[] = [];
    const SignInPage = () => {
      const { signIn, snapshot } = useAuth();
      return (
        <div>
          <button onClick={() => void signIn({ returnTo: "/workspace" }).catch((e: Error) => rejections.push(e.message))}>go</button>
          <p>status:{snapshot.status}</p>
          <p>error:{snapshot.error ?? ""}</p>
        </div>
      );
    };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/signin"]}>
          <AuthProvider deps={{ client: failing, fetchPrincipal: async () => { throw new Error("no"); } }}>
            <Routes>
              <Route path="/signin" element={<SignInPage />} />
              <Route path="/workspace" element={<RequireAuth><p>ws</p></RequireAuth>} />
            </Routes>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByText("status:signed-out");
    screen.getByText("go").click();
    await screen.findByText("status:signing-in");
    await screen.findByText("status:error");
    expect(screen.getByText(/^error:/).textContent).toBe("error:Failed to fetch .well-known/openid-configuration");
    expect(rejections).toEqual(["Failed to fetch .well-known/openid-configuration"]);
  });
});
