import type { TransactionType } from "@findimmo/shared";

const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });

export function formatPrice(n: number | undefined, transaction?: TransactionType): string {
  if (n == null) return "Prix non communiqué";
  return eur.format(n) + (transaction === "rent" ? "/mois" : "");
}

export function formatNumber(n: number): string {
  return num.format(n);
}

export function formatPpm2(n: number | undefined, transaction?: TransactionType): string | null {
  if (n == null) return null;
  return transaction === "rent" ? `${num.format(n)} €/m²` : `${eur.format(n)}/m²`;
}

export function formatDate(iso: string | undefined | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
}

export function relativeDays(iso: string, now = Date.now()): string {
  const days = Math.floor((now - Date.parse(iso)) / 86_400_000);
  if (days <= 0) return "aujourd'hui";
  if (days === 1) return "hier";
  if (days < 30) return `il y a ${days} j`;
  return `il y a ${Math.floor(days / 30)} mois`;
}

export function percent(a: number, b: number): string {
  const p = ((b - a) / a) * 100;
  return `${p > 0 ? "+" : ""}${num.format(p)} %`;
}
