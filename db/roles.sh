#!/bin/sh
# Rol propio para la aplicación, separado del superusuario de PostgreSQL. Corre en el contenedor
# "db" en cada arranque (ver docker-compose.yml) y se puede repetir a mano sin problema, por
# ejemplo después de restaurar un respaldo: docker compose exec db sh /roles.sh
#
# La imagen oficial crea POSTGRES_USER ("factura") como superusuario y no deja quitárselo. Si la
# app entrara con ese rol, una inyección SQL o un backend comprometido podrían ejecutar comandos
# en este contenedor (COPY ... FROM PROGRAM) y leer sus archivos. Por eso:
#   - la app entra como "factura_app": dueño de la base y de sus tablas, sin privilegios especiales;
#   - "factura" (superusuario) solo puede entrar desde dentro de este contenedor (respaldos, admin).
set -eu

APP_ROLE=factura_app
READY=/tmp/roles-ok  # el healthcheck del servicio espera este archivo
rm -f "$READY"

# Por TCP local, igual que backup.sh: en la primera instalación la base arranca un servidor
# temporal solo por socket mientras se crea, y ese todavía no es el definitivo.
export PGHOST=127.0.0.1 PGUSER=factura PGDATABASE=factura
until pg_isready -q; do sleep 2; done

# La contraseña es la de POSTGRES_PASSWORD: el backend ya la conoce, y con ella ya no puede entrar
# como superusuario porque "factura" queda rechazado desde fuera del contenedor (más abajo).
psql -v ON_ERROR_STOP=1 -q -v app_role="$APP_ROLE" -v pw="${POSTGRES_PASSWORD:?}" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'app_role')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_role') \gexec
ALTER ROLE :"app_role" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'pw';
-- Dueño de la base: también del esquema public (pg_database_owner), así las migraciones crean tablas.
ALTER DATABASE factura OWNER TO :"app_role";
ALTER SCHEMA public OWNER TO pg_database_owner;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Lo que crearon versiones anteriores (o una restauración) como "factura" pasa a ser de la app.
DO $$
DECLARE
  cmd text;
BEGIN
  FOR cmd IN
    SELECT format('ALTER %s %I.%I OWNER TO factura_app',
                  CASE c.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW'
                                 WHEN 'f' THEN 'FOREIGN TABLE' ELSE 'TABLE' END,
                  n.nspname, c.relname)
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND c.relowner <> 'factura_app'::regrole
  LOOP
    EXECUTE cmd;
  END LOOP;
  -- Secuencias sueltas (las de columnas id cambian de dueño junto con su tabla).
  FOR cmd IN
    SELECT format('ALTER SEQUENCE %I.%I OWNER TO factura_app', n.nspname, c.relname)
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'S' AND c.relowner <> 'factura_app'::regrole
      AND NOT EXISTS (SELECT FROM pg_depend d WHERE d.classid = 'pg_class'::regclass
                      AND d.objid = c.oid AND d.deptype IN ('a', 'i'))
  LOOP
    EXECUTE cmd;
  END LOOP;
  FOR cmd IN
    SELECT format('ALTER TYPE %I.%I OWNER TO factura_app', n.nspname, t.typname)
    FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typtype IN ('e', 'd', 'r', 'm') AND t.typowner <> 'factura_app'::regrole
  LOOP
    EXECUTE cmd;
  END LOOP;
  FOR cmd IN
    SELECT format('ALTER ROUTINE %s OWNER TO factura_app', p.oid::regprocedure)
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proowner <> 'factura_app'::regrole
  LOOP
    EXECUTE cmd;
  END LOOP;
END $$;
SQL

# "factura" solo entra desde dentro del contenedor (socket o 127.0.0.1, como el respaldo): se lo
# rechaza antes de la regla general por contraseña. La primera regla que coincide es la que vale.
HBA=$(psql -tAc 'SHOW hba_file')
RULE="host all factura all reject"
if ! grep -q "^$RULE\$" "$HBA"; then
  if grep -qE '^host[[:space:]]+all[[:space:]]+all[[:space:]]+all[[:space:]]' "$HBA"; then
    awk -v rule="$RULE" '!done && /^host[[:space:]]+all[[:space:]]+all[[:space:]]+all[[:space:]]/ { print rule; done = 1 } { print }' \
      "$HBA" > /tmp/pg_hba.conf.new
    cat /tmp/pg_hba.conf.new > "$HBA"  # conserva dueño y permisos del archivo original
    rm -f /tmp/pg_hba.conf.new
    psql -qtAc 'SELECT pg_reload_conf()' > /dev/null
  else
    echo "roles: pg_hba.conf no tiene la regla general esperada; no se restringió el acceso de \"factura\"" >&2
  fi
fi

touch "$READY"
echo "roles: la app usa \"$APP_ROLE\" (sin privilegios de superusuario)"
