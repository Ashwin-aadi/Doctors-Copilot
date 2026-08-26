import type { QueueEntryOut } from "../components/types";

const names = [
  "Ananya Sharma", "Rohit Verma", "Fatima Sheikh", "Karthik Iyer",
  "Priya Nair", "Suresh Patil", "Meera Joshi", "Arjun Reddy",
];

export const mockQueue: QueueEntryOut[] = names.map((patient_name, i) => ({
  id: `00000000-0000-0000-0000-0000000008${String(i).padStart(2, "0")}`,
  patient_id: `00000000-0000-0000-0000-0000000010${i}`,
  patient_name,
  doctor_id: "00000000-0000-0000-0000-000000000201",
  clinic_id: "00000000-0000-0000-0000-000000000001",
  severity_esi: i === 0 ? 1 : ((i % 5) + 1),
  triage_colour: i === 0 ? "red" : i % 5 < 2 ? "red" : i % 5 < 4 ? "yellow" : "green",
  emergency: i === 0,
  position: i + 1,
  waited_minutes: i * 6,
  estimated_wait_minutes: Math.max(0, 30 - i * 4),
  status: i === 1 ? "in_consult" : "waiting",
  reasons: i === 0 ? ["Chest pain with breathlessness", "Escalated by triage RAG"] : ["Routine OPD queue position"],
  reasons_hi: i === 0
    ? ["सांस फूलने के साथ सीने में दर्द", "ट्रायज आरएजी द्वारा एस्केलेट किया गया"]
    : ["नियमित ओपीडी कतार स्थिति"],
  token: `D-${String(i + 1).padStart(3, "0")}`,
}));
