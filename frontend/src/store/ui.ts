import { create } from "zustand";

export type Theme = "light" | "dark";

interface UiState {
  theme: Theme;
  modal: string | null;
  setTheme: (theme: Theme) => void;
  openModal: (id: string) => void;
  closeModal: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  theme: "light",
  modal: null,
  setTheme: (theme) => set({ theme }),
  openModal: (id) => set({ modal: id }),
  closeModal: () => set({ modal: null }),
}));
