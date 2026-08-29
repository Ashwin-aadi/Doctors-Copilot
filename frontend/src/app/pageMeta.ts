/**
 * What the top bar says you are looking at.
 *
 * Derived from the path rather than set by each screen, so a page that forgets
 * to declare a title still gets one and the bar never renders empty. Longest
 * matching prefix wins, which lets `/doctor/queue` win over `/doctor`.
 */
const TITLES: Array<[string, string]> = [
  ["/chat/assistant", "pageTitles.assistant"],
  ["/chat", "pageTitles.triage"],
  ["/booking", "pageTitles.booking"],
  ["/portal", "pageTitles.portal"],
  ["/visit", "pageTitles.visit"],
  ["/doctor/queue", "pageTitles.queue"],
  ["/doctor/lab-order", "pageTitles.labOrder"],
  ["/doctor/visit", "pageTitles.visit"],
  ["/doctor/patient", "pageTitles.patient"],
  ["/doctor", "pageTitles.doctorHome"],
  ["/onboarding", "pageTitles.onboarding"],
];

export function pageTitleKey(pathname: string): string {
  let best = "";
  let key = "app.name";
  for (const [prefix, titleKey] of TITLES) {
    if (pathname === prefix || pathname.startsWith(`${prefix}/`)) {
      if (prefix.length > best.length) {
        best = prefix;
        key = titleKey;
      }
    }
  }
  return key;
}
