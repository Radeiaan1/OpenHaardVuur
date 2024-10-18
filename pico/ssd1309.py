""" MicroPython SSD1309/SSD1306 OLED monochrome display driver.

    Source: https://github.com/rdagger/micropython-ssd1309/blob/master/ssd1309.py
    Port from SPI to I2C Hagen Patzke (using original code from 2022).

    Changes in October 2024: 
    - fix allocation bug in image rotation functions
    - refactoring to separate bitmap preparation from display
      - goal: make faster animation processing possible
      - apply rotation in xform_buf() to make image data independent from the frame buffer
      - add buf_hmsb_to_vlsb() to allow pre-computing image buffers in the format the OLED needs
    - add mirror_horizontal() function
    - remove 8-bit image display routine (load_sprite() now loads monochrome image data)
"""
from math import cos, sin, pi, radians
from micropython import const
from framebuf import FrameBuffer, MONO_HLSB, MONO_HMSB, MONO_VLSB
from utime import sleep_ms


def get_byte_size(width):
    return ((width - 1) >> 3) + 1


class Display(object):
    """Serial interface for monochrome OLED display.

    Note:  All coordinates are zero based.
    """

    # Command constants from display datasheet
    CONTRAST_CONTROL = const(0x81)
    ENTIRE_DISPLAY_ON = const(0xA4)
    ALL_PIXELS_ON = const(0XA5)
    INVERSION_OFF = const(0xA6)
    INVERSION_ON = const(0XA7)
    DISPLAY_OFF = const(0xAE)
    DISPLAY_ON = const(0XAF)
    NOP = const(0xE3)
    COMMAND_LOCK = const(0xFD)
    CHARGE_PUMP = const(0x8D)

    # Scrolling commands
    CH_SCROLL_SETUP_RIGHT = const(0x26)
    CH_SCROLL_SETUP_LEFT = const(0x27)
    CV_SCROLL_SETUP_RIGHT = const(0x29)
    CV_SCROLL_SETUP_LEFT = const(0x2A)
    DEACTIVATE_SCROLL = const(0x2E)
    ACTIVATE_SCROLL = const(0x2F)
    VSCROLL_AREA = const(0xA3)
    SCROLL_SETUP_LEFT = const(0x2C)
    SCROLL_SETUP_RIGHT = const(0x2D)

    # Addressing commands
    LOW_CSA_IN_PAM = const(0x00)
    HIGH_CSA_IN_PAM = const(0x10)
    MEMORY_ADDRESSING_MODE = const(0x20)
    COLUMN_ADDRESS = const(0x21)
    PAGE_ADDRESS = const(0x22)
    PSA_IN_PAM = const(0xB0)
    DISPLAY_START_LINE = const(0x40)
    SEGMENT_MAP_REMAP = const(0xA0)
    SEGMENT_MAP_FLIPPED = const(0xA1)
    MUX_RATIO = const(0xA8)
    COM_OUTPUT_NORMAL = const(0xC0)
    COM_OUTPUT_FLIPPED = const(0xC8)
    DISPLAY_OFFSET = const(0xD3)
    COM_PINS_HW_CFG = const(0xDA)
    GPIO = const(0xDC)

    # Timing and driving scheme commands
    DISPLAY_CLOCK_DIV = const(0xd5)
    PRECHARGE_PERIOD = const(0xd9)
    VCOM_DESELECT_LEVEL = const(0xdb)

    def __init__(self, i2c, address=0x78, width=128, height=64):
        """Constructor for Display.

        Args:
            i2c (Class I2C):  I2C interface for display
            address (Optional int): I2C address (default 0x78)
            width (Optional int): Screen width (default 128)
            height (Optional int): Screen height (default 64)
        """
        self.i2c = i2c
        self.address = (address >> 1)
        self.width = width
        self.height = height
        self.pages = self.height // 8
        self.byte_width = -(-width // 8)  # Ceiling division
        self.buffer_length = self.byte_width * height
        # Buffer
        self.mono_image = bytearray(self.buffer_length)
        # Frame Buffer
        self.monoFB = FrameBuffer(self.mono_image, width, height, MONO_VLSB)
        self.clear_buffers()

        self.reset()
        # Send initialization commands
        for cmd in (
                self.DISPLAY_OFF,
                self.DISPLAY_CLOCK_DIV, 0x80,
                self.MUX_RATIO, self.height - 1,
                self.DISPLAY_OFFSET, 0x00,
                self.DISPLAY_START_LINE,
                self.CHARGE_PUMP, 0x14,
                self.MEMORY_ADDRESSING_MODE, 0x00,
                self.SEGMENT_MAP_FLIPPED,
                self.COM_OUTPUT_FLIPPED,
                self.COM_PINS_HW_CFG, 0x02 if (self.height == 32 or self.height == 16) and (self.width != 64)
                else 0x12,
                self.CONTRAST_CONTROL, 0xFF,
                self.PRECHARGE_PERIOD, 0xF1,
                self.VCOM_DESELECT_LEVEL, 0x40,
                self.ENTIRE_DISPLAY_ON,  # output follows RAM contents
                self.INVERSION_OFF,  # not inverted
                self.DISPLAY_ON):  # on
            self.write_cmd(cmd)

        self.clear_buffers()
        self.present()

    def cleanup(self):
        """Clean up resources."""
        self.clear()
        self.sleep()
        # print('display off')

    def write_cmd(self, command, *args):
        """Write command to display.

        Args:
            command (byte): Display command code.
            *args (optional bytes): Data to transmit.
        """
        self.i2c.writeto(self.address, bytearray([0x80, command]))
        # Handle any passed data
        if len(args) > 0:
            self.write_data(args)

    def write_data(self, data):
        """Write data to display.

        Args:
            data (bytes): Data to transmit.
        """
        if isinstance(data, bytearray):
            self.i2c.writeto(self.address, bytearray([0x40]) + data)
        else:
            self.i2c.writeto(self.address, bytearray([0x40, data]))

    def clear(self):
        """Clear display."""
        self.clear_buffers()
        self.present()

    def clear_buffers(self):
        """Clear internal frame buffer."""
        self.monoFB.fill(0x00)

    def xform_buf(self, buf, w, h, invert=False, rotate=0):
        """Transform a given bytearray with bitmap data to a new bytearray.
           Options are rotation in 90 degree steps and inverting the image.
        """
        w_bytes = get_byte_size(w)
        h_bytes = get_byte_size(h)
        new_w, new_h = w, h

        buf_len = len(buf)

        if invert:  # if we need to invert, do it within the initial buffer
            for idx in range(buf_len):
                buf[idx] ^= 0xFF
            # This is an elegant alternative, but allocates a new buffer, 
            # so is likely less efficient:
            # buf = bytearray(map(lambda b: b ^ 0xFF, buf))

        if rotate == 180:  # 180 degrees -> reverse buffer order and bit order
            buf2 = bytearray(buf_len)
            for idx in range(buf_len):
                # reverse bit order
                cur_byte = buf[idx]
                new_byte = 0
                for i in range(8):
                    new_byte <<= 1
                    new_byte |= (cur_byte & 1)
                    cur_byte >>= 1
                buf2[buf_len - 1 - idx] = new_byte
            buf = buf2
        elif rotate == 90:  # 90 degrees to the right
            new_w, new_h = h, w
            buf2_len = h_bytes * w
            buf2 = bytearray(buf2_len)
            for y1 in range(h):
                for x1 in range(w):
                    y2 = x1
                    x2 = (h - 1) - y1
                    src_idx = (y1 * w_bytes) + (x1 >> 3)
                    src_bit = x1 & 7
                    dst_idx = (y2 * h_bytes) + (x2 >> 3)
                    dst_bit = x2 & 7
                    val_bit = ((buf[src_idx] >> src_bit) & 1) << dst_bit
                    buf2[dst_idx] |= val_bit
            buf = buf2
        elif rotate == 270:  # 90 degrees to the left
            new_w, new_h = h, w
            buf2_len = h_bytes * w
            buf2 = bytearray(buf2_len)
            for y1 in range(h):
                for x1 in range(w):
                    y2 = (w - 1) - x1
                    x2 = y1
                    src_idx = (y1 * w_bytes) + (x1 >> 3)
                    src_bit = x1 & 7
                    dst_idx = (y2 * h_bytes) + (x2 >> 3)
                    dst_bit = x2 & 7
                    val_bit = ((buf[src_idx] >> src_bit) & 1) << dst_bit
                    buf2[dst_idx] |= val_bit
            buf = buf2

        return buf, new_w, new_h

    def mirror_horizontal(self, buf, w, h):
        w_bytes = get_byte_size(w)
        buf2_len = w_bytes * h
        buf2 = bytearray(buf2_len)
        for y1 in range(h):
            for x1 in range(w // 2):  # swap left with right
                x2 = (w - 1) - x1
                y2 = y1
                src_idx = (y1 * w_bytes) + (x1 >> 3)
                src_bit = x1 & 7
                dst_idx = (y2 * w_bytes) + (x2 >> 3)
                dst_bit = x2 & 7
                # left part
                val_bit1 = ((buf[src_idx] >> src_bit) & 1) << dst_bit
                buf2[dst_idx] |= val_bit1
                # right part
                val_bit2 = ((buf[dst_idx] >> dst_bit) & 1) << src_bit
                buf2[src_idx] |= val_bit2
        return buf2

    def load_buf(self, path, w, h):
        """Load a bitmap from a file."""
        array_size = get_byte_size(w) * h
        with open(path, "rb") as f:
            buf = bytearray(f.read(array_size))
        return buf

    def make_fb(self, buf, w, h):
        """Convert a bitmap to a HMSB frame buffer."""
        fb = FrameBuffer(buf, w, h, MONO_HMSB)
        return fb

    def load_sprite(self, path, w, h, invert=False, rotate=0):
        """Load a MONO_HMSB bitmap from disc into a sprite (frame buffer).

        Args:
            path (string): Image file path.
            w (int): Width of image.
            h (int): Height of image.
            invert (bool): True = invert image, False (Default) = normal image.
            rotate (int): 0, 90, 180, 270

        Returns:
             FrameBuffer with the manipulated data
        """
        buf = self.load_buf(path, w, h)
        buf, new_w, new_h = self.xform_buf(buf, w, h, invert, rotate)
        return self.make_fb(buf, new_w, new_h)

    def draw_bitmap(self, path, x, y, w, h, invert=False, rotate=0):
        """Load a MONO_HMSB bitmap from disc and draw it to the internal screen representation.

        Args:
            path (string): Image file path.
            x (int): x-coord of image.
            y (int): y-coord of image.
            w (int): Width of image.
            h (int): Height of image.
            invert (bool): True = invert image, False (Default) = normal image.
            rotate (int): 0, 90, 180, 270
        Notes:
            w x h cannot exceed 2048
        """
        fb = self.load_sprite(path, w, h, invert, rotate)
        self.monoFB.blit(fb, x, y)

    def draw_circle(self, x0, y0, r, invert=False):
        """Draw a circle.

        Args:
            x0 (int): X coordinate of center point.
            y0 (int): Y coordinate of center point.
            r (int): Radius.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        f = 1 - r
        dx = 1
        dy = -r - r
        x = 0
        y = r
        self.draw_pixel(x0, y0 + r, invert)
        self.draw_pixel(x0, y0 - r, invert)
        self.draw_pixel(x0 + r, y0, invert)
        self.draw_pixel(x0 - r, y0, invert)
        while x < y:
            if f >= 0:
                y -= 1
                dy += 2
                f += dy
            x += 1
            dx += 2
            f += dx
            self.draw_pixel(x0 + x, y0 + y, invert)
            self.draw_pixel(x0 - x, y0 + y, invert)
            self.draw_pixel(x0 + x, y0 - y, invert)
            self.draw_pixel(x0 - x, y0 - y, invert)
            self.draw_pixel(x0 + y, y0 + x, invert)
            self.draw_pixel(x0 - y, y0 + x, invert)
            self.draw_pixel(x0 + y, y0 - x, invert)
            self.draw_pixel(x0 - y, y0 - x, invert)

    def draw_ellipse(self, x0, y0, a, b, invert=False):
        """Draw an ellipse.

        Args:
            x0, y0 (int): Coordinates of center point.
            a (int): Semi axis horizontal.
            b (int): Semi axis vertical.
            invert (bool): True = clear line, False (Default) = draw line.
        Note:
            The center point is the center of the x0,y0 pixel.
            Since pixels are not divisible, the axes are integer rounded
            up to complete on a full pixel.  Therefore the major and
            minor axes are increased by 1.
        """
        a2 = a * a
        b2 = b * b
        twoa2 = a2 + a2
        twob2 = b2 + b2
        x = 0
        y = b
        px = 0
        py = twoa2 * y
        # Plot initial points
        self.draw_pixel(x0 + x, y0 + y, invert)
        self.draw_pixel(x0 - x, y0 + y, invert)
        self.draw_pixel(x0 + x, y0 - y, invert)
        self.draw_pixel(x0 - x, y0 - y, invert)
        # Region 1
        p = round(b2 - (a2 * b) + (0.25 * a2))
        while px < py:
            x += 1
            px += twob2
            if p < 0:
                p += b2 + px
            else:
                y -= 1
                py -= twoa2
                p += b2 + px - py
            self.draw_pixel(x0 + x, y0 + y, invert)
            self.draw_pixel(x0 - x, y0 + y, invert)
            self.draw_pixel(x0 + x, y0 - y, invert)
            self.draw_pixel(x0 - x, y0 - y, invert)
        # Region 2
        p = round(b2 * (x + 0.5) * (x + 0.5) +
                  a2 * (y - 1) * (y - 1) - a2 * b2)
        while y > 0:
            y -= 1
            py -= twoa2
            if p > 0:
                p += a2 - py
            else:
                x += 1
                px += twob2
                p += a2 - py + px
            self.draw_pixel(x0 + x, y0 + y, invert)
            self.draw_pixel(x0 - x, y0 + y, invert)
            self.draw_pixel(x0 + x, y0 - y, invert)
            self.draw_pixel(x0 - x, y0 - y, invert)

    def draw_hline(self, x, y, w, invert=False):
        """Draw a horizontal line.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            w (int): Width of line.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        if self.is_off_grid(x, y, x + w - 1, y):
            return
        self.monoFB.hline(x, y, w, int(invert ^ 1))

    def draw_letter(self, x, y, letter, font, invert=False, rotate=False):
        """Draw a letter.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            letter (string): Letter to draw.
            font (XglcdFont object): Font.
            invert (bool): Invert color
            rotate (int): Rotation of letter
        """
        fbuf, w, h = font.get_letter(letter, invert=invert, rotate=rotate)
        # Check for errors
        if w == 0:
            return w, h
        # Offset y for 270 degrees and x for 180 degrees
        if rotate == 180:
            x -= w
        elif rotate == 270:
            y -= h
        self.monoFB.blit(fbuf, x, y)
        return w, h

    def draw_line(self, x1, y1, x2, y2, invert=False):
        """Draw a line using Bresenham's algorithm.

        Args:
            x1, y1 (int): Starting coordinates of the line
            x2, y2 (int): Ending coordinates of the line
            invert (bool): True = clear line, False (Default) = draw line.
        """
        # Check for horizontal line
        if y1 == y2:
            if x1 > x2:
                x1, x2 = x2, x1
            self.draw_hline(x1, y1, x2 - x1 + 1, invert)
            return
        # Check for vertical line
        if x1 == x2:
            if y1 > y2:
                y1, y2 = y2, y1
            self.draw_vline(x1, y1, y2 - y1 + 1, invert)
            return
        # Confirm coordinates in boundary
        if self.is_off_grid(min(x1, x2), min(y1, y2),
                            max(x1, x2), max(y1, y2)):
            return
        self.monoFB.line(x1, y1, x2, y2, invert ^ 1)

    def draw_lines(self, coords, invert=False):
        """Draw multiple lines.

        Args:
            coords ([[int, int],...]): Line coordinate X, Y pairs
            invert (bool): True = clear line, False (Default) = draw line.
        """
        # Starting point
        x1, y1 = coords[0]
        # Iterate through coordinates
        for i in range(1, len(coords)):
            x2, y2 = coords[i]
            self.draw_line(x1, y1, x2, y2, invert)
            x1, y1 = x2, y2

    def draw_pixel(self, x, y, invert=False):
        """Draw a single pixel.

        Args:
            x (int): X position.
            y (int): Y position.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        if self.is_off_grid(x, y, x, y):
            return
        self.monoFB.pixel(x, y, int(invert ^ 1))

    def draw_polygon(self, sides, x0, y0, r, invert=False, rotate=0):
        """Draw an n-sided regular polygon.

        Args:
            sides (int): Number of polygon sides.
            x0, y0 (int): Coordinates of center point.
            r (int): Radius.
            invert (bool): True = clear line, False (Default) = draw line.
            rotate (Optional float): Rotation in degrees relative to origin.
        Note:
            The center point is the center of the x0,y0 pixel.
            Since pixels are not divisible, the radius is integer rounded
            up to complete on a full pixel.  Therefore diameter = 2 x r + 1.
        """
        coords = []
        theta = radians(rotate)
        n = sides + 1
        for s in range(n):
            t = 2.0 * pi * s / sides + theta
            coords.append([int(r * cos(t) + x0), int(r * sin(t) + y0)])

        # Cast to python float first to fix rounding errors
        self.draw_lines(coords, invert)

    def draw_rectangle(self, x, y, w, h, invert=False):
        """Draw a rectangle.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            w (int): Width of rectangle.
            h (int): Height of rectangle.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        self.monoFB.rect(x, y, w, h, int(invert ^ 1))

    def draw_sprite(self, fbuf, x, y, w, h):
        """Draw a sprite.
        Args:
            fbuf (FrameBuffer): Buffer to draw.
            x (int): Starting X position.
            y (int): Starting Y position.
            w (int): Width of drawing.
            h (int): Height of drawing.
        """
        x2 = x + w - 1
        y2 = y + h - 1
        if self.is_off_grid(x, y, x2, y2):
            return
        self.monoFB.blit(fbuf, x, y)

    def draw_text(self, x, y, text, font, invert=False,
                  rotate=0, spacing=1):
        """Draw text.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            text (string): Text to draw.
            font (XglcdFont object): Font.
            invert (bool): Invert color
            rotate (int): Rotation of letter
            spacing (int): Pixels between letters (default: 1)
        """
        for letter in text:
            # Get letter array and letter dimensions
            w, h = self.draw_letter(x, y, letter, font, invert, rotate)
            # Stop on error
            if w == 0 or h == 0:
                return
            if rotate == 0:
                # Fill in spacing
                if spacing:
                    self.fill_rectangle(x + w, y, spacing, h, invert ^ 1)
                # Position x for next letter
                x += (w + spacing)
            elif rotate == 90:
                # Fill in spacing
                if spacing:
                    self.fill_rectangle(x, y + h, w, spacing, invert ^ 1)
                # Position y for next letter
                y += (h + spacing)
            elif rotate == 180:
                # Fill in spacing
                if spacing:
                    self.fill_rectangle(x - w - spacing, y, spacing, h, invert ^ 1)
                # Position x for next letter
                x -= (w + spacing)
            elif rotate == 270:
                # Fill in spacing
                if spacing:
                    self.fill_rectangle(x, y - h - spacing, w, spacing, invert ^ 1)
                # Position y for next letter
                y -= (h + spacing)
            else:
                print("Invalid rotation.")
                return

    def draw_text8x8(self, x, y, text):
        """Draw text using built-in MicroPython 8x8 bit font.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            text (string): Text to draw.
        """
        # Confirm coordinates in boundary
        if self.is_off_grid(x, y, x + 8, y + 8):
            return
        self.monoFB.text(text, x, y)

    def draw_vline(self, x, y, h, invert=False):
        """Draw a vertical line.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            h (int): Height of line.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        # Confirm coordinates in boundary
        if self.is_off_grid(x, y, x, y + h):
            return
        self.monoFB.vline(x, y, h, int(invert ^ 1))

    def fill_circle(self, x0, y0, r, invert=False):
        """Draw a filled circle.

        Args:
            x0 (int): X coordinate of center point.
            y0 (int): Y coordinate of center point.
            r (int): Radius.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        f = 1 - r
        dx = 1
        dy = -r - r
        x = 0
        y = r
        self.draw_vline(x0, y0 - r, 2 * r + 1, invert)
        while x < y:
            if f >= 0:
                y -= 1
                dy += 2
                f += dy
            x += 1
            dx += 2
            f += dx
            self.draw_vline(x0 + x, y0 - y, 2 * y + 1, invert)
            self.draw_vline(x0 - x, y0 - y, 2 * y + 1, invert)
            self.draw_vline(x0 - y, y0 - x, 2 * x + 1, invert)
            self.draw_vline(x0 + y, y0 - x, 2 * x + 1, invert)

    def fill_ellipse(self, x0, y0, a, b, invert=False):
        """Draw a filled ellipse.

        Args:
            x0, y0 (int): Coordinates of center point.
            a (int): Semi axis horizontal.
            b (int): Semi axis vertical.
            invert (bool): True = clear line, False (Default) = draw line.
        Note:
            The center point is the center of the x0,y0 pixel.
            Since pixels are not divisible, the axes are integer rounded
            up to complete on a full pixel.  Therefore the major and
            minor axes are increased by 1.
        """
        a2 = a * a
        b2 = b * b
        twoa2 = a2 + a2
        twob2 = b2 + b2
        x = 0
        y = b
        px = 0
        py = twoa2 * y
        # Plot initial points
        self.draw_line(x0, y0 - y, x0, y0 + y, invert)
        # Region 1
        p = round(b2 - (a2 * b) + (0.25 * a2))
        while px < py:
            x += 1
            px += twob2
            if p < 0:
                p += b2 + px
            else:
                y -= 1
                py -= twoa2
                p += b2 + px - py
            self.draw_line(x0 + x, y0 - y, x0 + x, y0 + y, invert)
            self.draw_line(x0 - x, y0 - y, x0 - x, y0 + y, invert)
        # Region 2
        p = round(b2 * (x + 0.5) * (x + 0.5) +
                  a2 * (y - 1) * (y - 1) - a2 * b2)
        while y > 0:
            y -= 1
            py -= twoa2
            if p > 0:
                p += a2 - py
            else:
                x += 1
                px += twob2
                p += a2 - py + px
            self.draw_line(x0 + x, y0 - y, x0 + x, y0 + y, invert)
            self.draw_line(x0 - x, y0 - y, x0 - x, y0 + y, invert)

    def fill_rectangle(self, x, y, w, h, invert=False):
        """Draw a filled rectangle.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            w (int): Width of rectangle.
            h (int): Height of rectangle.
            visble (bool): True (Default) = draw line, False = clear line.
        """
        if self.is_off_grid(x, y, x + w - 1, y + h - 1):
            return
        self.monoFB.fill_rect(x, y, w, h, int(invert ^ 1))

    def fill_polygon(self, sides, x0, y0, r, invert=False, rotate=0):
        """Draw a filled n-sided regular polygon.

        Args:
            sides (int): Number of polygon sides.
            x0, y0 (int): Coordinates of center point.
            r (int): Radius.
            visble (bool): True (Default) = draw line, False = clear line.
            rotate (Optional float): Rotation in degrees relative to origin.
        Note:
            The center point is the center of the x0,y0 pixel.
            Since pixels are not divisible, the radius is integer rounded
            up to complete on a full pixel.  Therefore diameter = 2 x r + 1.
        """
        # Determine side coordinates
        coords = []
        theta = radians(rotate)
        n = sides + 1
        for s in range(n):
            t = 2.0 * pi * s / sides + theta
            coords.append([int(r * cos(t) + x0), int(r * sin(t) + y0)])
        # Starting point
        x1, y1 = coords[0]
        # Minimum Maximum X dict
        xdict = {y1: [x1, x1]}
        # Iterate through coordinates
        for row in coords[1:]:
            x2, y2 = row
            xprev, yprev = x2, y2
            # Calculate perimeter
            # Check for horizontal side
            if y1 == y2:
                if x1 > x2:
                    x1, x2 = x2, x1
                if y1 in xdict:
                    xdict[y1] = [min(x1, xdict[y1][0]), max(x2, xdict[y1][1])]
                else:
                    xdict[y1] = [x1, x2]
                x1, y1 = xprev, yprev
                continue
            # Non horizontal side
            # Changes in x, y
            dx = x2 - x1
            dy = y2 - y1
            # Determine how steep the line is
            is_steep = abs(dy) > abs(dx)
            # Rotate line
            if is_steep:
                x1, y1 = y1, x1
                x2, y2 = y2, x2
            # Swap start and end points if necessary
            if x1 > x2:
                x1, x2 = x2, x1
                y1, y2 = y2, y1
            # Recalculate differentials
            dx = x2 - x1
            dy = y2 - y1
            # Calculate error
            error = dx >> 1
            ystep = 1 if y1 < y2 else -1
            y = y1
            # Calcualte minimum and maximum x values
            for x in range(x1, x2 + 1):
                if is_steep:
                    if x in xdict:
                        xdict[x] = [min(y, xdict[x][0]), max(y, xdict[x][1])]
                    else:
                        xdict[x] = [y, y]
                else:
                    if y in xdict:
                        xdict[y] = [min(x, xdict[y][0]), max(x, xdict[y][1])]
                    else:
                        xdict[y] = [x, x]
                error -= abs(dy)
                if error < 0:
                    y += ystep
                    error += dx
            x1, y1 = xprev, yprev
        # Fill polygon
        for y, x in xdict.items():
            self.draw_hline(x[0], y, x[1] - x[0] + 2, invert)

    def is_off_grid(self, xmin, ymin, xmax, ymax):
        """Check if coordinates extend past display boundaries.

        Args:
            xmin (int): Minimum horizontal pixel.
            ymin (int): Minimum vertical pixel.
            xmax (int): Maximum horizontal pixel.
            ymax (int): Maximum vertical pixel.
        Returns:
            boolean: False = Coordinates OK, True = Error.
        """
        if xmin < 0:
            print('x-coordinate: {0} below minimum of 0.'.format(xmin))
            return True
        if ymin < 0:
            print('y-coordinate: {0} below minimum of 0.'.format(ymin))
            return True
        if xmax >= self.width:
            print('x-coordinate: {0} above maximum of {1}.'.format(
                xmax, self.width - 1))
            return True
        if ymax >= self.height:
            print('y-coordinate: {0} above maximum of {1}.'.format(
                ymax, self.height - 1))
            return True
        return False

    def buf_hmsb_to_vlsb(self, buf, w, h):
        """Convert a bitmap in HMSB format to VLSB.
           This way we can do this step once (in a preparation phase),
           then we just have to send it to the OLED via present_buf().

            Args:
                buf (bytearray): bitmap in HMSB format.
                w (int): horizontal width.
                h (int): vertical height.
            Returns:
                bytearray: bitmap in VLSB format
        """
        w_bytes = get_byte_size(w)
        h_bytes = get_byte_size(h)
        buf2 = bytearray(h_bytes * w)
        for y1 in range(h):
            page = y1 >> 3
            for x1 in range(w):
                src_idx = (y1 * w_bytes) + (x1 >> 3)
                src_bit = x1 & 7
                dst_idx = (page * w) + x1
                dst_bit = y1 & 7
                val_bit = ((buf[src_idx] >> src_bit) & 1) << dst_bit
                buf2[dst_idx] |= val_bit
        buf = buf2
        return buf

    def present_buf(self, buf, w, h):
        """Present image (given as parameters) to display."""
        column_beg = 0
        column_end = w - 1
        if w == 64:
            # displays with width of 64 pixels are shifted by 32
            column_beg += 32
            column_end += 32
        pages_beg = 0
        pages_end = (h >> 3) - 1
        self.write_cmd(self.COLUMN_ADDRESS)
        self.write_cmd(column_beg)
        self.write_cmd(column_end)
        self.write_cmd(self.PAGE_ADDRESS)
        self.write_cmd(pages_beg)
        self.write_cmd(pages_end)
        self.write_data(buf)

    def present(self):
        """Present image (from internal frame buffer) to display."""
        self.present_buf(self.mono_image, self.width, self.height)

    def reset(self):
        """Perform reset."""
        pass  # there is no RESET command

    def sleep(self):
        """Put display to sleep."""
        self.write_cmd(self.DISPLAY_OFF)

    def wake(self):
        """Wake display from sleep."""
        self.write_cmd(self.DISPLAY_ON)

# eof
