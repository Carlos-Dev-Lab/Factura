import { Link } from 'react-router-dom';

import { useActiveAccounts, useUser } from '../../hooks/queries';
import { ACCOUNT_TYPES, formatMoney } from '../../lib/format';

/** Saldo de cada cuenta: "¿cuánto tengo en el banco y en efectivo?". */
export function AccountsCard() {
  const { currency } = useUser();
  const { data: accounts = [] } = useActiveAccounts();
  const total = accounts.filter((a) => a.type !== 'card').reduce((s, a) => s + a.balance, 0);
  const debt = accounts.filter((a) => a.type === 'card').reduce((s, a) => s + Math.max(0, -a.balance), 0);

  return (
    <section className="card" aria-label="Saldos de tus cuentas">
      <div className="card-head">
        <h2>Tus cuentas</h2>
        <Link to="/cuentas" className="link">
          Ver cuentas
        </Link>
      </div>
      <div className="mini-stats">
        <div>
          <small>Disponible</small>
          <b className={total < 0 ? 'neg' : 'pos'}>{formatMoney(total, currency, { short: true })}</b>
        </div>
        <div>
          <small>Deuda en tarjetas</small>
          <b className={debt > 0 ? 'neg' : ''}>{formatMoney(debt, currency, { short: true })}</b>
        </div>
      </div>
      <ul className="account-mini">
        {accounts.slice(0, 5).map((a) => (
          <li key={a.id}>
            <i style={{ background: a.color }} aria-hidden="true" />
            <span className="name">{a.name}</span>
            <small className="muted">{ACCOUNT_TYPES[a.type] === a.name ? '' : ACCOUNT_TYPES[a.type]}</small>
            <b className={a.balance < 0 ? 'neg' : ''}>{formatMoney(a.balance, currency)}</b>
          </li>
        ))}
      </ul>
    </section>
  );
}
