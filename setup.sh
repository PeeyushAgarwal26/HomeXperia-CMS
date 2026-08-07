#!/usr/bin/env bash
# =============================================================================
#  setup.sh — homexperia-backend management script
#
#  Commands
#  ────────
#  ./setup.sh setup     First-time setup: venv, deps, .env, database, superadmin
#  ./setup.sh reset     DROP + recreate the database and re-run setup
#  ./setup.sh start     Start the API server (background, logs → uvicorn.log)
#  ./setup.sh stop      Stop the API server
#  ./setup.sh restart   Stop then start
#  ./setup.sh status    Show whether the server is running
#  ./setup.sh logs      Tail live server logs
#  ./setup.sh help      Show this help
#
#  All prompts can be skipped by setting env vars up front, e.g.:
#    DB_HOST=localhost DB_PORT=5432 DB_NAME=homexperia_db DB_USER=postgres DB_PASS=secret \
#    SUPERADMIN_USERNAME=admin SUPERADMIN_PASSWORD=Admin@123 SUPERADMIN_NAME="Super Admin" \
#    SUPERADMIN_EMAIL=admin@homexperia.com SUPERADMIN_PHONE=9999999999 \
#    SUPERADMIN_PINCODE=302001 SUPERADMIN_STATE_CODE=RJ SUPERADMIN_CITY=Jaipur \
#    ./setup.sh setup
# =============================================================================

set -euo pipefail

# Remember whether the caller actually set APP_PORT before we default it below —
# setup_env needs to know whether to prompt, and by then the default has already applied.
_APP_PORT_FROM_ENV="${APP_PORT:-}"
APP_PORT="${APP_PORT:-8080}"
APP_HOST="${APP_HOST:-0.0.0.0}"
APP_ENV_DEFAULT="${APP_ENV:-development}"
VENV_DIR="${VENV_DIR:-.venv}"
ENV_FILE="${ENV_FILE:-.env}"
PID_FILE="${PID_FILE:-.server.pid}"
LOG_FILE="${LOG_FILE:-uvicorn.log}"
REQUIREMENTS="${REQUIREMENTS:-requirements-dev.txt}"
SQL_FILE="${SQL_FILE:-homexperia_v1.sql}"

DB_HOST="${DB_HOST:-}"
DB_PORT="${DB_PORT:-}"
DB_NAME="${DB_NAME:-}"
DB_USER="${DB_USER:-}"
DB_PASS="${DB_PASS:-}"

SUPERADMIN_USERNAME="${SUPERADMIN_USERNAME:-}"
SUPERADMIN_PASSWORD="${SUPERADMIN_PASSWORD:-}"
SUPERADMIN_NAME="${SUPERADMIN_NAME:-Super Admin}"
SUPERADMIN_EMAIL="${SUPERADMIN_EMAIL:-}"
SUPERADMIN_PHONE="${SUPERADMIN_PHONE:-}"
SUPERADMIN_PINCODE="${SUPERADMIN_PINCODE:-}"
SUPERADMIN_STATE_CODE="${SUPERADMIN_STATE_CODE:-}"
SUPERADMIN_CITY="${SUPERADMIN_CITY:-}"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; RESET=''
fi

info()    { echo -e "${CYAN}  [info]${RESET}  $*"; }
success() { echo -e "${GREEN}  [ok]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}  [warn]${RESET}  $*"; }
error()   { echo -e "${RED}  [error]${RESET} $*" >&2; }
die()     { error "$*"; exit 1; }
header()  { echo -e "\n${BOLD}━━━  $*  ${RESET}"; }

if [ "$(uname -s)" = "Darwin" ]; then
    [ -d /opt/homebrew/bin ] && export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
    [ -d /usr/local/bin ]    && export PATH="/usr/local/bin:$PATH"
fi

# Find PID listening on a TCP port — tries lsof → ss → netstat
find_pid_on_port() {
    local port="$1"
    if command -v lsof &>/dev/null; then
        lsof -ti :"$port" 2>/dev/null | head -1 || true
    elif command -v ss &>/dev/null; then
        ss -tlnp 2>/dev/null | awk -v p=":$port" '$4 ~ p {print $0}' \
            | grep -o 'pid=[0-9]*' | cut -d= -f2 | head -1 || true
    elif command -v netstat &>/dev/null; then
        netstat -tlnp 2>/dev/null | awk -v p=":$port " '$4 ~ p {print $7}' \
            | cut -d/ -f1 | head -1 || true
    fi
}

# Force-kill every PID bound to a port, not just the first — a reloader can
# leave more than one process holding the socket. (`xargs -r` is GNU-only,
# so guard emptiness ourselves for BSD/macOS xargs.)
kill_all_on_port() {
    local port="$1" pids
    command -v lsof &>/dev/null || return 0
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null || true
}

# ── Virtual environment / dependencies ────────────────────────────────────────
setup_venv() {
    header "Virtual Environment"
    if [ -d "$VENV_DIR" ]; then
        success "venv already exists at ./${VENV_DIR}"
    else
        info "Creating virtualenv at ./${VENV_DIR} ..."
        python3 -m venv "$VENV_DIR"
        success "venv created"
    fi
}

install_deps() {
    header "Installing Dependencies"
    # shellcheck disable=SC1090
    . "$VENV_DIR/bin/activate"
    pip install -q --upgrade pip
    pip install -q -r "$REQUIREMENTS"
    success "Dependencies installed from ${REQUIREMENTS}"
}

# ── Parse DB creds out of DATABASE_URL in .env ────────────────────────────────
load_db_creds() {
    [ -f "$ENV_FILE" ] || die ".env not found. Run './setup.sh setup' first."

    local url stripped rest pass_encoded hostpart portdb
    url=$(grep "^DATABASE_URL=" "$ENV_FILE" | cut -d= -f2-)

    stripped="${url#postgresql+asyncpg://}"
    _DB_USER="${stripped%%:*}"
    rest="${stripped#*:}"
    pass_encoded="${rest%%@*}"
    _DB_PASS="${pass_encoded//%40/@}"
    hostpart="${rest#*@}"
    _DB_HOST="${hostpart%%:*}"
    portdb="${hostpart#*:}"
    _DB_PORT="${portdb%%/*}"
    _DB_NAME="${portdb#*/}"

    if [ -z "${_DB_HOST:-}" ] || [ -z "${_DB_NAME:-}" ]; then
        die "Could not parse DATABASE_URL from .env. Check its format."
    fi
}

# ── .env — interactive DB + app config wizard ─────────────────────────────────
setup_env() {
    header "Environment Configuration (.env)"

    if [ -f "$ENV_FILE" ]; then
        load_db_creds
        echo ""
        echo -e "${BOLD}  Current database configuration (.env):${RESET}"
        echo -e "    Host : ${CYAN}${_DB_HOST}${RESET}"
        echo -e "    Port : ${CYAN}${_DB_PORT}${RESET}"
        echo -e "    Name : ${CYAN}${_DB_NAME}${RESET}"
        echo -e "    User : ${CYAN}${_DB_USER}${RESET}"
        echo ""

        local confirm_use
        if [ -n "${ENV_RECONFIGURE:-}" ]; then
            confirm_use="n"
            info "Reconfiguring .env from env vars (\$ENV_RECONFIGURE set)."
        elif [ ! -t 0 ]; then
            confirm_use="Y"
            info "Non-interactive shell — keeping existing .env as-is (set \$ENV_RECONFIGURE to override)."
        else
            read -rp "  Use this configuration? [Y/n]: " confirm_use
            confirm_use="${confirm_use:-Y}"
        fi
        if [[ "$confirm_use" =~ ^[Yy]$ ]]; then
            success "Using existing .env configuration."
            return
        fi

        cp "$ENV_FILE" "${ENV_FILE}.bak"
        warn "Existing .env backed up to ${ENV_FILE}.bak"
        rm -f "$ENV_FILE"
    fi

    echo -e "${BOLD}  Database Configuration${RESET}"
    echo -e "  ${CYAN}Tip: set DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASS env vars to skip these prompts.${RESET}\n"

    local db_host db_port db_name db_user db_pass app_env input_port db_pass_encoded secret_key

    if [ -n "${DB_HOST:-}" ]; then
        db_host="$DB_HOST"; info "DB host     → ${db_host}  (from \$DB_HOST)"
    else
        read -rp "  DB host     [localhost]: " db_host
        db_host="${db_host:-localhost}"
    fi

    if [ -n "${DB_PORT:-}" ]; then
        db_port="$DB_PORT"; info "DB port     → ${db_port}  (from \$DB_PORT)"
    else
        read -rp "  DB port     [5432]: " db_port
        db_port="${db_port:-5432}"
    fi

    if [ -n "${DB_NAME:-}" ]; then
        db_name="$DB_NAME"; info "DB name     → ${db_name}  (from \$DB_NAME)"
    else
        while true; do
            read -rp "  DB name     [homexperia_db]: " db_name
            db_name="${db_name:-homexperia_db}"
            [ -n "$db_name" ] && break
            error "Database name is required."
        done
    fi

    if [ -n "${DB_USER:-}" ]; then
        db_user="$DB_USER"; info "DB user     → ${db_user}  (from \$DB_USER)"
    else
        while true; do
            read -rp "  DB user     [postgres]: " db_user
            db_user="${db_user:-postgres}"
            [ -n "$db_user" ] && break
            error "Database user is required."
        done
    fi

    if [ -n "${DB_PASS:-}" ]; then
        db_pass="$DB_PASS"; info "DB password → (from \$DB_PASS)"
    else
        while true; do
            read -rsp "  DB password: " db_pass; echo ""
            if [ -n "$db_pass" ]; then break; fi
            error "Database password is required (set one even for local trust-auth Postgres)."
        done
    fi

    echo ""
    if [ -n "${_APP_PORT_FROM_ENV:-}" ]; then
        info "App port    → ${APP_PORT}  (from \$APP_PORT)"
    else
        read -rp "  App port    [8080]: " input_port
        APP_PORT="${input_port:-8080}"
    fi

    if [ -n "${APP_ENV:-}" ]; then
        app_env="$APP_ENV"; info "App env     → ${app_env}  (from \$APP_ENV)"
    else
        read -rp "  App env     [development] (development/production): " app_env
        app_env="${app_env:-development}"
    fi

    db_pass_encoded="${db_pass//@/%40}"
    secret_key=$(python3 -c "import secrets; print(secrets.token_hex(32))")

    cat > "$ENV_FILE" <<EOF
APP_ENV=${app_env}
APP_NAME=homexperia-admin-api
APP_VERSION=0.1.0
APP_DEBUG=$([ "$app_env" = "development" ] && echo true || echo false)
APP_HOST=${APP_HOST}
APP_PORT=${APP_PORT}

DATABASE_URL=postgresql+asyncpg://${db_user}:${db_pass_encoded}@${db_host}:${db_port}/${db_name}

SECRET_KEY=${secret_key}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=30

CORS_ORIGINS_RAW=http://localhost:5173
FRONTEND_URL=http://localhost:5173

SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_NAME=HomeXperia Admin

UPLOADS_DIR=uploads
UPLOADS_URL_PREFIX=uploads
LOG_DIR=logs
EOF

    _DB_HOST="$db_host"; _DB_PORT="$db_port"; _DB_NAME="$db_name"
    _DB_USER="$db_user"; _DB_PASS="$db_pass"

    success ".env created (SECRET_KEY auto-generated)"
}

# ── Database — create if missing, offer reset-or-keep if it already has tables ─
setup_database() {
    header "Database Setup"
    load_db_creds
    export PGPASSWORD="${_DB_PASS}"

    info "Checking if database '${_DB_NAME}' exists..."
    if psql -h "${_DB_HOST}" -p "${_DB_PORT}" -U "${_DB_USER}" -lqt postgres 2>/dev/null \
            | cut -d'|' -f1 | grep -qw "${_DB_NAME}"; then
        success "Database '${_DB_NAME}' already exists"

        local table_count
        table_count=$(psql -h "${_DB_HOST}" -p "${_DB_PORT}" -U "${_DB_USER}" -d "${_DB_NAME}" -tAc \
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" \
            2>/dev/null || echo "0")
        table_count="${table_count//[[:space:]]/}"

        if [ "${table_count:-0}" -gt 0 ]; then
            echo ""
            warn "Database '${_DB_NAME}' already has ${table_count} table(s)."
            echo -e "  ${BOLD}[k]${RESET}eep existing data and just apply any pending migrations (default)"
            echo -e "  ${BOLD}[d]${RESET}rop the database and start completely fresh"
            local choice
            if [ -n "${DB_RESET_CHOICE:-}" ]; then
                choice="$DB_RESET_CHOICE"
                info "Keep or drop → ${choice}  (from \$DB_RESET_CHOICE)"
            else
                read -rp "  Keep or drop? [k/d]: " choice
                choice="${choice:-k}"
            fi
            if [[ "$choice" =~ ^[Dd]$ ]]; then
                local confirm
                if [ -n "${DB_RESET_CHOICE:-}" ]; then
                    info "Skipping type-to-confirm — \$DB_RESET_CHOICE=d already gave explicit consent."
                else
                    read -rp "  Type the database name to confirm DROP (${_DB_NAME}): " confirm
                    if [ "$confirm" != "${_DB_NAME}" ]; then
                        die "Confirmation did not match — aborting."
                    fi
                fi
                if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
                    info "Stopping running server before drop..."
                    cmd_stop
                fi
                info "Dropping database '${_DB_NAME}'..."
                psql -h "${_DB_HOST}" -p "${_DB_PORT}" -U "${_DB_USER}" \
                     -c "DROP DATABASE \"${_DB_NAME}\";" postgres
                info "Creating database '${_DB_NAME}'..."
                psql -h "${_DB_HOST}" -p "${_DB_PORT}" -U "${_DB_USER}" \
                     -c "CREATE DATABASE \"${_DB_NAME}\";" postgres
                success "Database '${_DB_NAME}' dropped and recreated"
            else
                info "Keeping existing database — pending migrations will still run."
            fi
        fi
    else
        info "Creating database '${_DB_NAME}'..."
        psql -h "${_DB_HOST}" -p "${_DB_PORT}" -U "${_DB_USER}" \
             -c "CREATE DATABASE \"${_DB_NAME}\";" postgres
        success "Database '${_DB_NAME}' created"
    fi

    unset PGPASSWORD
}

run_migrations() {
    header "Database Migrations"
    # shellcheck disable=SC1090
    . "$VENV_DIR/bin/activate"
    info "Running alembic upgrade head..."
    alembic upgrade head
    success "Migrations applied"
}

seed_reference_data() {
    header "Reference Data (states + module catalog)"
    # shellcheck disable=SC1090
    . "$VENV_DIR/bin/activate"
    python -m scripts.seed_reference_data
}

setup_superadmin() {
    header "Super Admin"
    load_db_creds
    export PGPASSWORD="${_DB_PASS}"
    local su_count
    su_count=$(psql -h "${_DB_HOST}" -p "${_DB_PORT}" -U "${_DB_USER}" -d "${_DB_NAME}" -tAc \
        "SELECT COUNT(*) FROM admin_users WHERE is_super_admin = TRUE;" 2>/dev/null || echo "0")
    su_count="${su_count//[[:space:]]/}"
    unset PGPASSWORD

    if [ "${su_count:-0}" -gt 0 ]; then
        success "Super admin already exists — skipping."
        return
    fi

    info "No super admin found — let's create one. This is the only account with"
    info "full access; there is no sign-up page in this admin panel."
    echo ""

    [ -n "${SUPERADMIN_USERNAME:-}" ]  || read -rp   "  Username: " SUPERADMIN_USERNAME
    if [ -z "${SUPERADMIN_PASSWORD:-}" ]; then
        while true; do
            read -rsp "  Password (min 8 chars): " SUPERADMIN_PASSWORD; echo ""
            [ ${#SUPERADMIN_PASSWORD} -ge 8 ] && break
            error "Password must be at least 8 characters."
        done
    fi
    [ -n "${SUPERADMIN_EMAIL:-}" ]      || read -rp   "  Email: " SUPERADMIN_EMAIL
    [ -n "${SUPERADMIN_PHONE:-}" ]      || read -rp   "  Phone number: " SUPERADMIN_PHONE
    [ -n "${SUPERADMIN_PINCODE:-}" ]    || read -rp   "  Pin code: " SUPERADMIN_PINCODE
    [ -n "${SUPERADMIN_STATE_CODE:-}" ] || read -rp   "  State code (e.g. RJ — see docs/02-database-schema.md): " SUPERADMIN_STATE_CODE
    [ -n "${SUPERADMIN_CITY:-}" ]       || read -rp   "  City: " SUPERADMIN_CITY

    [ -n "$SUPERADMIN_USERNAME" ]  || die "Username cannot be empty."
    [ -n "$SUPERADMIN_EMAIL" ]     || die "Email cannot be empty."
    [ -n "$SUPERADMIN_PHONE" ]     || die "Phone number cannot be empty."
    [ -n "$SUPERADMIN_PINCODE" ]   || die "Pin code cannot be empty."
    [ -n "$SUPERADMIN_STATE_CODE" ] || die "State code cannot be empty."
    [ -n "$SUPERADMIN_CITY" ]      || die "City cannot be empty."

    # shellcheck disable=SC1090
    . "$VENV_DIR/bin/activate"
    info "Creating super admin '${SUPERADMIN_USERNAME}'..."
    python -m scripts.create_superadmin \
        --username    "$SUPERADMIN_USERNAME" \
        --password    "$SUPERADMIN_PASSWORD" \
        --name        "$SUPERADMIN_NAME" \
        --email       "$SUPERADMIN_EMAIL" \
        --phone-number "$SUPERADMIN_PHONE" \
        --pin-code    "$SUPERADMIN_PINCODE" \
        --state-code  "$SUPERADMIN_STATE_CODE" \
        --city        "$SUPERADMIN_CITY"
    success "Super admin '${SUPERADMIN_USERNAME}' ready — this is your login."
}

cmd_setup() {
    echo -e "\n${BOLD}  homexperia-backend — First-Time Setup${RESET}\n"

    setup_venv
    install_deps
    setup_env
    setup_database
    run_migrations
    seed_reference_data
    setup_superadmin

    mkdir -p uploads logs

    echo -e "\n${GREEN}${BOLD}  Setup complete!${RESET}"
    echo -e "  Run ${CYAN}./setup.sh start${RESET} to launch the server.\n"
}

cmd_reset() {
    header "Database Reset"
    load_db_creds
    export PGPASSWORD="${_DB_PASS}"

    warn "This will permanently DROP the database '${_DB_NAME}' and recreate it."
    warn "All existing data — including the super admin — will be lost."
    echo ""
    local confirm
    read -rp "  Type the database name to confirm (${_DB_NAME}): " confirm
    if [ "$confirm" != "${_DB_NAME}" ]; then
        die "Confirmation did not match — aborting reset."
    fi

    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        info "Stopping running server before reset..."
        cmd_stop
    fi

    info "Dropping database '${_DB_NAME}'..."
    psql -h "${_DB_HOST}" -p "${_DB_PORT}" -U "${_DB_USER}" \
         -c "DROP DATABASE IF EXISTS \"${_DB_NAME}\";" postgres
    info "Creating database '${_DB_NAME}'..."
    psql -h "${_DB_HOST}" -p "${_DB_PORT}" -U "${_DB_USER}" \
         -c "CREATE DATABASE \"${_DB_NAME}\";" postgres
    success "Database '${_DB_NAME}' dropped and recreated"
    unset PGPASSWORD

    run_migrations
    seed_reference_data
    setup_superadmin

    echo -e "\n${GREEN}${BOLD}  Reset complete!${RESET}"
    echo -e "  Run ${CYAN}./setup.sh start${RESET} to launch the server.\n"
}

cmd_start() {
    header "Starting Server"

    if [ -f "$PID_FILE" ]; then
        local old_pid
        old_pid=$(cat "$PID_FILE")
        if kill -0 "$old_pid" 2>/dev/null; then
            warn "Server is already running (PID ${old_pid})."
            warn "Use './setup.sh restart' to restart it."
            return
        else
            rm -f "$PID_FILE"
        fi
    fi

    [ -d "$VENV_DIR" ] || die "venv not found. Run './setup.sh setup' first."
    [ -f "$ENV_FILE" ] || die ".env not found. Run './setup.sh setup' first."

    # shellcheck disable=SC1090
    . "$VENV_DIR/bin/activate"

    info "Starting uvicorn — hot-reload on http://${APP_HOST}:${APP_PORT} ..."
    nohup uvicorn app.main:app --host "$APP_HOST" --port "$APP_PORT" --reload \
        >> "$LOG_FILE" 2>&1 &

    local pid=$!
    echo "$pid" > "$PID_FILE"

    local i=0
    while ! kill -0 "$pid" 2>/dev/null && [ "$i" -lt 5 ]; do
        sleep 1; i=$((i+1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        success "Server started (PID ${pid})"
        success "API  → http://localhost:${APP_PORT}"
        success "Docs → http://localhost:${APP_PORT}/docs"
        info    "Logs → ./${LOG_FILE}  (run './setup.sh logs' to tail)"
    else
        rm -f "$PID_FILE"
        die "Server failed to start. Check ./${LOG_FILE} for details."
    fi
}

cmd_stop() {
    header "Stopping Server"

    local pid=""
    [ -f "$PID_FILE" ] && pid=$(cat "$PID_FILE")

    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        pid=$(find_pid_on_port "$APP_PORT" || true)
        if [ -n "$pid" ]; then
            warn "No valid PID file — found process on port ${APP_PORT} (PID ${pid})."
        else
            warn "Server does not appear to be running."
            rm -f "$PID_FILE"
            return
        fi
    fi

    info "Stopping server (PID ${pid})..."
    kill "$pid" 2>/dev/null || true

    local i=0
    while kill -0 "$pid" 2>/dev/null && [ "$i" -lt 10 ]; do
        sleep 1; i=$((i+1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        warn "Process did not stop cleanly — force killing..."
        kill -9 "$pid" 2>/dev/null || true
    fi

    # `uvicorn --reload` runs a reloader parent + a separate worker child that
    # actually binds the port — killing the parent PID doesn't always reach
    # the child. Sweep everything still bound to the port as a backstop.
    kill_all_on_port "$APP_PORT"

    rm -f "$PID_FILE"
    success "Server stopped"
}

cmd_restart() {
    cmd_stop
    cmd_start
}

cmd_status() {
    header "Server Status"

    local running=0

    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            success "Running  (PID ${pid})"
            success "API  → http://localhost:${APP_PORT}"
            success "Docs → http://localhost:${APP_PORT}/docs"
            running=1
        else
            warn "PID file exists but process ${pid} is not running (stale — removed)."
            rm -f "$PID_FILE"
        fi
    fi

    if [ "$running" -eq 0 ]; then
        local pid
        pid=$(find_pid_on_port "$APP_PORT" || true)
        if [ -n "$pid" ]; then
            warn "Process on port ${APP_PORT} (PID ${pid}) but no PID file — started outside this script."
        else
            info "Server is not running."
            info "Start it with: ./setup.sh start"
        fi
    fi
}

cmd_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        warn "Log file '${LOG_FILE}' not found. Has the server been started yet?"
        exit 1
    fi
    echo -e "${CYAN}  Tailing ${LOG_FILE} — press Ctrl+C to stop${RESET}\n"
    tail -f "$LOG_FILE"
}

cmd_help() {
    echo -e "
${BOLD}  setup.sh — homexperia-backend management${RESET}

  ${BOLD}Usage:${RESET}  ./setup.sh <command>

  ${BOLD}Commands:${RESET}
    ${GREEN}setup${RESET}      First-time setup — venv, deps, .env, database, super admin
    ${GREEN}reset${RESET}      DROP + recreate the database and re-run setup
    ${GREEN}start${RESET}      Start the API server in the background
    ${GREEN}stop${RESET}       Stop the running API server
    ${GREEN}restart${RESET}    Stop then start the server
    ${GREEN}status${RESET}     Show whether the server is running
    ${GREEN}logs${RESET}       Tail live server logs (Ctrl+C to exit)
    ${GREEN}help${RESET}       Show this help message

  ${BOLD}Quick start on a fresh machine:${RESET}
    ${CYAN}./setup.sh setup${RESET}   ← prompts for DB creds + super admin details
    ${CYAN}./setup.sh start${RESET}

  ${BOLD}Non-interactive / CI mode (env vars skip all prompts):${RESET}
    export DB_HOST=localhost DB_PORT=5432 DB_NAME=homexperia_db DB_USER=postgres DB_PASS=secret
    export SUPERADMIN_USERNAME=admin SUPERADMIN_PASSWORD=Admin@123
    export SUPERADMIN_EMAIL=admin@homexperia.com SUPERADMIN_PHONE=9999999999
    export SUPERADMIN_PINCODE=302001 SUPERADMIN_STATE_CODE=RJ SUPERADMIN_CITY=Jaipur
    ./setup.sh setup
"
}

main() {
    case "${1:-help}" in
        setup)   cmd_setup ;;
        reset)   cmd_reset ;;
        start)   cmd_start ;;
        stop)    cmd_stop ;;
        restart) cmd_restart ;;
        status)  cmd_status ;;
        logs)    cmd_logs ;;
        help|-h|--help) cmd_help ;;
        *) error "Unknown command: ${1:-}"; cmd_help; exit 1 ;;
    esac
}

main "$@"
