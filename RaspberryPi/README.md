# Detalles de la configuración de Raspberry Pi

El primer requisito es cargar Raspberry Pi OS Trixie en la Raspberry Pi 4 con ayuda de Raspberry Pi Imager.

A continuación hay que activar la interfaz serial de la Raspberry Pi. Ejecuta:

```
sudo raspi-config
```

Ve a:

```
Interface Options
→ Serial Port
```

Cuando pregunte:

```
Would you like a login shell to be accessible over serial?
```

Responde:

```
No
```

Cuando pregunte:

```
Would you like the serial port hardware to be enabled?
```

Responde:

```
Yes
```

Luego reinicia:

```
sudo reboot
```

Después revisa:

```
ls -l /dev/serial0
```

Debería apuntar a algo como:

```
/dev/ttyAMA0
```

o:

```
/dev/ttyS0
```

Para Python, usa mejor:

```
/dev/serial0
```

porque es el alias estable.

Si tienes cargado el programa `03_Serial_Send` en el ESP32, tienes conectado el sensor de efecto Hall en el pin 4,  el boton de activación en el pin 23, el pin RX de la Raspberry Pi al pin TX del ESP32 y el pin GND de la Raspberry Pi conectado al pin GND del ESP32, puedes probar la conexión serial con el siguiente comando en una terminal de Raspberry Pi.

```
python3 -m serial.tools.miniterm /dev/serial0 19200
```

Deberás ver los datos enviados por el ESP32.

Para salir usa el comando `Ctrl + ]`

## Proyecto

Primero se debe crear la estructura de carpetas.

```
mkdir -p ~/bici-interactiva/static/videos
mkdir -p ~/bici-interactiva/static/css
mkdir -p ~/bici-interactiva/static/js
mkdir -p ~/bici-interactiva/templates
cd ~/bici-interactiva
```

Copiar los videos a la carpeta `~/bici-interactiva/static/videos` 

Deben tener los nombres `idle.mp4` y `game.mp4` con las siguientes características: resolución 640 × 1024 px, 30 fps, MP4 / H.264.

Instala Flask, es el framework Web basado en Python

```
sudo apt update
sudo apt install -y python3-flask chromium-browser
```

Copia la carpeta `bici-interactiva` que se encuentra en la ruta `~/Documents/GitHub/bici-interactiva/RaspberryPi/bici-interactiva` en el directorio `Home`.

Ejecuta el servidor, dirigete al directorio de la app con el comando `cd ~/bici-interactiva` y ejecuta el comando `python3 app.py`.

Deberías ver algo como:

```
Running on http://0.0.0.0:5000
```

**Para ver el video**

Ahora abre en la Raspberry http://localhost:5000/display


Abre Chromium en modo kiosko, en otra terminal ejecuta:

```
chromium-browser --kiosk http://localhost:5000/display
```

Si tu sistema usa chromium:

```
chromium --kiosk http://localhost:5000/display
```

**Para ingresar el nombre**

Abre Chromium en modo kiosko, en otra terminal ejecuta:

```
chromium-browser --kiosk http://localhost:5000/control
```

Si tu sistema usa chromium:

```
chromium --kiosk http://localhost:5000/control
```

**Para salir del modo kiosko:**

```
Alt + F4
```

o desde terminal por SSH:

```
pkill chromium
```