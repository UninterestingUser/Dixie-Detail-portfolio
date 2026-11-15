// How the booking flow shows the server's amounts. Display only: an amount
// arrives as text such as "1234.50" and leaves as "$1,234.50". No amount
// is ever turned into a number, added or rounded here (decision 0059);
// tests/no-browser-prices.mjs checks every file in this folder for that.

export function money(text) {
  if (text == null || text === "") return "";
  const [whole, cents = "00"] = String(text).split(".");
  const negative = whole.startsWith("-");
  const digits = negative ? whole.slice(1) : whole;
  return `${negative ? "-" : ""}$${digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${cents}`;
}

// "$250" for a whole-dollar card price, "$250.50" otherwise.
export function dollars(text) {
  return money(text).replace(/\.00$/, "");
}
