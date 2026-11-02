import json
from pathlib import Path
import urllib.request

PROJECT_DIR = Path(__file__).resolve().parent.parent
IMAGES_FILE = PROJECT_DIR / "images.json"


def img_table():
  if not IMAGES_FILE.exists():
    return []
  with open(IMAGES_FILE, "r") as f:
    return json.load(f)


def img_register(name, path, description=""):
  images = img_table()
  if any(image["name"] == name for image in images):
    raise ValueError("Image already exists.")
  image_path = Path(path).expanduser().resolve()
  if not image_path.is_file():
    raise ValueError("Image file not found.")
  image = {"name": name, "path": str(image_path), "description": description}
  images.append(image)
  with open(IMAGES_FILE, "w") as f:
    json.dump(images, f, indent=4)
  return image


def img_get(name):
  for image in img_table():
    if image["name"] == name:
      if not Path(image["path"]).is_file():
        raise ValueError("Image file not found.")
      return image
  raise ValueError("Image not found.")

def ensure_base_image():
  if not IMAGES_FILE.exists() or IMAGES_FILE.stat().st_size == 0:
    with open(IMAGES_FILE, "w") as f:
      json.dump([], f)

  try:
    img_get("ubuntu24")
    return
  except ValueError:
    pass

  image_dir = Path("/var/lib/libvirt/images")
  image_path = image_dir / "ubuntu24.qcow2"
  image_url = "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"

  if not image_path.exists():
    image_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(image_path) + ".tmp")
    urllib.request.urlretrieve(image_url, tmp)
    tmp.rename(image_path)
  img_register("ubuntu24", str(image_path), "Ubuntu 24.04 Cloud Image")
