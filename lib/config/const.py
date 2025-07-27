
from PIL import Image
from lib.imports.discord import *
 
def primary_color(image_path="data/bot\images/bot.png"):
    image = Image.open(image_path)
    image = image.convert("RGB")
    resized_image = image.resize((1, 1))
    dominant_color = resized_image.getpixel((0, 0))
    return discord.Color.from_rgb(
        dominant_color[0], dominant_color[1], dominant_color[2]
    )

