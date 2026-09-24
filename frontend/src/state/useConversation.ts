import { useCallback, useSyncExternalStore } from "react";
import {
  ask as askInThread,
  clear as clearThread,
  subscribe,
  threadFor,
} from "./conversationStore";
export type { Exchange } from "./conversationStore";
export function useConversation(documentId: string) {
  const thread = useSyncExternalStore(
    subscribe,
    () => threadFor(documentId),
    () => threadFor(documentId),
  );
  const ask = useCallback(
    (question: string) => askInThread(documentId, question),
    [documentId],
  );
  const clear = useCallback(() => clearThread(documentId), [documentId]);
  return {
    exchanges: thread.exchanges,
    pending: thread.pending,
    error: thread.error,
    ask,
    clear,
  };
}
