// Stateless server component — admin shell sidebar.
// Surface 1 of the chrome contract (frontend-contract.md).
// At T03 close: three placeholder nav items rendered as ghost
// Buttons. Real routes arrive in later tasks; the structural slot
// is permanent. Focus ring (the second allowlisted brand-orange
// surface) is rendered by the Button primitive's `:focus-visible`
// state via `--ring`.

import { Button } from "@/components/ui/button";

const NAV_ITEMS = ["Dashboard", "Sessions", "Settings"] as const;

export function Sidebar() {
  return (
    <aside className="w-60 border-r border-border-subtle bg-surface-raised p-4">
      <nav>
        <ul className="flex flex-col gap-1">
          {NAV_ITEMS.map((label) => (
            <li key={label}>
              <Button variant="ghost" className="w-full justify-start">
                {label}
              </Button>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}
