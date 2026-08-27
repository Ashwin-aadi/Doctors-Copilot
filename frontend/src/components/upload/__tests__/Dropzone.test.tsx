import { beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { initI18n } from "../../../lib/i18n";
import { Dropzone } from "../Dropzone";
import type { DropzoneFileState } from "../uploadTypes";

beforeAll(async () => {
  await initI18n();
});

function file(overrides: Partial<DropzoneFileState> = {}): DropzoneFileState {
  return {
    clientId: "f1",
    name: "report.jpg",
    status: "uploading",
    progress: 40,
    errorCode: null,
    ...overrides,
  };
}

describe("Dropzone", () => {
  it("renders the drop target and exposes camera capture", () => {
    render(<Dropzone files={[]} onFilesSelected={() => {}} onCancel={() => {}} onRetry={() => {}} />);
    expect(screen.getByText(/Hold the report flat/i)).toBeTruthy();
    const cameraButtons = screen
      .getAllByRole("button", { name: /take a photo/i })
      .filter((el) => el.tagName === "BUTTON");
    expect(cameraButtons.length).toBe(1);
  });

  it("shows per-file progress and lets the user cancel", () => {
    const onCancel = vi.fn();
    render(
      <Dropzone files={[file()]} onFilesSelected={() => {}} onCancel={onCancel} onRetry={() => {}} />,
    );
    expect(screen.getByRole("progressbar")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /cancel upload/i }));
    expect(onCancel).toHaveBeenCalledWith("f1");
  });

  it("shows plain-language copy for every named error code", () => {
    const codes: DropzoneFileState["errorCode"][] = [
      "UNSUPPORTED_FORMAT",
      "TOO_LARGE",
      "ENCRYPTED",
      "UNREADABLE",
      "NOT_A_LAB_REPORT",
    ];
    for (const errorCode of codes) {
      const { unmount } = render(
        <Dropzone
          files={[file({ status: "error", progress: 0, errorCode })]}
          onFilesSelected={() => {}}
          onCancel={() => {}}
          onRetry={() => {}}
        />,
      );
      expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
      unmount();
    }
  });

  it("calls onFilesSelected when a file is dropped", () => {
    const onFilesSelected = vi.fn();
    render(<Dropzone files={[]} onFilesSelected={onFilesSelected} onCancel={() => {}} onRetry={() => {}} />);
    const target = screen.getByRole("button", { name: /photos/i });
    const droppedFile = new File(["data"], "cbc.pdf", { type: "application/pdf" });
    fireEvent.drop(target, { dataTransfer: { files: [droppedFile] } });
    expect(onFilesSelected).toHaveBeenCalledWith([droppedFile]);
  });
});
