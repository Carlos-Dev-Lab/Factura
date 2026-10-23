#!/bin/sh
# Respaldo automático diario: base de datos (pg_dump) y archivos de las facturas.
# Corre en segundo plano dentro del contenedor "db" (ver docker-compose.yml).
# Guarda en /backups (la carpeta ./backups del proyecto) y borra los de más de BACKUP_KEEP_DAYS días.
set -eu

HOUR="${BACKUP_HOUR:-3}"
KEEP="${BACKUP_KEEP_DAYS:-14}"
OUT=/backups

# Por TCP local y no por socket: en la primera instalación la base arranca un servidor
# temporal solo por socket mientras se crea, y ese todavía no es el definitivo.
export PGHOST=127.0.0.1 PGPASSWORD="${POSTGRES_PASSWORD:-}"

num() { echo "$1" | sed 's/^0*//; s/^$/0/'; }

# Dentro de "backup || ..." el shell ignora set -e, así que cada paso corta a mano:
# si pg_dump falla no debe quedar un .dump vacío con nombre de respaldo bueno.
backup() {
  ts=$(date +%Y%m%d-%H%M)
  pg_dump -U factura -d factura -Fc -f "$OUT/.tmp-db-$ts.dump" || { rm -f "$OUT/.tmp-db-$ts.dump"; return 1; }
  [ -s "$OUT/.tmp-db-$ts.dump" ] || { rm -f "$OUT/.tmp-db-$ts.dump"; return 1; }
  tar -czf "$OUT/.tmp-archivos-$ts.tgz" -C /uploads . || { rm -f "$OUT"/.tmp-*-"$ts".*; return 1; }
  mv "$OUT/.tmp-db-$ts.dump" "$OUT/factura-db-$ts.dump" || return 1
  mv "$OUT/.tmp-archivos-$ts.tgz" "$OUT/factura-archivos-$ts.tgz" || return 1
  find "$OUT" -maxdepth 1 -name 'factura-*' -mtime +"$KEEP" -delete
  echo "$(date '+%F %T') respaldo $ts listo"
}

# El script arranca junto con PostgreSQL, así que se espera a que la base acepte
# conexiones, hasta 5 minutos.
wait_db() {
  i=0
  until pg_isready -U factura -d factura -q; do
    i=$((i + 1))
    [ "$i" -ge 150 ] && return 1
    sleep 2
  done
}

mkdir -p "$OUT"

# "sh /backup.sh ahora": un respaldo en el momento (por ejemplo antes de actualizar) y termina.
if [ "${1:-}" = "ahora" ]; then
  backup || { echo "$(date '+%F %T') falló el respaldo" >&2; exit 1; }
  exit 0
fi

rm -f "$OUT"/.tmp-* 2>/dev/null || true

# Al arrancar, si todavía no hay respaldo válido (no vacío) de hoy, se hace uno.
if [ -z "$(find "$OUT" -maxdepth 1 -name "factura-db-$(date +%Y%m%d)-*" -size +0 2>/dev/null)" ]; then
  { wait_db && backup; } || echo "$(date '+%F %T') falló el respaldo inicial" >&2
fi

while true; do
  now=$(( $(num "$(date +%H)") * 3600 + $(num "$(date +%M)") * 60 + $(num "$(date +%S)") ))
  target=$(( HOUR * 3600 ))
  wait=$(( target - now ))
  [ "$wait" -le 0 ] && wait=$(( wait + 86400 ))
  sleep "$wait"
  { wait_db && backup; } || echo "$(date '+%F %T') falló el respaldo" >&2
  sleep 60
done
