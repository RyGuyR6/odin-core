import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConversationSidebar } from "@/components/chat/conversation-sidebar";
import type { ConversationRecord } from "@/lib/api/types";

function makeConversation(overrides: Partial<ConversationRecord> = {}): ConversationRecord {
  return {
    id: "conv-1",
    title: "Test conversation",
    user_id: null,
    summary: null,
    metadata: {},
    archived: false,
    deleted_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    message_count: 3,
    ...overrides,
  };
}

describe("ConversationSidebar", () => {
  const noop = () => Promise.resolve();

  it("renders New Chat button", () => {
    render(
      <ConversationSidebar
        conversations={[]}
        activeId={null}
        onSelect={noop}
        onNewChat={noop}
        onRename={noop}
        onArchive={noop}
        onDelete={noop}
      />,
    );
    expect(screen.getByText("New Chat")).toBeInTheDocument();
  });

  it("renders conversation list", () => {
    render(
      <ConversationSidebar
        conversations={[makeConversation({ title: "My conversation" })]}
        activeId={null}
        onSelect={noop}
        onNewChat={noop}
        onRename={noop}
        onArchive={noop}
        onDelete={noop}
      />,
    );
    expect(screen.getByText("My conversation")).toBeInTheDocument();
  });

  it("filters conversations by search query", async () => {
    const user = userEvent.setup();
    render(
      <ConversationSidebar
        conversations={[
          makeConversation({ id: "1", title: "React hooks guide" }),
          makeConversation({ id: "2", title: "Python testing" }),
        ]}
        activeId={null}
        onSelect={noop}
        onNewChat={noop}
        onRename={noop}
        onArchive={noop}
        onDelete={noop}
      />,
    );

    const search = screen.getByPlaceholderText("Search conversations…");
    await user.type(search, "React");

    expect(screen.getByText("React hooks guide")).toBeInTheDocument();
    expect(screen.queryByText("Python testing")).not.toBeInTheDocument();
  });

  it("calls onNewChat when button clicked", async () => {
    const onNewChat = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(
      <ConversationSidebar
        conversations={[]}
        activeId={null}
        onSelect={noop}
        onNewChat={onNewChat}
        onRename={noop}
        onArchive={noop}
        onDelete={noop}
      />,
    );

    await user.click(screen.getByText("New Chat"));
    expect(onNewChat).toHaveBeenCalledOnce();
  });

  it("highlights active conversation", () => {
    render(
      <ConversationSidebar
        conversations={[makeConversation({ id: "active-1", title: "Active chat" })]}
        activeId="active-1"
        onSelect={noop}
        onNewChat={noop}
        onRename={noop}
        onArchive={noop}
        onDelete={noop}
      />,
    );
    const item = screen.getByText("Active chat").closest("div[class*='cursor-pointer']");
    expect(item?.className).toContain("violet");
  });

  it("does not show archived conversations by default", () => {
    render(
      <ConversationSidebar
        conversations={[
          makeConversation({ id: "1", title: "Active", archived: false }),
          makeConversation({ id: "2", title: "Archived chat", archived: true }),
        ]}
        activeId={null}
        onSelect={noop}
        onNewChat={noop}
        onRename={noop}
        onArchive={noop}
        onDelete={noop}
      />,
    );
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Archived chat")).not.toBeInTheDocument();
  });

  it("shows loading skeletons when loading=true", () => {
    const { container } = render(
      <ConversationSidebar
        conversations={[]}
        activeId={null}
        onSelect={noop}
        onNewChat={noop}
        onRename={noop}
        onArchive={noop}
        onDelete={noop}
        loading
      />,
    );
    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(3);
  });

  it("shows empty state when no conversations", () => {
    render(
      <ConversationSidebar
        conversations={[]}
        activeId={null}
        onSelect={noop}
        onNewChat={noop}
        onRename={noop}
        onArchive={noop}
        onDelete={noop}
      />,
    );
    expect(screen.getByText("No conversations yet.")).toBeInTheDocument();
  });

  it("calls onSelect when clicking a conversation", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();

    render(
      <ConversationSidebar
        conversations={[makeConversation({ id: "sel-1", title: "Click me" })]}
        activeId={null}
        onSelect={onSelect}
        onNewChat={noop}
        onRename={noop}
        onArchive={noop}
        onDelete={noop}
      />,
    );

    await user.click(screen.getByText("Click me"));
    expect(onSelect).toHaveBeenCalledWith("sel-1");
  });

  it("shows message count in conversation item", () => {
    render(
      <ConversationSidebar
        conversations={[makeConversation({ id: "1", title: "Count test", message_count: 7 })]}
        activeId={null}
        onSelect={noop}
        onNewChat={noop}
        onRename={noop}
        onArchive={noop}
        onDelete={noop}
      />,
    );
    expect(screen.getByText(/7 msgs/)).toBeInTheDocument();
  });
});
