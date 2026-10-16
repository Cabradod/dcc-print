# dcc-print 🖨️

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![DCC UChile](https://img.shields.io/badge/DCC-UChile-red.svg)](https://www.dcc.uchile.cl)
[![Python 3](https://img.shields.io/badge/Python-3.8+-green.svg)](https://www.python.org/)

Cliente de impresión CLI remoto para la comunidad del **Departamento de Ciencias de la Computación (DCC) de la Universidad de Chile** a través del servidor **Anakena**.

Permite imprimir documentos PDF y PostScript en un solo comando directamente desde tu computador personal a las impresoras del **Laboratorio Toqui** o de la **Salita**, con soporte para dúplex, simple faz, consulta de cuota de papel restante (`papel`), inspección de colas y modo carpeta vigilada (*watch mode*).

---

## ⚡ Instalación Rápida (1 solo comando)

Abre tu terminal en Linux o macOS y ejecuta:

```bash
curl -fsSL https://raw.githubusercontent.com/Cabradod/dcc-print/main/install.sh | bash
```

O si prefieres clonar el repositorio:

```bash
git clone https://github.com/Cabradod/dcc-print.git
cd dcc-print
./install.sh
```

El instalador colocará el comando en `~/.local/bin/dcc-print` y te pedirá tu usuario de Anakena por única vez.

---

## 🔑 Paso Recomendado: Acceso Sin Contraseña (1 sola vez)

Para no tener que escribir tu contraseña del DCC cada vez que quieras imprimir:

```bash
dcc-print --setup-ssh
```

Este comando:
1. Detecta o genera tu llave SSH (`~/.ssh/id_ed25519`).
2. La copia a `tu_usuario@anakena.dcc.uchile.cl` mediante `ssh-copy-id` (te pedirá la contraseña una última vez).
3. Habilita `ControlMaster` en tu `~/.ssh/config` para reutilizar conexiones SSH en segundo plano, haciendo que imprimir tome apenas **fracciones de segundo**.

---

## 🏛️ Destinos de Impresión: Toqui vs Salita

### 1. Laboratorio Toqui (Por defecto)
En el Toqui no es necesario especificar la impresora, ya que la cola predeterminada (`hp`) distribuye automáticamente tus trabajos.

```bash
# Imprime en Toqui en dúplex (doble cara, borde largo)
dcc-print apunte.pdf
```

> **Nota:** En el Toqui existen 2 impresoras físicas. Si deseas enviar tu documento específicamente a una de ellas:
> - `--toqui1` (dirige a `hp1`)
> - `--toqui2` (dirige a `hp2`)
>
> ```bash
> dcc-print --toqui1 informe.pdf
> dcc-print --toqui2 guia.pdf
> ```

### 2. La Salita (`hp-335`)
Para imprimir en la impresora ubicada en el pasillo / salita:

```bash
dcc-print --salita guia.pdf
```
*(También puedes usar `-p hp-335`).*

---

## 📖 Ejemplos de Uso

### Impresión Simple Faz (1 sola cara)
```bash
dcc-print --simplex guia.pdf
# o con la opción corta:
dcc-print -s guia.pdf
```

### Dúplex Borde Corto (Formato Libreta / Calendario)
```bash
dcc-print -l certamen_pasado.pdf
```

### Varias Copias y Múltiples Archivos
```bash
dcc-print -n 2 informe.pdf
dcc-print seccion1.pdf seccion2.pdf resumen.ps
```

### Consultar Cuota de Papel Restante (`papel`)
Consulta directamente tu saldo de hojas disponibles en Anakena:
```bash
dcc-print --quota
# o:
dcc-print -q
```

### Ver Cola de Impresión (`lpq`)
```bash
# Ver cola en Toqui
dcc-print --queue

# Ver cola en la Salita
dcc-print --salita --queue
```

### Cancelar un Trabajo
```bash
dcc-print --cancel <JOB_ID>
```

### Modo "Carpeta Caliente" (Watcher)
Ideal si quieres dejar una carpeta vigilada en tu computador (por ejemplo en Descargas) y que cada PDF que guardes allí se imprima automáticamente:

```bash
dcc-print --watch
```
*Vigila `~/DCC-Impresiones/` (la crea automáticamente). Al arrastrar un archivo allí, se imprime y se mueve ordenadamente a `~/DCC-Impresiones/impresos/`.*

### Modificar Configuración
Para cambiar tu usuario por defecto o tu impresora predilecta (Toqui vs Salita):
```bash
dcc-print --config
```

---

## 📋 Tabla de Flags y Parámetros

| Bandera | Descripción | Valor por Defecto |
|---|---|---|
| `files ...` | Archivos PDF o PostScript a imprimir | Obligatorio (salvo en utilidades) |
| `--toqui` | Enviar a la cola automática de Toqui | **Activo por defecto** |
| `--toqui1` | Enviar a la impresora 1 de Toqui (`hp1`) | - |
| `--toqui2` | Enviar a la impresora 2 de Toqui (`hp2`) | - |
| `--salita` | Enviar a la Salita (`hp-335`) | - |
| `-p, --printer` | Especificar nombre manual de impresora | Configurado en `~/.config/dcc-print/` |
| `-d, --duplex` | Doble cara / borde largo | **Activo por defecto** |
| `-s, --simplex` | Una sola cara | - |
| `-l, --short-edge` | Doble cara / borde corto (libreta) | - |
| `-n, --copies N` | Número de copias | `1` |
| `-q, --quota` | Ver saldo de papel restante en Anakena (`papel`) | - |
| `--queue` | Ver cola de impresión activa | - |
| `--cancel ID` | Cancelar un trabajo en cola | - |
| `--setup-ssh` | Configurar llave SSH y aceleración ControlMaster | - |
| `--config` | Modificar usuario o impresora favorita | - |
| `-w, --watch [DIR]` | Monitorear carpeta y auto-imprimir | `~/DCC-Impresiones` |
| `--dry-run` | Simular ejecución sin enviar nada a imprimir | - |

---

## 🛠️ ¿Cómo funciona por debajo?

El flujo tradicional de un estudiante en el DCC requería:
1. `scp archivo.pdf tu_usuario@anakena.dcc.uchile.cl:~/`
2. `ssh tu_usuario@anakena.dcc.uchile.cl`
3. `pdf2ps archivo.pdf out.ps`
4. `duplex out.ps | lpr -P hp-335` (o `duplex out.ps | lpr` en Toqui)
5. Borrar archivos temporales y cerrar sesión.

**`dcc-print` resuelve todo esto en un único paso:**
1. **Streaming sin basura:** Envía el archivo local a través del túnel SSH directo a la entrada estándar (`stdin`) en Anakena, sin requerir `scp` ni dejar archivos residuales en tu `home`.
2. **Entorno aislado:** En Anakena se crea un directorio temporal en `/tmp/dcc_print_XXXXXX` protegido con `trap 'rm -rf ...' EXIT`, garantizando que ante cualquier error o cancelación con `Ctrl+C` no queden archivos huérfanos.
3. **Conversión PostScript automática:** Si el archivo es PDF, ejecuta `pdf2ps` automáticamente en el servidor para evitar que la impresora pause o rechace el documento.
4. **Filtro Dúplex del DCC:** Conecta el documento al filtro `duplex` nativo de Anakena y lo redirige a la cola de impresión correspondiente.

---

## 🤝 Contribuciones

PRs y sugerencias son más que bienvenidas para la comunidad del DCC:
- Reporta cualquier error o impresora nueva en los [Issues](https://github.com/Cabradod/dcc-print/issues).
- Licencia: [MIT](LICENSE).
