# bici-interactiva
Este proyecto contiene el código necesario para crear la instalación de bicicleta interactiva

**Objetivo**
Realizar una instalación interactiva que mida la velocidad de una bicicleta para mostrar una serie de animaciones en video, calcular un puntaje basado en la constancia y a la intensidad con la que se pedalea, asociar cada sesión a un perfil en particular y generar una base de datos para llevar un ranking.

## Hardware
Las partes del proyecto consisten en lo siguiente:

**Sensor de velocidad**
- Sensor 49e 945bc
- Imánes de neodimio
- Micro controlador ESP32 DevKit V1

**Interactivo**
- Raspberry Pi 4B
- Memoria Micro SD
- Fuente 5V 3A
- Botón de arranque

**Estructura**
- Bicicleta de Spining
- Pantallas LED 640x1024
- Decodificador de Video
- Cable HDMI

## Software
Se requiere el siguiente software

- Raspberry Pi Imager
- Raspberry Pi OS
- Arduino IDE
- Drivers CH430 / CP2120
- Espressif ESP32 Arduino Core
- Python
- MariaDB

Se realizaran los siguientes programas
- Lector de velocidad para ESP32
- Lector de boton de inicio
- Lector de datos de velocidad de Raspberry Pi
- Servidor Web para ingresar Nombre
- Cliente de Base de Datos para registro
- Programa para hacer append en archivo excel
- Programa gráfico

