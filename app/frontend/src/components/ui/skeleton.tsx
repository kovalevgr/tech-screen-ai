import * as React from "react"

import { cn } from "@/lib/cn"

// Loading placeholder. Owns the `animate-pulse` motion so feature code never
// writes the bare utility (no-decorative-animation pre-commit hook carves out
// components/ui/skeleton*). Shape/size come from `className`; the default
// rounded-md + bg-surface-muted are overridable via tailwind-merge.
function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-surface-muted", className)}
      {...props}
    />
  )
}

export { Skeleton }
