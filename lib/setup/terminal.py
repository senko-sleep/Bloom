import os
import io
import requests
import numpy as np
from PIL import Image
import cv2


class AvatarToTextArt:
    def __init__(s, url, w=80, h=40):
        s.u = url
        s.w = w
        s.h = h
        s.i = s.g = s.r = s.a = s.ca = None
        s.c = '@%#*+=-:. '

    def f(s):
        s.i = np.array(Image.open(io.BytesIO(requests.get(s.u).content)).convert('RGB'))

    def g_(s):
        if s.i is not None: s.g = cv2.cvtColor(s.i, cv2.COLOR_RGB2GRAY)

    def r_(s):
        if s.g is not None:
            s.g = cv2.resize(s.g, (s.w, s.h))
            s.r = cv2.resize(s.i, (s.w, s.h))

    def m(s):
        if s.g is not None:
            n = len(s.c)
            s.a = ''.join([s.c[(n - 1) - (min(int(p), 255) * (n - 1) // 255)] for p in s.g.flatten()])

    def ansi(s, r, g, b):
        return f'\033[38;2;{r};{g};{b}m'

    def c_(s):
        if s.r is not None and s.a is not None:
            t = ""
            try: tw = os.get_terminal_size().columns
            except: tw = 120
            pad = " " * ((tw - s.w) // 2)
            for i, ch in enumerate(s.a):
                y, x = divmod(i, s.w)
                if x == 0 and i > 0: t += "\n" + pad
                elif i == 0: t += pad
                r, g, b = np.clip(s.r[y, x], 0, 255).astype(int)
                t += f"{s.ansi(r, g, b)}{ch}\033[0m"
            s.ca = t + "\n"

    def create_art(s):
        s.f()
        s.g_()
        s.r_()
        s.m()
        s.c_()

    def get_colored_ascii_art(s):
        return s.ca

    def p(s):
        print(s.ca if s.ca else "Run run() first.") 
   