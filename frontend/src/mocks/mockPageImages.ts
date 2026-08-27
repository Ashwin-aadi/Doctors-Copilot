import type { PageImage } from "../components/types";

// 1x1 neutral-grey PNG data URIs standing in for scanned report pages --
// keeps the mock self-contained (no network fetch) while still exercising
// the bbox-overlay scaling logic against a real <img>.
const PLACEHOLDER_PAGE =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

export const mockPageImages: PageImage[] = [
  { page: 1, url: PLACEHOLDER_PAGE, width: 1240, height: 1754 },
  { page: 2, url: PLACEHOLDER_PAGE, width: 1240, height: 1754 },
];
