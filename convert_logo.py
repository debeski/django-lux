from PIL import Image
import os

source = '/home/debeski/.gemini/antigravity/brain/db3cef5c-1d08-4b7e-8a85-e877395c1a4f/login_logo_gen_1769430792878.png'
dest = '/home/debeski/xPy/micro-users-pkg/users/static/img/login_logo.webp'

try:
    img = Image.open(source)
    img.save(dest, format='WEBP', quality=90)
    print(f"Successfully converted and saved to {dest}")
except Exception as e:
    print(f"Error: {e}")
