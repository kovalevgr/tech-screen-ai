// Stateless server component — admin shell top bar.
// Surface 1 of the chrome contract (frontend-contract.md).
// At T03 close: wordmark on the left; right side reserved for later
// tasks (user menu / search). The wordmark is the only brand-orange
// surface in this region (focus ring is the other allowlisted slot,
// rendered by the Sidebar's Button focus state).

export function TopBar() {
  return (
    <header className="flex h-16 items-center border-b border-border-subtle bg-surface-base px-6">
      <span className="font-semibold text-brand-primary">N-iX TechScreen</span>
    </header>
  );
}
