import type { NotificationItem } from "../components/types";

export const mockNotifications: NotificationItem[] = [
  { id: "n1", type: "queue", title: "You're next in line", body: "Dr. Kavita Rao will see you in about 5 minutes.", readAt: null, createdAt: "2026-08-26T09:40:00Z" },
  { id: "n2", type: "lab_order", title: "Lab order approved", body: "Your dengue NS1 and CBC tests were approved by Dr. Rao.", readAt: null, createdAt: "2026-08-26T09:10:00Z" },
  { id: "n3", type: "prescription", title: "Prescription ready", body: "Your prescription has been locked and is ready to download.", readAt: "2026-08-25T18:05:00Z", createdAt: "2026-08-25T18:00:00Z" },
];
