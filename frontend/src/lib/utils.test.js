import { cn } from "./utils";

describe("cn", () => {
  test("merges class names and resolves tailwind conflicts", () => {
    expect(cn("px-2", "px-4", "font-bold", false && "hidden")).toBe("px-4 font-bold");
  });
});
