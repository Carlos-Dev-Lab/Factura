# Factura

Aplicación web autoalojada para administrar las finanzas de un hogar o de un trabajador independiente en Paraguay: facturas, pagos fijos, cuentas, gastos diarios, avisos de vencimiento y reportes para el contador.

Corre con Docker en un equipo propio (PC, mini‑servidor o VPS), funciona en celular, tablet y computadora y se instala como aplicación (PWA). Los datos nunca salen del servidor.

**Tecnologías:** Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · Tesseract OCR · React 18 · TypeScript · Vite · Nginx · Docker Compose

---

## Contenido

1. [Funcionalidades](#funcionalidades)
2. [Arquitectura](#arquitectura)
3. [Contenedores](#contenedores)
4. [Instalación](#instalación)
5. [Configuración](#configuración)
6. [Aplicar cambios y actualizar](#aplicar-cambios-y-actualizar)
7. [Respaldos](#respaldos)
8. [Acceso con HTTPS (Tailscale)](#acceso-con-https-tailscale)
9. [Ingreso con Google](#ingreso-con-google)
10. [Avisos por email (Gmail)](#avisos-por-email-gmail)
11. [Avisos](#avisos)
12. [Seguridad](#seguridad)
13. [Operación y solución de problemas](#operación-y-solución-de-problemas)
14. [Desarrollo](#desarrollo)
15. [Estructura del proyecto](#estructura-del-proyecto)

---

## Funcionalidades

| Módulo | Qué hace |
|---|---|
| **Facturas** | Carga por foto o PDF con lectura automática (OCR). Con la **factura electrónica** (XML de SIFEN, QR del KuDE o CDC) los datos se toman exactos. Detecta facturas repetidas. |
| **Pagos y cobros fijos** | Alquiler, servicios de monto variable (ANDE, ESSAP), planes de cuotas y sueldo, con calendario de vencimientos. |
| **Cuentas** | Efectivo, banco, billeteras y tarjetas de crédito con fecha de cierre y vencimiento. Transferencias entre cuentas. |
| **Gastos del día** | Registro rápido con categoría sugerida (aprende de lo que elige el usuario) e importación de extractos bancarios (CSV o Excel). |
| **Control del mes** | Presupuesto general y por categoría, límite diario y proyección de cierre de mes. |
| **Avisos** | Vencimientos y presupuestos al límite: en la app, como notificación del celular o la PC, por Telegram y por email (Gmail). |
| **Ingreso** | Con email y contraseña o con la cuenta de Google. Cada usuario ve solo sus datos. |
| **Reportes** | Resumen anual y paquete para el contador: IVA 10 %, 5 %, exentas, gastos deducibles de IRP y archivos. |
| **Datos** | Papelera de 30 días con “Deshacer”, respaldos automáticos diarios y exportación completa de los datos de cada usuario. |

---

## Arquitectura

```
 Navegador / celular
         │
         │  http://servidor:APP_PORT  (único puerto expuesto)
         ▼
 ┌───────────────┐  /api/  ┌───────────────┐         ┌───────────────────┐
 │   frontend    │────────►│    backend    │────────►│        db         │
 │ Nginx + React │         │ FastAPI + OCR │         │   PostgreSQL 16   │
 └───────────────┘         └───────┬───────┘         │ + respaldo diario │
                                   │                 └───┬───────────┬───┘
 ┌───────────────┐                 │                     │           │
 │    worker     │─────────────────┼────────────────────►│           │
 │    avisos,    │                 ▼                     ▼           ▼
 │   limpieza    │──────► volumen factura_uploads   volumen     carpeta BACKUP_DIR
 └───────────────┘        (archivos de facturas)    db_data     del servidor (./backups)
```

Todos los contenedores están en la red interna de Docker `factura_default` (rango fijo y chico, `10.213.47.0/27`, para no chocar con la red Wi-Fi ni con otras redes del servidor); desde fuera solo se llega al `frontend`.

**Flujo de un pedido.** El navegador solo habla con `frontend`, el único contenedor con un puerto abierto. Nginx entrega la aplicación React y reenvía todo lo que empieza con `/api/` al `backend`, que valida la sesión, aplica la lógica y lee o escribe en PostgreSQL. Los archivos subidos (fotos, PDF, XML) se guardan en el volumen `factura_uploads`. El `worker` trabaja en segundo plano con la misma base y los mismos archivos.

**Capas del backend.** `api` → `services` → `models`. Los endpoints solo traducen la petición HTTP y llaman a los servicios; los servicios contienen toda la lógica y no conocen HTTP; el `worker` reutiliza los mismos servicios.

**Lectura de facturas.** Al subir un archivo se intenta, en este orden: (1) XML de SIFEN, datos exactos; (2) QR del KuDE, CDC, total e IVA exactos; (3) CDC de 44 dígitos impreso, validado con su dígito verificador; (4) OCR del texto, con validación del dígito verificador del RUC. Si un paso no reconoce el formato, se pasa al siguiente.

---

## Contenedores

El proyecto levanta **4 contenedores**, definidos en `docker-compose.yml` bajo el nombre de proyecto `factura`:

| Contenedor | Imagen | Puerto | Función |
|---|---|---|---|
| `factura-frontend-1` | construida desde `frontend/` | `APP_PORT` → 8080 (único expuesto) | Servidor web y proxy de la API |
| `factura-backend-1` | construida desde `backend/` | 8000 (solo interno) | API REST |
| `factura-worker-1` | la misma imagen del backend | — | Tareas en segundo plano |
| `factura-db-1` | `postgres:16-alpine` | 5432 (solo interno) | Base de datos y respaldo diario |

### `frontend` — Nginx + React

- **Construcción en dos etapas:** `node:22-alpine` compila la aplicación React con Vite; el resultado se copia a `nginx-unprivileged:1.27-alpine`, que no incluye Node ni el código fuente.
- **Sirve la aplicación** (HTML, JS, CSS, íconos, manifiesto PWA y *service worker*).
- **Reenvía `/api/`** al contenedor `backend` por la red interna de Docker.
- **Protege la API:** límite de pedidos por IP, tamaño máximo de cada pedido, corte de conexiones lentas y cabeceras de seguridad (CSP, `X-Frame-Options`, etc.).
- Corre **sin root**, sin capacidades del kernel.

### `backend` — API (FastAPI)

- Imagen `python:3.12-slim` con **Tesseract OCR** (español e inglés).
- **Al arrancar aplica las migraciones pendientes** de la base (`alembic upgrade head`) y luego inicia la API con Uvicorn (`WEB_CONCURRENCY` procesos, 2 por defecto).
- Atiende todo `/api/v1`: sesiones (también con Google), facturas (OCR y factura electrónica), cuentas, movimientos, categorías, pagos programados, reportes, importación y exportación.
- Guarda los archivos subidos en el volumen `factura_uploads` (`/data/uploads`).
- Lee la carpeta de respaldos **en solo lectura**, únicamente para mostrar en *Ajustes* cuándo fue el último.
- Corre como el usuario sin privilegios `factura`. Chequeo de salud: `GET /api/health`.

### `worker` — tareas en segundo plano

Usa la imagen del backend con otro comando (`python -m app.worker`):

- **Cada 30 segundos** revisa los avisos de cada usuario: a la hora elegida (8:00 por defecto) manda el resumen diario y, durante el día, solo lo urgente; nunca después de las 22:00.
- **Telegram:** si hay `TELEGRAM_BOT_TOKEN`, atiende los mensajes del bot para vincular cuentas.
- **Email:** si hay `SMTP_USER` y `SMTP_PASSWORD`, también manda los avisos por correo a quien lo activó.
- **Mantenimiento diario a las 4:00:** vacía de la papelera lo que tiene más de 30 días (con sus archivos), borra archivos subidos que nunca se asociaron a una factura, limpia los intentos de inicio de sesión viejos y el historial de avisos de más de 120 días.
- Si se levantan varias copias, solo una trabaja (bloqueo en PostgreSQL).

### `db` — PostgreSQL 16 y respaldo diario

- **Base de datos** de la aplicación. Los datos viven en el volumen `factura_db_data`; el puerto no se publica fuera de Docker.
- **Respaldo automático:** junto con PostgreSQL corre en segundo plano `backup/backup.sh`, que todos los días a las `BACKUP_HOUR` (3:00 por defecto) guarda en la carpeta del servidor `BACKUP_DIR`:
  - `factura-db-AAAAMMDD-HHMM.dump`: copia completa de la base (`pg_dump`, formato *custom*).
  - `factura-archivos-AAAAMMDD-HHMM.tgz`: todos los archivos de las facturas.
- Al arrancar, si todavía no hay respaldo del día, hace uno. Borra los de más de `BACKUP_KEEP_DAYS` días. Si el script se detiene por un error, se vuelve a lanzar solo al minuto.

### Volúmenes y carpetas

| Almacenamiento | Contenido | Lo usan |
|---|---|---|
| Volumen `factura_db_data` | Base de datos PostgreSQL | `db` |
| Volumen `factura_uploads` | Archivos de las facturas (fotos, PDF, XML) | `backend`, `worker` (lectura y escritura) · `db` (solo lectura, para el respaldo) |
| Carpeta `BACKUP_DIR` del servidor (por defecto `./backups`) | Respaldos diarios | `db` (escribe) · `backend` (solo lectura) |

> ⚠️ Los volúmenes contienen **todos los datos**. `docker compose down` los conserva; `docker compose down -v` **los borra definitivamente**.

---

## Instalación

### Requisitos

- **Windows o macOS:** [Docker Desktop](https://www.docker.com/products/docker-desktop/).
- **Linux:** Docker Engine con el complemento Docker Compose v2.
- En uso normal los 4 contenedores ocupan unos 400 MB de RAM; las imágenes, alrededor de 1,5 GB de disco.

### Pasos

1. **Obtener el código** y entrar a la carpeta:
   ```bash
   git clone <url-del-repositorio> factura
   cd factura
   ```

2. **Crear el archivo de configuración** a partir de la plantilla:
   ```bash
   cp .env.example .env
   ```

3. **Completar los dos valores obligatorios** en `.env`:
   - `POSTGRES_PASSWORD`: contraseña de la base de datos.
   - `SECRET_KEY`: clave con la que se firman las sesiones.

   Para ambos conviene una clave aleatoria de 64 caracteres:
   ```bash
   # Linux, macOS o Git Bash
   openssl rand -hex 32
   ```
   ```powershell
   # Windows PowerShell
   $b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); -join ($b | % { $_.ToString('x2') })
   ```
   > En `POSTGRES_PASSWORD` usar solo letras, números, `-` y `_`: la contraseña forma parte de la dirección de conexión a la base.

4. **Construir e iniciar:**
   ```bash
   docker compose up -d --build
   ```
   La primera vez demora varios minutos (descarga imágenes y compila). Al terminar, `docker compose ps` debe mostrar los 4 contenedores en estado `running` / `healthy`.

5. **Abrir** http://localhost:8080 y tocar **Empezar ahora** para crear la cuenta principal. Después del primer usuario el registro se cierra solo (ver `ALLOW_REGISTRATION`).

Para entrar desde un celular en la misma red Wi‑Fi: `http://IP-DEL-SERVIDOR:8080` (en Windows la IP se ve con `ipconfig`; en Linux con `ip addr`). Para usarla fuera de casa y recibir notificaciones, ver [Acceso con HTTPS](#acceso-con-https-tailscale).

**Opcional, cuando quieras:** [ingreso con Google](#ingreso-con-google) y [avisos por email (Gmail)](#avisos-por-email-gmail). Cada uno se configura en unos minutos y no hace falta para empezar.

---

## Configuración

Toda la configuración está en `.env` (no se sube a git). Después de modificarlo, aplicar con `docker compose up -d`.

| Variable | Por defecto | Descripción |
|---|---|---|
| `POSTGRES_PASSWORD` | — | **Obligatoria.** Contraseña de la base de datos. |
| `SECRET_KEY` | — | **Obligatoria.** Clave para firmar las sesiones (mínimo 32 caracteres). |
| `APP_PORT` | `8080` | Puerto del servidor donde se abre la aplicación. |
| `COOKIE_SECURE` | `false` | `true` **solo** si se accede por HTTPS. |
| `PUBLIC_URL` | vacío | Dirección pública con HTTPS, usada en los enlaces de las notificaciones. |
| `ALLOWED_HOSTS` | vacío | Nombres permitidos para entrar, separados por coma (ej. `mi-pc.tu-red.ts.net`). Vacío = cualquiera. |
| `TELEGRAM_BOT_TOKEN` | vacío | Token de un bot de Telegram; activa los avisos por ese canal. |
| `GOOGLE_CLIENT_ID` | vacío | ID de cliente OAuth de Google; con el secreto, activa **Continuar con Google** (ver [Ingreso con Google](#ingreso-con-google)). |
| `GOOGLE_CLIENT_SECRET` | vacío | Secreto de ese cliente OAuth. |
| `SMTP_USER` | vacío | Cuenta de correo que manda los avisos, por ejemplo `tu-cuenta@gmail.com` (ver [Avisos por email](#avisos-por-email-gmail)). |
| `SMTP_PASSWORD` | vacío | Contraseña de aplicación de esa cuenta (no la contraseña normal). |
| `SMTP_HOST` | `smtp.gmail.com` | Servidor de correo saliente. |
| `SMTP_PORT` | `587` | `587` (STARTTLS) o `465` (SSL). |
| `SMTP_FROM` | `Factura <SMTP_USER>` | Remitente que se ve en los correos. |
| `BACKUP_HOUR` | `3` | Hora del respaldo diario. |
| `BACKUP_KEEP_DAYS` | `14` | Días que se conservan los respaldos. |
| `BACKUP_DIR` | `./backups` | Carpeta del servidor donde se guardan los respaldos. |
| `ALLOW_REGISTRATION` | `false` | `true` para permitir más cuentas además de la primera. |
| `ACCESS_TOKEN_MINUTES` | `720` | Duración de la sesión en minutos. |
| `TZ` | `America/Asuncion` | Zona horaria: define la hora de los avisos y de los respaldos. |
| `WEB_CONCURRENCY` | `2` | Procesos de la API (opcional; subirlo si hay muchos usuarios). |
| `DOCKER_SUBNET` | `10.213.47.0/27` | Rango de la red interna de Docker. Cambiarlo solo si coincide con la red Wi-Fi o una VPN del servidor. |

---

## Aplicar cambios y actualizar

`docker compose up -d --build` es siempre seguro: reconstruye solo lo que cambió y recrea solo los contenedores afectados. Los datos de los volúmenes no se tocan.

| Qué cambió | Comando | Qué ocurre |
|---|---|---|
| Valores de `.env` | `docker compose up -d` | Se recrean los contenedores que usan esas variables. |
| Código del backend, `requirements.txt` o `backend/Dockerfile` | `docker compose up -d --build` | Se reconstruye la imagen y se recrean `backend` y `worker`. Las migraciones nuevas se aplican solas al arrancar. |
| Código del frontend (`frontend/src`, `public/`) o configuración de Nginx | `docker compose up -d --build` | Se reconstruye y recrea `frontend`. |
| `backup/backup.sh` | `docker compose restart db` | El script se lee al arrancar el contenedor. La base se reinicia en unos segundos. |
| `docker-compose.yml` | `docker compose up -d --remove-orphans` | Aplica los cambios y elimina contenedores de servicios que ya no existen. |

### Actualizar a una versión nueva

```bash
docker compose exec db sh /backup.sh ahora   # 1. respaldo previo
git pull                                     # 2. traer el código nuevo
docker compose up -d --build                 # 3. reconstruir y reiniciar
docker image prune -f                        # 4. (opcional) borrar imágenes viejas sin uso
```

Verificar después con `docker compose ps` que los contenedores estén `healthy`.

---

## Respaldos

### Dónde se guardan

En una **carpeta del servidor, fuera de Docker**, definida por `BACKUP_DIR` en `.env`:

| Configuración | Ubicación |
|---|---|
| `BACKUP_DIR` vacío (por defecto) | Carpeta `backups/` dentro del proyecto, por ejemplo `C:\...\factura\backups` o `/opt/factura/backups` |
| `BACKUP_DIR=D:/Respaldos/factura` | Esa carpeta en Windows (usar `/` en la ruta) |
| `BACKUP_DIR=/mnt/respaldos/factura` | Esa carpeta en Linux |

Dentro del contenedor `db` esa carpeta se ve como `/backups`. Cada respaldo son **dos archivos con la misma fecha y hora**: `factura-db-AAAAMMDD-HHMM.dump` (base) y `factura-archivos-AAAAMMDD-HHMM.tgz` (archivos de las facturas).

La fecha del último respaldo se ve en **Ajustes → Datos y respaldos**. Los mensajes del proceso aparecen en `docker compose logs db` (líneas `respaldo … listo`).

### Hacer un respaldo en el momento

```bash
docker compose exec db sh /backup.sh ahora
```

### Cambiar la carpeta de respaldos

1. Crear la carpeta nueva (en Linux: `sudo mkdir -p /mnt/respaldos/factura`).
2. Definirla en `.env`, por ejemplo `BACKUP_DIR=D:/Respaldos/factura`.
3. Mover a la carpeta nueva los respaldos existentes que se quieran conservar (copiar o cortar los archivos `factura-*`).
4. Aplicar: `docker compose up -d`.
5. Comprobar: `docker compose exec db sh /backup.sh ahora` y verificar que aparecen los archivos en la carpeta nueva.

### Copia fuera del servidor

Si el servidor se rompe, los respaldos de su disco se pierden con él. Conviene copiar la carpeta de respaldos a otro lugar con regularidad:

- **Disco externo o NAS:** apuntar `BACKUP_DIR` a esa unidad, o copiar los archivos periódicamente:
  ```powershell
  robocopy C:\ruta\factura\backups E:\Respaldos\factura factura-*   # Windows
  ```
  ```bash
  rsync -a /opt/factura/backups/ usuario@otro-equipo:/respaldos/factura/   # Linux
  ```
- **Nube:** apuntar `BACKUP_DIR` a una carpeta sincronizada (OneDrive, Google Drive, Syncthing). Los respaldos **no están cifrados** y contienen los datos de todos los usuarios: usar solo un servicio de confianza.

Los respaldos nunca se pueden descargar desde la web. Además, cada usuario puede exportar todos **sus** datos (JSON, CSV y archivos) desde **Ajustes → Datos y respaldos**.

### Restaurar un respaldo

Reemplaza **todos** los datos actuales por los del respaldo. Usar siempre los **dos archivos de la misma fecha y hora** (la base guarda qué archivo corresponde a cada factura). Reemplazar `AAAAMMDD-HHMM` por la fecha elegida:

```bash
docker compose stop backend worker
docker compose exec db dropdb -U factura factura
docker compose exec db createdb -U factura factura
docker compose exec db pg_restore -U factura -d factura --no-owner /backups/factura-db-AAAAMMDD-HHMM.dump
docker compose run --rm --no-deps backend sh -c "find /data/uploads -mindepth 1 -delete && tar xzf /backups/factura-archivos-AAAAMMDD-HHMM.tgz -C /data/uploads"
docker compose start backend worker
```

Los comandos funcionan igual en PowerShell, Linux y macOS.

### Mover la instalación a otro servidor

1. En el servidor nuevo: clonar el repositorio y copiar el `.env` del servidor anterior.
2. Copiar el par de respaldos más reciente a la carpeta de respaldos del servidor nuevo.
3. `docker compose up -d --build`.
4. Seguir los pasos de [Restaurar un respaldo](#restaurar-un-respaldo).

---

## Acceso con HTTPS (Tailscale)

Con HTTPS la aplicación funciona fuera de casa, se instala como app en el celular y puede mandar notificaciones. La forma más simple, sin abrir puertos a internet, es **Tailscale** (gratuito para uso personal):

1. Instalar Tailscale en el servidor y en el celular, con la misma cuenta.
2. En la consola de Tailscale activar **MagicDNS** y **HTTPS Certificates** (*DNS → HTTPS Certificates*).
3. En el servidor, publicar la aplicación dentro de la red privada:
   ```bash
   tailscale serve --bg 8080
   ```
   Tailscale muestra la dirección, por ejemplo `https://mi-pc.tu-red.ts.net`.
4. En `.env`:
   ```
   COOKIE_SECURE=true
   PUBLIC_URL=https://mi-pc.tu-red.ts.net
   ALLOWED_HOSTS=mi-pc.tu-red.ts.net
   ```
   Si también se entra por la IP local, agregarla a `ALLOWED_HOSTS` separada por coma. Aplicar con `docker compose up -d`.
5. Desde el celular, abrir esa dirección, agregarla a la pantalla de inicio y activar **Ajustes → Avisos → Recibir notificaciones aquí**.

> En iPhone las notificaciones requieren la app agregada a la pantalla de inicio (iOS 16.4 o posterior).

---

## Ingreso con Google

Agrega el botón **Continuar con Google** a la pantalla de ingreso y la opción **Ajustes → Seguridad → Vincular cuenta de Google**. Es opcional: sin configurarlo, todo funciona igual con email y contraseña.

> **Dónde funciona:** Google solo acepta volver a `http://localhost:8080` (entrando desde la misma PC del servidor) o a una dirección con **HTTPS**, como la de [Tailscale](#acceso-con-https-tailscale). Si se entra por la IP de la red (`http://192.168.x.x:8080`), el botón no aparece.

### 1. Crear el proyecto en Google Cloud

1. Entrar a [console.cloud.google.com](https://console.cloud.google.com) con tu cuenta de Google y crear un proyecto: arriba, **Seleccionar proyecto → Proyecto nuevo**, con un nombre como `Factura`.
2. Menú → **APIs y servicios → Pantalla de consentimiento de OAuth** (en la consola nueva se llama **Google Auth Platform**). Tocar **Comenzar** y completar:
   - **Nombre de la app:** `Factura`, y un email de asistencia (el tuyo).
   - **Público:** **Externo**.
   - **Información de contacto:** tu email. Aceptar y **Crear**.
3. **Permisos de datos (alcances):** no hace falta agregar nada. La app solo pide `openid`, `email` y `profile`, que Google no exige verificar.
4. **Público → Publicar app** (estado *En producción*). Si queda *En prueba*, solo pueden entrar las cuentas agregadas como usuarios de prueba.

### 2. Crear el cliente OAuth

1. **APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth** (en la consola nueva: **Google Auth Platform → Clientes → Crear cliente**).
2. **Tipo de aplicación:** *Aplicación web*. **Nombre:** `Factura`.
3. **URI de redireccionamiento autorizados:** agregar, exactos y sin barra al final:
   - `http://localhost:8080/api/v1/auth/google/callback`
   - con HTTPS, también tu `PUBLIC_URL` seguido de `/api/v1/auth/google/callback`, por ejemplo `https://mi-pc.tu-red.ts.net/api/v1/auth/google/callback`.

   Si cambiaste `APP_PORT`, usá ese puerto. **Orígenes autorizados de JavaScript** queda vacío.
4. **Crear** y copiar el **ID de cliente** y el **Secreto del cliente**.

### 3. Configurar el servidor

En `.env`:

```
GOOGLE_CLIENT_ID=1234567890-abc123def456.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxxxxxxxxxx
```

Aplicar con `docker compose up -d`. Al recargar la pantalla de ingreso aparece **Continuar con Google**.

### Cómo se comporta

- **Ya tenés cuenta con el mismo Gmail:** al entrar con Google se vincula sola. Lo mismo con un email de Google Workspace.
- **Tu cuenta usa otro email** (por ejemplo `@hotmail.com`): entrá con tu contraseña y tocá **Ajustes → Seguridad → Vincular cuenta de Google**. Por seguridad, con esas direcciones el vínculo no se hace solo.
- **Cuentas nuevas:** Google crea una cuenta solo si el registro está abierto (el primer usuario, o `ALLOW_REGISTRATION=true`), igual que el registro con contraseña.
- **Cuenta creada con Google:** puede crearse una contraseña en **Ajustes → Seguridad**. Para desvincular Google hace falta tener contraseña, si no, no habría forma de entrar.
- **Privacidad:** la app no guarda ningún token de Google, solo el identificador de la cuenta y su email.

---

## Avisos por email (Gmail)

Una cuenta de correo del servidor (un Gmail creado para esto, o el tuyo) manda los avisos. Cada usuario elige en **Ajustes → Avisos → Email** a qué dirección le llegan y la confirma con un código de 6 dígitos. Si es el email de su cuenta de Google vinculada, se activa sin código.

### 1. Crear una contraseña de aplicación en Gmail

Gmail no acepta la contraseña normal desde otros programas; se usa una **contraseña de aplicación**:

1. En [myaccount.google.com/security](https://myaccount.google.com/security) activar la **Verificación en 2 pasos**, si no está activa.
2. Entrar a [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), escribir un nombre (por ejemplo `Factura`) y tocar **Crear**.
3. Google muestra una contraseña de 16 letras, como `abcd efgh ijkl mnop`. Copiala: no se vuelve a mostrar.

> Si la página dice que la opción no está disponible, falta la verificación en 2 pasos o la cuenta pertenece a una organización (Google Workspace) que la desactivó.

### 2. Configurar el servidor

En `.env`, con la contraseña de aplicación sin espacios:

```
SMTP_USER=tu-cuenta@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
```

Opcional: `SMTP_FROM=Factura <tu-cuenta@gmail.com>` para el remitente. Aplicar con `docker compose up -d`.

### 3. Activarlo

Cada usuario entra a **Ajustes → Avisos → Email**, escribe la dirección, toca **Enviar código** y escribe el código que le llega. Si no aparece, mirar en *Spam*. Después, **Enviar prueba** (arriba, en la misma pantalla) confirma que funciona.

- **Otro proveedor de correo:** cambiar `SMTP_HOST` y `SMTP_PORT` (`587` con STARTTLS o `465` con SSL). La conexión siempre va cifrada y se verifica el certificado del servidor; si el servidor no ofrece TLS, no se envía.
- **Límite de Gmail:** unos 500 correos por día, de sobra para los avisos de un hogar.

---

## Avisos

| Canal | Requisito |
|---|---|
| En la app | Ninguno: la campana del encabezado muestra los avisos del día. |
| Notificaciones del celular o la PC | HTTPS y activarlas en **Ajustes → Avisos**. Las claves de envío se generan solas. |
| Telegram | Crear un bot con **@BotFather**, poner su token en `TELEGRAM_BOT_TOKEN` y tocar **Vincular Telegram** en **Ajustes → Avisos**. |
| Email | Configurar `SMTP_USER` y `SMTP_PASSWORD` (ver [Avisos por email](#avisos-por-email-gmail)) y activarlo en **Ajustes → Avisos → Email**. No necesita HTTPS. |

Cada aviso se envía una sola vez; lo vencido se recuerda una vez por semana.

---

## Seguridad

- **Contraseñas** con hash Argon2, mínimo 10 caracteres; se rechazan las obvias o las que contienen el email.
- **Sesión** en cookie `HttpOnly` y `SameSite=Strict` con token firmado y vencimiento; protección **CSRF** en toda escritura. Cambiar la contraseña cierra las demás sesiones.
- **Fuerza bruta:** 5 intentos de ingreso cada 5 minutos por IP y email, más límites por IP en Nginx.
- **Ingreso con Google (OAuth 2.0 / OpenID Connect):**
  - Flujo de código con **PKCE**, `state` y `nonce` de un solo uso, guardados en una cookie firmada `HttpOnly` que vence a los 10 minutos.
  - El `id_token` se valida completo: firma RS256 con las claves de Google, emisor, destinatario, vencimiento, `nonce` y email verificado.
  - Una cuenta existente se vincula sola solo si Google es la autoridad del email (Gmail o Workspace).
  - No hay redirecciones a direcciones externas y no se guarda ningún token de Google.
- **Email:**
  - El código de verificación vence a los 15 minutos, se anula al quinto intento fallido y se guarda solo como HMAC.
  - Máximo 3 códigos cada 15 minutos por usuario.
  - El envío siempre va por TLS verificado y los correos son de texto plano.
- **Aislamiento entre usuarios:** cada consulta filtra por usuario; las pruebas automáticas recorren todas las rutas de la API verificando sesión, CSRF y acceso a datos ajenos.
- **Archivos:** tipo validado por contenido, límite de 15 MB, nombres aleatorios; el XML se lee sin XXE y el OCR tiene límites de páginas, píxeles y tiempo.
- **Cabeceras:** CSP estricta, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`. Con `ALLOWED_HOSTS` se bloquea el *DNS rebinding*.
- **Contenedores:** `frontend`, `backend` y `worker` corren sin root, sin capacidades del kernel y con `no-new-privileges`. Solo se expone el puerto web; la base no es accesible desde fuera de Docker.
- **Datos sensibles fuera del repositorio:** `.env` y los respaldos están en `.gitignore`.

---

## Operación y solución de problemas

```bash
docker compose ps                       # estado de los contenedores
docker compose logs -f backend worker   # registros en vivo de la API y del worker
docker compose logs db                  # registros de la base y de los respaldos
docker compose restart backend          # reiniciar un contenedor
docker compose stop                     # detener todo (los datos se conservan)
docker compose up -d                    # volver a iniciar
```

| Síntoma | Qué revisar |
|---|---|
| La página no abre | `docker compose ps`: los 4 contenedores deben estar `running`. Si el puerto 8080 está ocupado, cambiar `APP_PORT`. |
| La app abre pero no carga datos (error 502) | `docker compose logs backend`: suele ser una variable de `.env` mal configurada o la base todavía iniciando. |
| El backend no arranca: `SECRET_KEY no fue configurada` | Generar una clave aleatoria (ver [Instalación](#instalación)). |
| *Ajustes* dice que no hay respaldos | `docker compose logs db` y verificar que `BACKUP_DIR` exista y Docker tenga acceso a esa unidad. |
| No llegan notificaciones al celular | Requieren HTTPS, `COOKIE_SECURE=true` y `PUBLIC_URL` (ver [HTTPS](#acceso-con-https-tailscale)). |
| No aparece **Continuar con Google** | Faltan `GOOGLE_CLIENT_ID` o `GOOGLE_CLIENT_SECRET`, o se entró por la IP de la red: Google solo funciona por `localhost` o por HTTPS. |
| Google muestra `Error 400: redirect_uri_mismatch` | La dirección de vuelta no está registrada: agregar exactamente `http://localhost:8080/api/v1/auth/google/callback` (o la de `PUBLIC_URL`) en el cliente OAuth. |
| Google muestra "Acceso bloqueado" o solo entran algunas cuentas | La app sigue *En prueba*: en Google Cloud, **Público → Publicar app**. |
| No llega el código o los avisos por email | `docker compose logs backend worker`. `SMTPAuthenticationError` = la contraseña de aplicación es incorrecta (no sirve la contraseña normal). Mirar también la carpeta *Spam*. |
| Con la app encendida el servidor pierde acceso a otros equipos de la red | La red interna de Docker coincide con la red Wi-Fi o una VPN. Elegir otro rango libre en `DOCKER_SUBNET` y aplicar con `docker compose down` y `docker compose up -d` (los datos se conservan). |
| `Pool overlaps with other one on this address space` al iniciar | Otra red de Docker ya usa ese rango (`docker network inspect` para verlo). Cambiar `DOCKER_SUBNET`. |

---

## Desarrollo

Entorno local sin Docker para el código (solo la base de pruebas corre en Docker). Requiere Python 3.12, Node 22 y, para el OCR, Tesseract instalado en el equipo.

```bash
# Base de datos de pruebas (desechable)
docker run -d --name factura-test-db -p 5433:5432 -e POSTGRES_USER=factura \
  -e POSTGRES_PASSWORD=factura -e POSTGRES_DB=factura_test postgres:16-alpine

# Backend
cd backend
pip install -r requirements-dev.txt
ruff check .                  # estilo
pytest                        # pruebas automáticas (usan la base de pruebas en el puerto 5433)

# Frontend
cd frontend
npm install
npm run dev                   # http://localhost:5173, reenvía /api a http://localhost:8000
npm run typecheck             # tipos
npm run check:unused          # código y dependencias sin usar
```

Para levantar la API en modo desarrollo (documentación interactiva en http://localhost:8000/api/docs), definir `ENVIRONMENT=development`, `SECRET_KEY` y `DATABASE_URL` apuntando a una base local, y ejecutar `alembic upgrade head` seguido de `uvicorn app.main:app --reload` dentro de `backend/`.

**Cambios en la base de datos:** modificar los modelos en `backend/app/models/`, generar la migración con `alembic revision --autogenerate -m "descripción"`, revisarla y aplicar con `docker compose up -d --build` (el backend la ejecuta al arrancar).

Al terminar, eliminar la base de pruebas con `docker rm -f factura-test-db`.

---

## Estructura del proyecto

```
factura/
├── docker-compose.yml        Servicios: db, backend, worker y frontend
├── .env.example              Plantilla de configuración (copiar como .env)
├── backup/
│   └── backup.sh             Respaldo diario (corre dentro del contenedor db)
├── backend/                  API · Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py           Crea la aplicación, registra rutas y manejo de errores
│   │   ├── worker.py         Avisos (push, Telegram y email) y mantenimiento diario
│   │   ├── core/             Configuración, base de datos, seguridad, límites, errores
│   │   ├── models/           Tablas (SQLAlchemy)
│   │   ├── schemas/          Validación de entrada y salida (Pydantic)
│   │   ├── services/         Lógica de negocio: OCR, factura electrónica, cuentas,
│   │   │                     avisos, email, ingreso con Google, papelera,
│   │   │                     importación, reportes, exportación
│   │   └── api/v1/           Endpoints HTTP
│   ├── alembic/              Migraciones versionadas de la base de datos
│   └── tests/                Pruebas automáticas (pytest)
└── frontend/                 Web · React 18 · TypeScript · Vite · TanStack Query
    ├── Dockerfile
    ├── nginx.conf            Servidor web, límites de pedidos y proxy a la API
    ├── api-proxy.conf        Reenvío al backend (común a todas las rutas /api/)
    ├── security-headers.conf Cabeceras de seguridad
    ├── public/               Íconos, manifiesto PWA y service worker
    └── src/
        ├── api/              Cliente HTTP tipado (con CSRF) y tipos de la API
        ├── hooks/            Consultas y mutaciones con caché (React Query)
        ├── context/          Estado global: mes seleccionado, avisos emergentes, diálogos
        ├── features/         Componentes por dominio: cuentas, facturas, pagos, ajustes…
        ├── pages/            Panel, Facturas, Calendario, Gastos, Cuentas, Reportes, Ajustes
        ├── components/       Componentes reutilizables
        ├── lib/              Formato de montos y fechas, RUC, PWA
        └── styles/           Estilos
```
