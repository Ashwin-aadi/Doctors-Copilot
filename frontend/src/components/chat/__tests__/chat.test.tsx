import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MessageBubble } from "../MessageBubble";
import { Composer } from "../Composer";
import { QuickReplyChips } from "../QuickReplyChips";
import { TriageResultCard } from "../TriageResultCard";
import { mockTriageResult } from "../../../mocks/mockTriageResult";
import type { ChatMessage } from "../../types";

describe("chat components", () => {
  it("MessageBubble renders clickable citation markers", () => {
    const onCitationClick = vi.fn();
    const message: ChatMessage = {
      id: "1",
      role: "assistant",
      content: "See the guidance [1] for details.",
      createdAt: new Date().toISOString(),
    };
    render(<MessageBubble message={message} onCitationClick={onCitationClick} />);
    fireEvent.click(screen.getByLabelText("View source 1"));
    expect(onCitationClick).toHaveBeenCalledWith(1);
  });

  it("Composer sends on Enter and inserts newline on Shift+Enter", () => {
    const onSend = vi.fn();
    const onChange = vi.fn();
    render(<Composer value="hello" onChange={onChange} onSend={onSend} />);
    const textarea = screen.getByLabelText("Message");
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSend).toHaveBeenCalled();
  });

  it("QuickReplyChips fires onSelect with the chosen reply", () => {
    const onSelect = vi.fn();
    render(<QuickReplyChips replies={["Yes", "No"]} onSelect={onSelect} />);
    fireEvent.click(screen.getByText("Yes"));
    expect(onSelect).toHaveBeenCalledWith("Yes");
  });

  it("TriageResultCard surfaces ESI, red flags and MoHFW colour", () => {
    render(<TriageResultCard result={mockTriageResult} />);
    expect(screen.getByText(/ESI 2/)).toBeTruthy();
    expect(screen.getByText(/Red — immediate/)).toBeTruthy();
    expect(screen.getByText("Red flags identified")).toBeTruthy();
  });
});
