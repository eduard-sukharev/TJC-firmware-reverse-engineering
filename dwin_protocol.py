import base64
import time
import math
import serial
import struct
import argparse
from PIL import Image
import io


class TJC3224_LCD:
    """
    Class representing the control interface for a TJC3224 LCD display.

    This class is based on the T5UIC1_LCD class from the DWIN_T5UIC1_LCD
    repository available on (https://github.com/odwdinc/DWIN_T5UIC1_LCD)
    for the TJC3224_011N display (3.2 inch, 240x320 pixels, no touch) used
    on 3d printers from creality. Most of the instructions are compatible
    with DWIN T5L instruction set available on the manufacturer website
    (https://www.dwin-global.com/uploads/T5L_TA-Instruction-Set-Development-Guide.pdf)
    """

    # Display resolution
    screen_width = 240
    screen_height = 320

    # Data frame structure
    data_frame_head = b"\xAA"
    data_frame_tail = [0xCC, 0x33, 0xC3, 0x3C]
    data_frame = []

    # Font size registers (for unicode and 8 bit text mode)
    font_8x8 = 0x00
    font_6x12 = 0x01
    font_8x16 = 0x02
    font_12x24 = 0x03
    font_16x32 = 0x04
    font_20x40 = 0x05
    font_24x48 = 0x06
    font_28x56 = 0x07
    font_32x64 = 0x08

    # Colors
    color_white = 0xFFFF
    color_black = 0x0000

    # Instructions
    cmd_handshake = 0x00
    cmd_draw_value = 0x14
    cmd_set_palette = 0x40
    cmd_draw_line = 0x51
    cmd_clear_screen = 0x52
    cmd_draw_rectangle = 0x59
    cmd_fill_rectangle = 0x5B
    cmd_reverse_color_area = 0x5C
    cmd_backlight_brightness = 0x5F
    cmd_show_image = 0x70
    cmd_move_screen_area = 0x09
    cmd_draw_icon = 0x97
    cmd_draw_text = 0x98

    # Alias for extra commands
    direction_up = 0x02
    direction_down = 0x03

    LCD_COLORS = {
        "black":  0x0841,
        "blue":   0x19FF,
        "red":    0xF44F,
        "yellow": 0xFE29,
        "white":  0xFFFF
    }

    img="""
        /9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAUDBAQEAwUEBAQFBQUGBwwIBwcHBw8LCwkMEQ8SEhEPER
        ETFhwXExQaFRERGCEYGh0dHx8fExciJCIeJBweHx7/2wBDAQUFBQcGBw4ICA4eFBEUHh4eHh4eHh4e
        Hh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh7/wAARCABgAGADASIAAhEBAx
        EB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQID
        AAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRk
        dISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2
        t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQ
        AAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEI
        FEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2
        hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU
        1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD4yooooAKKKKACiiigAooooAKKKK
        ACiiigAooooAK6bwL4Sk8Tyzg3bWkUIB3+QXDk9geBkcd889OtdF4R+GUl+Yr3Ub2F7CSNZI/sr5L5
        5wcjjjrXrmm6dZ2NpHaWttHDDGMKiLgCgDzH/hUUW3J1uQcdfsw/+Kqjqfwov4oy+n6pBcN18uWMxn
        HbnJ/pXtkECn7rEH86bcwg5VxtIz24oA+VtTsLzTbx7O+t3gnT7yMP85HuKrV9CeN/DFp4g077PcYj
        uowWt5h1U+nup44/LoK8Au7eW1upbadCksTlHU9iDg0ARUUUUAFFFFABRRRQB6L8H/FE9nejQ53LQy
        5Nvnna3Ur9Dyfr9a9ptbiK4T5DtkHVTXyxp8lxFfQSWpYTiQeXg4Oc+tfQllcTPBFLNE1vMVDPGTyh
        7jj0oA6lJCp5O1h0NWHmguYQrqFlHU+vuPT6VzQ1C4ZSCikqMlyT9cY7/WlOpRiMeaTGWICjqfy4/w
        AaANG7RXBU8lTwV4rxv4y6XELmHWbaF8OxguHA+UsANp9c4yPwFer2k11d3BZohDb52ByQxz2z6Cqe
        r2FpLa3FlqEazW8uVniHp6j3Bw2fUCgD5vorU8UaT/YusS2IuFuEHzJIFK5U9Mg9/pke9ZdABRRRQA
        UUUUAPhkMUySgAlGDAHocV7j4V1tdd0ldRWJk/emOVf7rgAnB7jBBrwuvYfglsXwteM3zIbxt4xnA2
        Jg4/E59jQB2MIVh5UhVQcgN2PHf/ABrRiTT45VaSxMd1jAk3cH3BHFZs9uYZC0fzRnB6+v8AnrSJcS
        whvLYj/ZzwfwoA2lgha4SEySRx7S7FWwScgckfjWbqUNskc0dphlRiZCSSAPc/3vamaa8jzlnAd5W5
        yvYKfy5qxPbhgDNLujT7kSqFVfwHFAHj/wAXrLypdOvApBdXhbjgbSCB/wCPE1wVfQWt6Fb+JrC70y
        ZtpwJIZAc7JBuwcd+CeK8H1bT7rS9Sn0+9jMdxA211/kR7EYIPoaAKtFFFABRRRQAV6r8Cr5XttQ0k
        lRIri4TnlgQFbj0GF/OvKquaPqmoaReC8026e2nCldy45B6gg8EUAfSvkIE2H/VN2zyp9jVeW0aBSR
        uceuQOOa838NfFaeORU1q3VweDJGMD8uo/WvT9A1/QNYiWXT7qMzFsCNnGB04B9fb9KAKcW2PKh2T6
        jpUcw1EsEQRbTwJA2f065rqLvT7WZDIqBZGONw5wfcVWFo0akHLc8bcDj+lAFLSbdLaJo2YszsTubq
        xHB/SvIvjykCeJLIRhfNNrlyAMkbjjP5GvZ7owW1m8k7pBDEpZmdsBAOck+3NfPPxO1SPV/Gd7cQTL
        LbxkRQspyCqjt7ZzQBzNFFFABRRRQAUUUUAFTWd1cWc4mtZnhkHdTjPsfUe1Q0UAdvYfFDxXZ2gtkn
        tpAAPmli3Nx+NJN8UvGUgwt/BH/u2yf1BriaKANvXvFniHXYFg1TU5JoVOfLVVjUnjqFADdOM5x2rE
        oooAKKKKAP/Z
    """

    def __init__(self, port, baud_rate):
        """
        Initializes the TJC3224_LCD object.

        Args:
            port (str): The port to which the LCD is connected.
            baud_rate (int): Baud rate for serial communication.
        """
        self.serial = serial.Serial(port, baud_rate, timeout=1)

        print("Sending handshake... ")
        while not self.handshake():
            pass
        print("Handshake response: OK.")

    def byte(self, bool_val):
        """
        Appends a single-byte value to the data frame.

        :param bval: The byte value to be appended.
        :type bval: int
        """
        self.data_frame += int(bool_val).to_bytes(1, byteorder="big")

    def word(self, word_val):
        """
        Appends a two-byte value to the data frame.

        :param wval: The two-byte value to be appended.
        :type wval: int
        """
        self.data_frame += int(word_val).to_bytes(2, byteorder="big")

    def long(self, long_val):
        """
        Appends a four-byte value to the data frame.

        :param lval: The four-byte value to be appended.
        :type lval: int
        """
        self.data_frame += int(long_val).to_bytes(4, byteorder="big")

    def double_64(self, double_val):
        """
        Appends an eight-byte value to the data frame.

        :param dval: The eight-byte value to be appended.
        :type value: int
        """
        self.data_frame += int(double_val).to_bytes(8, byteorder="big")

    def string(self, string):
        """
        Appends a UTF-8 encoded string to the data frame.

        :param string: The string to be appended.
        :type string: str
        """
        self.data_frame += string.encode("utf-8")

    def send(self):
        """
        Sends the prepared data frame to the display according to the T5L_TA serial protocol.

        Sends the current contents of the data frame, followed by a predefined
        tail sequence. After sending, the data frame is reset to the head sequence.
        """
        # Write the current data frame and tail sequence to the serial connection
        self.serial.write(self.data_frame)
        self.serial.write(self.data_frame_tail)

        # Reset the data frame to the head sequence for the next transmission
        self.data_frame = self.data_frame_head

        # Delay to allow for proper transmission
        time.sleep(0.001)

    def handshake(self):
        """
        Perform a handshake with the display.

        :return: True if handshake is successful, otherwise False.
        :rtype: bool
        """
        # Send the initiation byte (0x00)
        #self.byte(self.cmd_handshake)
        self.data_frame = [0xAA, 0x00]
        self.data_frame_tail = [0xCC, 0x33, 0xC3, 0x3C]
        print(f"Sending: {bytes(self.data_frame) + bytes(self.data_frame_tail)}")

        self.send()
        time.sleep(0.1)

        # Initialize a buffer to store received bytes
        rx_buffer = [None] * 26
        bytes_received = 0

        # Receive data while there is data available and not exceeding buffer size
        while self.serial.in_waiting and bytes_received < 26:
            # Unpack the received byte and store it in the buffer
            rx_buffer[bytes_received] = struct.unpack("B", self.serial.read())[0]

            # Ignore invalid data and reset if the first byte is not 0xAA
            if rx_buffer[0] != 0xAA:
                if bytes_received > 0:
                    bytes_received = 0
                    rx_buffer = [None] * 26
                continue

            time.sleep(0.010)
            bytes_received += 1
        print(f"Received: {rx_buffer[:bytes_received]}")
        # Verify the received data for a successful handshake
        return (
            bytes_received >= 3
            and rx_buffer[0] == 0xAA
            and rx_buffer[1] == 0
            and chr(rx_buffer[2]) == "O"
            and chr(rx_buffer[3]) == "K"
        )

    def set_backlight_brightness(self, brightness):
        """
        Set the backlight luminance.

        :param luminance: Luminance level (0x00-0x40).
        :type luminance: int
        """
        self.byte(self.cmd_backlight_brightness)
        self.byte(min(brightness, 0x40))
        self.send()

    def set_palette(self, background_color=color_black, foreground_color=color_white):
        """
        Set the palette colors for drawing functions.

        :param bg_color: Background color.
        :type bg_color: int
        :param front_color: Foreground (text) color.
        :type front_color: int
        """
        self.byte(self.cmd_set_palette)
        self.word(foreground_color)
        self.word(background_color)
        self.send()

    def clear_screen(self):
        """
        Clear the screen with a specified color.

        :param color: Background color.
        :type color: int
        """
        color=self.color_black
        self.set_palette(color)
        self.byte(self.cmd_clear_screen)
        self.send()

    def draw_point(self, color, x, y):
        """
        Draw a point on the screen.

        :param Color: Color of the point.
        :type Color: int
        :param x: X-coordinate of the point.
        :type x: int
        :param y: Y-coordinate of the point.
        :type y: int
        """
        self.set_palette(self.color_white, color)
        self.byte(self.cmd_draw_line)
        self.word(int(x))
        self.word(int(y))
        self.send()

    def draw_line(self, color, x_start, y_start, x_end, y_end):
        """
        Draw a line segment on the screen.

        :param color: Line segment color.
        :type color: int
        :param x_start: X-coordinate of the starting point.
        :type x_start: int
        :param y_start: Y-coordinate of the starting point.
        :type y_start: int
        :param x_end: X-coordinate of the ending point.
        :type x_end: int
        :param y_end: Y-coordinate of the ending point.
        :type y_end: int
        """
        self.set_palette(self.color_white, color)
        self.byte(self.cmd_draw_line)
        self.word(x_start)
        self.word(y_start)
        self.word(x_end)
        self.word(y_end)
        self.send()

    def draw_rectangle(self, mode, color, x_start, y_start, x_end, y_end):
        """
        Draw a rectangle on the screen.

        :param mode: 0=frame, 1=fill, 2=XOR fill.
        :type mode: int
        :param color: Rectangle color.
        :type color: int
        :param x_start: X-coordinate of the upper-left point.
        :type x_start: int
        :param y_start: Y-coordinate of the upper-left point.
        :type y_start: int
        :param x_end: X-coordinate of the lower-right point.
        :type x_end: int
        :param y_end: Y-coordinate of the lower-right point.
        :type y_end: int
        """
        self.set_palette(self.color_white, color)
        mode_to_command = {
            0: self.cmd_draw_rectangle,
            1: self.cmd_fill_rectangle,
            2: self.cmd_reverse_color_area,
        }
        command = mode_to_command.get(mode, 0)
        self.byte(command)
        self.word(x_start)
        self.word(y_start)
        self.word(x_end)
        self.word(y_end)
        self.send()

    def draw_circle(self, color, x_center, y_center, r):
        """
        Draw a circle on the screen using the draw points method.

        :param Color: Circle color.
        :type Color: int
        :param x_center: X-coordinate of the center of the circle.
        :type x_center: int
        :param y_center: Y-coordinate of the center of the circle.
        :type y_center: int
        :param r: Circle radius.
        :type r: int
        """
        b = 0
        a = 0
        while a <= b:
            b = math.sqrt(r * r - a * a)
            while a == 0:
                b = b - 1
                break
            self.draw_point(
                color, 1, 1, x_center + a, y_center + b
            )  # Draw some sector 1
            self.draw_point(
                color, 1, 1, x_center + b, y_center + a
            )  # Draw some sector 2
            self.draw_point(
                color, 1, 1, x_center + b, y_center - a
            )  # Draw some sector 3
            self.draw_point(
                color, 1, 1, x_center + a, y_center - b
            )  # Draw some sector 4

            self.draw_point(
                color, 1, 1, x_center - a, y_center - b
            )  # Draw some sector 5
            self.draw_point(
                color, 1, 1, x_center - b, y_center - a
            )  # Draw some sector 6
            self.draw_point(
                color, 1, 1, x_center - b, y_center + a
            )  # Draw some sector 7
            self.draw_point(
                color, 1, 1, x_center - a, y_center + b
            )  # Draw some sector 8
            a += 1

    def fill_circle(self, font_color, x_center, y_center, r):
        """
        Fill a circle with a color.

        :param font_color: Fill color.
        :type font_color: int
        :param x_center: X-coordinate of the center of the circle.
        :type x_center: int
        :param y_center: Y-coordinate of the center of the circle.
        :type y_center: int
        :param r: Circle radius.
        :type r: int
        """
        b = 0
        for i in range(r, 0, -1):
            a = 0
            while a <= b:
                b = math.sqrt(i * i - a * a)
                while a == 0:
                    b = b - 1
                    break
                self.draw_point(
                    font_color, 2, 2, x_center + a, y_center + b
                )  # Draw some sector 1
                self.draw_point(
                    font_color, 2, 2, x_center + b, y_center + a
                )  # raw some sector 2
                self.draw_point(
                    font_color, 2, 2, x_center + b, y_center - a
                )  # Draw some sector 3
                self.draw_point(
                    font_color, 2, 2, x_center + a, y_center - b
                )  # Draw some sector 4

                self.draw_point(
                    font_color, 2, 2, x_center - a, y_center - b
                )  # Draw some sector 5
                self.draw_point(
                    font_color, 2, 2, x_center - b, y_center - a
                )  # Draw some sector 6
                self.draw_point(
                    font_color, 2, 2, x_center - b, y_center + a
                )  # Draw some sector 7
                self.draw_point(
                    font_color, 2, 2, x_center - a, y_center + b
                )  # Draw some sector 8
                a = a + 2

    def draw_string(
        self, show_background, size, font_color, background_color, x, y, string
    ):
        """
        Draw a string on the screen.

        :param show_background: True to display the background color, False to not display the background color.
        :type show_background: bool
        :param size: Font size.
        :type size: int
        :param font_color: Character color.
        :type font_color: int
        :param background_color: Background color.
        :type background_color: int
        :param x: X-coordinate of the upper-left point.
        :type x: int
        :param y: Y-coordinate of the upper-left point.
        :type y: int
        :param string: The string to be drawn.
        :type string: str
        """
        self.byte(self.cmd_draw_text)
        self.word(x)
        self.word(y)
        self.byte(0x00)  # font
        self.byte(0x02 | (show_background * 0x40))  # mode (bshow)
        self.byte(size)  # size
        self.word(font_color)
        self.word(background_color)
        self.string(string)
        self.send()

    def draw_int_value(
        self,
        show_background,
        zeroFill,
        zeroMode,
        font_size,
        color,
        background_color,
        iNum,
        x,
        y,
        value,
    ):
        """
        Draw a positive integer value on the screen.

        :param show_background: True to display the background color, False to not display the background color.
        :type show_background: bool
        :param zeroFill: True to zero fill, False for no zero fill.
        :type zeroFill: bool
        :param zeroMode: 1 for leading 0 displayed as 0, 0 for leading 0 displayed as a space.
        :type zeroMode: int
        :param font_size: Font size.
        :type font_size: int
        :param color: Character color.
        :type color: int
        :param background_color: Background color.
        :type background_color: int
        :param iNum: Number of digits.
        :type iNum: int
        :param x: X-coordinate of the upper-left point.
        :type x: int
        :param y: Y-coordinate of the upper-left point.
        :type y: int
        :param value: Integer value.
        :type value: int
        """
        self.byte(0x14)
        # Bit 7: bshow
        # Bit 6: 1 = signed; 0 = unsigned number;
        # Bit 5: zeroFill
        # Bit 4: zeroMode
        # Bit 3-0: size
        self.byte(
            (show_background * 0x80)
            | (0 * 0x40)
            | (zeroFill * 0x20)
            | (zeroMode * 0x10)
            | font_size
        )
        self.word(color)
        self.word(background_color)
        self.byte(iNum)
        self.byte(0)  # fNum
        self.word(x)
        self.word(y)
        self.double_64(value)
        self.send()

    def draw_float_value(
        self,
        show_background,
        zeroFill,
        zeroMode,
        size,
        color,
        background_color,
        iNum,
        fNum,
        x,
        y,
        value,
    ):
        """
        Draw a floating point number on the screen.

        :param show_background: True to display the background color, False to not display the background color.
        :type show_background: bool
        :param zeroFill: True to zero fill, False for no zero fill.
        :type zeroFill: bool
        :param zeroMode: 1 for leading 0 displayed as 0, 0 for leading 0 displayed as a space.
        :type zeroMode: int
        :param size: Font size.
        :type size: int
        :param color: Character color.
        :type color: int
        :param background_color: Background color.
        :type background_color: int
        :param iNum: Number of whole digits.
        :type iNum: int
        :param fNum: Number of decimal digits.
        :type fNum: int
        :param x: X-coordinate of the upper-left point.
        :type x: int
        :param y: Y-coordinate of the upper-left point.
        :type y: int
        :param value: Float value.
        :type value: float
        """
        self.byte(self.cmd_draw_value)
        # Bit 7: bshow
        # Bit 6: 1 = signed; 0 = unsigned number;
        # Bit 5: zeroFill
        # Bit 4: zeroMode
        # Bit 3-0: size
        self.byte(
            (show_background * 0x80)
            | (0 * 0x40)
            | (zeroFill * 0x20)
            | (zeroMode * 0x10)
            | size
        )
        self.word(color)
        self.word(background_color)
        self.byte(iNum)
        self.byte(fNum)
        self.word(x)
        self.word(y)
        self.long(value)
        self.send()

    def draw_signed_float(
        self, show_background, size, color, background_color, iNum, fNum, x, y, value
    ):
        """
        Draw a signed floating-point number on the screen.

        :param size: Font size.
        :type size: int
        :param background_color: Background color.
        :type background_color: int
        :param iNum: Number of whole digits.
        :type iNum: int
        :param fNum: Number of decimal digits.
        :type fNum: int
        :param x: X-coordinate of the upper-left corner.
        :type x: int
        :param y: Y-coordinate of the upper-left corner.
        :type y: int
        :param value: Floating-point value to be displayed.
        :type value: float
        """
        if value < 0:
            self.draw_string(
                show_background, size, color, background_color, x - 6, y - 3, "-"
            )
            self.draw_float_value(
                show_background,
                False,
                0,
                size,
                color,
                background_color,
                iNum,
                fNum,
                x,
                y,
                -value,
            )
        else:
            self.draw_string(
                show_background, size, color, background_color, x - 6, y - 3, " "
            )
            self.draw_float_value(
                show_background,
                False,
                0,
                size,
                color,
                background_color,
                iNum,
                fNum,
                x,
                y,
                value,
            )

    def draw_icon(self, picID):
        """
        Draw an icon on the screen.

        :param show_background: True to display the background color, False to not display the background color.
        :type show_background: bool
        :param libID: Icon library ID.
        :type libID: int
        :param picID: Icon ID.
        :type picID: int
        :param x: X-coordinate of the upper-left corner.
        :type x: int
        :param y: Y-coordinate of the upper-left corner.
        :type y: int
        """
        lcd.clear_screen()
        x=40
        y=70
        if x > self.screen_width - 1:
            x = self.screen_width - 1
        if y > self.screen_height - 1:
            y = self.screen_height - 1
        self.byte(self.cmd_draw_icon)
        self.word(x)
        self.word(y)
        self.byte(0)
        self.byte(False * 0x01)
        self.word(picID)
        self.send()

    def draw_image(self, id=1):
        """
        Draw a JPG image on the screen and cache it in the virtual display area.

        :param id: Picture ID.
        :type id: int
        """
        self.byte(self.cmd_show_image)
        self.byte(id)
        self.send()

    def move_screen_area(
        self, direction, offset, background_color, x_start, y_start, x_end, y_end
    ):
        """
        Copy an area from the virtual display area to the current screen.

        :param direction: Direction ( 0 = ,1 =, 0x02= top, 0x03 = down)
        :type direction: int
        :param offset: How many pixels the copied area is going to be moved.
        :type offset: int
        :param offset: Color of background (to fill the previously moved area?).
        :type offset: int
        :param x_start: X-coordinate of the upper-left corner of the virtual area.
        :type x_start: int
        :param y_start: Y-coordinate of the upper-left corner of the virtual area.
        :type y_start: int
        :param x_end: X-coordinate of the lower-right corner of the virtual area.
        :type x_end: int
        :param y_end: Y-coordinate of the lower-right corner of the virtual area.
        :type y_end: int
        """
        self.byte(self.cmd_move_screen_area)
        self.byte(0x80 | direction)
        self.word(offset)
        self.word(background_color)
        self.word(x_start)
        self.word(y_start)
        self.word(x_end)
        self.word(y_end)
        self.send()




    def write_temp_buffer(self, ):
        """
        Write data to the temporary buffer (RAM).

        :param address: The starting address (Word address) of the temporary buffer (RAM).
        :type address: int
        :param data: The data to be written to the temporary buffer.
        :type data: list of int
        """

        data = base64.b64decode(self.img)
        self.byte(0xC0)  # Command for writing to temporary buffer
        self.word(0x02)  # Starting address
        for word in data:
            self.word(word)  # Data to be written
        self.send()


    def map_to_nearest_color(self, pixel):
        """
        Map grayscale pixel to the nearest LCD color.

        :param pixel: Grayscale pixel value (0-255).
        :type pixel: int
        :return: Nearest LCD color.
        :rtype: int
        """
        if pixel < 50:
            return self.LCD_COLORS["black"]
        elif pixel < 100:
            return self.LCD_COLORS["blue"]
        elif pixel < 150:
            return self.LCD_COLORS["red"]
        elif pixel < 200:
            return self.LCD_COLORS["yellow"]
        return self.LCD_COLORS["white"]


    def renderJPG2(self):
        lcd.clear_screen()

        # Decode the base64 image
        img_data = base64.b64decode(self.img)
        img = Image.open(io.BytesIO(img_data))

        # Ensure the image is 96x96
        #img = img.resize((96, 96))

        # Convert image to grayscale
        img = img.convert("L")

        # Get pixel data
        pixels = img.load()

        # Create an array of the pixel map
        pixel_map = []
        for y in range(96):
            for x in range(96):
                grayscale_value = pixels[x, y]
                color = self.map_to_nearest_color(grayscale_value)
                pixel_map.append(color)

        # Convert the pixel map to bytes
        img_data = bytearray()
        for color in pixel_map:
            img_data.extend(color.to_bytes(2, byteorder='big'))

        # Write the image data to the temporary buffer (SRAM)
        self.write_image_to_sram(img_data, 0x0000)

        # Display the image from the temporary buffer
        self.show_icon_sram()



    def write_image_to_sram(self, img_data, address):
        """
        Write image data to the temporary buffer (SRAM).

        :param img_data: The image data to be written to the temporary buffer.
        :type img_data: bytes
        :param address: The starting address (Word address) of the temporary buffer (RAM).
        :type address: int
        """
        self.byte(0xC0)  # Command for writing to temporary buffer
        self.word(address)  # Starting address
        for byte in img_data:
            self.byte(byte)  # Data to be written
        self.send()

    def renderJPG(self):
        lcd.clear_screen()

        # Decode the base64 image
        img_data = base64.b64decode(self.img)
        img = Image.open(io.BytesIO(img_data))

        # Ensure the image is 96x96
        img = img.resize((96, 96))

        # Convert image to grayscale
        img = img.convert("L")

        # Get pixel data
        pixels = img.load()

        # Render the image pixel by pixel
        for y in range(96):
            if 70 + y >= self.screen_height:
                break
            for x in range(96):
                if 50 + x >= self.screen_width:
                    break
                grayscale_value = pixels[x, y]
                color = self.map_to_nearest_color(grayscale_value)
                self.draw_point(color, 50 + x, 70 + y)
                time.sleep(0.00043)  # Adjust the delay as needed



    def wrSRAM(self, ):
        """
        Write data to the temporary buffer (RAM).

        :param address: The starting address (Word address) of the temporary buffer (RAM).
        :type address: int
        :param data: The data to be written to the temporary buffer.
        :type data: list of int
        """

        data = base64.b64decode(self.img)
        self.byte(0x31)  # Command for writing SRAM
        self.byte(0x5A)  # RAM selected
        self.word(0x02)  # Starting address
        for word in data:
            self.word(word)  # Data to be written
        self.send()

        # Read the response from the display
        response = self.serial.read(10)  # 2 bytes per word + header and tail
        print(f"Raw response: {response}")
        """ if response[:2] == b'\xAA\xC2' and response[-4:] == b'\xCC\x33\xC3\x3C':
            data = []
            for i in range(2, 2 + 2 * len(data), 2):
                data.append(int.from_bytes(response[i:i+2], byteorder='big'))
            return data
        else:
            rai se ValueError("Invalid response received from the display")
        """


    def owrIcon(self, ):

        self.byte(0x33)  # Command for writing SRAM
        self.byte(0x5A)  # RAM selected
        self.word(0x02)  # Starting address
        self.byte(0x8F)  # PIC ID

        self.send()




    def read_temp_buffer(self, address, length):
        """
        Read data from the temporary buffer (RAM).

        :param address: The starting address (Word address) of the temporary buffer (RAM).
        :type address: int
        :param length: The length of the data to be read (Word).
        :type length: int
        :return: The data read from the temporary buffer.
        :rtype: list of int
        """
        self.byte(0xC2)  # Command for reading from temporary buffer
        self.word(address)  # Starting address
        self.word(length)  # Length of data to read
        self.send()

        # Read the response from the display
        response = self.serial.read(2 * length + 6)  # 2 bytes per word + header and tail
        print(f"Raw response: {response}")
        if response[:2] == b'\xAA\xC2' and response[-4:] == b'\xCC\x33\xC3\x3C':
            data = []
            for i in range(2, 2 + 2 * length, 2):
                data.append(int.from_bytes(response[i:i+2], byteorder='big'))
            return data
        else:
            raise ValueError("Invalid response received from the display")


    def show_icon_sram(self,):
        lcd.clear_screen()
        """
        Show an icon from SRAM at the specified coordinates.

        :param x: X-coordinate of the upper-left corner.
        :type x: int
        :param y: Y-coordinate of the upper-left corner.
        :type y: int
        :param addr: The address in SRAM where the icon data is stored.
        :type addr: int
        """
        self.byte(0xC1)  # Command for showing icon from SRAM
        self.byte(0x12)  # Sub-command
        self.word(40)  # X-coordinate
        self.word(70)  # Y-coordinate
        self.byte(0)  # Reserved byte
        self.word(0x0000)  # Address in SRAM
        self.send()



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Control de pantalla TJC3224")
    parser.add_argument("command", choices=["renderJPG2","renderJPG","owrIcon","wrSRAM","init", "clear", "draw_rect","icon", "wr_ram","rd_ram", "showIcon"], help="cmd to execute")
    parser.add_argument("--port", type=str, required=True, help="serial port (ex: COM3 or /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baudrate (default: 115200)")
    parser.add_argument("--color", type=int, help="colorr")
    parser.add_argument("--x_start", type=int, help="Xcord")
    parser.add_argument("--y_start", type=int, help="Ycord")
    parser.add_argument("--x_end", type=int, help="Xcord")
    parser.add_argument("--y_end", type=int, help="YCord")
    parser.add_argument("--picID", type=int, help="IconID")
    parser.add_argument("--address", type=int, help="Starting address for temporary buffer")
    parser.add_argument("--data", type=int, nargs='+', help="Data to write to temporary buffer")
    parser.add_argument("--length", type=int, help="Length of data to read from temporary buffer")

    args = parser.parse_args()

    lcd = TJC3224_LCD(args.port, args.baud)

    if args.command == "init":
        print("Sending Handshake")
        if lcd.handshake():
            print("Handshake successful.")
        else:
            print("Error in handshake.")
    elif args.command == "clear":
        #if args.color is not None:
            lcd.clear_screen()
        #else:
            #print("missing")
    elif args.command == "icon":
        if args.picID is not None:
            lcd.draw_icon(args.picID)
        else:
            print("missing iconid.")
    elif args.command == "wr_ram":
        #if None not in (args.address, args.data):
            lcd.write_temp_buffer()
        #else:
            #print("missing args")
    elif args.command == "owrIcon":
        lcd.owrIcon()
    elif args.command == "wrSRAM":
        lcd.wrSRAM()
    elif args.command == "showIcon":
        lcd.show_icon_sram()
    elif args.command == "renderJPG":
        lcd.renderJPG()
    elif args.command == "renderJPG2":
        lcd.renderJPG2()

    elif args.command == "rd_ram":
        if None not in (args.address, args.length):
            data = lcd.read_temp_buffer(args.address, args.length)
            print(f"Data read from temporary buffer: {data}")
        else:
            print("missing args")
    elif args.command == "draw_rect":
        if None not in (args.color, args.x_start, args.y_start, args.x_end, args.y_end):
            lcd.draw_rectangle(1, args.color, args.x_start, args.y_start, args.x_end, args.y_end)
        else:
            print("missing args")
