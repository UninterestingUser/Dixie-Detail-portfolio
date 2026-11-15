// Times, not money: minutes on site shown as hours, and dates. The only
// file in this folder that does arithmetic, and it never touches a price.

export function hoursText(minutes, fullDay) {
  if (fullDay) return "Full day";
  if (minutes == null) return "";
  const quarters = Math.round(minutes / 15) / 4;
  const shown = String(quarters);
  return `About ${shown} hour${shown === "1" ? "" : "s"} on site`;
}

// "2026-11-20" as a date at noon, so no time zone shifts the day.
export function localDate(text) {
  return new Date(`${text}T12:00:00`);
}

export function isoDate(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

export function monthStart(date, months = 0) {
  return new Date(date.getFullYear(), date.getMonth() + months, 1, 12);
}

export const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export function longDate(text) {
  const date = localDate(text);
  return `${WEEKDAYS[date.getDay()]}, ${MONTHS[date.getMonth()]} ${date.getDate()}`;
}

// "08:30" as "8:30 AM".
export function clock(text) {
  const [hour, minute] = text.split(":").map(Number);
  return `${((hour + 11) % 12) + 1}:${String(minute).padStart(2, "0")} ${hour < 12 ? "AM" : "PM"}`;
}

// A date and "08:30" as an ISO moment with the browser's offset for that
// day. Customers book in Eastern time; the server stores UTC.
export function moment(dateText, timeText) {
  const date = new Date(`${dateText}T${timeText}:00`);
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const pad = (n) => String(Math.floor(Math.abs(n))).padStart(2, "0");
  return `${dateText}T${timeText}:00${sign}${pad(offset / 60)}:${pad(offset % 60)}`;
}
