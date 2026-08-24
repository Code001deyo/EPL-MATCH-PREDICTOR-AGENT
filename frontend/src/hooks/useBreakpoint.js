import useMediaQuery from "./useMediaQuery";
import { bp } from "../theme";

/* One place that decides what "narrow" means, so panels and the shell agree. */
export function useIsNarrow() {
  return useMediaQuery(`(max-width: ${bp.md}px)`);
}

export function useIsCompact() {
  return useMediaQuery(`(max-width: ${bp.lg}px)`);
}
