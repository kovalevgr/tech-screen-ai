"use client";

// Client-side providers mounted once in the root layout (under <Shell>).
// React Query needs a client-component provider above any hook consumer, so
// it lives here rather than in the server-component layout.

import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

export function Providers({ children }: { children: React.ReactNode }) {
  // One QueryClient per app mount. `useState` keeps it stable across renders
  // (a module-level singleton would leak between requests on the server).
  const [queryClient] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Server state is fetched on demand; refetch on focus is noise for
            // an admin tool. Mutations explicitly invalidate the lists they
            // affect (see src/api/position-templates.ts).
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
