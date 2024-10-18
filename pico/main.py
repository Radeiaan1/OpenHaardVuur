# OLED fire animation for the 2024 HBO-ICT TI Christmas Challenge
# Copyright 2024 Hogeschool Utrecht, Hagen Patzke
# Made available under MIT License
from time import sleep_ms
from machine import I2C, Pin
from ssd1309 import Display

# I2C pins (preferably hardware pins)
I2C_SCL = Pin(5)
I2C_SDA = Pin(4)
# I2C standard speeds, ready for selecting one by index.
# (5MHz never worked when testing, so I left it out.)
I2C_FRQ = (3_400_000, 1_000_000, 400_000, 100_000)[2]
# Number of milliseconds to sleep after each frame.
FRAME_SLEEP = 100


def pico_selftest():
    """BIST (Built-In Self Test).
       Flash the Raspberry Pi PICO LED three times."""
    try:  # RasPi PICO-W has a different LED control way
        led = Pin("LED", Pin.OUT)
    except: # RasPi PICO built-in LED is on Pin 25
        led = Pin(25, Pin.OUT)
    for i in range(3):
        led.on()
        sleep_ms(200)
        led.off()
        sleep_ms(200)


def test_fireplace_animation(display):
    """Attempt at generating a fire animation programmatically.
       (Alas, it does not look very convincing. It is also very slow.)"""
    from random import random
    WIDTH = 128
    HEIGHT = 64
    BLUE_AREA = 16
    for repeat in range(25):
        display.clear_buffers()
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if y < BLUE_AREA:
                    # Create a randomized spark effect in yellow part
                    if random() > 0.95:
                        display.draw_pixel(x, y)
                else:
                    # Density decreases as we move up
                    intensity_threshold = 0.2 + 0.5 * (64 - y) / 48
                    if random() > intensity_threshold:
                        display.draw_pixel(x, y)
        display.present()


def show_welcome_banner(display):
    display.clear_buffers()
    display.draw_text8x8(0, 0x04, 'Merry Christmas!')
    display.draw_text8x8(0, 0x10, '  OLED SSD1306  ')
    display.draw_text8x8(0, 0x18, '  DEMONSTRATION ')
    display.draw_text8x8(0, 0x24, ' Presented  by  ')
    display.draw_text8x8(0, 0x2C, '  Hogeschool    ')
    display.draw_text8x8(0, 0x34, ' U t r e c h t  ')
    display.present()


def prepare_fireplace_animation(display):
    """Load image data from disk and pre-process it for animation.
       We add each frame and add its mirror image.
       Goal is a better animation for this application (fire)."""
    fbuf_array = []
    maxi = 0
    for x in range(4):
        # Load a 128x64 monochrome bitmap from a file.
        buf = display.load_buf(f"px128w64h/vuur{x}.mono", 128, 64)
        # Convert the bitmap to a frame buffer.
        fbuf_array.append(display.make_fb(buf, 128, 64))
        maxi += 1
        # Mirror the bitmap and convert the result to a frame buffer.
        fbuf_array.append(display.make_fb(display.mirror_horizontal(buf, 128, 64), 128, 64))
        maxi += 1
    # To play the animation forward and back without any duplicates we make
    # a list of the frame numbers to play in order.
    displaylist = list(range(0, maxi)) + list(range(maxi - 2, 0, -1))
    # print("show", maxi, "list", displaylist)
    return fbuf_array, displaylist


def play_fireplace_animation(display, fbuf_array, displaylist):
    """Show the fireplace animation, one picture at a time."""
    # display.clear_buffers()  -- image is full screen, we don't need to clear before
    for i in displaylist:
        display.draw_sprite(fbuf_array[i], 0, 0, 128, 64)
        display.present()
        sleep_ms(FRAME_SLEEP)


# main #########################

# Flash Built-In LED three times
pico_selftest()
# Initialize I2C with pins and frequency
i2c = I2C(0, scl=I2C_SCL, sda=I2C_SDA, freq=I2C_FRQ)
# print('I2C scan:', i2c.scan())  # DEBUG
display = Display(i2c)
# Show the welcome message
show_welcome_banner(display)
sleep_ms(20_000)  # without a delay here we can't read any of it :-)
# Prepare the animation (we need to do this only one time)
fbuf_array, displaylist = prepare_fireplace_animation(display)
# Play the fire animation
while True:  # (forever)
    play_fireplace_animation(display, fbuf_array, displaylist)

# eof ########## (end of file)
