import cv2
import numpy as np
import asyncio

async def scroll_into_view(playwright_element):
    await playwright_element.scroll_into_view_if_needed(timeout=10000)

async def create_boundingbox(image_bytes, bounding_box):
    if not bounding_box:
        print("NO BOUNDING BOX")
        return image_bytes
    # else:
    #     print(f"BOUNDING BOX: {bounding_box}")
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    x, y, width, height = bounding_box['x'], bounding_box['y'], bounding_box['width'], bounding_box['height']
    top_left = (int(x), int(y))
    bottom_right = (int(x + width), int(y + height))
    color = (0, 255, 0)
    thickness = 2

    cv2.rectangle(img, top_left, bottom_right, color, thickness)

    # cv2.imwrite('testtest.png', img)

    _, buffer = cv2.imencode('.png', img)
    return buffer.tobytes()


