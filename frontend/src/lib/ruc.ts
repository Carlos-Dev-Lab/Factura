/** Dígito verificador módulo 11 que usa la SET para el RUC (igual que el backend). */
function rucCheckDigit(base: string): number {
  let total = 0;
  let weight = 2;
  for (const c of [...base].reverse()) {
    if (weight > 11) weight = 2;
    total += Number(c) * weight;
    weight += 1;
  }
  const rest = total % 11;
  return rest > 1 ? 11 - rest : 0;
}

/** true/false si el RUC tiene la forma "base-DV"; null si no se puede comprobar. */
export function rucIsValid(ruc: string): boolean | null {
  const m = /^(\d{1,8})-(\d)$/.exec(ruc.trim());
  if (!m) return null;
  return rucCheckDigit(m[1]!) === Number(m[2]);
}
