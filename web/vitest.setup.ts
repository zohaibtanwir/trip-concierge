/**
 * Vitest setup — hotfix-nwk infrastructure (2026-06-08).
 *
 * jsdom does not implement HTMLDialogElement.showModal / close. The
 * production code uses try/catch to absorb the resulting TypeError,
 * which had the side effect of also hiding the real-browser
 * InvalidStateError bug (showModal called on a dialog that already
 * has the `open` attribute throws — per MDN) for 4 slices.
 *
 * This polyfill mirrors real-browser semantics in jsdom so tests can
 * assert modal-mode entry. The showModal implementation specifically
 * THROWS InvalidStateError when the dialog already has `open`, which
 * is the exact failure mode hotfix-nwk fixes. Tests using
 * `vi.spyOn(HTMLDialogElement.prototype, "showModal")` can then
 * observe `mock.results[N].type === "return"` to assert the call
 * succeeded (i.e., dialog entered modal mode cleanly).
 *
 * Per banked observation from hotfix-nwk: workarounds for test
 * infrastructure should also be tested at the level they bypass.
 * The previous try/catch silently swallowed both the jsdom TypeError
 * AND the real-browser InvalidStateError; future test infrastructure
 * gaps should be explicit (polyfilled with matching semantics), not
 * silent (swallowed and forgotten).
 */

if (typeof HTMLDialogElement !== "undefined") {
  if (typeof HTMLDialogElement.prototype.showModal === "undefined") {
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
      configurable: true,
      writable: true,
      value: function showModal(this: HTMLDialogElement): void {
        if (this.hasAttribute("open")) {
          throw new DOMException(
            "Failed to execute 'showModal' on 'HTMLDialogElement': The element already has an 'open' attribute, and therefore cannot be opened modally.",
            "InvalidStateError",
          );
        }
        this.setAttribute("open", "");
      },
    });
  }
  if (typeof HTMLDialogElement.prototype.close === "undefined") {
    Object.defineProperty(HTMLDialogElement.prototype, "close", {
      configurable: true,
      writable: true,
      value: function close(this: HTMLDialogElement): void {
        if (!this.hasAttribute("open")) return;
        this.removeAttribute("open");
        this.dispatchEvent(new Event("close"));
      },
    });
  }
}
