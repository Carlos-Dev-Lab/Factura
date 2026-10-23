/**
 * Reglas de contraseña, las mismas que aplica el servidor (backend/app/core/security.py:
 * weak_password_reason). Acá solo sirven para avisar mientras se escribe; el servidor
 * vuelve a comprobarlas siempre.
 */

export const MIN_PASSWORD = 10;
export const MAX_PASSWORD = 128;

const COMMON = new Set([
  'password123', 'password1234', 'contraseña', 'contrasena', 'contraseña1', 'contrasena1', 'contraseña123',
  'contrasena123', 'administrador', 'admin12345', 'qwerty1234', 'qwerty123456', 'iloveyou12', 'paraguay123',
  'asuncion123', 'factura123', '1q2w3e4r5t', 'q1w2e3r4t5', 'abc1234567', '1234qwerty', 'pass123456',
]);
const SEQUENCES = ['0123456789012345678901234567890', 'abcdefghijklmnñopqrstuvwxyz', 'qwertyuiopasdfghjklñzxcvbnm'];

export interface PasswordCheck {
  id: 'length' | 'common' | 'email';
  label: string;
  ok: boolean;
}

/** Lista de requisitos con su estado, para mostrarla debajo del campo. */
export function passwordChecks(password: string, email = ''): PasswordCheck[] {
  const low = password.toLowerCase();
  const user = (email.split('@')[0] ?? '').toLowerCase();
  const obvious =
    new Set(low).size < 4 || COMMON.has(low) || SEQUENCES.some((s) => s.includes(low) || [...s].reverse().join('').includes(low));
  return [
    { id: 'length', label: `Al menos ${MIN_PASSWORD} caracteres`, ok: password.length >= MIN_PASSWORD },
    { id: 'common', label: 'No es una contraseña común ni una secuencia', ok: password.length > 0 && !obvious },
    { id: 'email', label: 'No contiene tu email', ok: password.length > 0 && !(user.length >= 4 && low.includes(user)) },
  ];
}

export function passwordValid(password: string, email = ''): boolean {
  return password.length <= MAX_PASSWORD && passwordChecks(password, email).every((c) => c.ok);
}

/** 0 = no cumple los requisitos; 1 débil, 2 buena, 3 fuerte. */
export function passwordStrength(password: string, email = ''): { level: 0 | 1 | 2 | 3; label: string } {
  if (!passwordValid(password, email)) return { level: 0, label: 'Faltan requisitos' };
  const variety = [/[a-zñáéíóú]/, /[A-ZÑÁÉÍÓÚ]/, /\d/, /[^a-zA-ZñÑáéíóúÁÉÍÓÚ\d]/].filter((r) => r.test(password)).length;
  if (password.length >= 14 && variety >= 3) return { level: 3, label: 'Fuerte' };
  if (variety >= 2) return { level: 2, label: 'Buena' };
  return { level: 1, label: 'Débil: combiná letras, números o símbolos' };
}

/** Validación simple de email (la completa la hace el servidor). */
export function emailValid(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email.trim()) && email.length <= 254;
}
