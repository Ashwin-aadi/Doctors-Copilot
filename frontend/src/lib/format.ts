import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";

dayjs.extend(utc);
dayjs.extend(timezone);

const IST = "Asia/Kolkata";

const inrFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

export function formatInr(amount: number): string {
  return inrFormatter.format(amount);
}

export function formatDateIst(value: string | Date): string {
  return dayjs(value).tz(IST).format("DD/MM/YYYY");
}

export function formatTimeIst(value: string | Date): string {
  return dayjs(value).tz(IST).format("h:mm A");
}

export function formatDateTimeIst(value: string | Date): string {
  return dayjs(value).tz(IST).format("DD/MM/YYYY, h:mm A");
}

export function formatKm(distanceKm: number): string {
  return `${distanceKm.toFixed(1)} km`;
}

export function formatPhone(e164: string): string {
  const digits = e164.replace(/^\+91/, "");
  if (digits.length !== 10) return e164;
  return `+91 ${digits.slice(0, 5)} ${digits.slice(5)}`;
}

export function formatAbha(id: string): string {
  const digits = id.replace(/\D/g, "");
  if (digits.length !== 14) return id;
  return `${digits.slice(0, 2)}-${digits.slice(2, 6)}-${digits.slice(6, 10)}-${digits.slice(10)}`;
}

export function isValidPincode(value: string): boolean {
  return /^\d{6}$/.test(value);
}
