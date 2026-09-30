import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SegmentedControl } from "./SegmentedControl";

const OPTIONS = [
  { value: "a", label: "A" },
  { value: "b", label: "B", disabled: true },
  { value: "c", label: "C" },
] as const;

describe("SegmentedControl", () => {
  it("is a radio group with one checked option", () => {
    render(<SegmentedControl ariaLabel="pick" options={OPTIONS} value="a" onChange={() => undefined} />);
    expect(screen.getByRole("radiogroup", { name: "pick" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "A" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "C" })).toHaveAttribute("aria-checked", "false");
  });

  it("moves with arrow keys, skipping disabled options", async () => {
    const onChange = vi.fn();
    render(<SegmentedControl ariaLabel="pick" options={OPTIONS} value="a" onChange={onChange} />);
    const user = userEvent.setup();
    screen.getByRole("radio", { name: "A" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("c");
    await user.keyboard("{End}");
    expect(onChange).toHaveBeenLastCalledWith("c");
    await user.keyboard("{Home}");
    expect(onChange).toHaveBeenLastCalledWith("a");
  });

  it("changes on click and ignores disabled options", async () => {
    const onChange = vi.fn();
    render(<SegmentedControl ariaLabel="pick" options={OPTIONS} value="a" onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: "C" }));
    expect(onChange).toHaveBeenCalledWith("c");
    await user.click(screen.getByRole("radio", { name: "B" }));
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
