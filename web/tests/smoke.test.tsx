import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import Page from "../app/page";

test("home page renders the Trip Concierge heading", () => {
  render(<Page />);
  const heading = screen.getByRole("heading", { level: 1 });
  expect(heading.textContent).toBe("Trip Concierge");
});
