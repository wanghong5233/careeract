"use client";

import { createContext, useContext } from "react";

export type MessageEdit = {
  id: string;
  text: string;
  busy: boolean;
  error?: string;
  onChange: (text: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
};

export type MessageFeedback = "positive" | "negative";
export type MessageFeedbackHandler = (id: string, feedback: MessageFeedback) => void;

export const MessageActionsContext = createContext<{ quote?: (id: string, text: string) => void; addToConversation?: (text: string) => void; edit?: (id: string, text: string) => void; editId?: string; editing?: MessageEdit; branch?: (id: string) => void; feedback?: MessageFeedbackHandler }>({});
export function useMessageActions() { return useContext(MessageActionsContext); }
