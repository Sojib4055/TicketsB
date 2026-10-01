export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    signal,
    ...(body === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Ticket-Request": "1",
          },
          body: JSON.stringify(body),
        }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new ApiError(
      data.error || "We couldn’t complete that request. Please try again.",
      response.status,
    );
  return data as T;
}
export const money = (value: string | number = 0) =>
  new Intl.NumberFormat("en-BD", { maximumFractionDigits: 2 }).format(
    Number(value),
  );
export const localDateTime = (value = new Date()) =>
  new Date(value.getTime() + 6 * 3600000).toISOString().slice(0, 16);
export const today = () => localDateTime().slice(0, 10);
export const dateOffset = (days: number, base = today()) =>
  new Date(new Date(base + "T12:00:00+06:00").getTime() + days * 86400000)
    .toISOString()
    .slice(0, 10);
export const dateLabel = (
  value: string | number,
  options: Intl.DateTimeFormatOptions = {},
) =>
  new Date(typeof value === "number" ? value * 1000 : value).toLocaleString(
    "en-GB",
    { timeZone: "Asia/Dhaka", day: "numeric", month: "short", ...options },
  );
export const when = (value: string | number) =>
  dateLabel(value, { hour: "2-digit", minute: "2-digit" });
export function minutes(value: string) {
  const match = value.match(/(\d{1,2}):(\d{2})\s*(AM|PM)?/i);
  if (!match) return 1440;
  let hour = Number(match[1]);
  if (match[3]) hour = (hour % 12) + (match[3].toUpperCase() === "PM" ? 12 : 0);
  return hour * 60 + Number(match[2]);
}
export const clockTime = (value: string) =>
  `${String(Math.floor(minutes(value) / 60)).padStart(2, "0")}:${String(minutes(value) % 60).padStart(2, "0")}`;
export const busType = (value: string) =>
  /non[ -]?ac/i.test(value) ? "Non AC" : /\bac\b/i.test(value) ? "AC" : "Other";
export const statusLabel: Record<string, string> = {
  SCHEDULED: "Scheduled",
  MONITORING: "Watching for seats",
  PREPARING: "Preparing booking",
  AWAITING_PAYMENT: "Payment required",
  NEEDS_ATTENTION: "Needs attention",
  PAUSED: "Paused",
  CONFIRMED: "Confirmed",
  CANCELLED: "Closed",
  EXPIRED: "Window ended",
};
export const alertLabel: Record<string, string> = {
  preview: "Demo preview · not sent",
  not_requested: "Website only",
  setup_required: "Setup required",
  queued: "Queued",
  sending: "Sending",
  accepted: "Accepted by WhatsApp",
  sent: "Sent",
  delivered: "Delivered",
  read: "Read",
  failed: "Delivery failed",
  unknown: "Delivery unknown",
  retrying: "Retry scheduled",
  expired: "Expired · not sent",
};
