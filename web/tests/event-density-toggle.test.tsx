/**
 * <EventDensityToggle /> tests — slice 4.7-theater commit 2.
 *
 * Two-state toggle: "major" (default — task_completed + callback_summary
 * only, clean demo narrative) vs "all" (engineering-depth, every step
 * event). Persists choice to sessionStorage per-tab so the user's
 * density preference survives polling refreshes but resets across
 * tabs/sessions.
 *
 * Parent owns the application of the filter; this component just
 * surfaces the toggle UI + persists the choice + calls back on change.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

beforeEach(() => {
  sessionStorage.clear();
});

describe("<EventDensityToggle />", () => {
  it("renders 'major' as the default mode and 'all' as a toggleable alternative", async () => {
    // sessionStorage empty → default to "major" (clean demo narrative
    // per Q-impl-249-e=A). User toggles to "all" for engineering-depth.
    const { EventDensityToggle } = await import("@/components/event-density-toggle");
    const onChange = vi.fn();
    render(<EventDensityToggle onChange={onChange} />);

    // Both options visible; "major" is the active/pressed state.
    const majorBtn = screen.getByRole("button", { name: /major|key|important/i });
    const allBtn = screen.getByRole("button", { name: /^all$|everything|show all/i });
    expect(majorBtn.getAttribute("aria-pressed")).toBe("true");
    expect(allBtn.getAttribute("aria-pressed")).toBe("false");
  });

  it("clicking 'all' fires onChange + persists choice to sessionStorage", async () => {
    // sessionStorage key: "theater-density". Value: "major" | "all".
    // Persistence per-session (not localStorage) means the user's
    // toggle survives polling refreshes within the tab but doesn't
    // bleed across tabs — appropriate for a transient demo preference.
    const { EventDensityToggle } = await import("@/components/event-density-toggle");
    const onChange = vi.fn();
    render(<EventDensityToggle onChange={onChange} />);

    const allBtn = screen.getByRole("button", { name: /^all$|everything|show all/i });
    fireEvent.click(allBtn);

    expect(onChange).toHaveBeenCalledWith("all");
    expect(sessionStorage.getItem("theater-density")).toBe("all");
  });

  it("renders nothing during SSR — avoids hydration mismatch (hotfix-0pj)", async () => {
    // sessionStorage is unavailable on the server. Reading it in the
    // useState initializer caused a hydration mismatch when the client
    // first render returned a different value than the server's default.
    // Mounted-flag pattern: render null until useEffect fires post-mount.
    // The SSR render path (renderToString) verifies the server-side output
    // is empty — guaranteeing client first render matches.
    const { renderToString } = await import("react-dom/server");
    const { EventDensityToggle } = await import("@/components/event-density-toggle");
    const onChange = vi.fn();
    const html = renderToString(<EventDensityToggle onChange={onChange} />);
    // Empty output: no Major/All buttons, no role="group" container,
    // nothing for the server-vs-client diff to catch on.
    expect(html).toBe("");
  });
});
