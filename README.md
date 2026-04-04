# hledger-add-tx 📜

`hledger-add-tx` es una utilidad en Python diseñada para añadir transacciones a tus archivos de **hledger** de forma rápida, segura y no interactiva. Es ideal para scripts de automatización, integraciones con otras herramientas o simplemente para quienes prefieren la velocidad de la línea de comandos. La utilidad ha sido programada con ayuda de la inteligencia artificial.

## ✨ Características principales

* ✅ **Validación de Cuentas**: Verifica que las cuentas existan en tu archivo principal o en archivos incluidos (`include`).
* 🔍 **Resolución de Nombres**: Soporta nombres de cuenta abreviados (leaf accounts) siempre que sean únicos.
* 💰 **Gestión de Commodities**: Infiere automáticamente el formato y precisión (decimales, miles, símbolos) basándose en tus declaraciones de `commodity` y `format`.
* 🛡️ **Validación de Balance**: Asegura que la transacción sume cero antes de escribirla.
* 📂 **Soporte de Includes**: Escanea recursivamente los archivos incluidos en tu journal.
* 🤖 **Modo IA**: Incluye un flag `--help-ai` que devuelve la ayuda en formato JSON para facilitar su uso con LLMs.

## 🚀 Instalación

1. Asegúrate de tener instalado `hledger` y `Python 3`.
2. Clona este repositorio:
```bash
git clone https://github.com/CrudeOhio/hledger-add-tx.git
```
Dale permisos de ejecución:

```bash
chmod +x hledger-add-tx.py
```

Para poder ejecutar el script desde cualquier carpeta simplemente escribiendo `hledger-add-tx`, sigue estos pasos:

3. Preparar el binario local
Primero, creamos el directorio de binarios de usuario si no existe, copiamos el archivo eliminando la extensión .py y le damos permisos de ejecución:

```bash
mkdir -p ~/.local/bin
cp hledger-add-tx.py ~/.local/bin/hledger-add-tx
chmod +x ~/.local/bin/hledger-add-tx
```

4. Configurar el PATH
Debemos asegurarnos de que tu terminal busque comandos en esa carpeta. Abre tu archivo de configuración (normalmente .bashrc o .zshrc):
```bash
nano ~/.bashrc
```
Añade esta línea al final del archivo, si no esta configurado:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

5. Recargar la configuración
Para que los cambios surtan efecto inmediatamente sin cerrar la terminal:
```bash
source ~/.bashrc
```
### ✅ Verificación
Ahora, desde cualquier ubicación, puedes comprobar que el sistema lo reconoce:
```bash
which hledger-add-tx
hledger-add-tx -h
```

## 🛠️ Uso
El script utiliza las variables de entorno LEDGER_FILE o HLEDGER_FILE para localizar tu journal. Si no están definidas, buscará en ~/hledger.journal.

Ejemplo básico
```bash
./hledger-add-tx.py -d "Café matutino" \
  expenses:food "2,50 EUR" \
  assets:cash "-2,50 EUR"
```
Ejemplo avanzado (con código y nota)
```bash
./hledger-add-tx.py -D 2026-04-04 -m "*" --code GIFT01 \
  -p "Amazon" -n "Compra de libro" \
  expenses:books "15,00 EUR" \
  assets:bank "-15,00 EUR"
```
## ⚙️ Argumentos comunes
`-D, --date`: Fecha de la transacción (YYYY-MM-DD).

`-p, --payee`: Beneficiario de la transacción.

`-d, --description`: Descripción general.

`--dry-run`: Muestra lo que se escribiría sin modificar el archivo.

`--amount-column`: Columna para alinear los importes (por defecto 60).
