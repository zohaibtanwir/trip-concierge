/**
 * shadcn-ui's standard cn() helper.
 *
 * Combines clsx (conditional className) + tailwind-merge (deduplicates
 * conflicting Tailwind utilities, e.g. `p-2 p-4` → `p-4`). Every shadcn
 * primitive imports this. Slice 4.3 components do too where they compose
 * variant classes conditionally.
 */

import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
