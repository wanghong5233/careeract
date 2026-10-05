"use client";

import { createContext, useContext } from "react";

export const MessageActionsContext = createContext<{ quote?: (id: string, text: string) => void; edit?: (id: string, text: string) => void; editId?: string; branch?: (id: string) => void }>({});
export function useMessageActions() { return useContext(MessageActionsContext); }
