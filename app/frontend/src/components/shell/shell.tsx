// Admin shell composition root — chrome host.
// Surface 1 of the chrome contract (frontend-contract.md).
// Composes <TopBar> + <Sidebar> + content slot. Mounted by
// app/layout.tsx so every later route inherits the chrome.
// `<Shell>` IS the chrome layer — the smoke test mounts it
// directly per the spec Clarifications "rendering pipeline" Q&A.

import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-surface-base text-content-primary">
      <TopBar />
      <div className="flex flex-1 min-h-0">
        <Sidebar />
        <main className="flex-1 min-w-0">{children}</main>
      </div>
    </div>
  );
}
