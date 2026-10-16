#!/usr/bin/env python3
"""
dcc-print: Cliente de impresión remoto para DCC (Universidad de Chile) vía Anakena.

Permite enviar documentos PDF/PS directamente a imprimir en el Laboratorio Toqui
(impresoras por defecto) o en la Salita (hp-335), con soporte para dúplex, simple faz,
consulta de saldo de papel ('papel'), cola de impresión y modo carpeta vigilada.
"""

import argparse
import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

DEFAULT_HOST = "anakena.dcc.uchile.cl"
CONFIG_DIR = Path.home() / ".config" / "dcc-print"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Script remoto en bash que se ejecuta en Anakena
REMOTE_PRINT_SCRIPT = r"""
set -e
PRINTER="$1"
DUPLEX_MODE="$2"
COPIES="$3"
ORIG_NAME="$4"

TMPDIR=$(mktemp -d /tmp/dcc_print_XXXXXX)
trap 'rm -rf "$TMPDIR"' EXIT

INPUT="$TMPDIR/input"
cat > "$INPUT"

# Detección del tipo de archivo y conversión a PostScript
if head -c 1024 "$INPUT" | grep -q "%PDF" || [[ "$ORIG_NAME" == *.pdf ]] || [[ "$ORIG_NAME" == *.PDF ]]; then
    PSFILE="$TMPDIR/doc.ps"
    echo "[anakena] Convirtiendo PDF a PostScript (pdf2ps)..." >&2
    pdf2ps "$INPUT" "$PSFILE"
elif head -c 1024 "$INPUT" | grep -q "%!" || [[ "$ORIG_NAME" == *.ps ]] || [[ "$ORIG_NAME" == *.PS ]]; then
    PSFILE="$INPUT"
else
    # Intento de conversión por defecto
    PSFILE="$TMPDIR/doc.ps"
    echo "[anakena] Intentando convertir con pdf2ps..." >&2
    pdf2ps "$INPUT" "$PSFILE" 2>/dev/null || PSFILE="$INPUT"
fi

LPR_OPTS=()
DEST_DESC="Laboratorio Toqui (cola por defecto)"

if [ -n "$PRINTER" ] && [ "$PRINTER" != "toqui" ] && [ "$PRINTER" != "default" ]; then
    LPR_OPTS+=("-P" "$PRINTER")
    DEST_DESC="Impresora '$PRINTER'"
fi

if [ "$COPIES" -gt 1 ]; then
    LPR_OPTS+=("-#$COPIES")
fi

echo "[anakena] Enviando a $DEST_DESC ($DUPLEX_MODE, $COPIES copia(s))..." >&2

if [ "$DUPLEX_MODE" = "duplex" ]; then
    if command -v duplex >/dev/null 2>&1; then
        duplex "$PSFILE" | lpr "${LPR_OPTS[@]}"
    else
        lpr "${LPR_OPTS[@]}" -o sides=two-sided-long-edge "$PSFILE"
    fi
elif [ "$DUPLEX_MODE" = "short" ]; then
    if command -v duplex >/dev/null 2>&1; then
        duplex -l "$PSFILE" | lpr "${LPR_OPTS[@]}"
    else
        lpr "${LPR_OPTS[@]}" -o sides=two-sided-short-edge "$PSFILE"
    fi
else
    # Simplex (una sola cara)
    lpr "${LPR_OPTS[@]}" "$PSFILE"
fi

echo "[anakena] ✓ Trabajo enviado exitosamente a $DEST_DESC"
"""


def color(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text


def green(text: str) -> str:
    return color(text, "32")


def red(text: str) -> str:
    return color(text, "31")


def yellow(text: str) -> str:
    return color(text, "33")


def cyan(text: str) -> str:
    return color(text, "36")


def bold(text: str) -> str:
    return color(text, "1")


def load_config() -> Dict[str, str]:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(cfg: Dict[str, str]):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass


def normalize_printer(name: Optional[str]) -> str:
    if not name:
        return "toqui"
    clean = name.strip().lower()
    if clean in ("salita", "hp335", "hp-335"):
        return "hp-335"
    if clean in ("toqui", "default", "toqui-default"):
        return "toqui"
    if clean in ("toqui1", "hp1", "toqui-1"):
        return "hp1"
    if clean in ("toqui2", "hp2", "toqui-2"):
        return "hp2"
    return name.strip()


def printer_display_name(printer: str) -> str:
    if printer in ("toqui", "default", ""):
        return "Toqui (impresora por defecto)"
    if printer == "hp-335":
        return "Salita (hp-335)"
    if printer == "hp1":
        return "Toqui 1 (hp1)"
    if printer == "hp2":
        return "Toqui 2 (hp2)"
    return f"Impresora personalizada '{printer}'"


def get_user(args_user: Optional[str], prompt_interactive: bool = True) -> str:
    if args_user:
        return args_user.strip()

    env_user = os.environ.get("DCC_USER")
    if env_user:
        return env_user.strip()

    cfg = load_config()
    if cfg.get("user"):
        return cfg["user"].strip()

    # Si no está configurado y estamos en un terminal interactivo
    if prompt_interactive and sys.stdin.isatty():
        print(bold(cyan("=== Configuración Inicial de dcc-print ===")))
        print(yellow("No se encontró un usuario de Anakena configurado."))
        while True:
            u = input("Ingresa tu nombre de usuario del DCC (ej. juan.perez): ").strip()
            if u:
                break
        resp = input(f"¿Deseas guardar '{u}' como usuario predeterminado? [S/n]: ").strip().lower()
        if resp in ("", "s", "si", "y", "yes"):
            cfg["user"] = u
            save_config(cfg)
            print(green(f"✓ Guardado en {CONFIG_FILE}\n"))
        return u

    print(
        red("Error: No se ha especificado el usuario de Anakena.\n"
            "Usa -u <usuario>, define DCC_USER, o ejecuta 'dcc-print --config'."),
        file=sys.stderr,
    )
    sys.exit(1)


def get_host(args_host: Optional[str]) -> str:
    if args_host:
        return args_host.strip()
    env_host = os.environ.get("DCC_HOST")
    if env_host:
        return env_host.strip()
    cfg = load_config()
    return cfg.get("host", DEFAULT_HOST).strip()


def resolve_printer(args, cfg: Dict[str, str]) -> str:
    if getattr(args, "toqui", False):
        return "toqui"
    if getattr(args, "toqui1", False):
        return "hp1"
    if getattr(args, "toqui2", False):
        return "hp2"
    if getattr(args, "salita", False):
        return "hp-335"
    if args.printer:
        return normalize_printer(args.printer)
    env_printer = os.environ.get("DCC_PRINTER")
    if env_printer:
        return normalize_printer(env_printer)
    if cfg.get("default_printer"):
        return normalize_printer(cfg["default_printer"])
    return "toqui"


def configure_interactive():
    """Menú interactivo para ver y actualizar la configuración de dcc-print."""
    cfg = load_config()
    print(bold(cyan("=== Configuración de dcc-print ===")))
    current_user = cfg.get("user", "(no configurado)")
    current_printer = printer_display_name(cfg.get("default_printer", "toqui"))
    current_host = cfg.get("host", DEFAULT_HOST)

    print(f"1. Usuario Anakena:     {bold(current_user)}")
    print(f"2. Impresora por defecto: {bold(current_printer)}")
    print(f"3. Servidor SSH:         {bold(current_host)}")
    print(f"Archivo de config:       {CONFIG_FILE}\n")

    new_user = input(f"Nuevo usuario DCC [{current_user}]: ").strip()
    if new_user:
        cfg["user"] = new_user

    print("\nElige la impresora predeterminada:")
    print("  1. Toqui (cola automática, recomendada)")
    print("  2. Toqui 1 (hp1)")
    print("  3. Toqui 2 (hp2)")
    print("  4. Salita (hp-335)")
    print("  5. Otra personalizada")
    p_opt = input("Selección [1-5, Enter para mantener actual]: ").strip()

    if p_opt == "1":
        cfg["default_printer"] = "toqui"
    elif p_opt == "2":
        cfg["default_printer"] = "hp1"
    elif p_opt == "3":
        cfg["default_printer"] = "hp2"
    elif p_opt == "4":
        cfg["default_printer"] = "hp-335"
    elif p_opt == "5":
        custom = input("Nombre de la impresora: ").strip()
        if custom:
            cfg["default_printer"] = custom

    save_config(cfg)
    print(bold(green(f"\n✓ Configuración actualizada en {CONFIG_FILE}")))


def print_quota(user: str, host: str, dry_run: bool = False):
    """Consulta la cuota de papel en Anakena."""
    cmd = ["ssh", "-t", f"{user}@{host}", "papel"]
    if dry_run:
        print(f"[dry-run] Ejecutando: {' '.join(shlex.quote(c) for c in cmd)}")
        return
    print(cyan(f"Consultando cuota de papel para {user} en {host}..."))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(red(f"Error al consultar cuota: código {e.returncode}"), file=sys.stderr)


def print_queue(printer: str, user: str, host: str, dry_run: bool = False):
    """Consulta la cola de impresión de la impresora."""
    display = printer_display_name(printer)
    if printer in ("toqui", "default", ""):
        remote_cmd = "lpq"
    else:
        remote_cmd = f"lpq -P {shlex.quote(printer)}"

    cmd = ["ssh", "-t", f"{user}@{host}", remote_cmd]
    if dry_run:
        print(f"[dry-run] Ejecutando: {' '.join(shlex.quote(c) for c in cmd)}")
        return
    print(cyan(f"Consultando cola de impresión para {display} en {host}..."))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(red(f"Error al consultar cola: código {e.returncode}"), file=sys.stderr)


def cancel_job(job_id: str, printer: str, user: str, host: str, dry_run: bool = False):
    """Cancela un trabajo de impresión por ID."""
    if printer in ("toqui", "default", ""):
        remote_cmd = f"lprm {shlex.quote(job_id)}"
    else:
        remote_cmd = f"lprm -P {shlex.quote(printer)} {shlex.quote(job_id)}"

    cmd = ["ssh", "-t", f"{user}@{host}", remote_cmd]
    if dry_run:
        print(f"[dry-run] Ejecutando: {' '.join(shlex.quote(c) for c in cmd)}")
        return
    print(yellow(f"Cancelando trabajo {job_id} en {printer_display_name(printer)}..."))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(red(f"Error al cancelar trabajo: código {e.returncode}"), file=sys.stderr)


def setup_ssh(user: str, host: str):
    """Configura llave SSH y ControlMaster para no volver a pedir contraseña."""
    print(bold(cyan("=== Configuración de Acceso SSH Sin Contraseña para DCC ===")))
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)

    # 1. Verificar si existe llave SSH
    key_types = ["id_ed25519", "id_rsa"]
    pub_key = None
    for kt in key_types:
        candidate = ssh_dir / f"{kt}.pub"
        if candidate.exists():
            pub_key = candidate
            break

    if not pub_key:
        print(yellow("No se encontró una llave SSH en ~/.ssh/. Generando una id_ed25519..."))
        new_key = ssh_dir / "id_ed25519"
        gen_cmd = ["ssh-keygen", "-t", "ed25519", "-f", str(new_key), "-N", ""]
        subprocess.run(gen_cmd, check=True)
        pub_key = ssh_dir / "id_ed25519.pub"
        print(green(f"✓ Llave SSH generada en {new_key}"))

    # 2. Copiar llave con ssh-copy-id
    print(cyan(f"\nCopiando llave pública a {user}@{host}..."))
    print(yellow("(Se te pedirá tu contraseña del DCC una última vez)"))
    copy_cmd = ["ssh-copy-id", "-i", str(pub_key), f"{user}@{host}"]
    res = subprocess.run(copy_cmd)
    if res.returncode == 0:
        print(green("✓ Llave copiada con éxito a Anakena!"))
    else:
        print(red("No se pudo copiar la llave automáticamente."), file=sys.stderr)

    # 3. Configurar ~/.ssh/config para ControlMaster y multiplexing
    config_file = ssh_dir / "config"
    sockets_dir = ssh_dir / "sockets"
    sockets_dir.mkdir(mode=0o700, exist_ok=True)

    block = f"""
# DCC Anakena Connection Multiplexing (dcc-print)
Host anakena anakena.dcc.uchile.cl
    HostName {host}
    User {user}
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h:%p
    ControlPersist 10m
"""
    existing_content = ""
    if config_file.exists():
        existing_content = config_file.read_text(encoding="utf-8")

    if "anakena" not in existing_content:
        with open(config_file, "a", encoding="utf-8") as f:
            f.write(block)
        config_file.chmod(0o600)
        print(green("✓ Configurado ControlMaster en ~/.ssh/config (las conexiones se reutilizan en 0.1s)"))
    else:
        print(green("✓ ~/.ssh/config ya contiene configuración para anakena"))

    print(bold(green("\n¡Listo! Ahora puedes imprimir directamente sin escribir contraseña.")))


def print_file(
    file_path: Path,
    printer: str,
    duplex_mode: str,
    copies: int,
    user: str,
    host: str,
    dry_run: bool = False,
) -> bool:
    """Envía un archivo local a imprimir en Anakena."""
    if not file_path.exists():
        print(red(f"Error: El archivo '{file_path}' no existe."), file=sys.stderr)
        return False
    if not file_path.is_file():
        print(red(f"Error: '{file_path}' no es un archivo regular."), file=sys.stderr)
        return False

    size_mb = file_path.stat().st_size / (1024 * 1024)
    display_dest = printer_display_name(printer)
    print(
        cyan(
            f"Preparando: {bold(file_path.name)} ({size_mb:.2f} MB) -> {display_dest} [{duplex_mode}]"
        )
    )

    remote_bash_args = [printer, duplex_mode, str(copies), file_path.name]
    b64_script = base64.b64encode(REMOTE_PRINT_SCRIPT.encode("utf-8")).decode("ascii")
    quoted_args = " ".join(shlex.quote(a) for a in remote_bash_args)
    remote_cmd_str = f'bash -c "$(echo {b64_script} | base64 -d 2>/dev/null || echo {b64_script} | base64 -D)" dcc-print {quoted_args}'

    ssh_cmd = [
        "ssh",
        "-T",
        f"{user}@{host}",
        remote_cmd_str,
    ]

    if dry_run:
        print(f"[dry-run] Ejecutaría SSH hacia {user}@{host} con:")
        print(f"  Destino: {display_dest}, Duplex: {duplex_mode}, Copias: {copies}")
        print(f"  Archivo enviado por stdin: {file_path}")
        return True

    try:
        with open(file_path, "rb") as f:
            result = subprocess.run(
                ssh_cmd,
                stdin=f,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                if "[anakena]" in line:
                    print(cyan(line))
                else:
                    print(line, file=sys.stderr)

        if result.returncode == 0:
            print(bold(green(f"✓ '{file_path.name}' enviado con éxito a {display_dest}")))
            return True
        else:
            print(
                bold(red(f"✗ Falló la impresión de '{file_path.name}' (código {result.returncode})")),
                file=sys.stderr,
            )
            return False

    except KeyboardInterrupt:
        print(yellow("\nOperación cancelada por el usuario."))
        return False
    except Exception as e:
        print(red(f"Error inesperado: {e}"), file=sys.stderr)
        return False


def watch_folder(
    folder: Path,
    printer: str,
    duplex_mode: str,
    copies: int,
    user: str,
    host: str,
    dry_run: bool = False,
    poll_interval: float = 2.0,
):
    """Monitorea una carpeta e imprime automáticamente cualquier PDF o PS que se guarde en ella."""
    folder.mkdir(parents=True, exist_ok=True)
    printed_dir = folder / "impresos"
    printed_dir.mkdir(exist_ok=True)
    error_dir = folder / "errores"
    error_dir.mkdir(exist_ok=True)

    display_dest = printer_display_name(printer)
    print(bold(cyan(f"Modo Watcher Activo: monitoreando '{folder}' cada {poll_interval}s...")))
    print(cyan(f"Destino: {display_dest} | Modo: {duplex_mode} | Copias: {copies}"))
    print(yellow("Arrastra o guarda tus archivos PDF/PS en esta carpeta para imprimirlos automáticamente."))
    print(yellow("Presiona Ctrl+C para detener.\n"))

    try:
        while True:
            for item in sorted(folder.iterdir()):
                if item.is_dir() or item.name.startswith("."):
                    continue
                if item.suffix.lower() not in [".pdf", ".ps"]:
                    continue

                try:
                    initial_size = item.stat().st_size
                    time.sleep(0.5)
                    if not item.exists() or item.stat().st_size != initial_size:
                        continue
                except OSError:
                    continue

                print(cyan(f"\n[Watcher] Nuevo archivo detectado: {item.name}"))
                ok = print_file(item, printer, duplex_mode, copies, user, host, dry_run=dry_run)
                target_dest = (printed_dir if ok else error_dir) / item.name
                if target_dest.exists():
                    target_dest = (printed_dir if ok else error_dir) / f"{item.stem}_{int(time.time())}{item.suffix}"
                try:
                    shutil.move(str(item), str(target_dest))
                    if ok:
                        print(green(f"[Watcher] Movido a: {target_dest.name}"))
                    else:
                        print(red(f"[Watcher] Error en impresión. Movido a: {target_dest.name}"))
                except OSError as e:
                    print(red(f"[Watcher] Error al mover archivo: {e}"), file=sys.stderr)

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print(yellow("\nWatcher detenido."))


def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(
        description="Cliente de impresión para el DCC (Universidad de Chile) vía Anakena.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Destinos de Impresión:
  Por defecto imprime en el Laboratorio Toqui (sin necesidad de especificar impresora).
  En el Toqui hay 2 máquinas, pero puedes dirigirla a una específica o a la Salita:
    dcc-print documento.pdf               # Imprime en Toqui (cola automática)
    dcc-print --toqui1 documento.pdf      # Imprime en Toqui impresora 1 (hp1)
    dcc-print --toqui2 documento.pdf      # Imprime en Toqui impresora 2 (hp2)
    dcc-print --salita documento.pdf      # Imprime en la Salita (hp-335)
    dcc-print -p hp-335 documento.pdf     # Especificar cualquier impresora

Opciones adicionales:
    dcc-print --simplex apunte.pdf        # Imprime por 1 sola cara
    dcc-print -l guia.pdf                 # Dúplex borde corto (libreta)
    dcc-print -n 2 informe.pdf            # 2 copias
    dcc-print --quota                     # Ver saldo de papel restante ('papel')
    dcc-print --queue                     # Ver estado de la cola en Toqui
    dcc-print --salita --queue            # Ver cola de la impresora de la Salita
    dcc-print --setup-ssh                 # Configurar acceso sin clave (1 sola vez)
    dcc-print --config                    # Cambiar usuario o impresora favorita
        """,
    )

    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Archivo(s) PDF o PostScript a imprimir",
    )

    # Selección de Impresoras
    printer_group = parser.add_mutually_exclusive_group()
    printer_group.add_argument(
        "--toqui",
        action="store_true",
        help="Imprimir en Laboratorio Toqui (cola automática por defecto)",
    )
    printer_group.add_argument(
        "--toqui1",
        action="store_true",
        help="Imprimir en Toqui impresora 1 (hp1)",
    )
    printer_group.add_argument(
        "--toqui2",
        action="store_true",
        help="Imprimir en Toqui impresora 2 (hp2)",
    )
    printer_group.add_argument(
        "--salita",
        action="store_true",
        help="Imprimir en la Salita (impresora hp-335)",
    )
    printer_group.add_argument(
        "-p",
        "--printer",
        help="Nombre específico de impresora (ej. hp-335, hp1, hp2)",
    )

    # Parámetros de conexión
    parser.add_argument(
        "-u",
        "--user",
        help="Usuario en Anakena (si no se indica, usa la configuración guardada)",
    )
    parser.add_argument(
        "--host",
        help=f"Servidor SSH del DCC (defecto: {DEFAULT_HOST})",
    )

    # Opciones de Impresión
    parser.add_argument(
        "-n",
        "--copies",
        type=int,
        default=1,
        help="Número de copias a imprimir (defecto: 1)",
    )

    duplex_group = parser.add_mutually_exclusive_group()
    duplex_group.add_argument(
        "-d",
        "--duplex",
        dest="duplex_mode",
        action="store_const",
        const="duplex",
        default="duplex",
        help="Impresión a doble cara / borde largo (por defecto)",
    )
    duplex_group.add_argument(
        "-s",
        "--simplex",
        dest="duplex_mode",
        action="store_const",
        const="simplex",
        help="Impresión a una sola cara",
    )
    duplex_group.add_argument(
        "-l",
        "--short-edge",
        dest="duplex_mode",
        action="store_const",
        const="short",
        help="Impresión a doble cara / borde corto (formato libreta/calendario)",
    )

    # Acciones y utilidades
    parser.add_argument(
        "-q",
        "--quota",
        action="store_true",
        help="Consultar saldo de papel disponible en Anakena ('papel')",
    )
    parser.add_argument(
        "--queue",
        action="store_true",
        help="Ver trabajos en cola para la impresora seleccionada",
    )
    parser.add_argument(
        "--cancel",
        metavar="JOB_ID",
        help="Cancelar un trabajo de impresión por ID",
    )
    parser.add_argument(
        "--setup-ssh",
        action="store_true",
        help="Configurar llave SSH y aceleración ControlMaster para evitar pedir contraseña",
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Ver o modificar la configuración interactiva de usuario e impresora predeterminada",
    )
    parser.add_argument(
        "--config-init",
        action="store_true",
        help=argparse.SUPPRESS,  # Usado internamente por el instalador
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar lo que se ejecutaría sin enviar nada a la impresora",
    )
    parser.add_argument(
        "-w",
        "--watch",
        nargs="?",
        const=str(Path.home() / "DCC-Impresiones"),
        metavar="CARPETA",
        help="Monitorear una carpeta e imprimir automáticamente (defecto: ~/DCC-Impresiones)",
    )

    args = parser.parse_args()

    if args.config:
        configure_interactive()
        return

    if args.config_init:
        # Si ya tiene usuario, no hacer nada
        if not cfg.get("user"):
            get_user(args.user, prompt_interactive=True)
        return

    user = get_user(args.user, prompt_interactive=True)
    host = get_host(args.host)
    printer = resolve_printer(args, cfg)

    if args.setup_ssh:
        setup_ssh(user, host)
        return

    if args.quota:
        print_quota(user, host, dry_run=args.dry_run)
        return

    if args.queue:
        print_queue(printer, user, host, dry_run=args.dry_run)
        return

    if args.cancel:
        cancel_job(args.cancel, printer, user, host, dry_run=args.dry_run)
        return

    if args.watch:
        watch_folder(
            folder=Path(args.watch).expanduser().resolve(),
            printer=printer,
            duplex_mode=args.duplex_mode,
            copies=args.copies,
            user=user,
            host=host,
            dry_run=args.dry_run,
        )
        return

    if not args.files:
        parser.print_help()
        print(yellow("\nNota: Proporciona al menos un archivo para imprimir o usa --quota / --queue / --watch."))
        sys.exit(1)

    all_ok = True
    for file_path in args.files:
        ok = print_file(
            file_path=file_path,
            printer=printer,
            duplex_mode=args.duplex_mode,
            copies=args.copies,
            user=user,
            host=host,
            dry_run=args.dry_run,
        )
        if not ok:
            all_ok = False

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
