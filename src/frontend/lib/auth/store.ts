'use client';

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { AuthUser } from '@/lib/api/types';

interface AuthState {
  accessToken: string | null;
  user: AuthUser | null;
  hydrated: boolean;
  setAuth: (token: string, user: AuthUser) => void;
  clearAuth: () => void;
  markHydrated: () => void;
  isAuthenticated: () => boolean;
}

/**
 * Zustand store for auth. Persists to sessionStorage so a tab keeps its
 * token, but a new tab must re-authenticate.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      user: null,
      hydrated: false,
      setAuth: (token, user) => set({ accessToken: token, user }),
      clearAuth: () => set({ accessToken: null, user: null }),
      markHydrated: () => set({ hydrated: true }),
      isAuthenticated: () => Boolean(get().accessToken),
    }),
    {
      name: 'bid-framework-auth',
      storage: createJSONStorage(() => {
        if (typeof window === 'undefined') {
          // SSR no-op storage — zustand persist calls only getItem during
          // hydration, so the missing length/clear/key members are safe.
          return {
            getItem: () => null,
            setItem: () => undefined,
            removeItem: () => undefined,
          } as unknown as Storage;
        }
        return window.sessionStorage;
      }),
      partialize: (state) => ({
        accessToken: state.accessToken,
        user: state.user,
      }),
      onRehydrateStorage: () => (state) => {
        state?.markHydrated();
      },
    },
  ),
);
