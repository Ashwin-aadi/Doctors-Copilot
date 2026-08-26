import type { PreviewState } from "../PreviewPage";

export function StatesSection({ state }: { state: PreviewState }) {
  return (
    <p className="text-sm text-fg-muted">
      Per-screen loading / empty / error / success coverage lands in CP2 (
      <code className="text-xs">D2.5</code>). Current toggle: <strong>{state}</strong>.
    </p>
  );
}
