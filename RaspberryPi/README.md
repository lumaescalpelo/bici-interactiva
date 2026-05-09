# Detalles de la configuración de Raspberry Pi

El primer requisito es cargar Raspberry Pi OS Trixie en la Raspberry Pi 4 con ayuda de Raspberry Pi Imager.

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