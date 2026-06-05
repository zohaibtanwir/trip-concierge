/**
 * BlockExpand — responsive expand-on-tap wrapper for a TripBlock.
 *
 * Slice 4.3. Renders shadcn Sheet (mobile, side="bottom") OR Dialog
 * (desktop) based on viewport. Both render <BlockDetail /> as the body.
 *
 * The responsive switch lives in a useMediaQuery hook at the parent
 * level; this component accepts a `forceVariant` prop so tests can
 * pin each variant without simulating viewport changes (jsdom doesn't
 * fully simulate media queries). Production callers pass the resolved
 * variant from the hook.
 */

"use client";

import type { ReactNode } from "react";

import { BlockDetail } from "@/components/block-detail";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import type { Block } from "@/lib/backend";

interface BlockExpandProps {
  block: Block;
  forceVariant?: "sheet" | "dialog";
  defaultOpen?: boolean;
  children: ReactNode;
}

export function BlockExpand({
  block,
  forceVariant = "sheet",
  defaultOpen,
  children,
}: BlockExpandProps) {
  if (forceVariant === "dialog") {
    return (
      <Dialog defaultOpen={defaultOpen}>
        <DialogTrigger render={<span>{children}</span>} />
        <DialogContent>
          <BlockDetail block={block} />
        </DialogContent>
      </Dialog>
    );
  }
  return (
    <Sheet defaultOpen={defaultOpen}>
      <SheetTrigger render={<span>{children}</span>} />
      <SheetContent side="bottom">
        <BlockDetail block={block} />
      </SheetContent>
    </Sheet>
  );
}
