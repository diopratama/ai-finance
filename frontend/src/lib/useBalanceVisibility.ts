"use client";

import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "ai_finance_balance_visibility_v1";
const SYNC_EVENT = "ai-finance-balance-visibility-change";

export interface BalanceVisibilityState {
  hideAll: boolean;
  overrides: Record<string, boolean>;
}

const DEFAULT_STATE: BalanceVisibilityState = {
  hideAll: false,
  overrides: {},
};

function readStoredState(): BalanceVisibilityState {
  if (typeof window === "undefined") return DEFAULT_STATE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_STATE;
    const parsed = JSON.parse(raw);
    return {
      hideAll: Boolean(parsed?.hideAll),
      overrides:
        parsed?.overrides && typeof parsed.overrides === "object" && !Array.isArray(parsed.overrides)
          ? parsed.overrides
          : {},
    };
  } catch {
    return DEFAULT_STATE;
  }
}

function writeStoredState(next: BalanceVisibilityState) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    window.dispatchEvent(new CustomEvent(SYNC_EVENT, { detail: next }));
  } catch {
    // Ignore storage quota or private mode errors
  }
}

/**
 * Manages persistent global and per-wallet balance visibility in localStorage.
 */
export function useBalanceVisibility() {
  const [state, setState] = useState<BalanceVisibilityState>(DEFAULT_STATE);

  useEffect(() => {
    setState(readStoredState());

    const handleSync = (event: Event) => {
      const customEvent = event as CustomEvent<BalanceVisibilityState>;
      if (customEvent.detail) {
        setState(customEvent.detail);
      } else {
        setState(readStoredState());
      }
    };

    const handleStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) {
        setState(readStoredState());
      }
    };

    window.addEventListener(SYNC_EVENT, handleSync);
    window.addEventListener("storage", handleStorage);
    return () => {
      window.removeEventListener(SYNC_EVENT, handleSync);
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  const isWalletHidden = useCallback(
    (walletId: string): boolean => {
      if (Object.prototype.hasOwnProperty.call(state.overrides, walletId)) {
        return Boolean(state.overrides[walletId]);
      }
      return state.hideAll;
    },
    [state]
  );

  const toggleHideAll = useCallback(() => {
    setState((prev) => {
      const next: BalanceVisibilityState = {
        hideAll: !prev.hideAll,
        overrides: {},
      };
      writeStoredState(next);
      return next;
    });
  }, []);

  const toggleWalletVisibility = useCallback((walletId: string) => {
    setState((prev) => {
      const currentlyHidden = Object.prototype.hasOwnProperty.call(prev.overrides, walletId)
        ? Boolean(prev.overrides[walletId])
        : prev.hideAll;
      const next: BalanceVisibilityState = {
        ...prev,
        overrides: {
          ...prev.overrides,
          [walletId]: !currentlyHidden,
        },
      };
      writeStoredState(next);
      return next;
    });
  }, []);

  return {
    hideAll: state.hideAll,
    isWalletHidden,
    toggleHideAll,
    toggleWalletVisibility,
  };
}

