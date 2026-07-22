import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MessageBubble, StreamingBubble } from "@/components/chat/message-bubble";
import type { MessageRecord } from "@/lib/api/types";

function makeMessage(overrides: Partial<MessageRecord> = {}): MessageRecord {
  return {
    id: "msg-1",
    conversation_id: "conv-1",
    role: "user",
    content: "Hello Odin",
    name: null,
    tool_call_id: null,
    metadata: {},
    prompt_tokens: 0,
    completion_tokens: 0,
    total_tokens: 0,
    provider: null,
    model: null,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("MessageBubble", () => {
  it("renders user message content", () => {
    render(<MessageBubble message={makeMessage({ content: "Hello Odin" })} />);
    expect(screen.getByText("Hello Odin")).toBeInTheDocument();
  });

  it("renders assistant message with markdown", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "**Bold text** and `inline code`",
        })}
      />,
    );
    expect(screen.getByText("Bold text")).toBeInTheDocument();
  });

  it("shows token count for assistant messages with usage", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "Response",
          prompt_tokens: 10,
          completion_tokens: 20,
          total_tokens: 30,
        })}
      />,
    );
    expect(screen.getByText(/30 tokens/)).toBeInTheDocument();
  });

  it("shows model name when present", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "Response",
          prompt_tokens: 8,
          completion_tokens: 2,
          total_tokens: 10,
          model: "openai/gpt-4o",
        })}
      />,
    );
    expect(screen.getByText(/gpt-4o/)).toBeInTheDocument();
  });

  it("renders regenerate button for assistant messages", () => {
    const onRegenerate = vi.fn();
    render(
      <MessageBubble
        message={makeMessage({ role: "assistant", content: "Reply" })}
        onRegenerate={onRegenerate}
      />,
    );
    const btn = screen.getByTitle("Regenerate");
    expect(btn).toBeInTheDocument();
  });

  it("renders edit button for user messages", () => {
    const onEdit = vi.fn();
    render(
      <MessageBubble
        message={makeMessage({ role: "user", content: "Hello" })}
        onEdit={onEdit}
      />,
    );
    expect(screen.getByTitle("Edit and resend")).toBeInTheDocument();
  });

  it("enters edit mode and calls onEdit on submit", async () => {
    const onEdit = vi.fn();
    const user = userEvent.setup();
    render(
      <MessageBubble
        message={makeMessage({ role: "user", content: "Original" })}
        onEdit={onEdit}
      />,
    );

    await user.click(screen.getByTitle("Edit and resend"));
    const textarea = screen.getByRole("textbox");
    await user.clear(textarea);
    await user.type(textarea, "Edited message");
    await user.click(screen.getByText("Send"));

    expect(onEdit).toHaveBeenCalledWith("Edited message");
  });

  it("renders code block with language label and copy button", () => {
    render(
      <MessageBubble
        message={makeMessage({
          role: "assistant",
          content: "```python\nprint('hello')\n```",
        })}
      />,
    );
    expect(screen.getByText("python")).toBeInTheDocument();
    expect(screen.getByLabelText("Copy code")).toBeInTheDocument();
  });
});

describe("StreamingBubble", () => {
  it("renders streaming content", () => {
    render(<StreamingBubble content="Partial response…" />);
    expect(screen.getByText("Partial response…")).toBeInTheDocument();
  });

  it("shows loading dots when content is empty", () => {
    const { container } = render(<StreamingBubble content="" />);
    expect(container.querySelectorAll(".animate-bounce")).toHaveLength(3);
  });
});
