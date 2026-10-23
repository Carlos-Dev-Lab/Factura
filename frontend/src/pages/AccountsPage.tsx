import { Link } from 'react-router-dom';

import { accountsApi } from '../api/endpoints';
import type { Account } from '../api/types';
import { ConfirmDeleteButton } from '../components/fields';
import { Icon, type IconName } from '../components/Icon';
import { Loading } from '../components/Loading';
import { useDialogs } from '../context/DialogsContext';
import { useAccounts, useFinancialMutation, useTransfers, useUser } from '../hooks/queries';
import { ACCOUNT_TYPES, formatDate, formatMoney, relativeDay, tint } from '../lib/format';

const TYPE_ICON: Record<Account['type'], IconName> = { cash: 'wallet', bank: 'wallet', card: 'card', wallet: 'wallet' };

function CardStatusBlock({ account }: { account: Account }) {
  const { currency } = useUser();
  const { openTransfer } = useDialogs();
  const c = account.card!;
  const money = (v: number) => formatMoney(v, currency);
  const usedPct = account.credit_limit ? Math.min(100, Math.round((c.debt / account.credit_limit) * 100)) : null;
  return (
    <div className="card-status">
      {usedPct !== null && (
        <div>
          <div className="row-between small">
            <span className="muted">Usado {usedPct}%</span>
            <span className="muted">Disponible {money(c.available ?? 0)}</span>
          </div>
          <div className={`meter thin ${usedPct >= 90 ? 'bad' : usedPct >= 70 ? 'warn' : ''}`}>
            <div style={{ width: `${usedPct}%` }} />
          </div>
        </div>
      )}
      <dl className="breakdown compact">
        <div>
          <dt>Resumen a pagar</dt>
          <dd className={c.statement_amount ? 'neg' : 'pos'}>
            {c.statement_amount ? money(c.statement_amount) : 'Nada pendiente'}
          </dd>
        </div>
        {/* Sin resumen pendiente se muestra el próximo vencimiento, no uno que ya pasó. */}
        <div>
          <dt>{c.statement_amount ? 'Vence' : 'Próximo vencimiento'}</dt>
          <dd>
            {formatDate(c.statement_amount ? c.due_date : c.next_due_date)} ·{' '}
            {relativeDay(c.statement_amount ? c.due_date : c.next_due_date)}
          </dd>
        </div>
        <div>
          <dt>Consumos desde el cierre</dt>
          <dd>{money(c.current_period)}</dd>
        </div>
        <div>
          <dt>Próximo cierre</dt>
          <dd>{formatDate(c.next_closing)}</dd>
        </div>
      </dl>
      {c.statement_amount > 0 && (
        <button
          className="btn small mint"
          onClick={() =>
            openTransfer({ to_account_id: account.id, amount: c.statement_amount, description: `Pago resumen ${account.name}` })
          }
        >
          Pagar resumen
        </button>
      )}
    </div>
  );
}

function AccountCard({ account }: { account: Account }) {
  const { currency } = useUser();
  const { openAccount } = useDialogs();
  const isCard = account.type === 'card';
  return (
    <article className={`card account-card ${account.archived ? 'archived' : ''}`}>
      <div className="account-head">
        <span className="ava" style={{ background: tint(account.color, 0.22), color: account.color }} aria-hidden="true">
          <Icon name={TYPE_ICON[account.type]} size={20} />
        </span>
        <div className="body">
          <b>{account.name}</b>
          <small className="muted">
            {ACCOUNT_TYPES[account.type]} · {account.movement_count} movimientos{account.archived ? ' · archivada' : ''}
          </small>
        </div>
        <button className="icon-btn" onClick={() => openAccount({ account })} aria-label={`Editar ${account.name}`}>
          <Icon name="edit" size={16} />
        </button>
      </div>
      <div>
        <small className="muted">{isCard ? 'Deuda total' : 'Saldo'}</small>
        <div className={`num xl ${account.balance < 0 ? 'neg' : ''}`}>
          {isCard ? formatMoney(Math.max(0, -account.balance), currency) : formatMoney(account.balance, currency)}
        </div>
      </div>
      {isCard && account.card && <CardStatusBlock account={account} />}
      <Link className="link" to={`/gastos?cuenta=${account.id}`}>
        Ver movimientos
      </Link>
    </article>
  );
}

function TransfersCard() {
  const { currency } = useUser();
  const transfers = useTransfers();
  const remove = useFinancialMutation(accountsApi.removeTransfer, 'Transferencia eliminada');
  return (
    <section className="card">
      <div className="card-head">
        <h2>Transferencias recientes</h2>
      </div>
      {!transfers.data ? (
        <Loading error={transfers.error} />
      ) : transfers.data.length ? (
        <ul className="list">
          {transfers.data.slice(0, 20).map((t) => (
            <li key={t.id} className="item">
              <span className="ava" style={{ background: tint('#8B7BFF'), color: '#B3A8FF' }} aria-hidden="true">
                <Icon name="transfer" size={18} />
              </span>
              <span className="body">
                <b>
                  {t.from_account.name} → {t.to_account.name}
                </b>
                <small>{[formatDate(t.date), t.description].filter(Boolean).join(' · ')}</small>
              </span>
              <span className="amt">{formatMoney(t.amount, currency)}</span>
              <ConfirmDeleteButton compact label="Eliminar transferencia" onConfirm={() => remove.mutate(t.id)} />
            </li>
          ))}
        </ul>
      ) : (
        <div className="empty">
          Registrá acá cuando sacás plata del cajero, pagás la tarjeta desde el banco o cargás tu billetera.
        </div>
      )}
    </section>
  );
}

export function AccountsPage() {
  const { currency } = useUser();
  const accounts = useAccounts();
  const { openAccount, openTransfer } = useDialogs();
  if (!accounts.data) return <Loading error={accounts.error} />;
  const active = accounts.data.filter((a) => !a.archived);
  const archived = accounts.data.filter((a) => a.archived);
  const available = active.filter((a) => a.type !== 'card').reduce((s, a) => s + a.balance, 0);
  const debt = active.filter((a) => a.type === 'card').reduce((s, a) => s + Math.max(0, -a.balance), 0);

  return (
    <div className="stack">
      <section className="card">
        <div className="toolbar">
          <div className="mini-stats three">
            <div>
              <small>Disponible</small>
              <b className={available < 0 ? 'neg' : 'pos'}>{formatMoney(available, currency)}</b>
            </div>
            <div>
              <small>Deuda en tarjetas</small>
              <b className={debt ? 'neg' : ''}>{formatMoney(debt, currency)}</b>
            </div>
            <div>
              <small>Neto</small>
              <b>{formatMoney(available - debt, currency)}</b>
            </div>
          </div>
          <div className="row-actions">
            <button className="btn violet" onClick={() => openTransfer()}>
              <Icon name="transfer" size={18} /> Transferir
            </button>
            <button className="btn mint" onClick={() => openAccount({})}>
              + Cuenta
            </button>
          </div>
        </div>
        <p className="hint">
          Los saldos se calculan con el saldo inicial de cada cuenta más los movimientos que tienen esa cuenta. Los
          movimientos sin cuenta no cambian ningún saldo.
        </p>
      </section>
      <div className="grid accounts">
        {active.map((a) => (
          <AccountCard key={a.id} account={a} />
        ))}
        <button className="card add-card" onClick={() => openAccount({ type: 'card' })}>
          <Icon name="card" size={26} />
          <b>Agregar tarjeta de crédito</b>
          <span className="muted">Con su día de cierre y vencimiento: te avisamos antes de que venza.</span>
        </button>
      </div>
      <TransfersCard />
      {archived.length > 0 && (
        <details className="card archived-list">
          <summary>Cuentas archivadas ({archived.length})</summary>
          <div className="grid accounts">
            {archived.map((a) => (
              <AccountCard key={a.id} account={a} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
