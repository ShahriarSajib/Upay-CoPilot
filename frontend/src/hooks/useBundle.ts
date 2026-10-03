import { useMemo } from "react";
import type { CopilotBundle } from "@/engines";
import { buildBundle } from "@/engines";
import { useCopilot } from "@/data/store";

/**
 * One bundle per selected customer.
 *
 * Every engine is pure and deterministic, so the whole Financial Context Engine
 * is memoised on the context object: switching language or persona on the same
 * customer does not recompute anything.
 */
export function useBundle(): CopilotBundle | null {
  const { ctx } = useCopilot();
  return useMemo(() => (ctx ? buildBundle(ctx) : null), [ctx]);
}