import os
from PIL import Image, ImageDraw, ImageFont

os.makedirs("webapp/public", exist_ok=True)

def create_app_icon(size: int) -> Image.Image:
    # 512x512 base canvas with high-res rendering
    base_size = 512
    img = Image.new("RGBA", (base_size, base_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background: dark slate rounded rectangle / filled background
    bg_color = (20, 22, 26, 255) # #14161a
    draw.rectangle([(0, 0), (base_size, base_size)], fill=bg_color)

    # Accent gradient glow / circles
    glow_color = (46, 125, 50, 60) # soft emerald glow
    draw.ellipse([(60, 60), (452, 452)], fill=glow_color)

    # Ring representing health & calories progress
    ring_bg = (38, 42, 50, 255)
    draw.ellipse([(96, 96), (416, 416)], outline=ring_bg, width=28)
    
    # Progress arc (emerald green to teal)
    draw.arc([(96, 96), (416, 416)], start=135, end=390, fill=(34, 197, 94, 255), width=28)

    # Center icon: Stylized nutrition leaf + sparkles/dots
    # Draw leaf / flame shape in center
    center_x, center_y = 256, 256
    
    # Stylized Apple / Flame shape
    leaf_color = (34, 197, 94, 255)
    draw.ellipse([(190, 190), (322, 322)], fill=(24, 30, 38, 255))
    
    # Diamond / Pulse spark
    points = [
        (256, 170), # top
        (296, 256), # right
        (256, 330), # bottom
        (216, 256)  # left
    ]
    draw.polygon(points, fill=leaf_color)

    # Inner highlight
    draw.ellipse([(240, 240), (272, 272)], fill=(255, 255, 255, 240))

    # Resize to requested size with high quality Lanczos filter
    if size != base_size:
        return img.resize((size, size), Image.Resampling.LANCZOS)
    return img

# Generate icons
icon_512 = create_app_icon(512)
icon_512.save("webapp/public/icon-512.png", "PNG")

icon_192 = create_app_icon(192)
icon_192.save("webapp/public/icon-192.png", "PNG")

icon_180 = create_app_icon(180)
icon_180.save("webapp/public/apple-touch-icon.png", "PNG")

print("Generated PWA icons successfully in webapp/public/")
