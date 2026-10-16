#!/usr/bin/env bash
# ==============================================================================
# Instalador de dcc-print para usuarios del DCC (Universidad de Chile)
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}${CYAN}=== Instalador de dcc-print (DCC Universidad de Chile) ===${NC}\n"

INSTALL_DIR="$HOME/.local/bin"
mkdir -p "$INSTALL_DIR"

TARGET_BIN="$INSTALL_DIR/dcc-print"

# 1. Copiar si se corre localmente, o descargar desde GitHub si se usa con curl
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"

if [ -f "$SCRIPT_DIR/dcc_print.py" ]; then
    echo -e "${CYAN}Instalando desde directorio local...${NC}"
    cp "$SCRIPT_DIR/dcc_print.py" "$TARGET_BIN"
else
    echo -e "${CYAN}Descargando dcc-print desde GitHub...${NC}"
    curl -fsSL "https://raw.githubusercontent.com/Cabradod/dcc-print/main/dcc_print.py" -o "$TARGET_BIN"
fi

chmod +x "$TARGET_BIN"
echo -e "${GREEN}✓ Ejecutable instalado en: ${BOLD}$TARGET_BIN${NC}"

# 2. Verificar que ~/.local/bin esté en el PATH
SHELL_NAME="$(basename "${SHELL:-bash}")"
RC_FILE=""

case "$SHELL_NAME" in
    zsh)
        RC_FILE="$HOME/.zshrc"
        ;;
    bash)
        if [ -f "$HOME/.bash_profile" ]; then
            RC_FILE="$HOME/.bash_profile"
        else
            RC_FILE="$HOME/.bashrc"
        fi
        ;;
    *)
        RC_FILE="$HOME/.profile"
        ;;
esac

if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo -e "${YELLOW}Añadiendo $INSTALL_DIR a tu PATH en $RC_FILE...${NC}"
    echo "" >> "$RC_FILE"
    echo "# dcc-print CLI" >> "$RC_FILE"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC_FILE"
    echo -e "${GREEN}✓ PATH actualizado en $RC_FILE${NC}"
    export PATH="$INSTALL_DIR:$PATH"
fi

# 3. Configuración inicial
echo ""
"$TARGET_BIN" --config-init || true

echo ""
echo -e "${BOLD}${GREEN}==============================================${NC}"
echo -e "${BOLD}${GREEN} ¡Instalación de dcc-print completada con éxito!${NC}"
echo -e "${BOLD}${GREEN}==============================================${NC}\n"
echo -e "Puedes comenzar a imprimir inmediatamente con:"
echo -e "  ${BOLD}dcc-print documento.pdf${NC}          (imprime en Toqui)"
echo -e "  ${BOLD}dcc-print --salita documento.pdf${NC} (imprime en la Salita hp-335)"
echo -e "  ${BOLD}dcc-print --quota${NC}                (ver saldo de papel restante)\n"
echo -e "${YELLOW}Tip recomendado:${NC} ejecuta ${BOLD}dcc-print --setup-ssh${NC} una sola vez para no volver a escribir tu contraseña."
