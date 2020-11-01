import machine
import network
import uasyncio
import utime
import usys

from machine import Pin

# Threshold for "hold button" action which turns off the relay
# Time is x * 100 milliseconds
# Default 15 => 1500 ms => 1.5s
BUTTON_HOLD_ITERS = 15

# Increment in milliseconds to add when the button is pressed once
T_INCREMENT = 30 * 1000

# Page title in the web UI
PAGE_TITLE = "Timer control"

# DHCP hostname
HOSTNAME = "timer"

# Wi-Fi connection info
SSID = "Wi-Fi name"
PSK = "Wi-Fi password"

# GPIOs. Defaults are for the Sonoff Basic
btn = Pin(0, Pin.IN, Pin.PULL_UP)
relay = Pin(12, Pin.OUT, value=0)
led = Pin(13, Pin.OUT, value=0)  # Inverted, ON

# HTML page template. If you want to disable auto-refresh,
# remove the `meta http-equiv` line.
html = """<!DOCTYPE html>
<html>
<head>
<meta http-equiv="refresh" content="5">
<title>{title}</title>
</head>
<body>
<h1>{title}</h1>
{content}
</body>
</html>""".format(title)

wlan = network.WLAN(network.STA_IF)


def do_connect():
    wlan.active(True)
    wlan.config(dhcp_hostname=HOSTNAME)
    if not wlan.isconnected():
        print('connecting to network...')
        wlan.connect(SSID, PSK)


async def blink_led():
    # LED is inverted
    led.on()
    for i in range(1):
        await uasyncio.sleep_ms(100)
        led.off()
        await uasyncio.sleep_ms(100)
        led.on()
    await uasyncio.sleep_ms(100)
    led.off()


class RelayTimer:
    button_down_t = 0
    last_run_until = 0
    run_until = 0
    btn_down_count = 0
    sock_inited = False

    def increment(self):
        time = utime.ticks_ms()
        if self.run_until < time:
            self.run_until = time + T_INCREMENT
        else:
            self.run_until += T_INCREMENT

    # Interrupt service routine, stores modified values for later use in mainloop
    def on_button(self, pin):
        self.increment()
        self.button_down_t = utime.ticks_ms()
        self.btn_down_count = 0

    async def http_response(self, reader, writer, status, headers=[], body=''):
        await reader.read(1000)
        writer.write("HTTP/1.0 ")
        writer.write(str(status))
        writer.write("\r\nConnection: close\r\n")
        writer.write('\r\n'.join(headers))
        writer.write("\r\n\r\n")
        writer.write(body)
        await writer.drain()
        reader.close()
        writer.close()
        await reader.wait_closed()
        await writer.wait_closed()

    def get_web_page(self):
        time = utime.ticks_ms()
        remaining = (self.run_until - time)//1000
        if remaining < 0:
            remaining = 0
        return html.format(content="""
        <div>
            <ul>
                <li>Status: {status}</li>
                <li>Remaining: {remaining} sec</li>
                <li><a href="/off">Turn off</a></li>
                <li><a href="/incr">Add {increment} sec</a></li>
            </ul>
        </div>
        <div>
            <form action="/" method="get">
                Turn on for: <input autofocus required
  inputmode="numeric" onfocus="this.setSelectionRange(this.value.length, this.value.length);" name="run" id="run"><input type="submit" value="Run">
            </form>
        </div>""".format(status=('OFF' if self.run_until < time else 'ON'), remaining=remaining, increment=T_INCREMENT//1000))

    async def on_connection(self, reader, writer):
        try:
            # Read and keep request method, path and HTTP version
            method, path, httpv = (await reader.readline()).decode().split(' ')

            # Refuse wrong HTTP methods
            if method != 'GET':
                return await self.http_response(reader, writer, '405 Method Not Allowed', '405 Method not allowed')

            if path.startswith('/?run='):
                # Run with provided timeout
                time = utime.ticks_ms()
                run_for = int(path.split('=')[1].strip())
                self.run_until = time + run_for * 1000
                return await self.http_response(reader, writer, '303 See Other', ['Location: /'])
            elif path.strip() == '/':
                # Just show the page
                return await self.http_response(reader, writer, '200 OK', [], self.get_web_page())
            elif path.strip() == '/off':
                # Trigger turn off in mainloop
                self.run_until = 1
                return await self.http_response(reader, writer, '303 See Other', ['Location: /'])
            elif path.strip() == '/incr':
                # Perform incremenent the same way the button would
                self.increment()
                return await self.http_response(reader, writer, '303 See Other', ['Location: /'])

            return await self.http_response(reader, writer, '404 Not Found', [], '404 Not Found')

        except Exception as e:
            await self.http_response(reader, writer, '500 Internal Server Error', [], '500 Internal Server Error')
            print("Exception while handling HTTP request")
            usys.print_exception(e)

    def all_off(self):
        print("Turning off")
        relay.off()
        self.run_until = 0
        self.last_run_until = 0

    async def mainloop(self):
        if wlan.isconnected() and not self.sock_inited:
            print("Connected to Wi-Fi:", wlan.config('essid'))
            ip, nm, gw, dns = wlan.ifconfig()
            print("- Address:", ip, 'mask', nm)
            print("- Gateway:", gw)
            await uasyncio.start_server(self.on_connection, "0.0.0.0", 80)
            print("Listening on 0.0.0.0:80/tcp")
            self.sock_inited = True

        time = utime.ticks_ms()

        # Check button hold
        if btn.value() == 0:
            if self.btn_down_count == BUTTON_HOLD_ITERS:
                # Button held down for BUTTON_HOLD_ITERS * 100 milliseconds
                # Trigger turn off action
                self.run_until = 1
            self.btn_down_count += 1
        else:
            self.btn_down_count = 0

        # Timer not set, no op
        if self.run_until == 0:
            # Yield to HTTP server
            await uasyncio.sleep_ms(100)
            return

        # Timer changed, check and turn on relay
        if self.last_run_until != self.run_until:
            if self.run_until > time:
                print("Running for", (self.run_until - time) / 1000, "seconds")
                relay.on()

        # Timer expired, turn off relay
        if time > self.run_until:
            self.all_off()

        # Timer changed, reset last saved and blink LED
        if self.last_run_until != self.run_until:
            self.last_run_until = self.run_until
            await blink_led()

        # Yield to HTTP server
        await uasyncio.sleep_ms(100)

    async def main(self):
        btn.irq(trigger=Pin.IRQ_FALLING, handler=self.on_button)
        while True:
            await self.mainloop()


def main():
    do_connect()
    timer = RelayTimer()
    try:
        uasyncio.run(timer.main())
    except (Exception, KeyboardInterrupt) as e:
        timer.all_off()
        led.on() # OFF
        usys.print_exception(e)
