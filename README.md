# MicroPython Relay/Sonoff countdown timer

Countdown timer for a Sonoff switch or a random relay, written in MicroPython.

### Features

- Simple countdown timer
- Relay is off when the device is powered. Press the button to add 30 seconds, or a different customizable time increment
- Hold the button to turn it off
- Connect it to Wi-Fi to control it using a simple web UI

![Screenshot](screenshot.png)

Edit the variables at the beginning of the script to customize.

Then, in your `boot.py` add the following code to run it:

```python
import timer
timer.main()
```

**DO NOT EXPOSE IT TO THE PUBLIC INTERNET!**

The web server is extremely basic and intended to be used in private networks only!

## Requires uasyncio!

Uasyncio is included in MicroPython builds only for ESP8266/ESP32 boards with 1MB or more flash.

For ESP8266 boards with 512KB of flash such as the Sonoff Basic, you need to rebuild MicroPython yourself.

I created a patch that disables a few unused drivers, TLS supports (it's not very good anyway) and the WebREPL to reclaim some space, and adds the `uasyncio` module. You can use [rshell](https://github.com/dhylands/rshell) as a replacement for the WebREPL to edit the files.

Building it is just a matter of running the following steps on GNU/Linux (requires `docker`, `git` and `esptool`):

```bash
git clone https://github.com/micropython/micropython.git --recursive
git clone https://github.com/micropython/micropython-lib.git --recursive
git clone https://github.com/Depau/upython-relay-timer.git
cd micropython
git am < ../upython-relay-timer/0001-Slim-ESP8266-with-uasyncio-built-in.patch
alias esp='docker run --rm -v $HOME:$HOME -u $(id -u) -w $(pwd) larsks/esp-open-sdk'
esp make -j12 -C ports/esp8266 BOARD=GENERIC_SLIM
```

Then you can flash it to your Sonoff, the firmware will be located at `ports/esp8266/build-GENERIC_SLIM/firmware-combined.bin`. Follow the official MicroPython instructions. 

```bash

esptool.py --port /dev/ttyUSBx erase_flash
esptool.py --port /dev/ttyUSBx --baud 460800 write_flash --flash_size=detect 0 ports/esp8266/build-GENERIC_SLIM/firmware-combined.bin
```

If you are using an ESP8266 with 1MB or more of flash, there's no need to create a custom build. If you're using an ESP32 with 512KB, you're on your own, read my patch and perform the same things on the ESP32 port.

## License

GNU Affero General Public License 3.0
