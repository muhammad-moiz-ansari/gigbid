export const currency = (value?: number | null) => value == null ? "—" :
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
export const percent = (value?: number | null) => value == null ? "—" : `${Math.round(value * 100)}%`;
export const CITATION = /\s*\[(?:[a-z_ ]{1,20}[:=]\s*)?[A-Za-z0-9_-]{6,}\]/gi;
