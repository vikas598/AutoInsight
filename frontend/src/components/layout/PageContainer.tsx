// PageContainer — scrollable content region with the standard page gutter
// and max width. Pages that manage their own scrolling (the AI Analyst)
// don't use it.

import type { ReactNode } from "react";

export function PageContainer({ children }: { children: ReactNode }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-content px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        {children}
      </div>
    </div>
  );
}
