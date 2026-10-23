import { useQuery } from '@tanstack/react-query';

import { authApi } from '../../api/endpoints';
import { Icon, type IconName } from '../../components/Icon';

type Tone = 'mint' | 'violet' | 'amber' | 'coral';

const FEATURES: { icon: IconName; tone: Tone; title: string; text: string }[] = [
  {
    icon: 'invoice',
    tone: 'mint',
    title: 'Facturas que se cargan solas',
    text: 'Subí el PDF, una foto o el XML de la factura electrónica. Lee el QR del KuDE y el CDC, valida el RUC y te avisa si ya la habías cargado.',
  },
  {
    icon: 'bell',
    tone: 'amber',
    title: 'Avisos antes de que venza',
    text: 'En la app, en el celular o por Telegram: facturas, pagos fijos y resúmenes de tarjeta, con un resumen diario a la hora que elijas.',
  },
  {
    icon: 'calendar',
    tone: 'violet',
    title: 'Pagos fijos y cuotas',
    text: 'Alquiler, servicios, sueldo o la heladera en 12 cuotas («Cuota 3 de 12»). En ANDE o ESSAP confirmás el monto real de cada mes.',
  },
  {
    icon: 'card',
    tone: 'coral',
    title: 'Cuentas y tarjetas',
    text: 'Efectivo, bancos, billeteras y tarjetas de crédito con su cierre y vencimiento. Las transferencias entre cuentas no cuentan como gasto.',
  },
  {
    icon: 'chart',
    tone: 'mint',
    title: '¿Cómo cerrás el mes?',
    text: 'Lo que ya gastaste más lo que falta pagar y cobrar: el saldo proyectado al último día y cuánto podés gastar por día.',
  },
  {
    icon: 'tag',
    tone: 'amber',
    title: 'Presupuestos por categoría',
    text: 'Ponele un tope a Supermercado o a Ocio y recibí un aviso al llegar al 80 % y otro si te pasás.',
  },
  {
    icon: 'report',
    tone: 'violet',
    title: 'Listo para el contador',
    text: 'IVA 10 %, 5 %, exentas y gastos deducibles de IRP del mes, en una planilla o en un ZIP con todas las facturas.',
  },
  {
    icon: 'upload',
    tone: 'coral',
    title: 'Importá tu extracto',
    text: 'El CSV o Excel de tu banco: detecta las columnas, sugiere categorías y marca lo que ya habías cargado.',
  },
];

const STEPS: { title: string; text: string }[] = [
  { title: 'Cargá', text: 'Subí la factura o anotá el gasto en segundos. Desde el celular, con la cámara.' },
  { title: 'Revisá', text: 'La app completa proveedor, RUC, montos y fechas, y sugiere la categoría según lo que elegiste antes.' },
  { title: 'Controlá', text: 'El panel te muestra el mes, los vencimientos y tus presupuestos, y te avisa a tiempo.' },
];

const TRUST: { icon: IconName; title: string; text: string }[] = [
  {
    icon: 'lock',
    title: 'Tus datos, en tu servidor',
    text: 'Factura se instala en tu propia computadora. Tus movimientos no pasan por servicios de terceros y las contraseñas se guardan cifradas.',
  },
  {
    icon: 'restore',
    title: 'Papelera y deshacer',
    text: 'Lo que borrás queda 30 días por si te arrepentís, y cada borrado se deshace con un toque.',
  },
  {
    icon: 'download',
    title: 'Respaldos automáticos',
    text: 'Una copia diaria de la base y de los archivos, y la descarga completa de tus datos cuando quieras.',
  },
  {
    icon: 'user',
    title: 'Cada uno con lo suyo',
    text: 'Si compartís el servidor con tu familia, cada cuenta ve solo sus propios datos.',
  },
];

const READS = ['PDF', 'Foto o captura', 'XML de la SET', 'QR del KuDE', 'CDC de 44 dígitos', 'Extracto CSV o Excel'];

const month = new Date().toLocaleDateString('es-PY', { month: 'long' });

/** Vista previa de la app con datos de ejemplo (no son datos reales). */
function Preview() {
  const dues = [
    { name: 'ANDE', note: 'Vence mañana · estimado', amount: '₲ 231.500', tone: 'amber' },
    { name: 'Alquiler', note: `28 de ${month}`, amount: '₲ 2.800.000', tone: 'violet' },
    { name: 'Visa', note: 'Resumen · día 15', amount: '₲ 640.000', tone: 'coral' },
  ];
  return (
    <div className="lp-preview" aria-hidden="true">
      <div className="lp-window">
        <div className="lp-window-bar">
          <i />
          <i />
          <i />
          <span>Panel</span>
        </div>
        <div className="lp-mock lp-balance">
          <span className="lp-mock-label">Saldo de {month}</span>
          <b className="num lp-mock-big">₲ 4.678.000</b>
          <span className="pill ghost">Presupuesto usado: 62 %</span>
          <div className="meter">
            <div style={{ width: '62%' }} />
          </div>
        </div>
        <div className="lp-mock lp-kpi">
          <span className="lp-chip mint">
            <Icon name="income" size={16} />
          </span>
          <span className="muted">Ingresos</span>
          <b className="num pos">₲ 6.950.000</b>
        </div>
        <div className="lp-mock lp-kpi">
          <span className="lp-chip coral">
            <Icon name="expense" size={16} />
          </span>
          <span className="muted">Gastos</span>
          <b className="num neg">₲ 2.272.000</b>
        </div>
        <div className="lp-mock lp-dues">
          <b className="lp-mock-title">Próximos vencimientos</b>
          {dues.map((d) => (
            <div className="lp-due" key={d.name}>
              <span className={`lp-dot ${d.tone}`} />
              <span className="lp-due-name">
                <b>{d.name}</b>
                <small>{d.note}</small>
              </span>
              <b className="num">{d.amount}</b>
            </div>
          ))}
        </div>
      </div>
      <div className="lp-toast">
        <span className="lp-chip amber">
          <Icon name="bell" size={16} />
        </span>
        <span>
          <b>La factura de ANDE vence mañana</b>
          <small>₲ 231.500 · desde Itaú</small>
        </span>
      </div>
    </div>
  );
}

function Budgets() {
  const rows = [
    { name: 'Supermercado', pct: 82, state: 'warn', note: '₲ 984.000 de ₲ 1.200.000' },
    { name: 'Comidas', pct: 46, state: '', note: '₲ 115.000 de ₲ 250.000' },
    { name: 'Ocio', pct: 104, state: 'bad', note: '₲ 312.000 de ₲ 300.000' },
  ];
  return (
    <div className="lp-mock lp-budgets" aria-hidden="true">
      <div className="lp-proj">
        <span className="muted">Saldo proyectado al cierre del mes</span>
        <b className="num pos">₲ 1.906.300</b>
        <span className="pill mint">Podés gastar ₲ 173.300 por día</span>
      </div>
      {rows.map((r) => (
        <div className="lp-budget" key={r.name}>
          <div className="row-between">
            <b>{r.name}</b>
            <span className={r.state === 'bad' ? 'neg' : r.state === 'warn' ? 'amber' : 'soft'}>{r.pct} %</span>
          </div>
          <div className={`meter ${r.state}`}>
            <div style={{ width: `${Math.min(100, r.pct)}%` }} />
          </div>
          <small className="muted">{r.note}</small>
        </div>
      ))}
    </div>
  );
}

export function LandingPage({ onEnter }: { onEnter: (register: boolean) => void }) {
  const { data: config } = useQuery({ queryKey: ['auth-config'], queryFn: authApi.config });
  const firstUser = config?.first_user ?? false;
  const canRegister = config?.registration_open ?? false;
  // Primera vez: el botón principal crea la cuenta del administrador.
  const primary = firstUser
    ? { label: 'Empezar ahora', register: true }
    : canRegister
      ? { label: 'Crear cuenta', register: true }
      : { label: 'Entrar', register: false };

  const Cta = ({ big = false }: { big?: boolean }) => (
    <div className="lp-cta">
      <button className={`btn mint ${big ? 'lp-big' : ''}`} onClick={() => onEnter(primary.register)}>
        {primary.label}
        <Icon name="right" size={18} />
      </button>
      {primary.register && !firstUser && (
        <button className={`btn ${big ? 'lp-big' : ''}`} onClick={() => onEnter(false)}>
          Ya tengo cuenta
        </button>
      )}
    </div>
  );

  return (
    <div className="lp">
      <header className="lp-nav">
        <a className="brand" href="#inicio">
          <span className="logo" aria-hidden="true">
            <Icon name="invoice" size={22} stroke={2.2} />
          </span>
          Factura
        </a>
        <nav className="lp-links" aria-label="Secciones">
          <a href="#funciones">Funciones</a>
          <a href="#como-funciona">Cómo funciona</a>
          <a href="#privacidad">Privacidad</a>
        </nav>
        <button className="btn small" onClick={() => onEnter(firstUser)}>
          {firstUser ? 'Crear cuenta' : 'Entrar'}
        </button>
      </header>

      <main>
        <section className="lp-hero" id="inicio">
          <div className="lp-hero-text">
            <span className="pill mint lp-eyebrow">Hecho para Paraguay · factura electrónica SIFEN</span>
            <h1>
              Tus facturas, pagos y gastos, <span className="lp-accent">bajo control</span>.
            </h1>
            <p className="lp-lead">
              Factura lee tus comprobantes, te avisa antes de cada vencimiento y te muestra cómo vas a cerrar el mes. Sin
              planillas, sin anotar todo a mano.
            </p>
            <Cta big />
            <ul className="lp-checks">
              {['Se instala en tu propia computadora', 'Funciona en el celular como una app', 'En guaraníes, con RUC y timbrado'].map(
                (t) => (
                  <li key={t}>
                    <Icon name="check" size={16} stroke={2.6} />
                    {t}
                  </li>
                ),
              )}
            </ul>
          </div>
          <Preview />
        </section>

        <section className="lp-reads" aria-label="Qué puede leer">
          <span className="muted">Lee y completa sola:</span>
          <ul>
            {READS.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>

        <section className="lp-section" id="funciones">
          <div className="lp-head">
            <span className="lp-kicker">Funciones</span>
            <h2>Todo lo que hace falta para ordenar la plata de la casa</h2>
            <p className="lp-sub">
              Desde la factura de la ANDE hasta el resumen de la tarjeta: cada cosa en su lugar y con su aviso.
            </p>
          </div>
          <div className="lp-grid">
            {FEATURES.map((f) => (
              <article className="lp-card" key={f.title}>
                <span className={`lp-chip ${f.tone} lg`}>
                  <Icon name={f.icon} size={22} />
                </span>
                <h3>{f.title}</h3>
                <p>{f.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="lp-section" id="como-funciona">
          <div className="lp-head">
            <span className="lp-kicker">Cómo funciona</span>
            <h2>Tres pasos, todos los días</h2>
          </div>
          <ol className="lp-steps">
            {STEPS.map((s, i) => (
              <li className="lp-card" key={s.title}>
                <span className="lp-step-n num">{i + 1}</span>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="lp-section lp-split">
          <div className="lp-head left">
            <span className="lp-kicker">Control del mes</span>
            <h2>Sabé hoy cuánto te va a quedar a fin de mes</h2>
            <p className="lp-sub">
              Factura suma lo que ya gastaste, los pagos fijos y facturas que faltan, y lo que vas a cobrar. Con eso te dice
              el saldo proyectado y cuánto podés gastar por día sin quedar en rojo.
            </p>
            <ul className="lp-checks col">
              {[
                'Presupuesto mensual y por categoría',
                'Límite diario con aviso cuando lo pasás',
                'Comparación con el mes anterior y resumen anual',
              ].map((t) => (
                <li key={t}>
                  <Icon name="check" size={16} stroke={2.6} />
                  {t}
                </li>
              ))}
            </ul>
          </div>
          <Budgets />
        </section>

        <section className="lp-section" id="privacidad">
          <div className="lp-head">
            <span className="lp-kicker">Privacidad y control</span>
            <h2>Tu información financiera no sale de tu casa</h2>
          </div>
          <div className="lp-grid four">
            {TRUST.map((t) => (
              <article className="lp-card flat" key={t.title}>
                <span className="lp-chip violet">
                  <Icon name={t.icon} size={18} />
                </span>
                <h3>{t.title}</h3>
                <p>{t.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="lp-final">
          <h2>Empezá a ordenar tus cuentas hoy</h2>
          <p className="lp-lead">Cargá tu primera factura en menos de un minuto.</p>
          <Cta big />
        </section>
      </main>

      <footer className="lp-foot">
        <span className="brand small-brand">
          <span className="logo" aria-hidden="true">
            <Icon name="invoice" size={16} stroke={2.2} />
          </span>
          Factura
        </span>
        <span className="muted">Control de facturas, pagos y gastos · Tus datos quedan en tu servidor</span>
      </footer>
    </div>
  );
}
